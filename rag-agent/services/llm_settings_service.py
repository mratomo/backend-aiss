# rag-agent/services/llm_settings_service.py
import logging
from datetime import datetime
from typing import Dict, Optional, Any

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from config.settings import Settings
from models.llm_settings import LLMSettingsDB, LLMSettingsResponse

logger = logging.getLogger(__name__)

class LLMSettingsService:
    """Servicio para gestionar configuraciones globales de LLM"""

    def __init__(self, database: AsyncIOMotorDatabase, settings: Settings):
        """Inicializar servicio con la base de datos y configuración"""
        self.db = database
        self.collection = database.llm_settings
        self.settings = settings
        self.cached_settings = None

    async def initialize(self):
        """Inicializar configuraciones, garantizando que existe un documento de configuración"""
        # Verificar si existe configuración en la base de datos
        settings_doc = await self.collection.find_one({})

        if not settings_doc:
            # Crear configuración inicial basada en los valores por defecto
            initial_settings = {
                "default_system_prompt": self.settings.mcp.default_system_prompt,
                "last_updated": datetime.utcnow()
            }

            await self.collection.insert_one(initial_settings)
            logger.info("Created initial LLM settings document")

            self.cached_settings = LLMSettingsDB(**initial_settings)
        else:
            self.cached_settings = LLMSettingsDB(**settings_doc)
            logger.info("Loaded existing LLM settings document")

    async def get_settings(self) -> LLMSettingsDB:
        """
        Obtener configuraciones actuales

        Returns:
            Configuraciones actuales
        """
        if not self.cached_settings:
            await self.initialize()

        return self.cached_settings

    async def update_system_prompt(self, system_prompt: str, user_id: Optional[str] = None) -> LLMSettingsDB:
        """
        Actualizar el prompt de sistema por defecto

        Args:
            system_prompt: Nuevo prompt de sistema
            user_id: ID del usuario que realiza la actualización (opcional)

        Returns:
            Configuraciones actualizadas
        """
        if not self.cached_settings:
            await self.initialize()

        # Actualizar en la base de datos
        now = datetime.utcnow()
        update_data = {
            "default_system_prompt": system_prompt,
            "last_updated": now
        }

        if user_id:
            update_data["updated_by"] = user_id

        result = await self.collection.update_one(
            {},  # Actualizar el primer documento (debería ser el único)
            {"$set": update_data},
            upsert=True  # Crear si no existe
        )

        # Actualizar el valor en la configuración actual también
        self.settings.mcp.default_system_prompt = system_prompt

        # Actualizar caché
        settings_doc = await self.collection.find_one({})
        self.cached_settings = LLMSettingsDB(**settings_doc)

        return self.cached_settings

    async def reset_to_defaults(self, user_id: Optional[str] = None) -> LLMSettingsDB:
        """
        Restablecer configuraciones a valores predeterminados

        Args:
            user_id: ID del usuario que realiza el restablecimiento (opcional)

        Returns:
            Configuraciones restablecidas
        """
        # Valores por defecto desde la configuración inicial
        return await self.update_system_prompt(
            system_prompt=Settings().mcp.default_system_prompt,
            user_id=user_id
        )