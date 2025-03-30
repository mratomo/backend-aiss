# services/embedding_service_client.py
import logging
from typing import Dict, List, Optional, Any, Union

import aiohttp
from fastapi import HTTPException

from config.settings import Settings

logger = logging.getLogger(__name__)

class EmbeddingServiceClient:
    """Cliente para interactuar con el servicio de embeddings"""

    def __init__(self, settings: Settings):
        """Inicializar cliente con configuración"""
        self.settings = settings
        self.base_url = settings.embedding_service_url

    async def create_embedding(self,
                               text: str,
                               embedding_type: str,
                               doc_id: str,
                               owner_id: str,
                               area_id: Optional[str] = None,
                               metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Crear un embedding para un texto

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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Error creando embedding: {response.status} - {error_text}")
                        raise HTTPException(status_code=response.status, detail=f"Error en servicio de embeddings: {error_text}")

                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Error de conexión con servicio de embeddings: {e}")
            raise HTTPException(status_code=502, detail=f"Error de conexión con servicio de embeddings: {str(e)}")

    async def search(self,
                     query: str,
                     embedding_type: str,
                     owner_id: Optional[str] = None,
                     area_id: Optional[str] = None,
                     limit: int = 10) -> Dict[str, Any]:
        """
        Buscar embeddings similares a una consulta

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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Error buscando embeddings: {response.status} - {error_text}")
                        raise HTTPException(status_code=response.status, detail=f"Error en servicio de embeddings: {error_text}")

                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Error de conexión con servicio de embeddings: {e}")
            raise HTTPException(status_code=502, detail=f"Error de conexión con servicio de embeddings: {str(e)}")