# services/vectordb_base.py
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class VectorDBBase(ABC):
    """Clase base abstracta para servicios de bases de datos vectoriales"""
    
    @abstractmethod
    async def get_status(self) -> Dict:
        """
        Verificar estado de la base de datos vectorial
        
        Returns:
            Dict con estado e información de la base de datos
        """
        pass
    
    @abstractmethod
    async def ensure_collections_exist(self, collections: List[str]) -> None:
        """
        Asegurar que las colecciones/clases necesarias existen, crearlas si no
        
        Args:
            collections: Lista de nombres de colecciones a verificar/crear
        """
        pass
    
    @abstractmethod
    async def store_vector(self,
                          vector: List[float],
                          collection: str,
                          entity_id: str,
                          text: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Almacenar un vector en la base de datos vectorial
        
        Args:
            vector: Vector a almacenar
            collection: Nombre de la colección
            entity_id: ID de la entidad asociada
            text: Texto asociado al vector
            metadata: Metadatos adicionales
            
        Returns:
            ID del vector almacenado
        """
        pass
    
    @abstractmethod
    async def delete_vector(self, vector_id: str, collection: str) -> bool:
        """
        Eliminar un vector de la base de datos vectorial
        
        Args:
            vector_id: ID del vector a eliminar
            collection: Nombre de la colección
            
        Returns:
            True si se eliminó correctamente
        """
        pass
    
    @abstractmethod
    async def search(self,
                    query_vector: List[float],
                    collection: str,
                    filters: Optional[Dict[str, Any]] = None,
                    limit: int = 10) -> List[Dict[str, Any]]:
        """
        Buscar vectores similares
        
        Args:
            query_vector: Vector de consulta
            collection: Nombre de la colección
            filters: Filtros adicionales
            limit: Número máximo de resultados
            
        Returns:
            Lista de resultados con scores
        """
        pass