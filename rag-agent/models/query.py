from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union, Any

from pydantic import BaseModel, Field

class QueryType(str, Enum):
    """Tipos de consultas"""
    RAG = "rag"                # Consulta RAG tradicional
    DB = "db"                  # Consulta a base de datos
    HYBRID = "hybrid"          # Consulta híbrida (RAG + DB)
    GRAPH = "graph"            # Consulta GraphRAG con Neo4j

# Modelos para solicitudes de consulta

class QueryRequest(BaseModel):
    """Solicitud para una consulta general RAG"""
    query: str = Field(..., description="Consulta del usuario")
    user_id: str = Field(..., description="ID del usuario que realiza la consulta")
    include_personal: bool = Field(True, description="Incluir conocimiento personal del usuario")
    area_ids: Optional[List[str]] = Field(None, description="IDs de áreas específicas para consultar")
    llm_provider_id: Optional[str] = Field(None, description="ID del proveedor LLM a utilizar")
    max_sources: int = Field(5, ge=1, le=20, description="Número máximo de fuentes a incluir")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="Temperatura para generación")
    max_tokens: Optional[int] = Field(None, ge=1, description="Número máximo de tokens en la respuesta")
    advanced_settings: Optional[Dict[str, Any]] = Field(None, description="Configuraciones avanzadas para la generación")


class AreaQueryRequest(BaseModel):
    """Solicitud para una consulta RAG en un área específica"""
    query: str = Field(..., description="Consulta del usuario")
    user_id: str = Field(..., description="ID del usuario que realiza la consulta")
    llm_provider_id: Optional[str] = Field(None, description="ID del proveedor LLM a utilizar")
    max_sources: int = Field(5, ge=1, le=20, description="Número máximo de fuentes a incluir")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="Temperatura para generación")
    max_tokens: Optional[int] = Field(None, ge=1, description="Número máximo de tokens en la respuesta")
    advanced_settings: Optional[Dict[str, Any]] = Field(None, description="Configuraciones avanzadas para la generación")


class PersonalQueryRequest(BaseModel):
    """Solicitud para una consulta RAG en conocimiento personal"""
    query: str = Field(..., description="Consulta del usuario")
    user_id: str = Field(..., description="ID del usuario que realiza la consulta")
    llm_provider_id: Optional[str] = Field(None, description="ID del proveedor LLM a utilizar")
    max_sources: int = Field(5, ge=1, le=20, description="Número máximo de fuentes a incluir")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="Temperatura para generación")
    max_tokens: Optional[int] = Field(None, ge=1, description="Número máximo de tokens en la respuesta")
    advanced_settings: Optional[Dict[str, Any]] = Field(None, description="Configuraciones avanzadas para la generación")


# Modelos para resultados y respuestas

class Source(BaseModel):
    """Información sobre una fuente utilizada en la respuesta"""
    id: str = Field(..., description="ID del documento")
    title: str = Field(..., description="Título del documento")
    url: Optional[str] = Field(None, description="URL para acceder al documento")
    snippet: str = Field(..., description="Fragmento relevante del documento")
    score: float = Field(..., description="Puntuación de relevancia")


class LLMUsage(BaseModel):
    """Información de uso de LLM"""
    model: str
    provider: str
    tokens_prompt: int
    tokens_completion: int
    cost: Optional[float] = None


class ContentChunk(BaseModel):
    """Fragmento de contenido recuperado"""
    text: str
    source: str
    relevance_score: float
    metadata: Optional[Dict[str, Any]] = None


class GeneratedDBQuery(BaseModel):
    """Consulta generada para base de datos"""
    connection_id: str
    connection_name: str
    query_text: str


class QueryResult(BaseModel):
    """Resultado de una consulta"""
    id: str
    query: str
    answer: str
    query_type: QueryType = QueryType.RAG
    has_error: bool = False
    error_message: Optional[str] = None
    execution_time_ms: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    relevance_score: Optional[float] = None
    content_chunks: Optional[List[ContentChunk]] = None
    llm_usage: Optional[LLMUsage] = None
    generated_queries: Optional[List[GeneratedDBQuery]] = None


class QueryResponse(BaseModel):
    """Respuesta a una consulta RAG"""
    query: str = Field(..., description="Consulta original")
    answer: str = Field(..., description="Respuesta generada")
    sources: List[Source] = Field(default_factory=list, description="Fuentes utilizadas")
    llm_provider: str = Field(..., description="Proveedor LLM utilizado")
    model: str = Field(..., description="Modelo utilizado")
    processing_time_ms: int = Field(..., description="Tiempo de procesamiento en ms")
    query_id: str = Field(..., description="ID único de la consulta")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    query_type: QueryType = QueryType.RAG
    generated_queries: Optional[List[GeneratedDBQuery]] = None


