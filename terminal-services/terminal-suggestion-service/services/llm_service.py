import json
import logging
import aiohttp
from typing import Dict, Any, Optional, List

from config.settings import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with LLM API"""
    
    async def generate_suggestion(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Generate suggestion using LLM service"""
        try:
            # Use the existing LLM service from rag-agent
            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": prompt,
                    "model": settings.LLM.model,
                    "temperature": settings.LLM.temperature,
                    "max_tokens": settings.LLM.max_tokens,
                    "response_format": {"type": "json_object"},
                }
                
                response = await session.post(
                    settings.LLM_SERVICE_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status != 200:
                    logger.error(f"LLM service error: {response.status}")
                    return None
                
                result = await response.json()
                return result
                
        except Exception as e:
            logger.exception(f"Error calling LLM service: {str(e)}")
            return None
    
    def parse_suggestion_response(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse response from LLM to extract suggestions"""
        try:
            # Get the response text
            response_text = response.get("response", "")
            
            # Parse JSON
            data = json.loads(response_text)
            
            # Extract suggestions
            if "suggestions" in data and isinstance(data["suggestions"], list):
                return data["suggestions"]
            
            return []
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing LLM response: {str(e)}")
            return []
