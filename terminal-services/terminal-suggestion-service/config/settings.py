import os
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class LLMSettings(BaseModel):
    provider: str = "openai"  # openai, anthropic, azure, etc.
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.9
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None

class Settings(BaseSettings):
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8093
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    
    # Service URLs
    CONTEXT_AGGREGATOR_URL: str = "http://terminal-context-aggregator:8092"
    MCP_SERVICE_URL: str = "http://context-service:8082"
    LLM_SERVICE_URL: str = "http://rag-agent:8080/api/v1/llm"
    
    # LLM settings
    LLM: LLMSettings = LLMSettings()
    
    # Application settings
    MAX_SUGGESTIONS: int = 5
    SUGGESTION_TIMEOUT_SECONDS: float = 2.0  # Maximum time to wait for suggestions
    CACHE_EXPIRY_MINUTES: int = 30  # How long to cache suggestions
    
    # Security
    API_KEY: Optional[str] = None
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = []
    
    # Suggestion promptbook paths
    PROMPT_TEMPLATES_DIR: str = "prompts"
    
    model_config = {
        "env_file": ".env"
    }

# Create global settings object
settings = Settings()

# Set ALLOWED_ORIGINS from environment variable or use defaults for development
origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
if origins_env:
    settings.ALLOWED_ORIGINS = origins_env.split(",")
else:
    # Default to secure development origins only
    settings.ALLOWED_ORIGINS = ["http://localhost:3000", "https://app.domain.com"]
    
# Validate JWT_SECRET
if not settings.JWT_SECRET:
    raise ValueError("JWT_SECRET environment variable is required")