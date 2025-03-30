from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

class EmbeddingType(str, Enum):
    """Tipos de embeddings soportados"""
    GENERAL = "general"    # Conocimiento general (áreas)
    PERSONAL = "personal"  # Conocimiento personal (usuario)

class EmbeddingRequest(BaseModel):
    """Solicitud para generar un embedding"""
    text: str = Field(..., description="Texto para generar el embedding")
    embedding_type: EmbeddingType = Field(..., description="Tipo de embedding a generar")
    doc_id: str = Field(..., description="ID del documento asociado")
    owner_id: str = Field(..., description="ID del propietario")
    area_id: Optional[str] = Field(None, description="ID del área (para conocimiento general)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadatos adicionales")

class EmbeddingResponse(BaseModel):
    """Respuesta con información del embedding generado"""
    embedding_id: str = Field(..., description="ID único del embedding generado")
    doc_id: str = Field(..., description="ID del documento asociado")
    embedding_type: EmbeddingType = Field(..., description="Tipo de embedding generado")
    context_id: Optional[str] = Field(None, description="ID del contexto MCP asociado")
    owner_id: str = Field(..., description="ID del propietario")
    area_id: Optional[str] = Field(None, description="ID del área")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(..., description="Estado del procesamiento")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class EmbeddingBatchRequest(BaseModel):
    """Solicitud para generar embeddings en batch"""
    texts: List[str] = Field(..., description="Lista de textos para generar embeddings")
    embedding_type: EmbeddingType = Field(..., description="Tipo de embedding a generar")
    doc_ids: List[str] = Field(..., description="Lista de IDs de documentos asociados")
    owner_id: str = Field(..., description="ID del propietario")
    area_id: Optional[str] = Field(None, description="ID del área (para conocimiento general)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadatos adicionales")

class EmbeddingBatchResponse(BaseModel):
    """Respuesta con información de los embeddings generados en batch"""
    embeddings: List[EmbeddingResponse] = Field(..., description="Lista de embeddings generados")

class SearchResult(BaseModel):
    """Resultado de búsqueda"""
    embedding_id: str = Field(..., description="ID del embedding")
    doc_id: str = Field(..., description="ID del documento asociado")
    score: float = Field(..., description="Puntuación de similitud (0-1)")
    text: Optional[str] = Field(None, description="Texto correspondiente")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SearchResponse(BaseModel):
    """Respuesta de búsqueda"""
    results: List[SearchResult] = Field(..., description="Resultados de la búsqueda")

class EmbeddingDB(BaseModel):
    """Modelo de embedding en la base de datos"""
    embedding_id: str = Field(..., description="ID único del embedding")
    doc_id: str = Field(..., description="ID del documento asociado")
    embedding_type: EmbeddingType = Field(..., description="Tipo de embedding")
    context_id: Optional[str] = Field(None, description="ID del contexto MCP asociado")
    owner_id: str = Field(..., description="ID del propietario")
    area_id: Optional[str] = Field(None, description="ID del área")
    vector_id: str = Field(..., description="ID del vector en la base de datos vectorial")
    collection_name: str = Field(..., description="Nombre de la colección en la base de datos vectorial")
    text_snippet: Optional[str] = Field(None, description="Fragmento del texto (para referencia)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class DocumentChunk(BaseModel):
    """Chunk de un documento para procesamiento"""
    chunk_id: str = Field(..., description="ID único del chunk")
    doc_id: str = Field(..., description="ID del documento original")
    text: str = Field(..., description="Texto del chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    chunk_index: int = Field(..., description="Índice del chunk en el documento")
    total_chunks: int = Field(..., description="Número total de chunks del documento")