class QueryHistoryItem(BaseModel):
    """Elemento de historial de consultas en la base de datos"""
    query_id: str = Field(..., description="ID único de la consulta")
    user_id: str = Field(..., description="ID del usuario que realizó la consulta")
    query: str = Field(..., description="Consulta realizada")
    answer: str = Field(..., description="Respuesta generada")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Fuentes utilizadas")
    llm_provider_id: str = Field(..., description="ID del proveedor LLM utilizado")
    llm_provider_name: str = Field(..., description="Nombre del proveedor LLM utilizado")
    model: str = Field(..., description="Modelo utilizado")
    area_ids: Optional[List[str]] = Field(None, description="IDs de áreas consultadas")
    include_personal: bool = Field(False, description="Si se incluyó conocimiento personal")
    processing_time_ms: int = Field(..., description="Tiempo de procesamiento en ms")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    temperature: Optional[float] = Field(None, description="Temperatura utilizada")
    max_tokens: Optional[int] = Field(None, description="Número máximo de tokens utilizado")
    advanced_settings: Optional[Dict[str, Any]] = Field(None, description="Configuraciones avanzadas utilizadas")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadatos adicionales")
    query_type: QueryType = Field(QueryType.RAG, description="Tipo de consulta")
    generated_queries: Optional[List[Dict[str, Any]]] = Field(None, description="Consultas generadas para BD")
    agent_id: Optional[str] = Field(None, description="ID del agente DB utilizado")


class QueryHistoryResponse(BaseModel):
    """Respuesta de historial de consultas para la API"""
    query_id: str
    query: str
    answer: str
    sources: List[Source]
    llm_provider: str
    model: str
    processing_time_ms: int
    created_at: datetime
    query_type: QueryType = QueryType.RAG
    generated_queries: Optional[List[GeneratedDBQuery]] = None
    agent_id: Optional[str] = None

    @classmethod
    def from_db_model(cls, item: Dict[str, Any]) -> "QueryHistoryResponse":
        # Convertir fuentes al formato de respuesta
        sources = []
        for source in item.get("sources", []):
            sources.append(Source(
                id=source.get("id", ""),
                title=source.get("title", ""),
                url=source.get("url"),
                snippet=source.get("snippet", ""),
                score=source.get("score", 0.0)
            ))

        # Convertir consultas generadas si existen
        generated_queries = None
        if item.get("generated_queries"):
            generated_queries = []
            for query in item.get("generated_queries", []):
                generated_queries.append(GeneratedDBQuery(
                    connection_id=query.get("connection_id", ""),
                    connection_name=query.get("connection_name", ""),
                    query_text=query.get("query_text", "")
                ))

        return cls(
            query_id=item.get("query_id", ""),
            query=item.get("query", ""),
            answer=item.get("answer", ""),
            sources=sources,
            llm_provider=item.get("llm_provider_name", ""),
            model=item.get("model", ""),
            processing_time_ms=item.get("processing_time_ms", 0),
            created_at=item.get("created_at", datetime.utcnow()),
            query_type=item.get("query_type", QueryType.RAG),
            generated_queries=generated_queries,
            agent_id=item.get("agent_id")
        )


class DBQueryRequest(BaseModel):
    """Solicitud de consulta a base de datos"""
    agent_id: str
    query: str
    connections: Optional[List[str]] = None
    options: Optional[Dict[str, Any]] = None


class GraphQueryRequest(BaseModel):
    """Solicitud para una consulta GraphRAG"""
    query: str = Field(..., description="Consulta del usuario")
    user_id: str = Field(..., description="ID del usuario que realiza la consulta")
    connection_id: Optional[str] = Field(None, description="ID de la conexión de base de datos")
    area_id: Optional[str] = Field(None, description="ID del área específica para consultar")
    llm_provider_id: Optional[str] = Field(None, description="ID del proveedor LLM a utilizar")
    max_sources: int = Field(5, ge=1, le=20, description="Número máximo de fuentes a incluir")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="Temperatura para generación")
    max_tokens: Optional[int] = Field(None, ge=1, description="Número máximo de tokens en la respuesta")
    exploration_depth: Optional[int] = Field(2, ge=1, le=5, description="Profundidad de exploración del grafo")
    include_communities: bool = Field(True, description="Incluir información de comunidades en el grafo")
    include_paths: bool = Field(True, description="Incluir caminos entre entidades en el grafo")
