# mcp-services/context-service/models/system_prompt.py
from pydantic import BaseModel, Field

class AreaSystemPromptUpdate(BaseModel):
    """Modelo para actualizar el prompt de sistema de un área"""
    system_prompt: str = Field(..., description="Nuevo prompt de sistema para el área")