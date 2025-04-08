import os
from typing import Optional, List
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
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = []
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set ALLOWED_ORIGINS from environment variable or use defaults for development
        origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
        if origins_env:
            self.ALLOWED_ORIGINS = origins_env.split(",")
        else:
            # Default to secure development origins only
            self.ALLOWED_ORIGINS = ["http://localhost:3000", "https://app.domain.com"]
            
        # Validate JWT_SECRET
        if not self.JWT_SECRET:
            raise ValueError("JWT_SECRET environment variable is required")
    
    class Config:
        env_file = ".env"

# Create global settings object
settings = Settings()
