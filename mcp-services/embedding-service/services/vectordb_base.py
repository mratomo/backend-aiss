import logging
import uuid
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

try:
    import structlog
    logger = structlog.get_logger("vectordb_service")
    structlog_available = True
except ImportError:
    logger = logging.getLogger("vectordb_service")
    structlog_available = False

from models.embedding import EmbeddingType, SearchResult

class VectorDBBase(ABC):
    """Clase base abstracta para servicios de bases de datos vectoriales"""
    
    @abstractmethod
    async def get_status(self) -> Dict:
        """Verificar estado de la base de datos vectorial"""
        pass
    
    @abstractmethod
    async def ensure_collections_exist(self) -> None:
        """Asegurar que las colecciones/clases necesarias existen, crearlas si no"""
        pass
    
    @abstractmethod
    async def store_vector(self,
                         vector: List[float],
                         embedding_type: EmbeddingType,
                         doc_id: str,
                         owner_id: str,
                         text: Optional[str] = None,
                         area_id: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> str:
        """Almacenar un vector en la base de datos vectorial"""
        pass
    
    @abstractmethod
    async def store_vectors_batch(self,
                                vectors: List[List[float]],
                                embedding_type: EmbeddingType,
                                doc_ids: List[str],
                                owner_id: str,
                                texts: Optional[List[str]] = None,
                                area_id: Optional[str] = None,
                                metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """Almacenar múltiples vectores en batch"""
        pass
    
    @abstractmethod
    async def delete_vector(self, vector_id: str, embedding_type: EmbeddingType) -> bool:
        """Eliminar un vector de la base de datos vectorial"""
        pass
    
    @abstractmethod
    async def search(self,
                   query_vector: List[float],
                   embedding_type: EmbeddingType,
                   owner_id: Optional[str] = None,
                   area_id: Optional[str] = None,
                   limit: int = 10) -> List[SearchResult]:
        """Buscar vectores similares"""
        pass