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
    primary_key: bool = False
    foreign_key: Optional[Dict[str, str]] = None
    sample_values: Optional[List[Any]] = None
    stats: Optional[Dict[str, Any]] = None
    tags: List[str] = []

class TableSchema(BaseModel):
    """Información de una tabla de base de datos"""
    name: str
    schema: Optional[str] = None
    description: Optional[str] = None
    columns: List[ColumnSchema] = []
    primary_keys: List[str] = []
    foreign_keys: List[Dict[str, Any]] = []
    indexes: List[Dict[str, Any]] = []
    row_count: Optional[int] = None
    sample_queries: List[str] = []
    tags: List[str] = []

class DatabaseSchema(BaseModel):
    """Información de esquema de una base de datos"""
    connection_id: str
    name: str
    type: str
    tables: List[TableSchema] = []
    functions: List[Dict[str, Any]] = []
    procedures: List[Dict[str, Any]] = []
    views: List[Dict[str, Any]] = []
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
    table_name: str
    query: str
    description: str

class SchemaInsightType(str, Enum):
    """Tipos de insights sobre esquemas"""
    DATA_QUALITY = "data_quality"
    PERFORMANCE = "performance"
    SCHEMA_DESIGN = "schema_design"
    SECURITY = "security"

class SchemaInsight(BaseModel):
    """Insight sobre un esquema"""
    type: SchemaInsightType
    title: str
    description: str
    recommendation: Optional[str] = None
    severity: str
    affected_tables: List[str] = []
    affected_columns: List[Dict[str, str]] = []

class SchemaAnalysisResponse(BaseModel):
    """Respuesta de análisis de esquema"""
    connection_id: str
    insights: List[SchemaInsight] = []
    query_suggestions: List[SchemaQuerySuggestion] = []
    analysis_date: datetime = Field(default_factory=datetime.utcnow)