# models/area.py
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

from models.common import PyObjectId


# Modelo para crear un área de conocimiento
class AreaCreate(BaseModel):
    name: str = Field(..., description="Nombre del área de conocimiento")
    description: str = Field(..., description="Descripción del área")
    icon: Optional[str] = Field(None, description="Ícono para representar el área")
    color: Optional[str] = Field(None, description="Color asociado al área")
    tags: List[str] = Field(default_factory=list, description="Etiquetas asociadas al área")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Metadatos adicionales")
    primary_llm_provider_id: Optional[str] = Field(None, description="ID del proveedor LLM principal para esta área")


# Modelo para actualizar un área de conocimiento
class AreaUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nuevo nombre del área")
    description: Optional[str] = Field(None, description="Nueva descripción del área")
    icon: Optional[str] = Field(None, description="Nuevo ícono para el área")
    color: Optional[str] = Field(None, description="Nuevo color para el área")
    tags: Optional[List[str]] = Field(None, description="Nuevas etiquetas")
    metadata: Optional[Dict[str, str]] = Field(None, description="Nuevos metadatos")
    active: Optional[bool] = Field(None, description="Estado de activación del área")
    primary_llm_provider_id: Optional[str] = Field(None, description="ID del proveedor LLM principal para esta área")


# Modelo para representar un área en la base de datos
class Area(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: str
    icon: Optional[str] = None
    color: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    mcp_context_id: Optional[str] = None
    primary_llm_provider_id: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "name": "Inteligencia Artificial",
                "description": "Conocimiento sobre IA, aprendizaje automático y redes neuronales",
                "icon": "brain",
                "color": "#3498DB",
                "tags": ["IA", "Machine Learning", "Deep Learning"],
                "metadata": {"source": "manual", "level": "advanced"},
                "mcp_context_id": "ctx_123456789",
                "primary_llm_provider_id": "llm_provider_openai_123",
                "active": True
            }
        }


# Modelo para la respuesta de área
class AreaResponse(BaseModel):
    id: str
    name: str
    description: str
    icon: Optional[str] = None
    color: Optional[str] = None
    tags: List[str]
    metadata: Dict[str, str]
    mcp_context_id: Optional[str] = None
    primary_llm_provider_id: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_model(cls, area: Area) -> "AreaResponse":
        return cls(
            id=str(area.id),
            name=area.name,
            description=area.description,
            icon=area.icon,
            color=area.color,
            tags=area.tags,
            metadata=area.metadata,
            mcp_context_id=area.mcp_context_id,
            primary_llm_provider_id=area.primary_llm_provider_id,
            active=area.active,
            created_at=area.created_at,
            updated_at=area.updated_at
        )