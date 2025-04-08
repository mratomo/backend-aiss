import logging
import time
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from config.settings import Settings
from models.embedding import EmbeddingType
from models.query import QueryResponse, QueryHistoryItem, QueryHistoryResponse, Source
from services.llm_service import LLMService
from services.mcp_service import MCPService
from services.retrieval_service import RetrievalService, DocumentInfo

logger = logging.getLogger(__name__)

class QueryService:
    """Servicio para procesar consultas y gestionar el historial"""

    def __init__(self,
                 database: AsyncIOMotorDatabase,
                 llm_service: LLMService,
                 retrieval_service: RetrievalService,
                 mcp_service: MCPService,
                 settings: Settings,
                 ollama_service=None):
        """
        Inicializar servicio con dependencias y configuración
        
        Args:
            database: Base de datos MongoDB
            llm_service: Servicio para LLMs
            retrieval_service: Servicio para recuperación
            mcp_service: Servicio MCP
            settings: Configuración
            ollama_service: Servicio opcional para Ollama MCP
        """
        self.db = database
        self.history_collection = database.query_history
        self.llm_service = llm_service
        self.retrieval_service = retrieval_service
        self.mcp_service = mcp_service
        self.settings = settings
        self.ollama_service = ollama_service

    async def process_query(self,
                            query: str,
                            user_id: str,
                            include_personal: bool = True,
                            area_ids: Optional[List[str]] = None,
                            llm_provider_id: Optional[str] = None,
                            max_sources: int = 5,
                            temperature: Optional[float] = None,
                            max_tokens: Optional[int] = None) -> QueryResponse:
        """
        Procesar una consulta RAG general

        Args:
            query: Consulta del usuario
            user_id: ID del usuario
            include_personal: Incluir conocimiento personal
            area_ids: Lista de IDs de áreas específicas
            llm_provider_id: ID del proveedor LLM a utilizar
            max_sources: Número máximo de fuentes a incluir
            temperature: Temperatura para generación
            max_tokens: Número máximo de tokens

        Returns:
            Respuesta a la consulta
        """
        # Iniciar temporizador
        start_time = time.time()

        # Generar ID único para la consulta
        query_id = str(uuid.uuid4())

        # Determinar IDs de contextos MCP a activar
        mcp_contexts = []

        # Añadir contextos de áreas específicas
        if area_ids:
            for area_id in area_ids:
                area = await self.mcp_service.get_area(area_id)
                if area and area.get("mcp_context_id"):
                    mcp_contexts.append(area["mcp_context_id"])

        # Añadir contexto personal si se solicita
        if include_personal:
            personal_context = await self.mcp_service.get_personal_context_id(user_id)
            if personal_context:
                mcp_contexts.append(personal_context)

        # Verificar si vamos a usar búsqueda basada en herramientas MCP
        use_mcp_retrieval = self.settings.use_mcp_tools and self.llm_service.mcp_client and self.llm_service.has_find_tool

        # Recuperar documentos relevantes
        documents = []

        if use_mcp_retrieval:
            # Usar herramienta MCP find_relevant cuando disponible
            context_texts = []

            # Recuperar de áreas específicas con MCP
            if area_ids:
                for area_id in area_ids:
                    area_results = await self.llm_service.find_relevant_information(
                        query=query,
                        embedding_type="general",
                        area_id=area_id,
                        limit=max_sources
                    )
                    if area_results and isinstance(area_results, list) and len(area_results) > 0:
                        context_texts.extend(area_results)
            else:
                # Si no se especifican áreas, buscar en todas
                general_results = await self.llm_service.find_relevant_information(
                    query=query,
                    embedding_type="general",
                    limit=max_sources
                )
                if general_results and isinstance(general_results, list) and len(general_results) > 0:
                    context_texts.extend(general_results)

            # Recuperar documentos personales si es necesario
            if include_personal:
                personal_results = await self.llm_service.find_relevant_information(
                    query=query,
                    embedding_type="personal",
                    owner_id=user_id,
                    limit=max_sources
                )
                if personal_results and isinstance(personal_results, list) and len(personal_results) > 0:
                    context_texts.extend(personal_results)

            # Convertir resultados MCP a formato DocumentInfo para mantener compatibilidad
            for i, text in enumerate(context_texts):
                # Extraer score e ID del formato "[Doc N] (score): text"
                score = 0.0
                doc_id = f"mcp_result_{i}"

                if text.startswith("[Doc") and "]" in text:
                    parts = text.split("]", 1)
                    if len(parts) > 1 and "(" in parts[0] and ")" in parts[0]:
                        score_part = parts[0].split("(")[1].split(")")[0]
                        try:
                            score = float(score_part)
                        except:
                            pass

                        content = parts[1].strip()
                    else:
                        content = text
                else:
                    content = text

                # Crear documento sintético con el resultado
                doc = DocumentInfo(
                    id=doc_id,
                    title=f"Resultado {i+1}",
                    content=content,
                    metadata={"score": score}
                )
                documents.append(doc)

        else:
            # Método tradicional: usar RetrievalService
            # Recuperar de áreas específicas
            if area_ids:
                for area_id in area_ids:
                    area_docs = await self.retrieval_service.retrieve_documents(
                        query=query,
                        embedding_type=EmbeddingType.GENERAL,
                        area_id=area_id,
                        limit=max_sources
                    )
                    documents.extend(area_docs)
            else:
                # Si no se especifican áreas, buscar en todas
                general_docs = await self.retrieval_service.retrieve_documents(
                    query=query,
                    embedding_type=EmbeddingType.GENERAL,
                    limit=max_sources
                )
                documents.extend(general_docs)

            # Recuperar documentos personales si es necesario
            if include_personal:
                personal_docs = await self.retrieval_service.retrieve_documents(
                    query=query,
                    embedding_type=EmbeddingType.PERSONAL,
                    owner_id=user_id,
                    limit=max_sources
                )
                documents.extend(personal_docs)

        # Limitar al número máximo de fuentes y ordenar por relevancia
        documents = sorted(documents, key=lambda d: d.metadata.get("score", 0.0), reverse=True)[:max_sources]

        # Formatear documentos para el contexto
        context_text = self.retrieval_service.format_documents_for_context(documents)

        # Formatear prompt final
        prompt = self.settings.rag_prompt_template.format(
            query=query,
            context=context_text
        )

        # Decisión: usar LLM con soporte MCP nativo o método tradicional
        # Si el proveedor soporta MCP nativo y tenemos contextos, los pasamos directamente
        llm_response = await self.llm_service.generate_text(
            prompt=prompt,
            system_prompt=self.settings.mcp.default_system_prompt,
            provider_id=llm_provider_id,
            max_tokens=max_tokens,
            temperature=temperature,
            active_contexts=mcp_contexts if self.settings.prefer_direct_mcp else None
        )

        # Formatear fuentes para la respuesta
        sources = self.retrieval_service.format_sources(documents)

        # Calcular tiempo de procesamiento
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Crear respuesta
        response = QueryResponse(
            query=query,
            answer=llm_response["text"],
            sources=sources,
            llm_provider=llm_response["provider_name"],
            model=llm_response["model"],
            processing_time_ms=processing_time_ms,
            query_id=query_id,
            timestamp=datetime.utcnow()
        )

        # Guardar en historial
        await self._save_to_history(
            query_id=query_id,
            user_id=user_id,
            query=query,
            answer=response.answer,
            sources=sources,
            llm_provider_id=llm_response["provider_id"],
            llm_provider_name=llm_response["provider_name"],
            model=llm_response["model"],
            area_ids=area_ids,
            include_personal=include_personal,
            processing_time_ms=processing_time_ms,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response

    async def process_area_query(self,
                                 query: str,
                                 user_id: str,
                                 area_id: str,
                                 llm_provider_id: Optional[str] = None,
                                 max_sources: int = 5,
                                 temperature: Optional[float] = None,
                                 max_tokens: Optional[int] = None) -> QueryResponse:
        """
        Procesar una consulta RAG en un área específica

        Args:
            query: Consulta del usuario
            user_id: ID del usuario
            area_id: ID del área
            llm_provider_id: ID del proveedor LLM
            max_sources: Número máximo de fuentes
            temperature: Temperatura para generación
            max_tokens: Número máximo de tokens

        Returns:
            Respuesta a la consulta
        """
        # Obtener system prompt específico del área
        area_system_prompt = await self.mcp_service.get_area_system_prompt(area_id)
        # Usar system prompt del área si existe, o el global si no
        system_prompt = area_system_prompt or self.settings.mcp.default_system_prompt

        start_time = time.time()
        query_id = str(uuid.uuid4())

        # Obtener contexto MCP del área
        area = await self.mcp_service.get_area(area_id)
        mcp_contexts = []

        if area and area.get("mcp_context_id"):
            mcp_contexts.append(area["mcp_context_id"])

        # Recuperar documentos relevantes
        documents = []

        # Verificar si vamos a usar búsqueda basada en herramientas MCP
        use_mcp_retrieval = self.settings.use_mcp_tools and self.llm_service.mcp_client and self.llm_service.has_find_tool

        if use_mcp_retrieval:
            # Usar herramienta MCP find_relevant
            context_texts = await self.llm_service.find_relevant_information(
                query=query,
                embedding_type="general",
                area_id=area_id,
                limit=max_sources
            )

            # Convertir resultados a formato DocumentInfo
            for i, text in enumerate(context_texts):
                # Extraer score e ID del formato "[Doc N] (score): text"
                score = 0.0
                doc_id = f"mcp_result_{i}"

                if text.startswith("[Doc") and "]" in text:
                    parts = text.split("]", 1)
                    if len(parts) > 1 and "(" in parts[0] and ")" in parts[0]:
                        score_part = parts[0].split("(")[1].split(")")[0]
                        try:
                            score = float(score_part)
                        except:
                            pass

                        content = parts[1].strip()
                    else:
                        content = text
                else:
                    content = text

                # Crear documento sintético
                doc = DocumentInfo(
                    id=doc_id,
                    title=f"Resultado {i+1}",
                    content=content,
                    metadata={"score": score}
                )
                documents.append(doc)
        else:
            # Método tradicional: usar RetrievalService
            documents = await self.retrieval_service.retrieve_documents(
                query=query,
                embedding_type=EmbeddingType.GENERAL,
                area_id=area_id,
                limit=max_sources
            )

        # Formatear documentos para el contexto
        context_text = self.retrieval_service.format_documents_for_context(documents)

        # Formatear prompt final
        prompt = self.settings.rag_prompt_template.format(
            query=query,
            context=context_text
        )

        # Generar respuesta con LLM
        llm_response = await self.llm_service.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            provider_id=llm_provider_id,
            max_tokens=max_tokens,
            temperature=temperature,
            active_contexts=mcp_contexts if self.settings.prefer_direct_mcp else None
        )

        # Formatear fuentes para la respuesta
        sources = self.retrieval_service.format_sources(documents)
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Crear objeto de respuesta
        response = QueryResponse(
            query=query,
            answer=llm_response["text"],
            sources=sources,
            llm_provider=llm_response["provider_name"],
            model=llm_response["model"],
            processing_time_ms=processing_time_ms,
            query_id=query_id,
            timestamp=datetime.utcnow()
        )

        # Guardar en historial
        await self._save_to_history(
            query_id=query_id,
            user_id=user_id,
            query=query,
            answer=response.answer,
            sources=sources,
            llm_provider_id=llm_response["provider_id"],
            llm_provider_name=llm_response["provider_name"],
            model=llm_response["model"],
            area_ids=[area_id],
            include_personal=False,
            processing_time_ms=processing_time_ms,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response

    async def process_personal_query(self,
                                     query: str,
                                     user_id: str,
                                     llm_provider_id: Optional[str] = None,
                                     max_sources: int = 5,
                                     temperature: Optional[float] = None,
                                     max_tokens: Optional[int] = None) -> QueryResponse:
        """
        Procesar una consulta RAG sólo en conocimiento personal

        Args:
            query: Consulta del usuario
            user_id: ID del usuario
            llm_provider_id: ID del proveedor LLM
            max_sources: Número máximo de fuentes
            temperature: Temperatura para generación
            max_tokens: Número máximo de tokens

        Returns:
            Respuesta a la consulta
        """
        # Iniciar temporizador
        start_time = time.time()
        query_id = str(uuid.uuid4())

        # Obtener contexto MCP personal
        personal_context_id = await self.mcp_service.get_personal_context_id(user_id)
        mcp_contexts = []

        if personal_context_id:
            mcp_contexts.append(personal_context_id)

        # Recuperar documentos relevantes
        documents = []

        # Verificar si vamos a usar búsqueda basada en herramientas MCP
        use_mcp_retrieval = self.settings.use_mcp_tools and self.llm_service.mcp_client and self.llm_service.has_find_tool

        if use_mcp_retrieval:
            # Usar herramienta MCP find_relevant
            context_texts = await self.llm_service.find_relevant_information(
                query=query,
                embedding_type="personal",
                owner_id=user_id,
                limit=max_sources
            )

            # Convertir resultados a formato DocumentInfo
            for i, text in enumerate(context_texts):
                # Extraer información
                score = 0.0
                doc_id = f"mcp_personal_{i}"

                if text.startswith("[Doc") and "]" in text:
                    parts = text.split("]", 1)
                    if len(parts) > 1 and "(" in parts[0] and ")" in parts[0]:
                        score_part = parts[0].split("(")[1].split(")")[0]
                        try:
                            score = float(score_part)
                        except:
                            pass

                        content = parts[1].strip()
                    else:
                        content = text
                else:
                    content = text

                # Crear documento sintético
                doc = DocumentInfo(
                    id=doc_id,
                    title=f"Documento Personal {i+1}",
                    content=content,
                    metadata={"score": score}
                )
                documents.append(doc)
        else:
            # Método tradicional: usar RetrievalService
            documents = await self.retrieval_service.retrieve_documents(
                query=query,
                embedding_type=EmbeddingType.PERSONAL,
                owner_id=user_id,
                limit=max_sources
            )

        # Formatear documentos para el contexto
        context_text = self.retrieval_service.format_documents_for_context(documents)

        # Formatear prompt final
        prompt = self.settings.rag_prompt_template.format(
            query=query,
            context=context_text
        )

        # Generar respuesta con LLM
        llm_response = await self.llm_service.generate_text(
            prompt=prompt,
            system_prompt=self.settings.mcp.default_system_prompt,
            provider_id=llm_provider_id,
            max_tokens=max_tokens,
            temperature=temperature,
            active_contexts=mcp_contexts if self.settings.prefer_direct_mcp else None
        )

        # Formatear fuentes para la respuesta
        sources = self.retrieval_service.format_sources(documents)
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Crear respuesta
        response = QueryResponse(
            query=query,
            answer=llm_response["text"],
            sources=sources,
            llm_provider=llm_response["provider_name"],
            model=llm_response["model"],
            processing_time_ms=processing_time_ms,
            query_id=query_id,
            timestamp=datetime.utcnow()
        )

        # Guardar en historial
        await self._save_to_history(
            query_id=query_id,
            user_id=user_id,
            query=query,
            answer=response.answer,
            sources=sources,
            llm_provider_id=llm_response["provider_id"],
            llm_provider_name=llm_response["provider_name"],
            model=llm_response["model"],
            area_ids=None,
            include_personal=True,
            processing_time_ms=processing_time_ms,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response

    async def _save_to_history(self,
                               query_id: str,
                               user_id: str,
                               query: str,
                               answer: str,
                               sources: List[Source],
                               llm_provider_id: str,
                               llm_provider_name: str,
                               model: str,
                               area_ids: Optional[List[str]],
                               include_personal: bool,
                               processing_time_ms: int,
                               temperature: Optional[float] = None,
                               max_tokens: Optional[int] = None) -> None:
        """
        Guardar consulta en el historial

        Args:
            query_id: ID de la consulta
            user_id: ID del usuario
            query: Consulta realizada
            answer: Respuesta generada
            sources: Fuentes utilizadas
            llm_provider_id: ID del proveedor LLM
            llm_provider_name: Nombre del proveedor LLM
            model: Modelo utilizado
            area_ids: IDs de áreas consultadas
            include_personal: Si se incluyó conocimiento personal
            processing_time_ms: Tiempo de procesamiento en ms
            temperature: Temperatura utilizada
            max_tokens: Número máximo de tokens utilizado
        """
        # Convertir fuentes a formato para almacenamiento
        sources_dict = [source.dict() for source in sources]

        # Crear documento para historial
        history_item = {
            "query_id": query_id,
            "user_id": user_id,
            "query": query,
            "answer": answer,
            "sources": sources_dict,
            "llm_provider_id": llm_provider_id,
            "llm_provider_name": llm_provider_name,
            "model": model,
            "area_ids": area_ids,
            "include_personal": include_personal,
            "processing_time_ms": processing_time_ms,
            "created_at": datetime.utcnow(),
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Guardar en la base de datos
        await self.history_collection.insert_one(history_item)

    async def get_query_history(self,
                                user_id: str,
                                limit: int = 10,
                                offset: int = 0) -> List[QueryHistoryResponse]:
        """
        Obtener historial de consultas de un usuario

        Args:
            user_id: ID del usuario
            limit: Número máximo de resultados
            offset: Número de resultados a saltar

        Returns:
            Lista de consultas históricas
        """
        # Buscar en la base de datos
        cursor = self.history_collection.find(
            {"user_id": user_id}
        ).sort(
            "created_at", -1  # Ordenar por fecha descendente
        ).skip(offset).limit(limit)

        history_items = await cursor.to_list(length=limit)

        # Convertir a modelo de respuesta
        return [QueryHistoryResponse.from_db_model(item) for item in history_items]