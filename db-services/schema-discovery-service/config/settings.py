# config/settings.py
import os
from typing import Dict, List, Optional, Union, Any
from pydantic_settings import BaseSettings
from pydantic import Field

class SchemaSettings(BaseSettings):
    """Configuración para descubrimiento de esquemas"""
    # Tiempo máximo para obtener esquemas en segundos
    schema_discovery_timeout: int = Field(default=60)
    
    # Número máximo de tablas a muestrear para inferencia
    max_tables_for_sample: int = Field(default=20)
    
    # Número máximo de filas a muestrear por tabla
    max_rows_per_table: int = Field(default=100)
    
    # Umbral para detectar datos sensibles
    sensitive_data_threshold: float = Field(default=0.8)
    
    # Opciones para vectorización de esquemas
    schema_vector_options: Dict[str, Any] = Field(default={
        "include_column_names": True,
        "include_column_types": True,
        "include_column_descriptions": True,
        "include_sample_data": True,
        "include_foreign_keys": True
    })

class MCPSettings(BaseSettings):
    """Configuración para integración con Model Context Protocol"""
    # URL del servicio MCP
    service_url: str = Field(default="http://context-service:8083")
    
    # Configuraciones MCP
    create_db_contexts: bool = Field(default=True)  # Crear contextos MCP para bases de datos
    store_schemas: bool = Field(default=True)       # Almacenar esquemas descubiertos en MCP
    
class Settings(BaseSettings):
    """Configuraciones para el servicio de descubrimiento de esquemas"""
    # Configuración del servidor
    environment: str = Field(default="development")
    port: int = Field(default=8087)
    cors_allowed_origins: List[str] = Field(default=["*"])
    
    # URL de servicio de conexiones a BD
    db_connection_url: str = Field(default="http://db-connection-service:8086")
    db_connection_service_url: str = Field(default="http://db-connection-service:8086")  # Alias para compatibilidad
    
    # URL de servicio de embedding
    embedding_service_url: str = Field(default="http://embedding-service:8084")
    
    # Configuración de MCP (Model Context Protocol)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    mcp_service_url: str = Field(default="http://context-service:8083")  # Para compatibilidad
    
    # Configuración de Weaviate
    weaviate_url: str = Field(default="http://weaviate:8080")
    weaviate_api_key: Optional[str] = Field(default=None)
    vector_db: str = Field(default="weaviate")  # Tipo de base de datos vectorial a usar
    
    # Configuración de descubrimiento de esquemas
    schema: SchemaSettings = Field(default_factory=SchemaSettings)
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False
    }
    
    # Configuración de Neo4j para GraphRAG
    neo4j_uri: str = Field(default="bolt://neo4j:7687")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="secretpassword")
    
    def __init__(self, **kwargs):
        """Inicializar configuraciones con valores de variables de entorno"""
        super().__init__(**kwargs)
        
        # Priorizar variables de entorno sobre valores por defecto
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        self.port = int(os.getenv("PORT", str(self.port)))
        
        # Configuración de CORS
        cors_origins = os.getenv("CORS_ALLOWED_ORIGINS")
        if cors_origins:
            # Manejar tanto formato JSON como separado por comas
            if cors_origins.startswith("["):
                try:
                    import json
                    self.cors_allowed_origins = json.loads(cors_origins)
                except:
                    self.cors_allowed_origins = cors_origins.split(",")
            else:
                self.cors_allowed_origins = cors_origins.split(",")
        
        # URLs de servicios
        self.db_connection_url = os.getenv("DB_CONNECTION_URL", self.db_connection_url)
        self.embedding_service_url = os.getenv("EMBEDDING_SERVICE_URL", self.embedding_service_url)
        
        # Configuración MCP
        mcp_service_url = os.getenv("MCP_SERVICE_URL")
        if mcp_service_url:
            self.mcp_service_url = mcp_service_url
            self.mcp.service_url = mcp_service_url
        
        create_db_contexts = os.getenv("MCP_CREATE_DB_CONTEXTS")
        if create_db_contexts:
            self.mcp.create_db_contexts = create_db_contexts.lower() in ("true", "1", "yes")
            
        store_schemas = os.getenv("MCP_STORE_SCHEMAS")
        if store_schemas:
            self.mcp.store_schemas = store_schemas.lower() in ("true", "1", "yes")
        
        # Configuración de Weaviate
        self.weaviate_url = os.getenv("WEAVIATE_URL", self.weaviate_url)
        self.weaviate_api_key = os.getenv("WEAVIATE_API_KEY", self.weaviate_api_key)
        self.vector_db = os.getenv("VECTOR_DB", self.vector_db)
        
        # Configuración de Neo4j
        self.neo4j_uri = os.getenv("NEO4J_URI", self.neo4j_uri)
        self.neo4j_username = os.getenv("NEO4J_USERNAME", self.neo4j_username)
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", self.neo4j_password)
        
        # Configuración de descubrimiento de esquemas
        timeout = os.getenv("SCHEMA_DISCOVERY_TIMEOUT")
        if timeout:
            self.schema.schema_discovery_timeout = int(timeout)
        
        max_tables = os.getenv("MAX_TABLES_FOR_SAMPLE")
        if max_tables:
            self.schema.max_tables_for_sample = int(max_tables)
        
        max_rows = os.getenv("MAX_ROWS_PER_TABLE")
        if max_rows:
            self.schema.max_rows_per_table = int(max_rows)