from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Any

from bson import ObjectId
from pydantic import BaseModel, Field

# Clase auxiliar para manejar ObjectId en modelos Pydantic
class PyObjectId(str):
    """
    Una clase personalizada para convertir ObjectIds de MongoDB a/desde strings.
    Esta implementación es compatible con Pydantic v2.
    """
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
        
    @classmethod
    def validate(cls, v):
        if not isinstance(v, (str, ObjectId)):
            raise TypeError("ObjectId required")
        
        if isinstance(v, str):
            if not ObjectId.is_valid(v):
                raise ValueError("Invalid ObjectId format")
            return str(v)
            
        return str(v)
    
    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")
    
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema, **kwargs):
        field_schema.update(type="string")
        return field_schema


class LLMProviderType(str, Enum):
    """Tipos de proveedores LLM soportados"""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    GOOGLE = "google"


class LLMProviderCreate(BaseModel):
    """Modelo para crear un proveedor LLM"""
    name: str = Field(..., description="Nombre descriptivo del proveedor")
    type: LLMProviderType = Field(..., description="Tipo de proveedor")
    api_key: Optional[str] = Field(None, description="API key (para OpenAI, Azure, Anthropic)")
    api_endpoint: Optional[str] = Field(None, description="Endpoint de API (para Azure, Ollama)")
    model: str = Field(..., description="Modelo a utilizar")
    default: bool = Field(False, description="Si es el proveedor por defecto")
    temperature: float = Field(0.0, ge=0.0, le=1.0, description="Temperatura para generación")
    max_tokens: int = Field(4096, ge=1, description="Número máximo de tokens")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadatos adicionales")
    use_gpu: bool = Field(True, description="Utilizar GPU para aceleración si está disponible")


class LLMProviderUpdate(BaseModel):
    """Modelo para actualizar un proveedor LLM"""
    name: Optional[str] = None
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None
    model: Optional[str] = None
    default: Optional[bool] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    use_gpu: Optional[bool] = None


class LLMProvider(BaseModel):
    """Modelo para representar un proveedor LLM en la base de datos"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    type: LLMProviderType
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None
    model: str
    default: bool = False
    temperature: float
    max_tokens: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    use_gpu: bool = Field(True, description="Utilizar GPU para aceleración si está disponible")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }