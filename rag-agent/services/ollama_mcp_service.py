import asyncio
import json
import logging
import os
import subprocess
import sys
from typing import Dict, List, Optional, Any, Union

import aiohttp
import httpx
from fastapi import HTTPException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Intentar usar structlog para logging estructurado
try:
    import structlog
    logger = structlog.get_logger("ollama_mcp_service")
    structlog_available = True
except ImportError:
    logger = logging.getLogger("ollama_mcp_service")
    structlog_available = False

from config.settings import Settings
from models.llm_provider import LLMProviderType

class OllamaMCPService:
    """Servicio para interactuar con Ollama a través de MCP"""

    def __init__(self, settings: Settings):
        """Inicializar servicio con configuración"""
        self.settings = settings
        self.ollama_url = settings.ollama.api_url
        self.ollama_mcp_url = settings.ollama.mcp_url
        self.is_remote = settings.ollama.is_remote
        self.http_client = None
        self.mcp_client = None
        self.mcp_initialized = False
        self.available_models = []
        
        # Log de configuración
        logger.info(f"Initializing OllamaMCPService with API URL: {self.ollama_url}")
        logger.info(f"MCP URL: {self.ollama_mcp_url}, Remote instance: {self.is_remote}")
        
        self._initialize_mcp()

    def _initialize_mcp(self):
        """Inicializar cliente MCP si está disponible"""
        try:
            from mcp import Client
            self.mcp_client = Client()
            self.mcp_initialized = True
            logger.info("MCP client initialized for Ollama integration")
        except ImportError:
            logger.warning("MCP package not installed. Install it with: pip install mcp-python")
            self.mcp_initialized = False
    
    async def get_http_client(self):
        """Obtener o crear cliente HTTP bajo demanda"""
        if self.http_client is None:
            if httpx_available:
                timeout = httpx.Timeout(30.0)
                self.http_client = httpx.AsyncClient(timeout=timeout)
            else:
                timeout = aiohttp.ClientTimeout(total=30)
                self.http_client = aiohttp.ClientSession(timeout=timeout)
        return self.http_client
    
    async def close(self):
        """Cerrar recursos al finalizar"""
        if self.http_client:
            if isinstance(self.http_client, httpx.AsyncClient):
                await self.http_client.aclose()
            else:
                await self.http_client.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def list_models(self) -> List[Dict[str, Any]]:
        """Listar modelos disponibles en el servidor Ollama"""
        try:
            client = await self.get_http_client()
            
            if isinstance(client, httpx.AsyncClient):
                response = await client.get(f"{self.ollama_url}/api/tags")
                if response.status_code != 200:
                    logger.error(f"Error listing Ollama models: {response.status_code} - {response.text}")
                    return []
                data = response.json()
            else:
                async with client.get(f"{self.ollama_url}/api/tags") as response:
                    if response.status != 200:
                        logger.error(f"Error listing Ollama models: {response.status}")
                        return []
                    data = await response.json()
            
            models = []
            for model in data.get("models", []):
                models.append({
                    "name": model.get("name"),
                    "size": model.get("size"),
                    "modified_at": model.get("modified_at"),
                    "details": model
                })
            
            self.available_models = models
            return models
            
        except Exception as e:
            logger.error(f"Error listing Ollama models: {e}")
            return []
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def generate_text(
        self,
        prompt: str,
        system_prompt: str,
        model: str = "llama3",
        max_tokens: int = 2048,
        temperature: float = 0.2,
        mcp_context_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generar texto con Ollama y MCP
        
        Args:
            prompt: Texto del usuario
            system_prompt: Instrucciones del sistema
            model: Modelo a utilizar
            max_tokens: Máximo de tokens a generar
            temperature: Temperatura para la generación
            mcp_context_ids: Lista de IDs de contextos MCP (opcional)
            
        Returns:
            Respuesta con el texto generado
        """
        # Si MCP está inicializado y se proporcionan contextos, usar la integración MCP
        if self.mcp_initialized and self.mcp_client and mcp_context_ids and len(mcp_context_ids) > 0:
            try:
                # Activar contextos MCP
                for context_id in mcp_context_ids:
                    await self.mcp_client.activate_context(context_id)
                
                # Llamar a Ollama a través de MCP
                logger.info(f"Generating text with Ollama via MCP, model: {model}, contexts: {mcp_context_ids}")
                response_text = await self._generate_with_mcp(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                
                # Desactivar contextos MCP
                for context_id in mcp_context_ids:
                    await self.mcp_client.deactivate_context(context_id)
                
                return {
                    "text": response_text,
                    "model": model,
                    "using_mcp": True
                }
            
            except Exception as e:
                logger.error(f"Error generating text with Ollama via MCP: {e}")
                logger.info("Falling back to standard Ollama API")
                # Desactivar contextos en caso de error
                for context_id in mcp_context_ids:
                    try:
                        await self.mcp_client.deactivate_context(context_id)
                    except:
                        pass
        
        # Usar la API estándar de Ollama
        try:
            client = await self.get_http_client()
            
            payload = {
                "model": model,
                "prompt": prompt,
                "system": system_prompt,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                },
                "stream": False
            }
            
            if isinstance(client, httpx.AsyncClient):
                response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
                if response.status_code != 200:
                    logger.error(f"Error from Ollama API: {response.status_code} - {response.text}")
                    raise HTTPException(status_code=response.status_code, detail=f"Error from Ollama API: {response.text}")
                result = response.json()
            else:
                async with client.post(f"{self.ollama_url}/api/chat", json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"Error from Ollama API: {response.status} - {text}")
                        raise HTTPException(status_code=response.status, detail=f"Error from Ollama API: {text}")
                    result = await response.json()
            
            # Extraer respuesta
            response_text = result.get("message", {}).get("content", "")
            
            return {
                "text": response_text,
                "model": model,
                "using_mcp": False
            }
            
        except Exception as e:
            logger.error(f"Error generating text with Ollama: {e}")
            raise HTTPException(status_code=500, detail=f"Error generating text with Ollama: {str(e)}")
    
    async def _generate_with_mcp(
        self,
        prompt: str,
        system_prompt: str,
        model: str = "llama3",
        max_tokens: int = 2048,
        temperature: float = 0.2
    ) -> str:
        """
        Generar texto con Ollama a través de MCP
        
        Args:
            prompt: Texto del usuario
            system_prompt: Instrucciones del sistema
            model: Modelo a utilizar
            max_tokens: Máximo de tokens a generar
            temperature: Temperatura para la generación
            
        Returns:
            Texto generado
        """
        try:
            # Configurar cliente MCP para Ollama
            # En una implementación real, este código podría ser más complejo
            # y manejar la comunicación con un servidor MCP externo
            
            # Crear una solicitud MCP para Ollama
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                }
            }
            
            # Llamar a Ollama a través de la interfaz MCP
            # Este es un ejemplo simplificado, en la implementación real
            # se usaría el protocolo MCP completo
            client = await self.get_http_client()
            if isinstance(client, httpx.AsyncClient):
                response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
                if response.status_code != 200:
                    raise Exception(f"Error from Ollama API: {response.status_code}")
                result = response.json()
            else:
                async with client.post(f"{self.ollama_url}/api/chat", json=payload) as response:
                    if response.status != 200:
                        raise Exception(f"Error from Ollama API: {response.status}")
                    result = await response.json()
            
            # Extraer y devolver la respuesta
            return result.get("message", {}).get("content", "")
            
        except Exception as e:
            logger.error(f"Error in MCP generation: {e}")
            raise Exception(f"MCP generation failed: {str(e)}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar la salud del servicio Ollama"""
        try:
            models = await self.list_models()
            return {
                "status": "ok" if len(models) > 0 else "degraded",
                "models_available": len(models),
                "models": [m["name"] for m in models][:5],  # Mostrar solo los primeros 5 modelos
                "mcp_available": self.mcp_initialized,
                "api_url": self.ollama_url,
                "mcp_url": self.ollama_mcp_url,
                "is_remote": self.is_remote
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "mcp_available": self.mcp_initialized,
                "api_url": self.ollama_url,
                "mcp_url": self.ollama_mcp_url,
                "is_remote": self.is_remote
            }