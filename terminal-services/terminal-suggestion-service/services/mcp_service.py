import json
import logging
import httpx
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Union

# Importación de la biblioteca oficial de MCP
try:
    import mcp
    from mcp import Context, ContextType, Tool, Client
    from mcp.client import ClientError
    MCP_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info(f"MCP Python client library loaded successfully. Version: {getattr(mcp, '__version__', 'unknown')}")
except ImportError:
    # Fallback en caso de que la biblioteca no esté disponible
    logger = logging.getLogger(__name__)
    logger.warning("Official MCP Python client library not available. Using HTTP fallback implementation.")
    MCP_AVAILABLE = False

from config.settings import settings
from models.suggestion import Suggestion, SuggestionType, SuggestionRisk

logger = logging.getLogger(__name__)

class MCPService:
    """Service to interact with MCP (Model Context Protocol) services using the official library"""
    
    def __init__(self):
        """Initialize the MCP service with configuration"""
        self.mcp_service_url = settings.MCP_SERVICE_URL
        
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
    
    async def get_status(self) -> Dict[str, Any]:
        """Get the status of the MCP service"""
        if self.use_native_client and self.mcp_client:
            try:
                # Usar método nativo del cliente MCP
                status = await self.mcp_client.get_status()
                return {
                    "name": status.name,
                    "version": status.version,
                    "tools": [t.dict() for t in status.tools] if hasattr(status, 'tools') else [],
                    "client_type": "native"
                }
            except Exception as e:
                logger.error(f"Error using native MCP client for get_status: {e}")
                # Caer en implementación por HTTP en caso de error
        
        # Implementación HTTP
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.mcp_service_url}/mcp/status")
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, dict):
                        result["client_type"] = "http"
                    return result
                else:
                    return {"status": "error", "error": f"HTTP error {response.status_code}"}
        except Exception as e:
            logger.error(f"Error in HTTP implementation for get_status: {e}")
            return {"status": "error", "error": str(e)}
    
    async def find_relevant(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Find relevant information using the MCP find_relevant tool
        
        Args:
            query: The query to search for
            limit: Maximum number of results to return
            
        Returns:
            List of relevant information items
        """
        if self.use_native_client and self.mcp_client:
            try:
                # Use native client to call find_relevant tool
                contexts = await self.mcp_client.get_active_contexts()
                
                if not contexts:
                    return [{"text": "No active contexts found", "score": 0, "client_type": "native"}]
                
                # Call find_relevant on first active context
                tool_results = await self.mcp_client.call_tool(
                    "find_relevant",
                    query=query,
                    limit=limit
                )
                
                # Process the results
                if isinstance(tool_results, list):
                    return [
                        {"text": item, "score": None, "client_type": "native"} 
                        if isinstance(item, str) else 
                        {**item, "client_type": "native"} 
                        for item in tool_results
                    ]
                else:
                    return [{"text": str(tool_results), "score": None, "client_type": "native"}]
            except Exception as e:
                logger.error(f"Error using native MCP client for find_relevant: {e}")
                # Fallback to HTTP implementation
        
        # HTTP implementation
        try:
            tool_data = {
                "query": query,
                "limit": limit
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.mcp_service_url}/mcp/tools/find-relevant",
                    json=tool_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Process the results
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
                    else:
                        return [{"text": str(result), "score": None, "client_type": "http"}]
                else:
                    return [{"text": f"Error: {response.status_code}", "score": 0, "client_type": "http"}]
        except Exception as e:
            logger.error(f"Error in HTTP implementation for find_relevant: {e}")
            return [{"text": f"Error: {str(e)}", "score": 0, "client_type": "http"}]
    
    async def get_command_context(self, session_id: str, command: str) -> Dict[str, Any]:
        """
        Get relevant context for a terminal command
        
        This method uses the custom /api/v1/context/retrieve endpoint to get
        relevant context specifically optimized for terminal commands.
        
        Args:
            session_id: The terminal session ID
            command: The command to get context for
            
        Returns:
            Dictionary with relevant context information
        """
        try:
            # First try to use the find_relevant tool if available
            if self.use_native_client and self.mcp_client:
                try:
                    # Try to find relevant information using the standard MCP tool
                    tool_results = await self.mcp_client.call_tool(
                        "find_relevant",
                        query=command,
                        limit=5
                    )
                    
                    # Process the results
                    if isinstance(tool_results, list) and len(tool_results) > 0:
                        return {
                            "enriched": True,
                            "relevant_context": tool_results,
                            "context_score": 0.95,  # High confidence
                            "client_type": "native"
                        }
                except Exception as e:
                    logger.warning(f"Native MCP client failed for command context: {e}")
            
            # Fallback to the custom endpoint for terminal context
            # Configure timeout
            timeout = settings.SUGGESTION_TIMEOUT_SECONDS
            
            # Call MCP service with retries
            max_retries = 3
            retry_delay = 0.5  # seconds
            
            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        # Set headers for authentication if available
                        headers = {"Content-Type": "application/json"}
                        if hasattr(settings, "API_KEY") and settings.API_KEY:
                            headers["X-API-Key"] = settings.API_KEY
                            
                        # Create payload for the custom endpoint
                        payload = {
                            "query": command,
                            "context": {
                                "session_id": session_id
                            }
                        }
                        
                        response = await client.post(
                            f"{self.mcp_service_url}/api/v1/context/retrieve",
                            json=payload,
                            headers=headers
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            return {
                                "enriched": True,
                                "relevant_context": data.get("relevant_context", []),
                                "context_score": data.get("context_score", 0),
                                "client_type": "http"
                            }
                        
                        # Log error details but continue with retries for 5xx errors
                        logger.warning(f"MCP service returned error: {response.status_code}")
                        
                        # Don't retry for client errors
                        if response.status_code < 500:
                            return {"enriched": False, "error": f"MCP service error: {response.status_code}"}
                            
                        # Last retry failed with server error
                        if attempt == max_retries - 1:
                            return {"enriched": False, "error": f"MCP service error after {max_retries} attempts: {response.status_code}"}
                            
                        # Wait before retrying with exponential backoff
                        await asyncio.sleep(retry_delay * (2 ** attempt))
                
                except (httpx.RequestError, asyncio.TimeoutError) as e:
                    # Network or timeout error
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to connect to MCP service after {max_retries} attempts: {str(e)}")
                        return {"enriched": False, "error": f"MCP service connection error: {str(e)}"}
                    
                    logger.warning(f"MCP connection attempt {attempt+1} failed: {str(e)}")
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                
        except Exception as e:
            logger.exception(f"Error calling MCP service: {str(e)}")
            return {"enriched": False, "error": str(e)}
        
    async def store_suggestion(self, 
                              session_id: str, 
                              command: str, 
                              suggestion: Suggestion) -> Dict[str, Any]:
        """
        Store a suggestion in MCP for future reference
        
        This method uses the standard MCP store_document tool to save 
        suggestions that were useful for the user.
        
        Args:
            session_id: The terminal session ID
            command: The command the suggestion was generated for
            suggestion: The suggestion object
            
        Returns:
            Result of the operation
        """
        try:
            # Prepare the text representation of the suggestion
            text = f"""Terminal Suggestion:
Command: {command}
Suggestion Title: {suggestion.title}
Suggestion Type: {suggestion.type}
Suggested Command: {suggestion.command if suggestion.command else 'N/A'}
Description: {suggestion.content}
Risk Level: {suggestion.risk_level}
"""
            
            # Prepare metadata
            metadata = {
                "session_id": session_id,
                "suggestion_id": suggestion.id,
                "suggestion_type": suggestion.type,
                "original_command": command,
                "suggested_command": suggestion.command,
                "risk_level": suggestion.risk_level
            }
            
            # Use the native client if available
            if self.use_native_client and self.mcp_client:
                try:
                    # Use the store_document tool
                    result = await self.mcp_client.call_tool(
                        "store_document",
                        information=text,
                        metadata=metadata
                    )
                    
                    return {
                        "success": True,
                        "result": result,
                        "client_type": "native"
                    }
                except Exception as e:
                    logger.error(f"Error using native MCP client for store_suggestion: {e}")
                    # Fallback to HTTP implementation
            
            # HTTP implementation
            tool_data = {
                "information": text,
                "metadata": metadata
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.mcp_service_url}/mcp/tools/store-document",
                    json=tool_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, dict):
                        result["client_type"] = "http"
                        result["success"] = True
                    return result
                else:
                    return {
                        "success": False,
                        "error": f"HTTP error {response.status_code}",
                        "client_type": "http"
                    }
                    
        except Exception as e:
            logger.exception(f"Error storing suggestion: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }