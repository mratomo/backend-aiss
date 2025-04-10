"""
Servicio para integración con Model Context Protocol (MCP)

Este servicio permite almacenar y recuperar información sobre esquemas de
bases de datos mediante el protocolo MCP, facilitando la integración con 
el resto del sistema.
"""

import json
import logging
import httpx
from typing import Dict, List, Optional, Any, Union, cast

# Importación de la biblioteca oficial de MCP
try:
    import mcp
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

class MCPService:
    """Servicio para interactuar con Model Context Protocol para esquemas de bases de datos"""

    def __init__(self, mcp_service_url: str):
        """
        Inicializar servicio con la URL del servicio MCP
        
        Args:
            mcp_service_url: URL del servicio MCP (context-service)
        """
        self.mcp_service_url = mcp_service_url
        
        # Inicializar cliente MCP oficial si está disponible
        self.mcp_client = None
        self.use_native_client = MCP_AVAILABLE
        
        if self.use_native_client:
            try:
                self.mcp_client = mcp.Client(base_url=f"{self.mcp_service_url}/api/v1/mcp")
                logger.info(f"MCP native client initialized with base URL: {self.mcp_service_url}/api/v1/mcp")
            except Exception as e:
                logger.error(f"Error initializing MCP native client: {e}")
                self.use_native_client = False
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Realizar una petición a la API del servicio de contexto MCP usando httpx
        (Método de fallback cuando el cliente nativo no está disponible)
        """
        url = f"{self.mcp_service_url}/{endpoint}"
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
                    return {"error": error_text, "status_code": response.status_code}
                
                return response.json()

        except httpx.RequestError as e:
            logger.error(f"Error de cliente en petición MCP {method} {url}: {str(e)}")
            return {"error": str(e), "status_code": 502}

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
        return response if isinstance(response, list) else []
    
    async def store_schema_in_mcp(self, schema_description: str, connection_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Almacena la descripción de un esquema de base de datos en MCP
        utilizando la herramienta store_document.
        
        Args:
            schema_description: Descripción textual del esquema
            connection_id: ID de la conexión a la base de datos
            metadata: Metadatos adicionales sobre el esquema
            
        Returns:
            Resultado de la operación
        """
        # Enriquecer metadatos con información relevante
        enriched_metadata = {
            **metadata,
            "connection_id": connection_id,
            "document_type": "database_schema",
            "source": "schema-discovery-service"
        }
        
        # 1. Buscar un contexto relacionado con la base de datos, si existe
        db_context_id = f"db_{connection_id}"
        try:
            if self.use_native_client and self.mcp_client:
                # Usar cliente nativo
                try:
                    # Intentar activar el contexto específico para esta base de datos
                    await self.mcp_client.activate_context(db_context_id)
                    logger.info(f"Activated existing database context: {db_context_id}")
                except ContextNotFoundError:
                    # Si no existe, buscar un contexto general para bases de datos
                    await self.activate_or_create_db_context()
                    
                # Llamar a la herramienta store_document
                result = await self.mcp_client.call_tool(
                    "store_document",
                    information=schema_description,
                    metadata=enriched_metadata
                )
                
                return {
                    "success": True,
                    "result": result,
                    "context_id": db_context_id,
                    "client_type": "native"
                }
            else:
                # Usar HTTP fallback
                # Primero intentar activar un contexto relevante
                try:
                    await self._make_request("POST", f"contexts/{db_context_id}/activate")
                except Exception:
                    # Si falla, crear un nuevo contexto genérico para bases de datos
                    await self.activate_or_create_db_context()
                    
                # Almacenar el documento usando la herramienta store_document
                tool_data = {
                    "information": schema_description,
                    "metadata": enriched_metadata
                }
                
                result = await self._make_request("POST", "mcp/tools/store-document", tool_data)
                if "error" in result:
                    return {
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                        "client_type": "http"
                    }
                
                return {
                    "success": True,
                    "result": result,
                    "client_type": "http"
                }
        except Exception as e:
            logger.error(f"Error storing schema in MCP: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def find_similar_schemas(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Busca esquemas de base de datos similares utilizando MCP
        
        Args:
            query: Consulta para buscar esquemas similares
            limit: Número máximo de resultados
            
        Returns:
            Lista de esquemas similares encontrados
        """
        if self.use_native_client and self.mcp_client:
            try:
                # Activar primero un contexto de bases de datos
                await self.activate_or_create_db_context()
                
                # Usar el método nativo para llamar a find_relevant
                result = await self.mcp_client.call_tool(
                    "find_relevant",
                    query=query,
                    embedding_type="general",
                    limit=limit
                )
                
                # Procesar resultados
                if isinstance(result, list):
                    return [
                        {"text": item, "score": None, "client_type": "native"} 
                        if isinstance(item, str) else 
                        {**item, "client_type": "native"} 
                        for item in result
                    ]
                elif isinstance(result, dict) and "results" in result:
                    return [
                        {**item, "client_type": "native"} 
                        for item in result["results"]
                    ]
                else:
                    return [{"text": str(result), "client_type": "native"}]
            except Exception as e:
                logger.error(f"Error using native MCP client for find_similar_schemas: {e}")
                # Caer en fallback HTTP
        
        # Método HTTP
        # Primero activar un contexto de bases de datos
        await self.activate_or_create_db_context()
        
        # Luego hacer la consulta
        tool_data = {
            "query": query,
            "embedding_type": "general",
            "limit": limit
        }
        
        result = await self._make_request("POST", "mcp/tools/find-relevant", tool_data)
        
        # Procesar los resultados
        if isinstance(result, dict) and "results" in result:
            results = result["results"]
            return results if isinstance(results, list) else []
        elif isinstance(result, list):
            return result
        elif isinstance(result, dict) and "result" in result:
            items = result["result"]
            return items if isinstance(items, list) else []
        
        return []
    
    async def activate_or_create_db_context(self) -> Dict[str, Any]:
        """
        Activa un contexto para bases de datos o lo crea si no existe
        
        Returns:
            Información sobre el contexto activado
        """
        # Nombre estandarizado para el contexto de bases de datos
        db_context_id = "database_schemas"
        
        if self.use_native_client and self.mcp_client:
            try:
                # Intentar activar el contexto existente
                await self.mcp_client.activate_context(db_context_id)
                logger.info(f"Activated database context: {db_context_id}")
                return {"status": "activated", "context_id": db_context_id, "client_type": "native"}
            except ContextNotFoundError:
                # El contexto no existe, necesitamos crearlo
                # Nota: la API actual no tiene un método directo para crear contextos
                # Usamos el método HTTP como fallback
                pass
            except Exception as e:
                logger.error(f"Error activating database context: {e}")
        
        # Método HTTP - Intentar activar primero
        activate_result = await self._make_request("POST", f"contexts/{db_context_id}/activate")
        
        # Si la activación es exitosa, devolver el resultado
        if "error" not in activate_result:
            return {"status": "activated", "context_id": db_context_id, "client_type": "http"}
        
        # Si la activación falló porque el contexto no existe, crear uno nuevo
        # (Nota: esto requiere una implementación específica en el servicio context-service)
        create_data = {
            "name": "Database Schemas",
            "description": "Contexto para esquemas de bases de datos descubiertos",
            "metadata": {
                "type": "database_schemas",
                "created_by": "schema-discovery-service"
            }
        }
        
        create_result = await self._make_request("POST", "areas", create_data)
        
        if "error" not in create_result and "id" in create_result:
            new_context_id = create_result.get("mcp_context_id", db_context_id)
            
            # Activar el nuevo contexto
            await self._make_request("POST", f"contexts/{new_context_id}/activate")
            
            return {"status": "created_and_activated", "context_id": new_context_id, "client_type": "http"}
        
        # Si todo lo demás falla, intentar usar un contexto general
        general_result = await self._make_request("GET", "mcp/active-contexts")
        
        if isinstance(general_result, list) and len(general_result) > 0:
            # Usar el primer contexto activo disponible
            return {"status": "using_general_context", "context_id": general_result[0].get("id"), "client_type": "http"}
        
        return {"status": "no_context_available", "error": "No se pudo activar ni crear un contexto", "client_type": "http"}