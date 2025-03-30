# services/retrieval_service.py
import logging

from typing import Dict, List, Optional, Any

import aiohttp

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from config.settings import Settings
from models.embedding import EmbeddingType
from models.query import Source

logger = logging.getLogger(__name__)

class DocumentInfo(BaseModel):
    """Información sobre un documento recuperado"""
    id: str
    title: str
    url: Optional[str] = None
    content: str
    metadata: Dict[str, Any]


class RetrievalService:
    """Servicio para recuperar información relevante para consultas"""

    def __init__(self, database: AsyncIOMotorDatabase, settings: Settings):
        """Inicializar servicio con la base de datos y configuración"""
        self.db = database
        self.settings = settings
        self.embedding_service_url = settings.retrieval.embedding_service_url
        self.document_service_url = settings.retrieval.document_service_url

    async def retrieve_documents(self,
                                 query: str,
                                 embedding_type: EmbeddingType,
                                 owner_id: Optional[str] = None,
                                 area_id: Optional[str] = None,
                                 limit: int = 10) -> List[DocumentInfo]:
        """
        Recuperar documentos relevantes para una consulta

        Args:
            query: Consulta del usuario
            embedding_type: Tipo de embedding a utilizar
            owner_id: ID del propietario (para filtrar)
            area_id: ID del área (para filtrar)
            limit: Número máximo de documentos

        Returns:
            Lista de documentos relevantes
        """
        # Realizar búsqueda semántica en el servicio de embeddings
        search_results = await self._search_embeddings(
            query=query,
            embedding_type=embedding_type,
            owner_id=owner_id,
            area_id=area_id,
            limit=limit
        )

        # Si no hay resultados, devolver lista vacía
        if not search_results:
            return []

        # Obtener IDs únicos de documentos
        doc_ids = list(set(result.get("doc_id") for result in search_results
                           if result.get("doc_id")))

        # Obtener información de los documentos
        documents = []
        for doc_id in doc_ids:
            try:
                doc_info = await self._get_document_info(
                    doc_id=doc_id,
                    embedding_type=embedding_type,
                    owner_id=owner_id
                )

                if doc_info:
                    # Encontrar el resultado de búsqueda correspondiente
                    for result in search_results:
                        if result.get("doc_id") == doc_id:
                            # Añadir snippet y score del resultado
                            doc_info.content = result.get("text", "")
                            doc_info.metadata["score"] = result.get("score", 0.0)
                            break

                    documents.append(doc_info)
            except Exception as e:
                logger.warning(f"Error retrieving document {doc_id}: {str(e)}")
                continue

        return documents

    async def _search_embeddings(self,
                                 query: str,
                                 embedding_type: EmbeddingType,
                                 owner_id: Optional[str] = None,
                                 area_id: Optional[str] = None,
                                 limit: int = 10) -> List[Dict[str, Any]]:
        """
        Realizar búsqueda semántica en el servicio de embeddings

        Args:
            query: Consulta del usuario
            embedding_type: Tipo de embedding
            owner_id: ID del propietario
            area_id: ID del área
            limit: Número máximo de resultados

        Returns:
            Lista de resultados de búsqueda
        """
        url = f"{self.embedding_service_url}/search"

        # Construir parámetros de consulta
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
                        logger.error(f"Error searching embeddings: {response.status} - {error_text}")
                        return []

                    data = await response.json()

                    # Filtrar resultados por umbral de similitud
                    threshold = self.settings.retrieval.similarity_threshold
                    filtered_results = [
                        result for result in data.get("results", [])
                        if result.get("score", 0) >= threshold
                    ]

                    return filtered_results
        except Exception as e:
            logger.error(f"Error searching embeddings: {str(e)}")
            return []

    async def _get_document_info(self,
                                 doc_id: str,
                                 embedding_type: EmbeddingType,
                                 owner_id: Optional[str] = None) -> Optional[DocumentInfo]:
        """
        Obtener información de un documento

        Args:
            doc_id: ID del documento
            embedding_type: Tipo de embedding
            owner_id: ID del propietario

        Returns:
            Información del documento o None si no se encuentra
        """
        # Determinar el endpoint según el tipo de embedding
        if embedding_type == EmbeddingType.PERSONAL:
            url = f"{self.document_service_url}/personal/{doc_id}"
        else:
            url = f"{self.document_service_url}/shared/{doc_id}"

        try:
            headers = {}
            if owner_id:
                # Añadir token de usuario para autenticación
                # En un entorno real, este token debería obtenerse de un servicio de autenticación
                headers["X-User-ID"] = owner_id

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        if response.status == 404:
                            logger.warning(f"Document not found: {doc_id}")
                            return None

                        error_text = await response.text()
                        logger.error(f"Error getting document: {response.status} - {error_text}")
                        return None

                    data = await response.json()

                    # Generar URL para acceder al documento
                    download_url = data.get("download_url", "")

                    return DocumentInfo(
                        id=data.get("id", doc_id),
                        title=data.get("title", "Unknown Document"),
                        url=download_url,
                        content="",  # El contenido se añadirá del resultado de búsqueda
                        metadata={
                            "file_name": data.get("file_name", ""),
                            "file_type": data.get("file_type", ""),
                            "doc_type": data.get("doc_type", ""),
                            "created_at": data.get("created_at", ""),
                            "score": 0.0  # Se actualizará con el score del resultado
                        }
                    )
        except Exception as e:
            logger.error(f"Error getting document {doc_id}: {str(e)}")
            return None

    def format_sources(self, documents: List[DocumentInfo]) -> List[Source]:
        """
        Formatear documentos como fuentes para la respuesta

        Args:
            documents: Lista de documentos

        Returns:
            Lista de fuentes formateadas
        """
        sources = []

        for doc in documents:
            # Limitar longitud del snippet
            snippet = doc.content
            if len(snippet) > self.settings.retrieval.max_source_length:
                snippet = snippet[:self.settings.retrieval.max_source_length] + "..."

            source = Source(
                id=doc.id,
                title=doc.title,
                url=doc.url,
                snippet=snippet,
                score=doc.metadata.get("score", 0.0)
            )
            sources.append(source)

        # Ordenar por puntuación descendente
        return sorted(sources, key=lambda s: s.score, reverse=True)

    @staticmethod
    def format_documents_for_context(documents: List[DocumentInfo]) -> str:
        """
        Formatear documentos para incluir en el contexto del prompt

        Args:
            documents: Lista de documentos

        Returns:
            Texto formateado con documentos numerados
        """
        if not documents:
            return "No se encontró información relevante."

        # Ordenar documentos por puntuación
        sorted_docs = sorted(documents, key=lambda d: d.metadata.get("score", 0.0), reverse=True)

        # Formatear cada documento con número de referencia
        context_parts = []
        for i, doc in enumerate(sorted_docs, 1):
            title = doc.title
            content = doc.content

            # Formatear como referencia
            doc_text = f"[{i}] {title}:\n{content}\n"
            context_parts.append(doc_text)

        return "\n".join(context_parts)