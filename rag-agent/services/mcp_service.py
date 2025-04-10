# services/mcp_service.py
import logging
from typing import Dict, List, Optional, Any, Union, cast
import httpx
from fastapi import HTTPException

# Importación de la biblioteca oficial de MCP
try:
    import mcp
    import fastmcp
    from mcp import Context, ContextType, Tool, Client
    from mcp.client import ClientError, ContextNotFoundError
    MCP_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info(f"MCP Python client library loaded successfully. Version: {getattr(mcp, '__version__', 'unknown')}")
except ImportError:
    # Fallback en caso de que la biblioteca no esté disponible
    logger = logging.getLogger(__name__)
    logger.warning("Official MCP Python client library not available. Using HTTP fallback implementation.")
    MCP_AVAILABLE = False

from config.settings import Settings

class MCPService:
    """Servicio para interactuar con Model Context Protocol (MCP) v1.6.0 usando la biblioteca oficial"""

    def __init__(self, settings: Settings):
        """Inicializar servicio con la configuración"""
        self.settings = settings
        self.context_service_url = settings.mcp.context_service_url
        # Versión objetivo de MCP
        self.target_mcp_version = "1.6.0"
        
        # Inicializar cliente MCP oficial si está disponible
        self.mcp_client = None
        self.use_native_client = MCP_AVAILABLE
        
        if self.use_native_client:
            try:
                self.mcp_client = mcp.Client(base_url=f"{self.context_service_url}/api/v1/mcp")
                logger.info(f"MCP native client initialized with base URL: {self.context_service_url}/api/v1/mcp")
            except Exception as e:
                logger.error(f"Error initializing MCP native client: {e}")
                self.use_native_client = False
                
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Realizar una petición a la API del servicio de contexto MCP usando httpx
        (Método de fallback cuando el cliente nativo no está disponible)

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
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=data)
                elif method == "PUT":
                    response = await client.put(url, headers=headers, json=data)
                elif method == "DELETE":
                    response = await client.delete(url, headers=headers, json=data)
                else:
                    raise ValueError(f"Método HTTP no soportado: {method}")
                
                if response.status_code >= 400:
                    error_text = response.text
                    logger.error(f"Error en petición MCP {method} {url}: {response.status_code} - {error_text}")
                    raise HTTPException(status_code=response.status_code, detail=f"Error en MCP: {error_text}")
                
                return response.json()

        except httpx.RequestError as e:
            logger.error(f"Error de cliente en petición MCP {method} {url}: {str(e)}")
            raise HTTPException(status_code=502, detail=f"Error de conexión con MCP: {str(e)}")

    async def get_status(self) -> Dict:
        """
        Obtener estado del servicio MCP

        Returns:
            Información de estado
        """
        if self.use_native_client and self.mcp_client:
            try:
                # Usar método nativo del cliente MCP
                status = await self.mcp_client.get_status()
                return {
                    "name": status.name,
                    "version": status.version,
                    "tools": [t.dict() for t in status.tools] if hasattr(status, 'tools') else [],
                    "contexts_count": getattr(status, 'contexts_count', 0),
                    "active_contexts": getattr(status, 'active_contexts', 0),
                    "client_type": "native"
                }
            except Exception as e:
                logger.error(f"Error using native MCP client for get_status: {e}")
                # Caer en implementación por HTTP en caso de error
        
        # Método tradicional por HTTP
        result = await self._make_request("GET", "mcp/status")
        if isinstance(result, dict):
            result["client_type"] = "http"
        return result

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
        if self.use_native_client and self.mcp_client:
            try:
                # Método nativo para activar contexto
                result = await self.mcp_client.activate_context(context_id)
                return {
                    "id": context_id,
                    "status": "activated",
                    "active": True,
                    "client_type": "native"
                }
            except ContextNotFoundError:
                raise HTTPException(status_code=404, detail=f"Contexto no encontrado: {context_id}")
            except Exception as e:
                logger.error(f"Error using native MCP client for activate_context: {e}")
                # Caer en implementación por HTTP en caso de error
        
        # Método tradicional por HTTP
        result = await self._make_request("POST", f"contexts/{context_id}/activate")
        if isinstance(result, dict):
            result["client_type"] = "http"
        return result

    async def deactivate_context(self, context_id: str) -> Dict:
        """
        Desactivar un contexto MCP

        Args:
            context_id: ID del contexto

        Returns:
            Información de desactivación
        """
        if self.use_native_client and self.mcp_client:
            try:
                # Método nativo para desactivar contexto
                result = await self.mcp_client.deactivate_context(context_id)
                return {
                    "id": context_id,
                    "status": "deactivated",
                    "active": False,
                    "client_type": "native"
                }
            except ContextNotFoundError:
                raise HTTPException(status_code=404, detail=f"Contexto no encontrado: {context_id}")
            except Exception as e:
                logger.error(f"Error using native MCP client for deactivate_context: {e}")
                # Caer en implementación por HTTP en caso de error
        
        # Método tradicional por HTTP
        result = await self._make_request("POST", f"contexts/{context_id}/deactivate")
        if isinstance(result, dict):
            result["client_type"] = "http"
        return result

    async def get_active_contexts(self) -> List[Dict]:
        """
        Obtener lista de contextos activos

        Returns:
            Lista de contextos activos
        """
        if self.use_native_client and self.mcp_client:
            try:
                # Método nativo para obtener contextos activos
                contexts = await self.mcp_client.get_active_contexts()
                return [
                    {
                        "id": ctx.id,
                        "name": ctx.name,
                        "description": ctx.description,
                        "type": ctx.type.name if hasattr(ctx.type, 'name') else str(ctx.type),
                        "metadata": ctx.metadata,
                        "client_type": "native"
                    }
                    for ctx in contexts
                ]
            except Exception as e:
                logger.error(f"Error using native MCP client for get_active_contexts: {e}")
                # Caer en implementación por HTTP en caso de error
        
        # Método tradicional por HTTP
        response = await self._make_request("GET", "mcp/active-contexts")
        if isinstance(response, list):
            for ctx in response:
                if isinstance(ctx, dict):
                    ctx["client_type"] = "http"
        return response

    async def get_context(self, context_id: str) -> Dict:
        """
        Obtener información de un contexto

        Args:
            context_id: ID del contexto

        Returns:
            Información del contexto
        """
        # El cliente nativo no tiene método directo para get_context específico
        # por lo que usamos el método HTTP para todos los casos
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
            
    # Método estándar MCP para guardar información en un contexto
    async def store_text(self, context_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict:
        """
        Almacena texto en un contexto MCP utilizando la herramienta store_document.
        Esta es una implementación estándar según el protocolo MCP.

        Args:
            context_id: ID del contexto donde guardar la información
            text: Texto a almacenar
            metadata: Metadatos opcionales

        Returns:
            Resultado de la operación
        """
        if self.use_native_client and self.mcp_client:
            try:
                # Activar el contexto primero
                await self.activate_context(context_id)
                
                # Usar el método nativo para llamar a la herramienta store_document
                tool_result = await self.mcp_client.call_tool(
                    "store_document",
                    information=text,
                    metadata=metadata or {}
                )
                
                return {
                    "result": tool_result,
                    "context_id": context_id,
                    "success": True,
                    "client_type": "native"
                }
            except Exception as e:
                logger.error(f"Error using native MCP client for store_text: {e}")
                # Caer en implementación por HTTP en caso de error
        
        # Implementación por HTTP
        tool_data = {
            "information": text,
            "metadata": metadata or {}
        }
        
        # Primero activamos el contexto
        await self.activate_context(context_id)
        
        # Luego llamamos a la herramienta store_document
        result = await self._make_request("POST", "mcp/tools/store-document", tool_data)
        
        if isinstance(result, dict):
            result.update({
                "context_id": context_id,
                "success": True,
                "client_type": "http"
            })
        
        return result
        
    # Método estándar MCP para buscar información relevante
    async def find_relevant(self, context_id: str, query: str, limit: int = 5) -> List[Dict]:
        """
        Busca información relevante en un contexto MCP utilizando la herramienta find_relevant.
        Esta es una implementación estándar según el protocolo MCP.

        Args:
            context_id: ID del contexto donde buscar
            query: Consulta para buscar información relevante
            limit: Número máximo de resultados

        Returns:
            Lista de resultados relevantes
        """
        if self.use_native_client and self.mcp_client:
            try:
                # Activar el contexto primero
                await self.activate_context(context_id)
                
                # Usar el método nativo para llamar a la herramienta find_relevant
                tool_results = await self.mcp_client.call_tool(
                    "find_relevant",
                    query=query,
                    limit=limit
                )
                
                # Procesar los resultados que pueden venir en diferentes formatos
                if isinstance(tool_results, list):
                    return [
                        {"text": item, "score": None, "client_type": "native"} 
                        if isinstance(item, str) else 
                        {**item, "client_type": "native"} 
                        for item in tool_results
                    ]
                elif isinstance(tool_results, dict) and "results" in tool_results:
                    return [
                        {**item, "client_type": "native"} 
                        for item in tool_results["results"]
                    ]
                else:
                    return [{"text": str(tool_results), "client_type": "native"}]
                
            except Exception as e:
                logger.error(f"Error using native MCP client for find_relevant: {e}")
                # Caer en implementación por HTTP en caso de error
        
        # Implementación por HTTP
        tool_data = {
            "query": query,
            "limit": limit
        }
        
        # Primero activamos el contexto
        await self.activate_context(context_id)
        
        # Luego llamamos a la herramienta find_relevant
        result = await self._make_request("POST", "mcp/tools/find-relevant", tool_data)
        
        # Procesar los resultados
        if isinstance(result, dict) and "results" in result:
            results = result["results"]
            for item in results:
                if isinstance(item, dict):
                    item["client_type"] = "http"
            return results
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    item["client_type"] = "http"
            return result
        elif isinstance(result, dict) and "result" in result:
            items = result["result"]
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        item["client_type"] = "http"
                return items
        
        # Fallback si no se puede interpretar el resultado
        return [{"text": str(result), "client_type": "http"}]