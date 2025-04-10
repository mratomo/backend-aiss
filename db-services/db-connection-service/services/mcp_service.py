"""
Servicio para integración con Model Context Protocol (MCP)

Este servicio permite gestionar y compartir información de conexiones a bases de datos
mediante el protocolo MCP, facilitando la integración con el resto del sistema.
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
    """Servicio para interactuar con Model Context Protocol para conexiones a bases de datos"""

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

    async def store_connection_in_mcp(self, 
                                     connection_id: str, 
                                     connection_name: str, 
                                     db_type: str,
                                     metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Almacena información sobre una conexión a base de datos en MCP
        
        Args:
            connection_id: ID único de la conexión
            connection_name: Nombre descriptivo de la conexión
            db_type: Tipo de base de datos (postgres, mysql, etc.)
            metadata: Metadatos adicionales sobre la conexión
            
        Returns:
            Resultado de la operación
        """
        # Generar descripción textual de la conexión
        connection_description = f"""
Database Connection: {connection_name}
ID: {connection_id}
Type: {db_type}
Metadata:
"""
        # Añadir metadatos no sensibles
        safe_metadata = {k: v for k, v in metadata.items() if k not in ["password", "secret", "key"]}
        for key, value in safe_metadata.items():
            connection_description += f"- {key}: {value}\n"
        
        # Preparar metadatos para el documento MCP
        mcp_metadata = {
            "connection_id": connection_id,
            "db_type": db_type,
            "connection_name": connection_name,
            "document_type": "database_connection",
            "source": "db-connection-service",
            **safe_metadata
        }
        
        # Crear o activar contexto específico para esta conexión
        db_context_id = f"db_{connection_id}"
        await self.create_or_activate_db_connection_context(db_context_id, connection_name)
        
        # Almacenar la información usando MCP
        if self.use_native_client and self.mcp_client:
            try:
                # Usar cliente nativo
                result = await self.mcp_client.call_tool(
                    "store_document",
                    information=connection_description,
                    metadata=mcp_metadata
                )
                
                return {
                    "success": True,
                    "result": result,
                    "context_id": db_context_id,
                    "client_type": "native"
                }
            except Exception as e:
                logger.error(f"Error using native MCP client for store_connection: {e}")
                # Caer en implementación por HTTP en caso de error
        
        # Método tradicional por HTTP
        tool_data = {
            "information": connection_description,
            "metadata": mcp_metadata
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
            "context_id": db_context_id,
            "client_type": "http"
        }
    
    async def create_or_activate_db_connection_context(self, 
                                                      context_id: str, 
                                                      connection_name: str) -> Dict[str, Any]:
        """
        Crea o activa un contexto específico para una conexión a base de datos
        
        Args:
            context_id: ID del contexto a crear/activar
            connection_name: Nombre de la conexión para la descripción del contexto
            
        Returns:
            Información sobre el contexto
        """
        # Primero intentar activar el contexto si ya existe
        if self.use_native_client and self.mcp_client:
            try:
                await self.mcp_client.activate_context(context_id)
                logger.info(f"Activated existing database connection context: {context_id}")
                return {"status": "activated", "context_id": context_id, "client_type": "native"}
            except ContextNotFoundError:
                # El contexto no existe, necesitamos crearlo a través de la API HTTP
                pass
            except Exception as e:
                logger.error(f"Error activating context with native client: {e}")
        
        # Método HTTP - Intentar activar primero
        activate_result = await self._make_request("POST", f"contexts/{context_id}/activate")
        
        # Si la activación es exitosa, devolver el resultado
        if "error" not in activate_result:
            return {"status": "activated", "context_id": context_id, "client_type": "http"}
        
        # Si la activación falló porque el contexto no existe, crear uno nuevo a través de un área
        create_data = {
            "name": f"Database Connection: {connection_name}",
            "description": f"Contexto para la conexión a base de datos: {connection_name}",
            "metadata": {
                "type": "database_connection",
                "connection_id": context_id,
                "created_by": "db-connection-service"
            }
        }
        
        create_result = await self._make_request("POST", "areas", create_data)
        
        if "error" not in create_result and "id" in create_result:
            new_context_id = create_result.get("mcp_context_id", context_id)
            
            # Activar el nuevo contexto
            await self._make_request("POST", f"contexts/{new_context_id}/activate")
            
            return {"status": "created_and_activated", "context_id": new_context_id, "client_type": "http"}
        
        # Si todo lo demás falla, reportar error
        return {
            "status": "error", 
            "error": "No se pudo crear ni activar el contexto",
            "context_id": context_id,
            "client_type": "http"
        }
        
    async def find_similar_connections(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Busca conexiones a bases de datos similares utilizando MCP
        
        Args:
            query: Consulta para buscar conexiones similares
            limit: Número máximo de resultados
            
        Returns:
            Lista de conexiones similares encontradas
        """
        if self.use_native_client and self.mcp_client:
            try:
                # Buscar contextos activos relacionados con conexiones
                contexts = await self.mcp_client.get_active_contexts()
                
                # Filtrar solo los contextos de conexiones a bases de datos
                db_contexts = [
                    ctx for ctx in contexts 
                    if hasattr(ctx, 'metadata') and 
                    ctx.metadata.get('type') == 'database_connection'
                ]
                
                # Si no hay contextos activos, activar un contexto general
                if not db_contexts:
                    # Activar un contexto general para conexiones
                    await self.create_or_activate_general_db_context()
                
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
                    return result["results"]
                else:
                    return [{"text": str(result), "client_type": "native"}]
            except Exception as e:
                logger.error(f"Error using native MCP client for find_similar_connections: {e}")
                # Caer en fallback HTTP
        
        # Método HTTP
        # Primero activar un contexto general para conexiones
        await self.create_or_activate_general_db_context()
        
        # Luego hacer la consulta
        tool_data = {
            "query": query,
            "embedding_type": "general",
            "limit": limit
        }
        
        result = await self._make_request("POST", "mcp/tools/find-relevant", tool_data)
        
        # Procesar los resultados
        if isinstance(result, dict) and "results" in result:
            return result["results"]
        elif isinstance(result, list):
            return result
        elif isinstance(result, dict) and "result" in result:
            items = result["result"]
            if isinstance(items, list):
                return items
        
        return []
    
    async def create_or_activate_general_db_context(self) -> Dict[str, Any]:
        """
        Crea o activa un contexto general para todas las conexiones a bases de datos
        
        Returns:
            Información sobre el contexto
        """
        # Contexto general para todas las conexiones a bases de datos
        context_id = "database_connections"
        
        # Primero intentar activar el contexto si ya existe
        if self.use_native_client and self.mcp_client:
            try:
                await self.mcp_client.activate_context(context_id)
                logger.info(f"Activated general database connections context: {context_id}")
                return {"status": "activated", "context_id": context_id, "client_type": "native"}
            except ContextNotFoundError:
                # El contexto no existe, necesitamos crearlo a través de la API HTTP
                pass
            except Exception as e:
                logger.error(f"Error activating general context with native client: {e}")
        
        # Método HTTP - Intentar activar primero
        activate_result = await self._make_request("POST", f"contexts/{context_id}/activate")
        
        # Si la activación es exitosa, devolver el resultado
        if "error" not in activate_result:
            return {"status": "activated", "context_id": context_id, "client_type": "http"}
        
        # Si la activación falló porque el contexto no existe, crear uno nuevo a través de un área
        create_data = {
            "name": "Database Connections",
            "description": "Contexto general para todas las conexiones a bases de datos",
            "metadata": {
                "type": "database_connections_general",
                "created_by": "db-connection-service"
            }
        }
        
        create_result = await self._make_request("POST", "areas", create_data)
        
        if "error" not in create_result and "id" in create_result:
            new_context_id = create_result.get("mcp_context_id", context_id)
            
            # Activar el nuevo contexto
            await self._make_request("POST", f"contexts/{new_context_id}/activate")
            
            return {"status": "created_and_activated", "context_id": new_context_id, "client_type": "http"}
        
        # Si todo lo demás falla, reportar error
        return {
            "status": "error", 
            "error": "No se pudo crear ni activar el contexto general",
            "context_id": context_id,
            "client_type": "http"
        }