import json
import logging
import hashlib
import asyncio
from typing import Any, Dict, List, Optional

import aiohttp
from motor.motor_asyncio import AsyncIOMotorClient

from config.settings import Settings
from models.models import DatabaseSchema, TableSchema, ColumnSchema

logger = logging.getLogger(__name__)

class SchemaVectorizationService:
    """Servicio para vectorización de esquemas para búsquedas semánticas"""

    def __init__(self, http_client: aiohttp.ClientSession, settings: Settings):
        """
        Inicializar servicio de vectorización
        
        Args:
            http_client: Cliente HTTP para comunicación con otros servicios
            settings: Configuración global
        """
        self.http_client = http_client
        self.settings = settings

    async def vectorize_schema(self, schema: DatabaseSchema, session: Optional[aiohttp.ClientSession] = None) -> str:
        """
        Vectorizar esquema de base de datos para búsqueda semántica
        
        Args:
            schema: Esquema a vectorizar
            session: Sesión HTTP opcional. Si se proporciona, se usa en lugar de self.http_client
            
        Returns:
            ID del vector generado
        """
        try:
            # Generar texto descriptivo del esquema
            schema_text = self._generate_schema_description(schema)
            
            # Limitar el tamaño del texto para evitar problemas de memoria
            max_schema_text_length = 100000  # Aproximadamente 100KB
            if len(schema_text) > max_schema_text_length:
                logger.warning(f"Esquema demasiado grande ({len(schema_text)} caracteres), truncando a {max_schema_text_length}")
                schema_text = schema_text[:max_schema_text_length] + "\n[... contenido truncado por límites de memoria ...]"
            
            # Calcular hash único del esquema para identificación
            schema_hash = hashlib.md5(schema_text.encode()).hexdigest()
            vector_id = f"schema_{schema.connection_id}_{schema_hash}"
            
            # Preparar payload para el servicio de embeddings
            payload = {
                "text": schema_text,
                "metadata": {
                    "connection_id": schema.connection_id,
                    "db_type": schema.type,
                    "name": schema.name,
                    "schema_hash": schema_hash,
                    "tables_count": len(schema.tables) if schema.tables else 0
                },
                "vector_id": vector_id,
                "collection_name": "database_schemas"
            }
            
            # Llamar al servicio de embeddings usando la sesión proporcionada o la propia del servicio
            url = f"{self.settings.embedding_service_url}/embedding"
            
            # Determinar qué cliente HTTP usar
            use_provided_session = session is not None
            http_client = session if use_provided_session else self.http_client
            
            # Realizar la solicitud HTTP con manejo adecuado de sesión
            try:
                async with http_client.post(url, json=payload, timeout=60) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Error vectorizing schema: {error_text}")
                        raise ValueError(f"Error vectorizing schema: {error_text}")
                    
                    result = await response.json()
                    return vector_id
            except asyncio.TimeoutError:
                logger.error(f"Timeout vectorizing schema for {schema.connection_id}")
                raise ValueError(f"Timeout vectorizing schema: operation took too long")
                
        except Exception as e:
            logger.error(f"Error vectorizing schema for {schema.connection_id}: {e}")
            raise ValueError(f"Failed to vectorize schema: {str(e)}")

    def _generate_schema_description(self, schema: DatabaseSchema) -> str:
        """
        Generar descripción textual del esquema para vectorización
        
        Args:
            schema: Esquema a describir
            
        Returns:
            Descripción textual del esquema
        """
        lines = []
        
        # Información general de la base de datos
        lines.append(f"Database: {schema.name}")
        lines.append(f"Type: {schema.type}")
        
        if schema.description:
            lines.append(f"Description: {schema.description}")
            
        if schema.version:
            lines.append(f"Version: {schema.version}")
        
        # Información de tablas
        if schema.tables:
            collection_term = "Collections" if schema.type == "mongodb" else "Tables"
            lines.append(f"\n{collection_term}:")
            
            for table in schema.tables:
                table_type = "Collection" if getattr(table, "is_collection", False) else "Table"
                lines.append(f"\n{table_type}: {table.name}")
                
                if table.schema:
                    lines.append(f"Schema: {table.schema}")
                
                if table.description:
                    lines.append(f"Description: {table.description}")
                    
                lines.append(f"Rows: {table.rows_count}")
                
                # Columnas/campos
                if table.columns:
                    field_term = "Fields" if getattr(table, "is_collection", False) else "Columns"
                    lines.append(f"{field_term}:")
                    
                    for column in table.columns:
                        col_desc = f"- {column.name} ({column.data_type})"
                        
                        # Añadir flags importantes
                        flags = []
                        if column.is_primary:
                            flags.append("PRIMARY KEY")
                        
                        if column.is_foreign:
                            flags.append("FOREIGN KEY")
                            if column.references:
                                flags.append(f"→ {column.references}")
                                
                        if not column.nullable:
                            flags.append("NOT NULL")
                            
                        if flags:
                            col_desc += f" {' '.join(flags)}"
                            
                        if column.description:
                            col_desc += f" - {column.description}"
                            
                        lines.append(col_desc)
                        
        # Unir todas las líneas con saltos de línea
        return "\n".join(lines)