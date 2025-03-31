# services/connection_service.py
import logging
import asyncio
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from bson import ObjectId

from models.models import DBConnection, DBConnectionResponse, DBConnectionUpdate, ConnectionStatus
from config.settings import Settings
from services.encryption_service import EncryptionService
from services.security_service import SecurityService
from services.db_clients import get_db_client

logger = logging.getLogger(__name__)

class ConnectionService:
    """Servicio para gestionar conexiones a bases de datos"""

    def __init__(self, db, encryption_service: EncryptionService, security_service: SecurityService, settings: Settings):
        """
        Inicializar servicio con la base de datos y servicios dependientes
        
        Args:
            db: Instancia de la base de datos MongoDB
            encryption_service: Servicio de encriptación
            security_service: Servicio de seguridad
            settings: Configuración de la aplicación
        """
        self.db = db
        self.collection = db[settings.mongodb.connections_collection]
        self.encryption_service = encryption_service
        self.security_service = security_service
        self.settings = settings
    
    async def get_all_connections(self) -> List[DBConnectionResponse]:
        """
        Obtener todas las conexiones de BD
        
        Returns:
            Lista de conexiones (sin credenciales)
        """
        connections = await self.collection.find().to_list(length=100)
        return [self._to_connection_response(conn) for conn in connections]
    
    async def get_connection(self, connection_id: str) -> Optional[DBConnectionResponse]:
        """
        Obtener una conexión específica por ID
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            Conexión si existe, None en caso contrario
        """
        try:
            obj_id = ObjectId(connection_id)
        except Exception:
            return None
        
        connection = await self.collection.find_one({"_id": obj_id})
        if not connection:
            return None
        
        return self._to_connection_response(connection)
    
    async def create_connection(self, connection: DBConnection) -> DBConnectionResponse:
        """
        Crear una nueva conexión a BD
        
        Args:
            connection: Datos de la conexión
            
        Returns:
            Conexión creada (sin credenciales)
            
        Raises:
            ValueError: Si hay errores de validación
        """
        # Validar tipo de BD
        if connection.type not in self.settings.db_connections.allowed_operations:
            raise ValueError(f"Tipo de BD no soportado: {connection.type}")
        
        # Encriptar contraseña
        if connection.password:
            connection.password = self.encryption_service.encrypt(connection.password)
        
        # Preparar documento
        connection_dict = connection.dict(exclude={"id"})
        connection_dict["created_at"] = datetime.utcnow()
        connection_dict["updated_at"] = datetime.utcnow()
        
        # Insertar en MongoDB
        result = await self.collection.insert_one(connection_dict)
        
        # Obtener documento insertado
        connection_dict["id"] = str(result.inserted_id)
        connection_dict["_id"] = result.inserted_id
        
        return self._to_connection_response(connection_dict)
    
    async def update_connection(self, connection_id: str, update: DBConnectionUpdate) -> Optional[DBConnectionResponse]:
        """
        Actualizar una conexión existente
        
        Args:
            connection_id: ID de la conexión
            update: Datos a actualizar
            
        Returns:
            Conexión actualizada si existe, None en caso contrario
            
        Raises:
            ValueError: Si hay errores de validación
        """
        try:
            obj_id = ObjectId(connection_id)
        except Exception:
            return None
        
        # Obtener conexión existente
        connection = await self.collection.find_one({"_id": obj_id})
        if not connection:
            return None
        
        # Preparar actualización
        update_dict = update.dict(exclude_none=True)
        
        # Encriptar contraseña si se proporciona
        if "password" in update_dict and update_dict["password"]:
            update_dict["password"] = self.encryption_service.encrypt(update_dict["password"])
        
        # Añadir timestamp de actualización
        update_dict["updated_at"] = datetime.utcnow()
        
        # Actualizar en MongoDB
        await self.collection.update_one(
            {"_id": obj_id},
            {"$set": update_dict}
        )
        
        # Obtener documento actualizado
        updated = await self.collection.find_one({"_id": obj_id})
        return self._to_connection_response(updated)
    
    async def delete_connection(self, connection_id: str) -> bool:
        """
        Eliminar una conexión
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            True si se eliminó, False si no existía
        """
        try:
            obj_id = ObjectId(connection_id)
        except Exception:
            return False
        
        result = await self.collection.delete_one({"_id": obj_id})
        return result.deleted_count > 0
    
    async def test_connection(self, connection_id: str) -> Dict[str, Any]:
        """
        Probar una conexión a BD
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            Resultado de la prueba
            
        Raises:
            ValueError: Si la conexión no existe
            Exception: Si hay error de conexión
        """
        # Obtener conexión
        connection = await self.get_connection_with_credentials(connection_id)
        if not connection:
            raise ValueError(f"Conexión no encontrada: {connection_id}")
        
        start_time = time.time()
        status = ConnectionStatus.ACTIVE
        error_message = None
        
        try:
            # Obtener cliente de BD según el tipo
            client = get_db_client(connection.type)
            
            # Probar conexión
            result = await client.test_connection(connection)
            
            # Actualizar estado de la conexión
            await self.update_connection_status(connection_id, ConnectionStatus.ACTIVE)
        except Exception as e:
            status = ConnectionStatus.ERROR
            error_message = str(e)
            
            # Actualizar estado con error
            await self.update_connection_status(connection_id, ConnectionStatus.ERROR)
            
            logger.error(f"Error probando conexión {connection_id}: {e}")
            raise
        finally:
            elapsed_time = round((time.time() - start_time) * 1000)
        
        return {
            "status": status,
            "elapsed_ms": elapsed_time,
            "error": error_message,
            "timestamp": datetime.utcnow()
        }
    
    async def execute_query(self, connection_id: str, query: str, params: Dict[str, Any] = None,
                          timeout: int = None) -> Tuple[Any, int]:
        """
        Ejecutar una consulta en una conexión
        
        Args:
            connection_id: ID de la conexión
            query: Consulta a ejecutar
            params: Parámetros para la consulta
            timeout: Tiempo límite en segundos
            
        Returns:
            Tupla con (resultado, tiempo de ejecución en ms)
            
        Raises:
            ValueError: Si la conexión no existe o la consulta no es válida
            Exception: Si hay error durante la ejecución
        """
        # Obtener conexión
        connection = await self.get_connection_with_credentials(connection_id)
        if not connection:
            raise ValueError(f"Conexión no encontrada: {connection_id}")
        
        # Validar consulta
        if not self.security_service.validate_query(query, connection.type):
            raise ValueError("Consulta no válida o potencialmente peligrosa")
        
        # Aplicar timeout predeterminado si no se especifica
        if timeout is None:
            timeout = self.settings.db_connections.query_timeout
        
        start_time = time.time()
        
        try:
            # Obtener cliente de BD según el tipo
            client = get_db_client(connection.type)
            
            # Ejecutar consulta con timeout
            result = await asyncio.wait_for(
                client.execute_query(connection, query, params),
                timeout=timeout
            )
            
            elapsed_time = round((time.time() - start_time) * 1000)
            return result, elapsed_time
        except asyncio.TimeoutError:
            elapsed_time = round((time.time() - start_time) * 1000)
            logger.warning(f"Timeout ejecutando consulta en conexión {connection_id} después de {elapsed_time}ms")
            raise ValueError(f"La consulta excedió el tiempo límite de {timeout} segundos")
        except Exception as e:
            elapsed_time = round((time.time() - start_time) * 1000)
            logger.error(f"Error ejecutando consulta en conexión {connection_id}: {e}")
            raise
    
    async def get_connection_with_credentials(self, connection_id: str) -> Optional[DBConnection]:
        """
        Obtener una conexión con credenciales desencriptadas
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            Conexión si existe, None en caso contrario
        """
        try:
            obj_id = ObjectId(connection_id)
        except Exception:
            return None
        
        connection = await self.collection.find_one({"_id": obj_id})
        if not connection:
            return None
        
        # Crear instancia de DBConnection
        conn = DBConnection(**{**connection, "id": str(connection["_id"])})
        
        # Desencriptar contraseña si existe
        if conn.password:
            conn.password = self.encryption_service.decrypt(conn.password)
        
        return conn
    
    async def update_connection_status(self, connection_id: str, status: ConnectionStatus) -> bool:
        """
        Actualizar el estado de una conexión
        
        Args:
            connection_id: ID de la conexión
            status: Nuevo estado
            
        Returns:
            True si se actualizó, False si no existía
        """
        try:
            obj_id = ObjectId(connection_id)
        except Exception:
            return False
        
        result = await self.collection.update_one(
            {"_id": obj_id},
            {"$set": {"status": status, "last_checked": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
    
    def _to_connection_response(self, connection: Dict[str, Any]) -> DBConnectionResponse:
        """
        Convertir documento de conexión a modelo de respuesta (sin credenciales)
        
        Args:
            connection: Documento de conexión
            
        Returns:
            Modelo de respuesta
        """
        # Convertir _id a string
        connection_id = str(connection["_id"])
        
        # Eliminar _id y password
        if "_id" in connection:
            del connection["_id"]
        if "password" in connection:
            del connection["password"]
        
        # Crear respuesta
        return DBConnectionResponse(id=connection_id, **connection)