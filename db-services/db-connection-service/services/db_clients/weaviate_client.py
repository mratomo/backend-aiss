# services/db_clients/weaviate_client.py
import logging
from typing import Dict, Any, List, Optional
import json

import weaviate
from weaviate.exceptions import WeaviateBaseError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from services.db_clients.base_client import BaseDBClient
from models.models import DBConnection

logger = logging.getLogger(__name__)

class WeaviateClient(BaseDBClient):
    """Cliente para bases de datos Weaviate"""
    
    def __init__(self):
        """Inicializar cliente Weaviate"""
        self.clients_cache = {}  # Cache de conexiones por ID
    
    def _get_client(self, connection: DBConnection) -> weaviate.Client:
        """
        Obtener cliente para una conexión
        
        Args:
            connection: Conexión a la BD
            
        Returns:
            Cliente Weaviate
        """
        # Si ya existe en caché, devolver
        if connection.id in self.clients_cache:
            return self.clients_cache[connection.id]
        
        # Configurar autenticación si hay credenciales
        auth_config = None
        if connection.password:
            auth_config = weaviate.auth.AuthApiKey(api_key=connection.password)
        
        # Crear cliente
        client = weaviate.Client(
            url=f"http://{connection.host}:{connection.port}",
            auth_client_secret=auth_config,
            timeout_config=(60, 60),  # (connect_timeout, read_timeout)
            additional_headers={"X-OpenAI-Api-Key": connection.password} if connection.password else None
        )
        
        # Guardar en caché
        if connection.id:
            self.clients_cache[connection.id] = client
            
        return client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def test_connection(self, connection: DBConnection) -> bool:
        """
        Probar conexión a Weaviate
        
        Args:
            connection: Conexión a probar
            
        Returns:
            True si la conexión es exitosa
            
        Raises:
            Exception: Si hay error de conexión
        """
        try:
            client = self._get_client(connection)
            
            # Verificar si el servidor está vivo
            is_ready = client.is_ready()
            if not is_ready:
                raise Exception("Weaviate no está listo")
                
            # Si llegamos aquí, la conexión es exitosa
            return True
            
        except WeaviateBaseError as e:
            logger.error(f"Error conectando a Weaviate: {str(e)}")
            raise Exception(f"Error conectando a Weaviate: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error inesperado probando conexión Weaviate: {str(e)}")
            raise Exception(f"Error inesperado: {str(e)}")
    
    async def execute_query(self, connection: DBConnection, query: str, params: Dict[str, Any] = None) -> Any:
        """
        Ejecutar una consulta GraphQL en Weaviate
        
        Args:
            connection: Conexión a la BD
            query: Consulta GraphQL a ejecutar
            params: Parámetros para la consulta
            
        Returns:
            Resultado de la consulta
            
        Raises:
            Exception: Si hay error durante la ejecución
        """
        try:
            client = self._get_client(connection)
            
            # Ejecutar consulta GraphQL
            result = client.query.raw(query)
            
            return result
            
        except WeaviateBaseError as e:
            logger.error(f"Error ejecutando consulta en Weaviate: {str(e)}")
            raise Exception(f"Error ejecutando consulta en Weaviate: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error inesperado ejecutando consulta en Weaviate: {str(e)}")
            raise Exception(f"Error inesperado: {str(e)}")
    
    async def get_schema(self, connection: DBConnection) -> Dict[str, Any]:
        """
        Obtener esquema de Weaviate
        
        Args:
            connection: Conexión a la BD
            
        Returns:
            Información del esquema
            
        Raises:
            Exception: Si hay error durante la obtención
        """
        try:
            client = self._get_client(connection)
            
            # Obtener esquema
            schema = client.schema.get()
            
            # Formatear resultado
            result = {
                "type": "weaviate",
                "name": connection.database or "weaviate",
                "tables": []
            }
            
            # Procesar clases como tablas
            if "classes" in schema:
                for cls in schema["classes"]:
                    table = {
                        "name": cls["class"],
                        "description": cls.get("description", ""),
                        "rows_count": self._get_class_count(client, cls["class"]),
                        "columns": []
                    }
                    
                    # Procesar propiedades como columnas
                    if "properties" in cls:
                        for prop in cls["properties"]:
                            column = {
                                "name": prop["name"],
                                "data_type": self._get_data_type(prop),
                                "description": prop.get("description", ""),
                                "nullable": True,  # En Weaviate todas las propiedades son opcionales por defecto
                                "is_primary": False,
                                "is_foreign": False
                            }
                            table["columns"].append(column)
                    
                    result["tables"].append(table)
            
            return result
            
        except WeaviateBaseError as e:
            logger.error(f"Error obteniendo esquema de Weaviate: {str(e)}")
            raise Exception(f"Error obteniendo esquema de Weaviate: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error inesperado obteniendo esquema de Weaviate: {str(e)}")
            raise Exception(f"Error inesperado: {str(e)}")
    
    def _get_class_count(self, client: weaviate.Client, class_name: str) -> int:
        """
        Obtener conteo de objetos en una clase
        
        Args:
            client: Cliente Weaviate
            class_name: Nombre de la clase
            
        Returns:
            Número de objetos en la clase
        """
        try:
            result = client.query.aggregate(class_name).with_meta_count().do()
            
            if "data" in result and "Aggregate" in result["data"] and class_name in result["data"]["Aggregate"]:
                return result["data"]["Aggregate"][class_name][0]["meta"]["count"]
                
            return 0
            
        except Exception:
            return 0
    
    def _get_data_type(self, property_info: Dict[str, Any]) -> str:
        """
        Obtener tipo de dato para una propiedad
        
        Args:
            property_info: Información de la propiedad
            
        Returns:
            Tipo de dato como cadena
        """
        if "dataType" in property_info:
            data_types = property_info["dataType"]
            
            if "text" in data_types:
                return "text"
            elif "string" in data_types:
                return "string"
            elif "int" in data_types:
                return "int"
            elif "number" in data_types:
                return "number"
            elif "boolean" in data_types:
                return "boolean"
            elif "date" in data_types:
                return "date"
            elif "object" in data_types:
                return "object"
            elif len(data_types) > 0:
                return data_types[0]
                
        return "unknown"