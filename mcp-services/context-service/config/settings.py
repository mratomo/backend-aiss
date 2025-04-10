# config/settings.py
import os
import json
from typing import List, Optional, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from pydantic.fields import FieldInfo


class MCPSettings(BaseSettings):
    """Configuración específica para MCP"""
    server_name: str = Field(default="MCP Knowledge Server")
    server_version: str = Field(default="1.6.0")  # Actualizado a la versión compatible más reciente
    api_route: str = Field(default="/mcp")
    sse_route: str = Field(default="/mcp/sse")
    default_system_prompt: str = Field(
        default="Eres un asistente de inteligencia artificial especializado en responder preguntas "
                "basadas en la información proporcionada. Utiliza SOLO la información en el contexto "
                "para responder. Si la información no está en el contexto, indica que no tienes "
                "esa información. Proporciona respuestas detalladas y bien estructuradas."
    )
    
    model_config = {
        "extra": "ignore"
    }


class Settings(BaseSettings):
    """Configuraciones para el servicio de contexto MCP"""

    # Configuración del servidor
    environment: str = Field(default="development")
    port: int = Field(default=8083)
    cors_allowed_origins: List[str] = Field(default=["*"])

    # Configuración de MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="mcp_knowledge_system")
    
    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, v):
        """Preprocesar el campo cors_allowed_origins para asegurar una lista de strings"""
        if isinstance(v, str):
            if v == "*":
                return ["*"]
            if "," in v:
                return v.split(",")
            return [v]
        return v

    # Configuración de MCP
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    mcp_api_url: str = Field(default="http://localhost:8085/api/v1/mcp")
    mcp_api_key: str = Field(default="")

    # Configuración para integración con otros servicios
    embedding_service_url: str = Field(default="http://embedding-service:8084")
    embedding_service_timeout: float = Field(default=30.0)
    allow_degraded_mode: bool = Field(default=True)
    
    # Configuración de modelo embedding común con Embedding Service
    embedding_model: str = Field(default="nomic-ai/nomic-embed-text-v1.5-fp16")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False
    }

    def __init__(self, **kwargs):
        """Inicializar configuraciones con valores de variables de entorno"""
        # Procesamos primero la configuración de CORS para evitar errores de parsing JSON
        cors_origins = os.getenv("CORS_ALLOWED_ORIGINS")
        if cors_origins:
            try:
                # Intentar parsear como JSON primero
                origins_list = json.loads(cors_origins)
                kwargs["cors_allowed_origins"] = origins_list
            except json.JSONDecodeError:
                # Si no es JSON, dividir por comas
                if "," in cors_origins:
                    kwargs["cors_allowed_origins"] = cors_origins.split(",")
                else:
                    kwargs["cors_allowed_origins"] = [cors_origins]
        
        # Inicializar con los valores procesados
        super().__init__(**kwargs)

        # Priorizar variables de entorno sobre valores por defecto
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        self.port = int(os.getenv("PORT", str(self.port)))

        # Configuración de MongoDB
        self.mongodb_uri = os.getenv("MONGODB_URI", self.mongodb_uri)
        self.mongodb_database = os.getenv("MONGODB_DATABASE", self.mongodb_database)

        # Configuración de MCP
        self.mcp_api_url = os.getenv("MCP_API_URL", self.mcp_api_url)
        self.mcp_api_key = os.getenv("MCP_API_KEY", self.mcp_api_key)

        # Configuración del servidor MCP
        self.mcp.server_name = os.getenv("MCP_SERVER_NAME", self.mcp.server_name)
        self.mcp.server_version = os.getenv("MCP_SERVER_VERSION", self.mcp.server_version)
        self.mcp.api_route = os.getenv("MCP_API_ROUTE", self.mcp.api_route)
        self.mcp.sse_route = os.getenv("MCP_SSE_ROUTE", self.mcp.sse_route)
        self.mcp.default_system_prompt = os.getenv("MCP_DEFAULT_SYSTEM_PROMPT", self.mcp.default_system_prompt)

        # Configuración de integración con otros servicios
        self.embedding_service_url = os.getenv("EMBEDDING_SERVICE_URL", self.embedding_service_url)