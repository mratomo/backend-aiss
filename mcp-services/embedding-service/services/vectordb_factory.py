import logging
from typing import Optional

try:
    import structlog
    logger = structlog.get_logger("vectordb_factory")
    structlog_available = True
except ImportError:
    logger = logging.getLogger("vectordb_factory")
    structlog_available = False

from config.settings import Settings
from services.vectordb_base import VectorDBBase
from services.weaviate_service import WeaviateVectorDB

class VectorDBFactory:
    """Fábrica para crear instancias de servicios de bases de datos vectoriales"""
    
    @staticmethod
    def create(settings: Settings) -> VectorDBBase:
        """
        Crear una instancia del servicio de base de datos vectorial según la configuración
        
        Args:
            settings: Configuración de la aplicación
            
        Returns:
            Una instancia de VectorDBBase (WeaviateVectorDB)
        
        Raises:
            ValueError: Si el tipo de base de datos vectorial no está soportado
        """
        vector_db_type = settings.vector_db.lower()
        
        if vector_db_type == "weaviate":
            logger.info("Inicializando servicio para Weaviate")
            return WeaviateVectorDB(settings)
        else:
            error_msg = f"Tipo de base de datos vectorial no soportado: {vector_db_type}. Solo se admite 'weaviate'."
            logger.error(error_msg)
            raise ValueError(error_msg)