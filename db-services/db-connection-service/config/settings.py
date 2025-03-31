# config/settings.py
import os
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseSettings, Field

class DatabaseConnectionSettings(BaseSettings):
    """Configuración de conexiones a bases de datos"""
    # Tiempo máximo de conexión en segundos
    connection_timeout: int = Field(default=10)
    
    # Tiempo máximo de consulta en segundos (valor por defecto)
    query_timeout: int = Field(default=30)
    
    # Cantidad máxima de registros permitidos (valor por defecto)
    max_result_size: int = Field(default=1000)
    
    # Encriptación para credenciales
    encryption_key: str = Field(default="")
    
    # Operaciones permitidas por tipo de BD
    allowed_operations: Dict[str, List[str]] = Field(default={
        "postgresql": ["SELECT", "SHOW", "DESCRIBE", "EXPLAIN"],
        "mysql": ["SELECT", "SHOW", "DESCRIBE", "EXPLAIN"],
        "mongodb": ["FIND", "AGGREGATE", "COUNT", "DISTINCT"],
        "sqlserver": ["SELECT", "EXEC SP_HELP"],
        "elasticsearch": ["SEARCH", "GET", "COUNT", "EXPLAIN"],
        "influxdb": ["SELECT", "SHOW"]
    })

class MongoDBSettings(BaseSettings):
    """Configuración de MongoDB"""
    uri: str = Field(default="mongodb://mongodb:27017")
    database: str = Field(default="mcp_knowledge_system")
    connections_collection: str = Field(default="db_connections")
    agents_collection: str = Field(default="db_agents")
    agent_connections_collection: str = Field(default="db_agent_connections")
    query_history_collection: str = Field(default="db_queries")

class SecuritySettings(BaseSettings):
    """Configuración de seguridad"""
    # Lista de SQL keywords que requieren verificación adicional
    sensitive_keywords: List[str] = Field(default=[
        "DELETE", "DROP", "ALTER", "TRUNCATE", "GRANT", "REVOKE", 
        "INSERT", "UPDATE", "CREATE", "EXEC", "sp_", "xp_"
    ])
    
    # Lista de patrones regex para detectar inyecciones SQL
    injection_patterns: List[str] = Field(default=[
        r"--\s*$", r";\s*$", r"/\*.*\*/", r"UNION\s+ALL\s+SELECT"
    ])
    
    # Hash salt para valores sensibles
    hash_salt: str = Field(default="")

class Settings(BaseSettings):
    """Configuraciones para el servicio de conexión a bases de datos"""
    # Configuración del servidor
    environment: str = Field(default="development")
    port: int = Field(default=8086)
    cors_allowed_origins: List[str] = Field(default=["*"])
    
    # MongoDB
    mongodb: MongoDBSettings = Field(default_factory=MongoDBSettings)
    
    # Configuración de seguridad
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    
    # Configuración de conexiones
    db_connections: DatabaseConnectionSettings = Field(default_factory=DatabaseConnectionSettings)
    
    # Comunicación con otros servicios
    schema_discovery_url: str = Field(default="http://schema-discovery-service:8087")
    embedding_service_url: str = Field(default="http://embedding-service:8084")
    
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
        
        # MongoDB
        self.mongodb.uri = os.getenv("MONGODB_URI", self.mongodb.uri)
        self.mongodb.database = os.getenv("MONGODB_DATABASE", self.mongodb.database)
        
        # Seguridad
        self.db_connections.encryption_key = os.getenv("DB_ENCRYPTION_KEY", self.db_connections.encryption_key)
        self.security.hash_salt = os.getenv("HASH_SALT", self.security.hash_salt)
        
        # URLs de servicios
        self.schema_discovery_url = os.getenv("SCHEMA_DISCOVERY_URL", self.schema_discovery_url)
        self.embedding_service_url = os.getenv("EMBEDDING_SERVICE_URL", self.embedding_service_url)