import logging
import uuid
from typing import Dict, List, Optional, Any

import aiohttp
from fastapi import HTTPException

from config.settings import Settings
from models.embedding import EmbeddingType, SearchResult

logger = logging.getLogger(__name__)

class VectorDBService:
    """Servicio para interactuar con la base de datos vectorial (Qdrant)"""

    def __init__(self, settings: Settings):
        """Inicializar servicio con la configuración"""
        self.settings = settings
        self.qdrant_url = settings.qdrant.url
        self.api_key = settings.qdrant.api_key
        self.collection_general = settings.qdrant.collection_general
        self.collection_personal = settings.qdrant.collection_personal
        self.vector_size = settings.qdrant.vector_size
        self.distance = settings.qdrant.distance

    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Realizar una petición a la API de Qdrant

        Args:
            method: Método HTTP (GET, POST, PUT, DELETE)
            endpoint: Endpoint de la API
            data: Datos para la petición (para POST, PUT)

        Returns:
            Respuesta de la API como diccionario
        """
        url = f"{self.qdrant_url}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Api-Key"] = self.api_key

        if method not in {"GET", "POST", "PUT", "DELETE"}:
            logger.error(f"Método HTTP no soportado: {method}")
            raise HTTPException(status_code=500, detail=f"Método HTTP no soportado: {method}")
        try:
            async with aiohttp.ClientSession() as session:
                kwargs = {"headers": headers}
                if data is not None:
                    kwargs["json"] = data
                async with session.request(method, url, **kwargs) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        logger.error(f"Error en petición Qdrant {method} {url}: {response.status} - {error_text}")
                        raise HTTPException(status_code=response.status, detail=f"Error en Qdrant: {error_text}")
                    return await response.json()
        except aiohttp.ClientConnectionError as e:
            logger.error(f"Error de conexión con Qdrant en {method} {url}: {e}")
            raise HTTPException(status_code=502, detail=f"Error de conexión con Qdrant: {e}")
        except aiohttp.ClientResponseError as e:
            logger.error(f"Error de respuesta de Qdrant en {method} {url}: {e.status} - {e.message}")
            raise HTTPException(status_code=e.status, detail=f"Error en respuesta de Qdrant: {e.message}")
        except aiohttp.ClientError as e:
            logger.error(f"Error de cliente en petición Qdrant {method} {url}: {e}")
            raise HTTPException(status_code=502, detail=f"Error de conexión con Qdrant: {e}")

    async def get_status(self) -> Dict:
        """Verificar estado de Qdrant"""
        return await self._make_request("GET", "service/status")

    async def ensure_collections_exist(self) -> None:
        """Asegurar que las colecciones necesarias existen, crearlas si no"""
        collections_response = await self._make_request("GET", "collections")
        collections = [col["name"] for col in collections_response.get("result", {}).get("collections", [])]

        # Crear colección para embeddings generales si no existe
        if self.collection_general not in collections:
            await self._create_collection(self.collection_general)

        # Crear colección para embeddings personales si no existe
        if self.collection_personal not in collections:
            await self._create_collection(self.collection_personal)

    async def _create_collection(self, collection_name: str) -> None:
        """Crear una colección en Qdrant"""
        config = {
            "name": collection_name,
            "vectors": {
                "size": self.vector_size,
                "distance": self.distance
            },
            "optimizers_config": {
                "default_segment_number": 2
            },
            "replication_factor": 1
        }
        await self._make_request("PUT", f"collections/{collection_name}", config)

        # Crear índices para filtrado por campos de metadata
        payload = {"field_name": "metadata.owner_id", "field_schema": "keyword"}
        await self._make_request("PUT", f"collections/{collection_name}/index", payload)
        payload = {"field_name": "metadata.area_id", "field_schema": "keyword"}
        await self._make_request("PUT", f"collections/{collection_name}/index", payload)
        payload = {"field_name": "metadata.doc_id", "field_schema": "keyword"}
        await self._make_request("PUT", f"collections/{collection_name}/index", payload)

    def _get_collection_for_type(self, embedding_type: EmbeddingType) -> str:
        """Obtener el nombre de la colección correspondiente al tipo de embedding"""
        if embedding_type == EmbeddingType.GENERAL:
            return self.collection_general
        elif embedding_type == EmbeddingType.PERSONAL:
            return self.collection_personal
        else:
            logger.error(f"Tipo de embedding no soportado: {embedding_type}")
            raise HTTPException(status_code=400, detail=f"Tipo de embedding no soportado: {embedding_type}")

    async def store_vector(self,
                           vector: List[float],
                           embedding_type: EmbeddingType,
                           doc_id: str,
                           owner_id: str,
                           text: Optional[str] = None,
                           area_id: Optional[str] = None,
                           metadata: Optional[Dict[str, Any]] = None) -> str:
        """Almacenar un vector en la base de datos vectorial"""
        collection_name = self._get_collection_for_type(embedding_type)

        # Generar ID único para el vector
        vector_id = str(uuid.uuid4())

        # Preparar metadatos
        payload_metadata = metadata.copy() if metadata else {}
        payload_metadata.update({
            "doc_id": doc_id,
            "owner_id": owner_id
        })
        if area_id:
            payload_metadata["area_id"] = area_id
        if text:
            payload_metadata["text"] = text

        # Preparar payload
        payload = {
            "points": [
                {
                    "id": vector_id,
                    "vector": vector,
                    "payload": payload_metadata
                }
            ]
        }

        # Almacenar vector
        await self._make_request("PUT", f"collections/{collection_name}/points", payload)
        return vector_id

    async def store_vectors_batch(self,
                                  vectors: List[List[float]],
                                  embedding_type: EmbeddingType,
                                  doc_ids: List[str],
                                  owner_id: str,
                                  texts: Optional[List[str]] = None,
                                  area_id: Optional[str] = None,
                                  metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """Almacenar múltiples vectores en batch"""
        collection_name = self._get_collection_for_type(embedding_type)

        # Verificar que las listas tienen el mismo tamaño
        if len(vectors) != len(doc_ids):
            logger.error("Las listas de vectores y doc_ids tienen diferente tamaño")
            raise HTTPException(status_code=400, detail="Las listas de vectores y doc_ids deben tener el mismo tamaño")
        if texts and len(texts) != len(vectors):
            logger.error("La lista de textos no coincide con la lista de vectores")
            raise HTTPException(status_code=400, detail="La lista de textos debe tener el mismo tamaño que la lista de vectores")

        # Preparar points para el batch
        points = []
        vector_ids: List[str] = []
        for i, vector in enumerate(vectors):
            vector_id = str(uuid.uuid4())
            vector_ids.append(vector_id)
            # Preparar metadatos
            point_metadata = metadata.copy() if metadata else {}
            point_metadata.update({
                "doc_id": doc_ids[i],
                "owner_id": owner_id
            })
            if area_id:
                point_metadata["area_id"] = area_id
            if texts:
                point_metadata["text"] = texts[i]
            # Añadir point al batch
            points.append({
                "id": vector_id,
                "vector": vector,
                "payload": point_metadata
            })

        # Preparar payload
        payload = {"points": points}

        # Almacenar vectores
        await self._make_request("PUT", f"collections/{collection_name}/points", payload)
        return vector_ids

    async def delete_vector(self, vector_id: str, embedding_type: EmbeddingType) -> bool:
        """Eliminar un vector de la base de datos vectorial"""
        collection_name = self._get_collection_for_type(embedding_type)
        payload = {"points": [vector_id]}
        response = await self._make_request("DELETE", f"collections/{collection_name}/points", payload)
        return response.get("result", {}).get("status", "") == "completed"

    async def search(self,
                     query_vector: List[float],
                     embedding_type: EmbeddingType,
                     owner_id: Optional[str] = None,
                     area_id: Optional[str] = None,
                     limit: int = 10) -> List[SearchResult]:
        """Buscar vectores similares"""
        collection_name = self._get_collection_for_type(embedding_type)

        # Preparar filtros
        filter_condition = None
        if owner_id or area_id:
            must_conditions = []
            if owner_id:
                must_conditions.append({
                    "key": "metadata.owner_id",
                    "match": {"value": owner_id}
                })
            if area_id:
                must_conditions.append({
                    "key": "metadata.area_id",
                    "match": {"value": area_id}
                })
            filter_condition = {"must": must_conditions}

        # Preparar payload de búsqueda
        payload = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
            "with_vectors": False
        }
        if filter_condition:
            payload["filter"] = filter_condition

        # Realizar búsqueda
        response = await self._make_request("POST", f"collections/{collection_name}/points/search", payload)

        # Procesar resultados
        results: List[SearchResult] = []
        for hit in response.get("result", []):
            result = SearchResult(
                embedding_id=hit["id"],
                doc_id=hit["payload"]["doc_id"],
                score=hit["score"],
                metadata=hit["payload"]
            )
            # Añadir texto si está disponible
            if "text" in hit["payload"]:
                result.text = hit["payload"]["text"]
            results.append(result)
        return results
