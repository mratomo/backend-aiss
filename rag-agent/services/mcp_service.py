# services/mcp_service.py
import logging
from typing import Dict, List, Optional, Any, Union

import aiohttp
from fastapi import HTTPException

from config.settings import Settings

logger = logging.getLogger(__name__)

class MCPService:
    """Servicio para interactuar con Model Context Protocol (MCP)"""

    def __init__(self, settings: Settings):
        """Inicializar servicio con la configuración"""
        self.settings = settings
        self.context_service_url = settings.mcp.context_service_url

    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Realizar una petición a la API del servicio de contexto MCP

        Args:
            method: Método HTTP (GET, POST, PUT, DELETE)
            endpoint: Endpoint de la API
            data: Datos para la petición (para POST, PUT)

        Returns:
            Respuesta de la API como diccionario
        """
        url = f"{self.context_service_url}/{endpoint}"
        headers = {"Content-Type": "application/json"}

        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers) as response:
                        if response.status >= 400:
                            error_text = await response.text()
                            logger.error(f"Error en petición MCP {method} {url}: {response.status} - {error_text}")
                            raise HTTPException(status_code=response.status, detail=f"Error en MCP: {error_text}")
                        return await response.json()

                elif method == "POST":
                    async with session.post(url, headers=headers, json=data) as response:
                        if response.status >= 400:
                            error_text = await response.text()
                            logger.error(f"Error en petición MCP {method} {url}: {response.status} - {error_text}")
                            raise HTTPException(status_code=response.status, detail=f"Error en MCP: {error_text}")
                        return await response.json()

                elif method == "PUT":
                    async with session.put(url, headers=headers, json=data) as response:
                        if response.status >= 400:
                            error_text = await response.text()
                            logger.error(f"Error en petición MCP {method} {url}: {response.status} - {error_text}")
                            raise HTTPException(status_code=response.status, detail=f"Error en MCP: {error_text}")
                        return await response.json()

                elif method == "DELETE":
                    async with session.delete(url, headers=headers, json=data) as response:
                        if response.status >= 400:
                            error_text = await response.text()
                            logger.error(f"Error en petición MCP {method} {url}: {response.status} - {error_text}")
                            raise HTTPException(status_code=response.status, detail=f"Error en MCP: {error_text}")
                        return await response.json()

                else:
                    raise ValueError(f"Método HTTP no soportado: {method}")

        except aiohttp.ClientError as e:
            logger.error(f"Error de cliente en petición MCP {method} {url}: {str(e)}")
            raise HTTPException(status_code=502, detail=f"Error de conexión con MCP: {str(e)}")

    async def get_status(self) -> Dict:
        """
        Obtener estado del servicio MCP

        Returns:
            Información de estado
        """
        return await self._make_request("GET", "mcp/status")

    async def get_area(self, area_id: str) -> Dict:
        """
        Obtener información de un área

        Args:
            area_id: ID del área

        Returns:
            Información del área
        """
        return await self._make_request("GET", f"areas/{area_id}")

    async def get_areas(self) -> List[Dict]:
        """
        Obtener lista de áreas

        Returns:
            Lista de áreas
        """
        response = await self._make_request("GET", "areas")
        return response

    async def activate_context(self, context_id: str) -> Dict:
        """
        Activar un contexto MCP

        Args:
            context_id: ID del contexto

        Returns:
            Información de activación
        """
        return await self._make_request("POST", f"contexts/{context_id}/activate")

    async def deactivate_context(self, context_id: str) -> Dict:
        """
        Desactivar un contexto MCP

        Args:
            context_id: ID del contexto

        Returns:
            Información de desactivación
        """
        return await self._make_request("POST", f"contexts/{context_id}/deactivate")

    async def get_active_contexts(self) -> List[Dict]:
        """
        Obtener lista de contextos activos

        Returns:
            Lista de contextos activos
        """
        response = await self._make_request("GET", "mcp/active-contexts")
        return response

    async def get_context(self, context_id: str) -> Dict:
        """
        Obtener información de un contexto

        Args:
            context_id: ID del contexto

        Returns:
            Información del contexto
        """
        return await self._make_request("GET", f"contexts/{context_id}")

    async def activate_area_context(self, area_id: str) -> Dict:
        """
        Activar el contexto asociado a un área

        Args:
            area_id: ID del área

        Returns:
            Información de activación
        """
        # Obtener información del área para encontrar su contexto MCP
        area = await self.get_area(area_id)

        if not area.get("mcp_context_id"):
            raise HTTPException(status_code=404, detail=f"El área {area_id} no tiene contexto MCP asociado")

        # Activar el contexto
        return await self.activate_context(area["mcp_context_id"])

    async def activate_multiple_area_contexts(self, area_ids: List[str]) -> List[Dict]:
        """
        Activar múltiples contextos de áreas

        Args:
            area_ids: Lista de IDs de áreas

        Returns:
            Lista de resultados de activación
        """
        results = []
        for area_id in area_ids:
            try:
                result = await self.activate_area_context(area_id)
                results.append({
                    "area_id": area_id,
                    "status": "success",
                    "result": result
                })
            except Exception as e:
                logger.error(f"Error activating context for area {area_id}: {str(e)}")
                results.append({
                    "area_id": area_id,
                    "status": "error",
                    "error": str(e)
                })

        return results

    async def get_personal_context_id(self, user_id: str) -> Optional[str]:
        """
        Obtener el ID del contexto personal de un usuario

        Args:
            user_id: ID del usuario

        Returns:
            ID del contexto personal o None si no existe
        """
        try:
            # En un sistema real, aquí se buscaría el contexto personal en la BD
            # Por simplicidad, seguimos el formato "personal_{user_id}"
            # Verificamos primero si existe en el servicio de contexto
            personal_context_id = f"personal_{user_id}"

            try:
                # Intentar obtener el contexto para verificar existencia
                context = await self.get_context(personal_context_id)
                return personal_context_id if context else None
            except HTTPException as e:
                if e.status_code == 404:
                    return None
                raise

        except Exception as e:
            logger.error(f"Error retrieving personal context for user {user_id}: {e}")
            return None

    async def get_area_system_prompt(self, area_id: str) -> Optional[str]:
        """
        Obtener el prompt de sistema para un área específica

        Args:
            area_id: ID del área

        Returns:
            Prompt de sistema o None si no existe
        """
        try:
            # Ruta específica para obtener el system prompt del área
            endpoint = f"areas/{area_id}/system-prompt"
            response = await self._make_request("GET", endpoint)

            # Extraer y devolver prompt del sistema, si existe
            if response and "system_prompt" in response:
                return response["system_prompt"]

            return None
        except Exception as e:
            logger.error(f"Error retrieving system prompt for area {area_id}: {e}")
            return None