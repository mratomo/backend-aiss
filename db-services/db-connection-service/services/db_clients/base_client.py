# services/db_clients/base_client.py
from abc import ABC, abstractmethod
from typing import Dict, Any

from models.models import DBConnection

class BaseDBClient(ABC):
    """Clase base para clientes de BD"""
    
    @abstractmethod
    async def test_connection(self, connection: DBConnection) -> bool:
        """
        Probar conexión a la BD
        
        Args:
            connection: Conexión a probar
            
        Returns:
            True si la conexión es exitosa
            
        Raises:
            Exception: Si hay error de conexión
        """
        pass
    
    @abstractmethod
    async def execute_query(self, connection: DBConnection, query: str, params: Dict[str, Any] = None) -> Any:
        """
        Ejecutar una consulta en la BD
        
        Args:
            connection: Conexión a la BD
            query: Consulta a ejecutar
            params: Parámetros para la consulta
            
        Returns:
            Resultado de la consulta
            
        Raises:
            Exception: Si hay error durante la ejecución
        """
        pass
    
    @abstractmethod
    async def get_schema(self, connection: DBConnection) -> Dict[str, Any]:
        """
        Obtener esquema de la BD
        
        Args:
            connection: Conexión a la BD
            
        Returns:
            Información del esquema
            
        Raises:
            Exception: Si hay error durante la obtención
        """
        pass