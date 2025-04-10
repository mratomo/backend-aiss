import json
import logging
import hashlib
import asyncio
from typing import Any, Dict, List, Optional, Union, Protocol

# Soporte para múltiples clientes HTTP
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

import aiohttp
from motor.motor_asyncio import AsyncIOMotorClient

from config.settings import Settings
from models.models import DatabaseSchema, TableSchema, ColumnSchema
from services.vectordb_factory import VectorDBFactory
from services.vectordb_base import VectorDBBase

logger = logging.getLogger(__name__)

# Protocolo para abstraer clientes HTTP
class HTTPClient(Protocol):
    async def post(self, url: str, **kwargs): ...

class SchemaVectorizationService:
    """Servicio para vectorización de esquemas para búsquedas semánticas"""

    def __init__(self, http_client: Any, settings: Settings):
        """
        Inicializar servicio de vectorización
        
        Args:
            http_client: Cliente HTTP para comunicación con otros servicios (httpx.AsyncClient o aiohttp.ClientSession)
            settings: Configuración global
        """
        self.http_client = http_client
        self.settings = settings
        self.use_httpx = HTTPX_AVAILABLE and isinstance(http_client, httpx.AsyncClient)
        
        # Inicializar cliente vectorial si está especificado en configuración
        self.vector_db: Optional[VectorDBBase] = None
        try:
            if self.settings.vector_db:
                self.vector_db = VectorDBFactory.create(settings)
                logger.info(f"Inicializado cliente vectorial {self.settings.vector_db}")
        except Exception as e:
            logger.error(f"Error inicializando cliente vectorial: {str(e)}")
            self.vector_db = None

    async def vectorize_schema(self, schema: DatabaseSchema, session: Optional[Any] = None) -> str:
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
            
            # Preparar metadata común
            metadata = {
                "connection_id": schema.connection_id,
                "db_type": schema.type,
                "name": schema.name,
                "schema_hash": schema_hash,
                "tables_count": len(schema.tables) if schema.tables else 0
            }
            
            # Si tenemos acceso directo a la base de datos vectorial, la usamos
            # De lo contrario, usamos el servicio de embeddings
            if self.vector_db:
                try:
                    # Asegurar que existe la colección
                    await self.vector_db.ensure_collections_exist(["database_schemas"])
                    
                    # Generar el vector y almacenarlo directamente
                    embedding_response = await self._generate_embedding(schema_text, session)
                    if embedding_response and "vector" in embedding_response:
                        vector = embedding_response["vector"]
                        
                        # Almacenar vector en la base de datos vectorial
                        await self.vector_db.store_vector(
                            vector=vector,
                            collection="database_schemas",
                            entity_id=schema.connection_id,
                            text=schema_text,
                            metadata=metadata
                        )
                        
                        logger.info(f"Vector almacenado directamente en {self.settings.vector_db} para schema {schema.connection_id}")
                        return vector_id
                    else:
                        logger.error("No se pudo generar el embedding para el esquema")
                        raise ValueError("No se pudo generar el embedding para el esquema")
                        
                except Exception as e:
                    logger.error(f"Error utilizando cliente vectorial directo: {str(e)}")
                    logger.info("Intentando con el servicio de embeddings...")
                    # Continuamos con el servicio de embeddings
            
            # Método tradicional: usar el servicio de embeddings
            # Preparar payload para el servicio de embeddings
            payload = {
                "text": schema_text,
                "metadata": metadata,
                "vector_id": vector_id,
                "collection_name": "database_schemas"
            }
            
            # Llamar al servicio de embeddings usando la sesión proporcionada o la propia del servicio
            url = f"{self.settings.embedding_service_url}/embedding"
            
            # Determinar qué cliente HTTP usar
            use_provided_session = session is not None
            http_client = session if use_provided_session else self.http_client
            
            # Verificar tipo de cliente HTTP (httpx o aiohttp)
            client_is_httpx = False
            if HTTPX_AVAILABLE:
                if isinstance(http_client, httpx.AsyncClient):
                    client_is_httpx = True
                elif use_provided_session and hasattr(http_client, "request"):
                    # Detectar si es un cliente compatible con httpx por duck typing
                    client_is_httpx = True
            
            # Realizar la solicitud HTTP según el tipo de cliente
            try:
                if client_is_httpx:
                    # Usar cliente httpx
                    response = await http_client.post(url, json=payload, timeout=60.0)
                    if response.status_code != 200:
                        error_text = response.text
                        logger.error(f"Error vectorizing schema: {error_text}")
                        raise ValueError(f"Error vectorizing schema: {error_text}")
                    
                    return vector_id
                else:
                    # Usar cliente aiohttp
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
            
    async def _generate_embedding(self, text: str, session: Optional[Any] = None) -> Dict[str, Any]:
        """
        Generar embedding para un texto usando el servicio de embeddings
        
        Args:
            text: Texto para generar embedding
            session: Sesión HTTP opcional
            
        Returns:
            Diccionario con el vector generado
        """
        url = f"{self.settings.embedding_service_url}/generate_embedding"
        payload = {"text": text}
        
        # Determinar qué cliente HTTP usar
        use_provided_session = session is not None
        http_client = session if use_provided_session else self.http_client
        
        # Verificar tipo de cliente HTTP
        client_is_httpx = False
        if HTTPX_AVAILABLE:
            if isinstance(http_client, httpx.AsyncClient):
                client_is_httpx = True
            elif use_provided_session and hasattr(http_client, "request"):
                client_is_httpx = True
        
        try:
            if client_is_httpx:
                # Usar cliente httpx
                response = await http_client.post(url, json=payload, timeout=30.0)
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"Error generating embedding: {error_text}")
                    return {}
                
                return response.json()
            else:
                # Usar cliente aiohttp
                async with http_client.post(url, json=payload, timeout=30) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Error generating embedding: {error_text}")
                        return {}
                    
                    return await response.json()
                    
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            return {}

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