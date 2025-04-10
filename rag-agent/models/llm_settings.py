# rag-agent/models/llm_settings.py
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from pydantic import BaseModel, Field

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

class GlobalSystemPromptUpdate(BaseModel):
    """Modelo para actualizar el prompt de sistema global"""
    system_prompt: str = Field(..., description="Nuevo prompt de sistema para usar con LLMs")

class ProviderSystemPromptUpdate(BaseModel):
    """Modelo para actualizar el prompt de sistema de un proveedor específico"""
    system_prompt: str = Field(..., description="Nuevo prompt de sistema para el proveedor")

class LLMAdvancedSettings(BaseModel):
    """Configuración avanzada para un proveedor LLM"""
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Parámetro top_p para muestreo")
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0, description="Penalty para frecuencia de tokens")
    presence_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0, description="Penalty para presencia de tokens")
    stop_sequences: Optional[List[str]] = Field(None, description="Secuencias para detener la generación")
    max_retries: Optional[int] = Field(None, ge=0, le=5, description="Número máximo de reintentos en caso de error")

class LLMSettingsDB(BaseModel):
    """Modelo para configuraciones de LLM en la base de datos"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    default_system_prompt: str = Field(..., description="Prompt de sistema predeterminado")
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    updated_by: Optional[str] = Field(None, description="ID del usuario que realizó la última actualización")

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }

class LLMSettingsResponse(BaseModel):
    """Respuesta con configuraciones de LLM"""
    default_system_prompt: str
    last_updated: datetime
    updated_by: Optional[str] = None

    @classmethod
    def from_db_model(cls, settings: LLMSettingsDB) -> "LLMSettingsResponse":
        return cls(
            default_system_prompt=settings.default_system_prompt,
            last_updated=settings.last_updated,
            updated_by=settings.updated_by
        )