import logging
from datetime import datetime
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
from models.models import (
    DatabaseSchema, SchemaDiscoveryStatus, TableSchema, ColumnSchema
)

logger = logging.getLogger(__name__)

# Protocolo para abstraer clientes HTTP
class HTTPClient(Protocol):
    async def get(self, url: str, **kwargs): ...
    async def post(self, url: str, **kwargs): ...
    async def put(self, url: str, **kwargs): ...
    async def delete(self, url: str, **kwargs): ...

class SchemaDiscoveryService:
    """Servicio para descubrimiento de esquemas de bases de datos"""

    def __init__(self, http_client: Any, settings: Settings):
        """
        Inicializar servicio de descubrimiento
        
        Args:
            http_client: Cliente HTTP para comunicación con otros servicios (httpx.AsyncClient o aiohttp.ClientSession)
            settings: Configuración global
        """
        self.http_client = http_client
        self.settings = settings
        self.use_httpx = HTTPX_AVAILABLE and isinstance(http_client, httpx.AsyncClient)
        
        # Inicializar cliente MongoDB
        self.mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
        self.db = self.mongo_client[settings.mongodb_db_name]
        self.collection = self.db["database_schemas"]
        
        # Crear índice en connection_id si no existe
        self.collection.create_index("connection_id", unique=True)

    async def get_schema(self, connection_id: str) -> Optional[DatabaseSchema]:
        """
        Obtener esquema de base de datos por ID de conexión
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            DatabaseSchema si existe, None si no
        """
        schema_doc = await self.collection.find_one({"connection_id": connection_id})
        
        if not schema_doc:
            return None
            
        return DatabaseSchema(**schema_doc)

    async def save_schema(self, schema: DatabaseSchema) -> str:
        """
        Guardar o actualizar esquema
        
        Args:
            schema: Esquema a guardar
            
        Returns:
            ID del documento
        """
        # Convertir a dict para MongoDB
        schema_dict = schema.dict()
        
        # Actualizar o insertar
        result = await self.collection.update_one(
            {"connection_id": schema.connection_id},
            {"$set": schema_dict},
            upsert=True
        )
        
        # Devolver ID del documento
        if result.upserted_id:
            return str(result.upserted_id)
        else:
            doc = await self.collection.find_one({"connection_id": schema.connection_id})
            return str(doc["_id"])

    async def discover_schema(
        self, connection_id: str, options: Optional[Dict[str, Any]] = None
    ) -> DatabaseSchema:
        """
        Descubrir esquema de base de datos
        
        Args:
            connection_id: ID de la conexión
            options: Opciones de descubrimiento
            
        Returns:
            Esquema descubierto
        """
        # Establecer límites para control de memoria
        max_tables = 500  # Máximo de tablas a procesar
        max_columns_per_table = 300  # Máximo de columnas por tabla
        max_table_name_length = 100  # Máximo largo de nombre de tabla
        max_column_name_length = 100  # Máximo largo de nombre de columna
        try:
            # Actualizar esquema a en progreso
            schema = await self.get_schema(connection_id)
            if not schema:
                schema = DatabaseSchema(
                    connection_id=connection_id,
                    name="Discovering...",
                    type="unknown",
                    status=SchemaDiscoveryStatus.IN_PROGRESS,
                    discovery_date=datetime.utcnow()
                )
            else:
                schema.status = SchemaDiscoveryStatus.IN_PROGRESS
            
            # Guardar estado inicial
            await self.save_schema(schema)
            
            # Obtener detalles de la conexión del servicio de conexión
            connection_details = await self._get_connection_details(connection_id)
            
            # Verificar el tipo de base de datos
            if not connection_details:
                raise ValueError(f"Connection details not found for {connection_id}")
            
            db_type = connection_details.get("type", "").lower()
            
            # Descubrir esquema según el tipo de base de datos
            if db_type == "postgresql":
                schema = await self._discover_postgres_schema(connection_id, connection_details, options)
            elif db_type == "mysql":
                schema = await self._discover_mysql_schema(connection_id, connection_details, options)
            elif db_type == "mongodb":
                schema = await self._discover_mongodb_schema(connection_id, connection_details, options)
            else:
                raise ValueError(f"Unsupported database type: {db_type}")
            
            # Actualizar fecha de descubrimiento
            schema.discovery_date = datetime.utcnow()
            schema.status = SchemaDiscoveryStatus.COMPLETED
            
            # Guardar esquema completo
            await self.save_schema(schema)
            
            return schema
            
        except Exception as e:
            logger.error(f"Error discovering schema for connection {connection_id}: {e}")
            
            # Actualizar esquema con error
            schema = DatabaseSchema(
                connection_id=connection_id,
                name=f"Error: {connection_id}",
                type="unknown",
                status=SchemaDiscoveryStatus.FAILED,
                discovery_date=datetime.utcnow(),
                error=str(e)
            )
            
            await self.save_schema(schema)
            return schema

    async def _get_connection_details(self, connection_id: str) -> Dict[str, Any]:
        """
        Obtener detalles de conexión del servicio de conexión
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            Detalles de la conexión
        """
        try:
            # Construir URL para el endpoint de conexión
            url = f"{self.settings.db_connection_url}/connections/{connection_id}"
            
            if self.use_httpx:
                # Usar httpx
                response = await self.http_client.get(url)
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"Error getting connection details: {error_text}")
                    return {}
                
                return response.json()
            else:
                # Usar aiohttp
                async with self.http_client.get(url) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Error getting connection details: {error_text}")
                        return {}
                        
                    data = await response.json()
                    return data
                
        except Exception as e:
            logger.error(f"Error communicating with connection service: {e}")
            return {}

    async def _discover_postgres_schema(
        self, connection_id: str, connection_details: Dict[str, Any], options: Optional[Dict[str, Any]]
    ) -> DatabaseSchema:
        """
        Descubrir esquema de PostgreSQL
        
        Args:
            connection_id: ID de la conexión
            connection_details: Detalles de la conexión
            options: Opciones de descubrimiento
            
        Returns:
            Esquema descubierto
        """
        try:
            # Extraer opciones
            schema_names = options.get("schemas", ["public"]) if options else ["public"]
            excluded_tables = options.get("excluded_tables", []) if options else []
            
            # Solicitar descubrimiento al servicio de conexión
            url = f"{self.settings.db_connection_service_url}/connections/{connection_id}/discover"
            
            payload = {
                "schemas": schema_names,
                "excluded_tables": excluded_tables,
                "analyze": True
            }
            
            # Hacer solicitud HTTP
            async with self.http_client.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Error discovering schema: {error_text}")
                    
                data = await response.json()
            
            # Procesar resultados
            schema = DatabaseSchema(
                connection_id=connection_id,
                name=connection_details.get("name", "PostgreSQL Database"),
                type="postgresql",
                description=connection_details.get("description", ""),
                version=data.get("version", ""),
                status=SchemaDiscoveryStatus.COMPLETED,
                discovery_date=datetime.utcnow()
            )
            
            # Agregar tablas (con límites de memoria)
            tables = []
            table_count = 0
            for table_data in data.get("tables", []):
                # Limitar el número máximo de tablas para prevenir consumo excesivo de memoria
                if table_count >= max_tables:
                    logger.warning(f"Se alcanzó el límite máximo de {max_tables} tablas para {connection_id}")
                    break
                
                # Procesar columnas con límites
                columns = []
                column_count = 0
                for col_data in table_data.get("columns", []):
                    # Limitar el número de columnas por tabla
                    if column_count >= max_columns_per_table:
                        logger.warning(f"Se alcanzó el límite máximo de {max_columns_per_table} columnas para la tabla {table_data.get('name', '')}")
                        break
                    
                    # Truncar nombres muy largos para prevenir problemas de memoria
                    col_name = col_data.get("name", "")
                    if len(col_name) > max_column_name_length:
                        col_name = col_name[:max_column_name_length] + "..."
                        logger.warning(f"Nombre de columna truncado: {col_data.get('name', '')} -> {col_name}")
                    
                    column = ColumnSchema(
                        name=col_name,
                        data_type=col_data.get("data_type", ""),
                        nullable=col_data.get("nullable", True),
                        is_primary=col_data.get("is_primary", False),
                        is_foreign=col_data.get("is_foreign", False),
                        references=col_data.get("references", None),
                        description=col_data.get("description", "")
                    )
                    columns.append(column)
                    column_count += 1
                
                # Truncar nombres de tabla muy largos
                table_name = table_data.get("name", "")
                if len(table_name) > max_table_name_length:
                    table_name = table_name[:max_table_name_length] + "..."
                    logger.warning(f"Nombre de tabla truncado: {table_data.get('name', '')} -> {table_name}")
                
                # Crear tabla
                table = TableSchema(
                    name=table_name,
                    schema=table_data.get("schema", "public"),
                    description=table_data.get("description", ""),
                    rows_count=table_data.get("rows_count", 0),
                    columns=columns
                )
                tables.append(table)
                table_count += 1
            
            schema.tables = tables
            return schema
            
        except Exception as e:
            logger.error(f"Error discovering PostgreSQL schema: {e}")
            raise ValueError(f"Failed to discover PostgreSQL schema: {str(e)}")

    async def _discover_mysql_schema(
        self, connection_id: str, connection_details: Dict[str, Any], options: Optional[Dict[str, Any]]
    ) -> DatabaseSchema:
        """
        Descubrir esquema de MySQL
        
        Args:
            connection_id: ID de la conexión
            connection_details: Detalles de la conexión
            options: Opciones de descubrimiento
            
        Returns:
            Esquema descubierto
        """
        try:
            # Extraer opciones
            database_name = connection_details.get("database", "")
            excluded_tables = options.get("excluded_tables", []) if options else []
            
            # Solicitar descubrimiento al servicio de conexión
            url = f"{self.settings.db_connection_service_url}/connections/{connection_id}/discover"
            
            payload = {
                "database": database_name,
                "excluded_tables": excluded_tables,
                "analyze": True
            }
            
            # Hacer solicitud HTTP
            async with self.http_client.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Error discovering schema: {error_text}")
                    
                data = await response.json()
            
            # Procesar resultados
            schema = DatabaseSchema(
                connection_id=connection_id,
                name=connection_details.get("name", "MySQL Database"),
                type="mysql",
                description=connection_details.get("description", ""),
                version=data.get("version", ""),
                status=SchemaDiscoveryStatus.COMPLETED,
                discovery_date=datetime.utcnow()
            )
            
            # Agregar tablas (con límites de memoria)
            tables = []
            table_count = 0
            for table_data in data.get("tables", []):
                # Limitar el número máximo de tablas para prevenir consumo excesivo de memoria
                if table_count >= max_tables:
                    logger.warning(f"Se alcanzó el límite máximo de {max_tables} tablas para {connection_id}")
                    break
                
                # Procesar columnas con límites
                columns = []
                column_count = 0
                for col_data in table_data.get("columns", []):
                    # Limitar el número de columnas por tabla
                    if column_count >= max_columns_per_table:
                        logger.warning(f"Se alcanzó el límite máximo de {max_columns_per_table} columnas para la tabla {table_data.get('name', '')}")
                        break
                    
                    # Truncar nombres muy largos para prevenir problemas de memoria
                    col_name = col_data.get("name", "")
                    if len(col_name) > max_column_name_length:
                        col_name = col_name[:max_column_name_length] + "..."
                        logger.warning(f"Nombre de columna truncado: {col_data.get('name', '')} -> {col_name}")
                    
                    column = ColumnSchema(
                        name=col_name,
                        data_type=col_data.get("data_type", ""),
                        nullable=col_data.get("nullable", True),
                        is_primary=col_data.get("is_primary", False),
                        is_foreign=col_data.get("is_foreign", False),
                        references=col_data.get("references", None),
                        description=col_data.get("description", "")
                    )
                    columns.append(column)
                    column_count += 1
                
                # Truncar nombres de tabla muy largos
                table_name = table_data.get("name", "")
                if len(table_name) > max_table_name_length:
                    table_name = table_name[:max_table_name_length] + "..."
                    logger.warning(f"Nombre de tabla truncado: {table_data.get('name', '')} -> {table_name}")
                
                # Crear tabla
                table = TableSchema(
                    name=table_name,
                    schema=database_name,
                    description=table_data.get("description", ""),
                    rows_count=table_data.get("rows_count", 0),
                    columns=columns
                )
                tables.append(table)
                table_count += 1
            
            schema.tables = tables
            return schema
            
        except Exception as e:
            logger.error(f"Error discovering MySQL schema: {e}")
            raise ValueError(f"Failed to discover MySQL schema: {str(e)}")

    async def _discover_mongodb_schema(
        self, connection_id: str, connection_details: Dict[str, Any], options: Optional[Dict[str, Any]]
    ) -> DatabaseSchema:
        """
        Descubrir esquema de MongoDB
        
        Args:
            connection_id: ID de la conexión
            connection_details: Detalles de la conexión
            options: Opciones de descubrimiento
            
        Returns:
            Esquema descubierto
        """
        try:
            # Extraer opciones
            database_name = connection_details.get("database", "")
            excluded_collections = options.get("excluded_collections", []) if options else []
            sample_size = options.get("sample_size", 100) if options else 100
            
            # Solicitar descubrimiento al servicio de conexión
            url = f"{self.settings.db_connection_service_url}/connections/{connection_id}/discover"
            
            payload = {
                "database": database_name,
                "excluded_collections": excluded_collections,
                "sample_size": sample_size
            }
            
            # Hacer solicitud HTTP
            async with self.http_client.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Error discovering schema: {error_text}")
                    
                data = await response.json()
            
            # Procesar resultados
            schema = DatabaseSchema(
                connection_id=connection_id,
                name=connection_details.get("name", "MongoDB Database"),
                type="mongodb",
                description=connection_details.get("description", ""),
                version=data.get("version", ""),
                status=SchemaDiscoveryStatus.COMPLETED,
                discovery_date=datetime.utcnow()
            )
            
            # Transformar colecciones en "tablas" (con límites de memoria)
            tables = []
            table_count = 0
            for collection_data in data.get("collections", []):
                # Limitar el número máximo de colecciones para prevenir consumo excesivo de memoria
                if table_count >= max_tables:
                    logger.warning(f"Se alcanzó el límite máximo de {max_tables} colecciones para {connection_id}")
                    break
                
                # Inferir columnas desde los campos descubiertos con límites
                columns = []
                column_count = 0
                for field_name, field_info in collection_data.get("fields", {}).items():
                    # Limitar el número de campos por colección
                    if column_count >= max_columns_per_table:
                        logger.warning(f"Se alcanzó el límite máximo de {max_columns_per_table} campos para la colección {collection_data.get('name', '')}")
                        break
                    
                    # Truncar nombres muy largos para prevenir problemas de memoria
                    col_name = field_name
                    if len(col_name) > max_column_name_length:
                        col_name = col_name[:max_column_name_length] + "..."
                        logger.warning(f"Nombre de campo truncado: {field_name} -> {col_name}")
                    
                    column = ColumnSchema(
                        name=col_name,
                        data_type=field_info.get("type", "mixed"),
                        nullable=field_info.get("nullable", True),
                        is_primary=field_name == "_id",
                        description=field_info.get("description", "")
                    )
                    columns.append(column)
                    column_count += 1
                
                # Truncar nombres de colección muy largos
                coll_name = collection_data.get("name", "")
                if len(coll_name) > max_table_name_length:
                    coll_name = coll_name[:max_table_name_length] + "..."
                    logger.warning(f"Nombre de colección truncado: {collection_data.get('name', '')} -> {coll_name}")
                
                # Crear "tabla" (colección)
                table = TableSchema(
                    name=coll_name,
                    schema=database_name,
                    description=collection_data.get("description", ""),
                    rows_count=collection_data.get("count", 0),
                    columns=columns,
                    is_collection=True
                )
                tables.append(table)
                table_count += 1
            
            schema.tables = tables
            return schema
            
        except Exception as e:
            logger.error(f"Error discovering MongoDB schema: {e}")
            raise ValueError(f"Failed to discover MongoDB schema: {str(e)}")