"""
Implementación del método para obtener el LLM principal de un área de conocimiento.
Este archivo debe ser incluido en el servicio LLM principal.
"""

import logging
import aiohttp
from typing import Optional

# Usar el mismo logger que el servicio principal
logger = logging.getLogger("llm_service")

async def get_area_primary_llm(self, area_id: str, context_service_url: str) -> Optional[str]:
    """
    Obtener el ID del proveedor LLM primario de un área de conocimiento.
    
    Args:
        area_id: ID del área de conocimiento
        context_service_url: URL base del servicio de contexto
        
    Returns:
        ID del proveedor LLM principal o None si no está configurado
    """
    try:
        # Consultamos el servicio de contexto para obtener el área
        async with aiohttp.ClientSession() as session:
            url = f"{context_service_url}/areas/{area_id}/primary-llm"
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Error consultando LLM primario del área: {response.status}")
                    return None
                
                data = await response.json()
                return data.get('primary_llm_provider_id')
    except Exception as e:
        logger.warning(f"Error obteniendo LLM primario del área {area_id}: {e}")
        return None