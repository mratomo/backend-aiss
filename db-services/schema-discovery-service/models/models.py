# models/models.py
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field

class SchemaDiscoveryStatus(str, Enum):
    """Estados de descubrimiento de esquemas"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class ColumnSchema(BaseModel):
    """Información de una columna de base de datos"""
    name: str
    data_type: str
    description: Optional[str] = None
    nullable: bool = True
    is_primary: bool = False
    is_foreign: bool = False
    references: Optional[str] = None
    sample_values: Optional[List[Any]] = None
    stats: Optional[Dict[str, Any]] = None

class TableSchema(BaseModel):
    """Información de una tabla de base de datos"""
    name: str
    schema: Optional[str] = None
    description: Optional[str] = None
    rows_count: int = 0
    columns: List[ColumnSchema] = []
    is_collection: bool = False  # Para MongoDB

class DatabaseSchema(BaseModel):
    """Información de esquema de una base de datos"""
    connection_id: str
    name: str
    type: str
    description: Optional[str] = None
    version: Optional[str] = None
    tables: Optional[List[TableSchema]] = []
    status: SchemaDiscoveryStatus = SchemaDiscoveryStatus.PENDING
    discovery_date: datetime = Field(default_factory=datetime.utcnow)
    vector_id: Optional[str] = None
    error: Optional[str] = None

class SchemaDiscoveryOptions(BaseModel):
    """Opciones para descubrimiento de esquemas"""
    include_sample_data: bool = True
    include_statistics: bool = True
    max_tables: Optional[int] = None
    max_rows_per_table: Optional[int] = None
    excluded_schemas: List[str] = ["pg_catalog", "information_schema"]
    excluded_tables: List[str] = []
    generate_embeddings: bool = True

class SchemaDiscoveryRequest(BaseModel):
    """Solicitud de descubrimiento de esquema"""
    connection_id: str
    options: Optional[SchemaDiscoveryOptions] = None

class SchemaDiscoveryResponse(BaseModel):
    """Respuesta a solicitud de descubrimiento de esquema"""
    job_id: str
    connection_id: str
    status: SchemaDiscoveryStatus
    started_at: datetime
    estimated_completion_time: Optional[datetime] = None

class SchemaQuerySuggestion(BaseModel):
    """Sugerencia de consulta para un esquema"""
    title: str
    description: str
    sql_query: str

class SchemaInsight(BaseModel):
    """Insight sobre un esquema"""
    type: str  # "info", "warning", "performance", "suggestion"
    title: str
    description: str
    recommendation: Optional[str] = None

class SchemaAnalysisResponse(BaseModel):
    """Respuesta de análisis de esquema"""
    connection_id: str
    insights: List[SchemaInsight] = []
    query_suggestions: List[SchemaQuerySuggestion] = []
    analysis_date: datetime = Field(default_factory=datetime.utcnow)