# config/settings.py
import os
from typing import Dict, List, Optional, Union

from pydantic import BaseSettings, Field, validator


class QdrantSettings(BaseSettings):
    """Configuración para Qdrant"""
    url: str = Field(default="http://qdrant:6333")
    api_key: Optional[str] = Field(default=None)

    # Nombres de colecciones para diferentes tipos de embeddings
    collection_general: str = Field(default="general_knowledge")
    collection_personal: str = Field(default="personal_knowledge")

    # Configuración de las colecciones
    vector_size: Optional[int] = Field(default=None)  # Automático basado en modelo
    distance: str = Field(default="Cosine")  # Métrica de distancia (Cosine, Euclid, Dot)


class ModelSettings(BaseSettings):
    """Configuración para modelos de embeddings"""
    # Modelos actualizados
    general_model: str = Field(default="BAAI/bge-large-en-v1.5")
    personal_model: str = Field(default="BAAI/bge-large-en-v1.5")
    # O alternativa multilingüe: "intfloat/multilingual-e5-base"

    # Configuración común
    batch_size: int = Field(default=32)
    use_gpu: bool = Field(default=True)
    device: Optional[str] = Field(default=None)  # Auto-detection if None

    # Opciones de optimización
    use_8bit: bool = Field(default=False)  # Cuantización 8-bit para ahorrar memoria
    use_fp16: bool = Field(default=True)   # Habilitar media precisión cuando hay GPU
    max_length: int = Field(default=512)   # Máxima longitud de secuencia para BGE

    # Umbral de similaridad (0.0 a 1.0)
    similarity_threshold: float = Field(default=0.65)


class Settings(BaseSettings):
    """Configuraciones para el servicio de embeddings"""

    # Configuración del servidor
    environment: str = Field(default="development")
    port: int = Field(default=8084)
    cors_allowed_origins: List[str] = Field(default=["*"])

    # Configuración de MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="mcp_knowledge_system")

    # Configuración de Qdrant
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)

    # Configuración de modelos
    models: ModelSettings = Field(default_factory=ModelSettings)

    # Configuración de MCP
    mcp_service_url: str = Field(default="http://context-service:8083")

    # Procesamiento de documentos
    chunk_size: int = Field(default=1000)  # Tamaño de los fragmentos para documentos grandes
    chunk_overlap: int = Field(default=200)  # Superposición entre fragmentos

    # Límites
    max_document_size_mb: int = Field(default=20)  # Tamaño máximo de documento en MB
    max_texts_per_batch: int = Field(default=50)  # Número máximo de textos por batch

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **kwargs):
        """Inicializar configuraciones con valores de variables de entorno"""
        super().__init__(**kwargs)

        # Priorizar variables de entorno sobre valores por defecto
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        self.port = int(os.getenv("PORT", str(self.port)))

        # Configuración de CORS
        cors_origins = os.getenv("CORS_ALLOWED_ORIGINS")
        if cors_origins:
            self.cors_allowed_origins = cors_origins.split(",")

        # Configuración de MongoDB
        self.mongodb_uri = os.getenv("MONGODB_URI", self.mongodb_uri)
        self.mongodb_database = os.getenv("MONGODB_DATABASE", self.mongodb_database)

        # Configuración de Qdrant
        self.qdrant.url = os.getenv("QDRANT_URL", self.qdrant.url)
        self.qdrant.api_key = os.getenv("QDRANT_API_KEY", self.qdrant.api_key)
        self.qdrant.collection_general = os.getenv("QDRANT_COLLECTION_GENERAL", self.qdrant.collection_general)
        self.qdrant.collection_personal = os.getenv("QDRANT_COLLECTION_PERSONAL", self.qdrant.collection_personal)

        # Configuración de modelos
        self.models.general_model = os.getenv("GENERAL_EMBEDDING_MODEL", self.models.general_model)
        self.models.personal_model = os.getenv("PERSONAL_EMBEDDING_MODEL", self.models.personal_model)
        self.models.use_gpu = os.getenv("USE_GPU", "true").lower() in ("true", "1", "yes")
        self.models.use_8bit = os.getenv("USE_8BIT", "false").lower() in ("true", "1", "yes")
        self.models.use_fp16 = os.getenv("USE_FP16", "true").lower() in ("true", "1", "yes")

        # Configuración de MCP
        self.mcp_service_url = os.getenv("MCP_SERVICE_URL", self.mcp_service_url)

        # Configuración de procesamiento
        self.chunk_size = int(os.getenv("CHUNK_SIZE", str(self.chunk_size)))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", str(self.chunk_overlap)))

        # Límites
        self.max_document_size_mb = int(os.getenv("MAX_DOCUMENT_SIZE_MB", str(self.max_document_size_mb)))
        self.max_texts_per_batch = int(os.getenv("MAX_TEXTS_PER_BATCH", str(self.max_texts_per_batch)))