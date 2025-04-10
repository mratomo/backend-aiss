# config/settings.py
import os
from typing import Dict, List, Optional, Union

from pydantic import Field, validator
from pydantic_settings import BaseSettings



class WeaviateSettings(BaseSettings):
    """Configuración para Weaviate"""
    url: str = Field(default="http://weaviate:8080")  # Puerto interno de Weaviate
    api_key: Optional[str] = Field(default=None)
    
    # Nombres de clases para diferentes tipos de embeddings
    class_general: str = Field(default="GeneralKnowledge")
    class_personal: str = Field(default="PersonalKnowledge")
    
    # Parámetros para Weaviate
    batch_size: int = Field(default=100)
    timeout: int = Field(default=60)


class ModelSettings(BaseSettings):
    """Configuración para modelos de embeddings (SOLO NOMIC v1.5)"""
    # Modelos fijos - ya no configurables por env var para estos campos
    general_model: str = Field(default="nomic-ai/nomic-embed-text-v1.5")
    personal_model: str = Field(default="nomic-ai/nomic-embed-text-v1.5")

    # Configuración común - Optimizada para RTX 4090 con 24GB VRAM
    batch_size: int = Field(default=128) # Aumentado para RTX 4090 (24GB VRAM)
    use_gpu: bool = Field(default=True) # Forzar uso de GPU por defecto
    device: Optional[str] = Field(default=None)  # Se detectará automáticamente ("cuda:0" o "cpu")
    fallback_to_cpu: bool = Field(default=False) # IMPORTANTE: Poner en False si la GPU es requisito estricto

    # Opciones de optimización
    use_fp16: bool = Field(default=True) # Media precisión para mayor rendimiento en RTX 4090
    # Estas opciones ya no son relevantes al quitar los modelos HF genéricos
    # use_8bit: bool = Field(default=False)
    # max_length: int = Field(default=512) # Nomic/SentenceTransformer lo maneja internamente

    # Umbral de similaridad (0.0 a 1.0) - Aún relevante para búsquedas
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

    # Configuración de base de datos vectorial
    weaviate: WeaviateSettings = Field(default_factory=WeaviateSettings)
    
    # Selección de base de datos vectorial a utilizar (weaviate)
    vector_db: str = Field(default="weaviate")

    # Configuración de modelos
    models: ModelSettings = Field(default_factory=ModelSettings)

    # Configuración de MCP
    mcp_service_url: str = Field(default="http://context-service:8083")
    mcp_service_timeout: float = Field(default=30.0)
    allow_degraded_mode: bool = Field(default=True)
    use_httpx: bool = Field(default=True)  # Usar httpx en lugar de aiohttp

    # Procesamiento de documentos
    chunk_size: int = Field(default=1000)  # Tamaño de los fragmentos para documentos grandes
    chunk_overlap: int = Field(default=200)  # Superposición entre fragmentos

    # Límites
    max_document_size_mb: int = Field(default=20)  # Tamaño máximo de documento en MB
    max_texts_per_batch: int = Field(default=50)  # Número máximo de textos por batch

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False
    }

    def __init__(self, **kwargs):
        """Inicializar configuraciones con valores de variables de entorno"""
        # Definir CORS primero para evitar problemas de parsing
        cors_origins = os.getenv("CORS_ALLOWED_ORIGINS")
        if cors_origins:
            kwargs["cors_allowed_origins"] = cors_origins.split(",")
            
        super().__init__(**kwargs)

        # Priorizar variables de entorno sobre valores por defecto
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        self.port = int(os.getenv("PORT", str(self.port)))

        # Configuración de MongoDB
        self.mongodb_uri = os.getenv("MONGODB_URI", self.mongodb_uri)
        self.mongodb_database = os.getenv("MONGODB_DATABASE", self.mongodb_database)

        # Configuración de Weaviate
        self.weaviate.url = os.getenv("WEAVIATE_URL", self.weaviate.url)
        self.weaviate.api_key = os.getenv("WEAVIATE_API_KEY", self.weaviate.api_key)
        self.weaviate.class_general = os.getenv("WEAVIATE_CLASS_GENERAL", self.weaviate.class_general)
        self.weaviate.class_personal = os.getenv("WEAVIATE_CLASS_PERSONAL", self.weaviate.class_personal)

        # Configuración de modelos - Ya no se leen de env vars los nombres de modelos
        # Los modelos están fijos en "nomic-ai/nomic-embed-text-v1.5"
        self.models.use_gpu = os.getenv("USE_GPU", "true").lower() in ("true", "1", "yes")
        self.models.fallback_to_cpu = os.getenv("FALLBACK_TO_CPU", "false").lower() in ("true", "1", "yes")
        self.models.use_fp16 = os.getenv("USE_FP16", "true").lower() in ("true", "1", "yes")

        # Configuración de MCP
        self.mcp_service_url = os.getenv("MCP_SERVICE_URL", self.mcp_service_url)
        self.mcp_service_timeout = float(os.getenv("MCP_SERVICE_TIMEOUT", str(self.mcp_service_timeout)))
        self.allow_degraded_mode = os.getenv("ALLOW_DEGRADED_MODE", str(self.allow_degraded_mode)).lower() in ("true", "1", "yes")
        self.use_httpx = os.getenv("USE_HTTPX", str(self.use_httpx)).lower() in ("true", "1", "yes")

        # Configuración de procesamiento
        self.chunk_size = int(os.getenv("CHUNK_SIZE", str(self.chunk_size)))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", str(self.chunk_overlap)))

        # Límites
        self.max_document_size_mb = int(os.getenv("MAX_DOCUMENT_SIZE_MB", str(self.max_document_size_mb)))
        self.max_texts_per_batch = int(os.getenv("MAX_TEXTS_PER_BATCH", str(self.max_texts_per_batch)))