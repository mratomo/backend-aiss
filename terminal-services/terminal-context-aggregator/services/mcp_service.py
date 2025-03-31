import json
import logging
import aiohttp
from typing import Dict, List, Any, Optional

from config.settings import settings
from models.terminal import TerminalContext

logger = logging.getLogger(__name__)

class MCPService:
    """Service to interact with MCP (Model Context Protocol) services"""
    
    async def enrich_context(self, context: TerminalContext, query: str) -> Dict[str, Any]:
        """Enrich terminal context with information from MCP"""
        try:
            # Prepare simplified command history for context
            command_history = "\n".join(context.last_commands[-10:]) if context.last_commands else ""
            
            # Create MCP document payload
            payload = {
                "query": query,
                "context": {
                    "session_id": context.session_id,
                    "user_id": context.user_id,
                    "terminal_context": {
                        "current_directory": context.current_directory,
                        "current_user": context.current_user,
                        "hostname": context.hostname,
                        "command_history": command_history,
                        "detected_applications": context.detected_applications
                    }
                }
            }
            
            # Call MCP service
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"{settings.MCP_SERVICE_URL}/api/v1/context/retrieve",
                    json=payload
                )
                
                if response.status != 200:
                    logger.warning(f"MCP service returned error: {response.status}")
                    return {"enriched": False, "error": f"MCP service error: {response.status}"}
                
                data = await response.json()
                return {
                    "enriched": True,
                    "relevant_context": data.get("relevant_context", []),
                    "context_score": data.get("context_score", 0)
                }
                
        except Exception as e:
            logger.exception(f"Error calling MCP service: {str(e)}")
            return {"enriched": False, "error": str(e)}
    
    async def get_embeddings(self, text: str) -> Optional[List[float]]:
        """Get embeddings for text using the embedding service"""
        try:
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"{settings.EMBEDDING_SERVICE_URL}/api/v1/embeddings",
                    json={"text": text}
                )
                
                if response.status != 200:
                    logger.warning(f"Embedding service returned error: {response.status}")
                    return None
                
                data = await response.json()
                return data.get("embedding")
                
        except Exception as e:
            logger.exception(f"Error getting embeddings: {str(e)}")
            return None
