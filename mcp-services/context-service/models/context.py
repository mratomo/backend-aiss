# models/context.py
from datetime import datetime
from typing import Dict, List, Optional, Union

from bson import ObjectId
from pydantic import BaseModel, Field

# Corrección: Importar PyObjectId del módulo correcto

from models.common import PyObjectId

# Modelo para crear un contexto MCP
class ContextCreate(BaseModel):
    """Solicitud para generar un embedding"""
    name: str = Field(..., description="Nombre del contexto")
    description: str = Field(..., description="Descripción del contexto")
    area_id: Optional[str] = Field(None, description="ID del área asociada")
    owner_id: Optional[str] = Field(None, description="ID del propietario")
    is_personal: bool = Field(False, description="Indica si es un contexto personal")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Metadatos adicionales")


# Modelo para actualizar un contexto MCP
class ContextUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nuevo nombre del contexto")
    description: Optional[str] = Field(None, description="Nueva descripción del contexto")
    metadata: Optional[Dict[str, str]] = Field(None, description="Nuevos metadatos")


# Modelo para representar un contexto en la base de datos
class Context(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    context_id: str = Field(..., description="ID del contexto en MCP")
    name: str
    description: str
    area_id: Optional[str] = None
    owner_id: Optional[str] = None
    is_personal: bool = False
    metadata: Dict[str, str] = Field(default_factory=dict)
    is_active: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_activated: Optional[datetime] = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
        "json_schema_extra": {
            "example": {
                "context_id": "ctx_123456789",
                "name": "Inteligencia Artificial",
                "description": "Contexto sobre IA, aprendizaje automático y redes neuronales",
                "area_id": "5f8a12e65d4b1e2a3c4b5678",
                "is_personal": False,
                "metadata": {"source": "manual", "level": "advanced"},
                "is_active": True,
                "last_activated": "2023-01-15T12:30:45.123Z"
            }
        }
    }


# Modelo para la respuesta de contexto
class ContextResponse(BaseModel):
    id: str
    context_id: str
    name: str
    description: str
    area_id: Optional[str] = None
    owner_id: Optional[str] = None
    is_personal: bool
    metadata: Dict[str, str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_activated: Optional[datetime] = None

    @classmethod
    def from_db_model(cls, context: Context) -> "ContextResponse":
        return cls(
            id=str(context.id),
            context_id=context.context_id,
            name=context.name,
            description=context.description,
            area_id=context.area_id,
            owner_id=context.owner_id,
            is_personal=context.is_personal,
            metadata=context.metadata,
            is_active=context.is_active,
            created_at=context.created_at,
            updated_at=context.updated_at,
            last_activated=context.last_activated
        )