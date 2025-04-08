import json
import logging
import aiohttp
import asyncio
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
            
            # Configure timeout
            timeout = aiohttp.ClientTimeout(
                total=settings.SUGGESTION_TIMEOUT_SECONDS, 
                connect=5.0
            )
            
            # Call MCP service with retries
            max_retries = 3
            retry_delay = 0.5  # seconds
            
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        # Set headers for authentication if available
                        headers = {}
                        if hasattr(settings, "API_KEY") and settings.API_KEY:
                            headers["X-API-Key"] = settings.API_KEY
                            
                        response = await session.post(
                            f"{settings.MCP_SERVICE_URL}/api/v1/context/retrieve",
                            json=payload,
                            headers=headers
                        )
                        
                        if response.status == 200:
                            data = await response.json()
                            return {
                                "enriched": True,
                                "relevant_context": data.get("relevant_context", []),
                                "context_score": data.get("context_score", 0)
                            }
                        
                        # Log error details but continue with retries for 5xx errors
                        logger.warning(f"MCP service returned error: {response.status}")
                        
                        # Don't retry for client errors
                        if response.status < 500:
                            return {"enriched": False, "error": f"MCP service error: {response.status}"}
                            
                        # Last retry failed with server error
                        if attempt == max_retries - 1:
                            return {"enriched": False, "error": f"MCP service error after {max_retries} attempts: {response.status}"}
                            
                        # Wait before retrying with exponential backoff
                        await asyncio.sleep(retry_delay * (2 ** attempt))
                
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    # Network or timeout error
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to connect to MCP service after {max_retries} attempts: {str(e)}")
                        return {"enriched": False, "error": f"MCP service connection error: {str(e)}"}
                    
                    logger.warning(f"MCP connection attempt {attempt+1} failed: {str(e)}")
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                
        except Exception as e:
            logger.exception(f"Error calling MCP service: {str(e)}")
            return {"enriched": False, "error": str(e)}
    
    async def get_embeddings(self, text: str) -> Optional[List[float]]:
        """Get embeddings for text using the embedding service"""
        try:
            # Configure timeout
            timeout = aiohttp.ClientTimeout(
                total=10.0,  # Embedding generation should be faster than context retrieval
                connect=5.0
            )
            
            # Call embedding service with retries
            max_retries = 2
            retry_delay = 0.5  # seconds
            
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        # Set headers for authentication if available
                        headers = {}
                        if hasattr(settings, "API_KEY") and settings.API_KEY:
                            headers["X-API-Key"] = settings.API_KEY
                            
                        response = await session.post(
                            f"{settings.EMBEDDING_SERVICE_URL}/api/v1/embeddings",
                            json={"text": text, "model": "default"},
                            headers=headers
                        )
                        
                        if response.status == 200:
                            data = await response.json()
                            return data.get("embedding")
                        
                        # Log error details
                        logger.warning(f"Embedding service returned error: {response.status}")
                        
                        # Don't retry for client errors
                        if response.status < 500:
                            return None
                            
                        # Last retry failed with server error
                        if attempt == max_retries - 1:
                            return None
                            
                        # Wait before retrying with exponential backoff
                        await asyncio.sleep(retry_delay * (2 ** attempt))
                
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    # Network or timeout error
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to connect to embedding service after {max_retries} attempts: {str(e)}")
                        return None
                    
                    logger.warning(f"Embedding service connection attempt {attempt+1} failed: {str(e)}")
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                
        except Exception as e:
            logger.exception(f"Error getting embeddings: {str(e)}")
            return None
