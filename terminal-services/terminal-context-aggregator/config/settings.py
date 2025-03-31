import os
from typing import Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8092
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    
    # Service URLs
    EMBEDDING_SERVICE_URL: str = "http://embedding-service:8081"
    MCP_SERVICE_URL: str = "http://context-service:8082"
    SUGGESTION_SERVICE_URL: str = "http://terminal-suggestion-service:8093"
    
    # Application settings
    MAX_CONTEXT_TOKENS: int = 4096
    MAX_TERMINAL_OUTPUT_SIZE: int = 100000  # Maximum size in characters for terminal output
    CONTEXT_EXPIRY_MINUTES: int = 60  # How long to keep context in memory
    SUGGESTION_TIMEOUT_SECONDS: float = 5.0  # Increased timeout for suggestion service
    
    # MongoDB settings
    MONGODB_URI: str = "mongodb://mongodb:27017"
    MONGODB_DATABASE: str = "terminal_sessions"
    
    # Security
    API_KEY: Optional[str] = None
    JWT_SECRET: str = "replace-in-production"
    JWT_ALGORITHM: str = "HS256"
    
    class Config:
        env_file = ".env"

# Create global settings object
settings = Settings()
