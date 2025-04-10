# services/embedding_service_client.py
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union, Protocol, Tuple

# Soporte para múltiples clientes HTTP
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

import aiohttp
from fastapi import HTTPException
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from config.settings import Settings

logger = logging.getLogger(__name__)

# Protocolo para abstraer clientes HTTP
class HTTPClient(Protocol):
    async def get(self, url: str, **kwargs): ...
    async def post(self, url: str, **kwargs): ...

class EmbeddingServiceClient:
    """Cliente optimizado para interactuar con el servicio de embeddings"""

    def __init__(self, settings: Settings):
        """Inicializar cliente con configuración"""
        self.settings = settings
        self.base_url = settings.embedding_service_url
        self.client = None
        self.use_httpx = HTTPX_AVAILABLE
        self.timeout = getattr(settings, "embedding_service_timeout", 30.0)
        self.service_available = False
        self.allow_degraded_mode = getattr(settings, "allow_degraded_mode", False)
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, aiohttp.ClientError))
    )
    async def check_health(self) -> Tuple[bool, dict]:
        """Verifica la disponibilidad del servicio de embeddings"""
        url = f"{self.base_url}/health"
        try:
            if self.use_httpx:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        self.service_available = data.get("status") == "ok"
                        return self.service_available, data
                    else:
                        logger.warning(f"Embedding service health check failed with status {response.status_code}")
                        self.service_available = False
                        return False, {"status": "error", "code": response.status_code}
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.service_available = data.get("status") == "ok"
                            return self.service_available, data
                        else:
                            logger.warning(f"Embedding service health check failed with status {response.status}")
                            self.service_available = False
                            return False, {"status": "error", "code": response.status}
        except Exception as e:
            logger.warning(f"Embedding service health check failed: {str(e)}")
            self.service_available = False
            return False, {"status": "error", "error": str(e)}

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, aiohttp.ClientError, httpx.HTTPError)),
        retry_error_callback=lambda retry_state: logger.error(f"Failed embedding request after {retry_state.attempt_number} attempts")
    )
    async def create_embedding(self,
                               text: str,
                               embedding_type: str,
                               doc_id: str,
                               owner_id: str,
                               area_id: Optional[str] = None,
                               metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Crear un embedding para un texto con reintentos automáticos y manejo mejorado de errores

        Args:
            text: Texto para generar embedding
            embedding_type: Tipo de embedding ("general" o "personal")
            doc_id: ID del documento
            owner_id: ID del propietario
            area_id: ID del área (opcional)
            metadata: Metadatos adicionales (opcional)

        Returns:
            Respuesta del servicio de embeddings
        """
        # Verificar disponibilidad del servicio
        if not self.service_available and not self.allow_degraded_mode:
            if not await self._check_service_availability():
                raise HTTPException(
                    status_code=503, 
                    detail="Embedding Service is not available and degraded mode is disabled"
                )
        
        url = f"{self.base_url}/embeddings"

        payload = {
            "text": text,
            "embedding_type": embedding_type,
            "doc_id": doc_id,
            "owner_id": owner_id
        }

        if area_id:
            payload["area_id"] = area_id

        if metadata:
            payload["metadata"] = metadata

        # Determinar qué cliente HTTP usar
        if self.use_httpx:
            # Usar httpx
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload)
                    if response.status_code != 200:
                        error_text = response.text
                        logger.error(f"Error creando embedding: {response.status_code} - {error_text}")
                        
                        # Si estamos en modo degradado y es un error del servidor, devolver respuesta simulada
                        if self.allow_degraded_mode and response.status_code >= 500:
                            logger.warning("Running in degraded mode - returning simulated embedding")
                            return self._create_degraded_embedding(text, embedding_type, doc_id, owner_id, area_id, metadata)
                        
                        raise HTTPException(status_code=response.status_code, detail=f"Error en servicio de embeddings: {error_text}")
                    
                    return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Error de conexión con servicio de embeddings (httpx): {e}")
                
                # Si estamos en modo degradado, devolver respuesta simulada
                if self.allow_degraded_mode:
                    logger.warning("Running in degraded mode - returning simulated embedding")
                    return self._create_degraded_embedding(text, embedding_type, doc_id, owner_id, area_id, metadata)
                
                raise HTTPException(status_code=502, detail=f"Error de conexión con servicio de embeddings: {str(e)}")
        else:
            # Usar aiohttp (tradicional)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=self.timeout) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Error creando embedding: {response.status} - {error_text}")
                            
                            # Si estamos en modo degradado y es un error del servidor, devolver respuesta simulada
                            if self.allow_degraded_mode and response.status >= 500:
                                logger.warning("Running in degraded mode - returning simulated embedding")
                                return self._create_degraded_embedding(text, embedding_type, doc_id, owner_id, area_id, metadata)
                            
                            raise HTTPException(status_code=response.status, detail=f"Error en servicio de embeddings: {error_text}")

                        return await response.json()
            except aiohttp.ClientError as e:
                logger.error(f"Error de conexión con servicio de embeddings (aiohttp): {e}")
                
                # Si estamos en modo degradado, devolver respuesta simulada
                if self.allow_degraded_mode:
                    logger.warning("Running in degraded mode - returning simulated embedding")
                    return self._create_degraded_embedding(text, embedding_type, doc_id, owner_id, area_id, metadata)
                
                raise HTTPException(status_code=502, detail=f"Error de conexión con servicio de embeddings: {str(e)}")
    
    def _create_degraded_embedding(self, text: str, embedding_type: str, doc_id: str, 
                                  owner_id: str, area_id: Optional[str] = None,
                                  metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Crea un embedding simulado para modo degradado"""
        import uuid
        import hashlib
        
        # Crear un ID determinista basado en el texto
        hash_obj = hashlib.md5(text.encode())
        embedding_id = f"degraded_{hash_obj.hexdigest()[:16]}"
        
        result = {
            "id": embedding_id,
            "doc_id": doc_id,
            "owner_id": owner_id,
            "embedding_type": embedding_type,
            "text_snippet": text[:100] + ("..." if len(text) > 100 else ""),
            "metadata": metadata or {},
            "degraded_mode": True,
            "vector_id": str(uuid.uuid4())
        }
        
        if area_id:
            result["area_id"] = area_id
            
        return result
        
    async def _check_service_availability(self) -> bool:
        """Verifica la disponibilidad del servicio usando el endpoint de healthcheck"""
        try:
            available, _ = await self.check_health()
            return available
        except Exception:
            return False

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, aiohttp.ClientError, httpx.HTTPError)),
        retry_error_callback=lambda retry_state: logger.error(f"Failed embedding search after {retry_state.attempt_number} attempts")
    )
    async def search(self,
                     query: str,
                     embedding_type: str,
                     owner_id: Optional[str] = None,
                     area_id: Optional[str] = None,
                     limit: int = 10) -> Dict[str, Any]:
        """
        Buscar embeddings similares a una consulta con reintentos automáticos

        Args:
            query: Texto de consulta
            embedding_type: Tipo de embedding ("general" o "personal")
            owner_id: ID del propietario para filtrar (opcional)
            area_id: ID del área para filtrar (opcional)
            limit: Número máximo de resultados

        Returns:
            Resultados de la búsqueda
        """
        url = f"{self.base_url}/search"

        params = {
            "query": query,
            "embedding_type": embedding_type,
            "limit": limit
        }

        if owner_id:
            params["owner_id"] = owner_id

        if area_id:
            params["area_id"] = area_id

        # Determinar qué cliente HTTP usar
        if self.use_httpx:
            # Usar httpx
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, params=params)
                    if response.status_code != 200:
                        error_text = response.text
                        logger.error(f"Error buscando embeddings: {response.status_code} - {error_text}")
                        raise HTTPException(status_code=response.status_code, detail=f"Error en servicio de embeddings: {error_text}")
                    
                    return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Error de conexión con servicio de embeddings (httpx): {e}")
                raise HTTPException(status_code=502, detail=f"Error de conexión con servicio de embeddings: {str(e)}")
        else:
            # Usar aiohttp (tradicional)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=30) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Error buscando embeddings: {response.status} - {error_text}")
                            raise HTTPException(status_code=response.status, detail=f"Error en servicio de embeddings: {error_text}")

                        return await response.json()
            except aiohttp.ClientError as e:
                logger.error(f"Error de conexión con servicio de embeddings (aiohttp): {e}")
                raise HTTPException(status_code=502, detail=f"Error de conexión con servicio de embeddings: {str(e)}")