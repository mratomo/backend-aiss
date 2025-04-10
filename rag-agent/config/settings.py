# config/settings.py
import os
from typing import Dict, List, Optional, Union, Any

from pydantic import Field
from pydantic_settings import BaseSettings


class OpenAISettings(BaseSettings):
    """Configuración para proveedores OpenAI"""
    default_model: str = Field(default="gpt-4o")
    default_temperature: float = Field(default=0.0)
    default_max_tokens: int = Field(default=4096)
    timeout_seconds: int = Field(default=60)


class AnthropicSettings(BaseSettings):
    """Configuración para proveedores Anthropic"""
    default_model: str = Field(default="claude-3-opus-20240229")
    default_temperature: float = Field(default=0.0)
    default_max_tokens: int = Field(default=4096)
    timeout_seconds: int = Field(default=60)


class GoogleSettings(BaseSettings):
    """Configuración para proveedores Google AI (Gemini)"""
    default_model: str = Field(default="gemini-1.5-pro")
    default_temperature: float = Field(default=0.0)
    default_max_tokens: int = Field(default=4096)
    timeout_seconds: int = Field(default=60)
    api_base: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    enable_mcp: bool = Field(default=True)  # Habilitar integración MCP para Google


class OllamaSettings(BaseSettings):
    """Configuración para proveedores Ollama (local o remoto)"""
    default_model: str = Field(default="llama3")
    default_temperature: float = Field(default=0.0)
    default_max_tokens: int = Field(default=4096)
    timeout_seconds: int = Field(default=120)
    api_url: str = Field(default="http://localhost:11434")
    mcp_url: str = Field(default="http://ollama-mcp-server:8095")  # URL del servidor MCP para Ollama
    enable_mcp: bool = Field(default=True)  # Habilitar integración MCP para Ollama
    models_path: str = Field(default="/usr/local/share/ollama/models")  # Ruta a los modelos de Ollama
    is_remote: bool = Field(default=False)  # Indica si Ollama está en un servidor remoto
    use_gpu: bool = Field(default=True)  # Usar GPU para la instancia local (validación de consultas)
    # Opciones para optimizar el rendimiento de GPU con Ollama local
    gpu_options: Dict[str, Any] = Field(
        default_factory=lambda: {
            "num_gpu": 1,         # Número de GPUs a usar
            "f16_kv": True,       # Usar FP16 para KV-cache (menor uso de memoria)
            "mirostat": 2,        # Estabilizador de muestreo (2 = medio)
        }
    )


class RetrievalSettings(BaseSettings):
    """Configuración para el servicio de recuperación"""
    embedding_service_url: str = Field(default="http://embedding-service:8084")
    document_service_url: str = Field(default="http://document-service:8082")
    max_sources_per_query: int = Field(default=10)
    similarity_threshold: float = Field(default=0.65)


class MCPSettings(BaseSettings):
    """Configuración para el servicio MCP"""
    context_service_url: str = Field(default="http://context-service:8083")
    endpoint_sse: str = Field(default="/mcp/sse")  # Ruta de SSE para cliente MCP
    default_system_prompt: str = Field(
        default="Eres un asistente de inteligencia artificial especializado en responder preguntas "
                "basadas en la información proporcionada. Utiliza SOLO la información en el contexto "
                "para responder. Si la información no está en el contexto, indica que no tienes "
                "esa información. Proporciona respuestas detalladas y bien estructuradas."
    )


class Settings(BaseSettings):
    """Configuraciones para el Agente RAG"""

    # Configuración del servidor
    environment: str = Field(default="development")
    port: int = Field(default=8085)
    cors_allowed_origins: List[str] = Field(default=["*"])

    # Configuración de MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="mcp_knowledge_system")

    # Configuración de proveedores LLM
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    google: GoogleSettings = Field(default_factory=GoogleSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)

    # Configuración de servicios
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)

    # Plantillas para prompts
    rag_prompt_template: str = Field(
        default="A continuación tienes información relevante para responder a la pregunta del usuario.\n\n"
                "INFORMACIÓN RELEVANTE:\n{context}\n\n"
                "PREGUNTA DEL USUARIO:\n{query}\n\n"
                "Responde a la pregunta basándote solo en la información proporcionada. "
                "Si la información no es suficiente, indícalo claramente. "
                "Cita las fuentes utilizando los números de referencia [1], [2], etc. al final de las frases relevantes."
    )

    # Configuración de formato de respuestas
    include_source_documents: bool = Field(default=True)
    max_source_length: int = Field(default=1000)

    # Configuración de MCP (nuevo)
    use_mcp_tools: bool = Field(default=True)  # Usar herramientas MCP cuando estén disponibles
    prefer_direct_mcp: bool = Field(default=True)  # Preferir LLMs con soporte MCP nativo

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }

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

        # Configuración de servicios
        self.retrieval.embedding_service_url = os.getenv(
            "EMBEDDING_SERVICE_URL", self.retrieval.embedding_service_url
        )
        self.retrieval.document_service_url = os.getenv(
            "DOCUMENT_SERVICE_URL", self.retrieval.document_service_url
        )
        self.mcp.context_service_url = os.getenv(
            "CONTEXT_SERVICE_URL", self.mcp.context_service_url
        )

        # Configuración de proveedores
        # OpenAI
        self.openai.default_model = os.getenv(
            "OPENAI_DEFAULT_MODEL", self.openai.default_model
        )
        # Anthropic
        self.anthropic.default_model = os.getenv(
            "ANTHROPIC_DEFAULT_MODEL", self.anthropic.default_model
        )
        # Google
        self.google.default_model = os.getenv(
            "GOOGLE_DEFAULT_MODEL", self.google.default_model
        )
        self.google.api_base = os.getenv(
            "GOOGLE_API_BASE", self.google.api_base
        )
        self.google.enable_mcp = os.getenv("GOOGLE_ENABLE_MCP", "true").lower() in ("true", "1", "yes")
        # Ollama
        self.ollama.default_model = os.getenv(
            "OLLAMA_DEFAULT_MODEL", self.ollama.default_model
        )
        self.ollama.api_url = os.getenv(
            "OLLAMA_API_BASE", self.ollama.api_url
        )
        self.ollama.mcp_url = os.getenv(
            "OLLAMA_MCP_URL", self.ollama.mcp_url
        )
        self.ollama.is_remote = os.getenv("OLLAMA_IS_REMOTE", "false").lower() in ("true", "1", "yes")
        self.ollama.use_gpu = os.getenv("OLLAMA_USE_GPU", "true").lower() in ("true", "1", "yes")

        # Configuración de MCP
        self.use_mcp_tools = os.getenv("USE_MCP_TOOLS", "true").lower() in ("true", "1", "yes")
        self.prefer_direct_mcp = os.getenv("PREFER_DIRECT_MCP", "true").lower() in ("true", "1", "yes")
        
        # Configuración de Neo4j para GraphRAG
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "secretpassword")