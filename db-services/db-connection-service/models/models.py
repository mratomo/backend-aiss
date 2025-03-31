# models/models.py
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field

class DBType(str, Enum):
    """Tipos de bases de datos soportados"""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    SQLSERVER = "sqlserver"
    ELASTICSEARCH = "elasticsearch"
    INFLUXDB = "influxdb"

class ConnectionStatus(str, Enum):
    """Estados posibles de una conexión"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"

class PermissionLevel(str, Enum):
    """Niveles de permiso para conexiones a BD"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

class DBConnection(BaseModel):
    """Modelo para una conexión a base de datos"""
    id: Optional[str] = None
    name: str
    type: DBType
    host: str
    port: int
    database: str
    username: str
    password: Optional[str] = None
    ssl: bool = False
    description: Optional[str] = None
    tags: List[str] = []
    options: Dict[str, str] = {}
    status: ConnectionStatus = ConnectionStatus.INACTIVE
    last_checked: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "name": "Producción PostgreSQL",
                "type": "postgresql",
                "host": "db.example.com",
                "port": 5432,
                "database": "production",
                "username": "readonly",
                "password": "secret",
                "ssl": True,
                "description": "Base de datos principal de producción",
                "tags": ["produccion", "principal"],
                "options": {"sslmode": "require"}
            }
        }

class DBConnectionResponse(BaseModel):
    """Modelo para respuesta de conexión (sin credenciales)"""
    id: str
    name: str
    type: DBType
    host: str
    port: int
    database: str
    username: str
    ssl: bool
    description: Optional[str] = None
    tags: List[str] = []
    status: ConnectionStatus
    last_checked: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

class DBConnectionUpdate(BaseModel):
    """Modelo para actualización de una conexión"""
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    ssl: Optional[bool] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    options: Optional[Dict[str, str]] = None

class AgentType(str, Enum):
    """Tipos de agentes DB"""
    DB_ONLY = "db-only"           # Solo consultas a BD
    RAG_DB = "rag+db"             # Combina RAG tradicional y BD

class DBAgent(BaseModel):
    """Modelo para un agente DB"""
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    type: AgentType = AgentType.RAG_DB
    model_id: str
    allowed_operations: List[str] = []
    max_result_size: int = 1000
    query_timeout_secs: int = 30
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    prompts: Dict[str, str] = {}
    default_system_prompt: Optional[str] = None

class DBAgentUpdate(BaseModel):
    """Modelo para actualización de un agente"""
    name: Optional[str] = None
    description: Optional[str] = None
    model_id: Optional[str] = None
    allowed_operations: Optional[List[str]] = None
    max_result_size: Optional[int] = None
    query_timeout_secs: Optional[int] = None
    active: Optional[bool] = None
    default_system_prompt: Optional[str] = None

class AgentPrompts(BaseModel):
    """Modelo para prompts de agente DB"""
    system_prompt: Optional[str] = None
    query_evaluation_prompt: Optional[str] = None
    query_generation_prompt: Optional[str] = None
    result_formatting_prompt: Optional[str] = None
    example_db_queries: Optional[str] = None

class ConnectionAssignment(BaseModel):
    """Modelo para asignación de conexión a agente"""
    id: Optional[str] = None
    agent_id: str
    connection_id: str
    permissions: List[PermissionLevel] = [PermissionLevel.READ]
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_by: Optional[str] = None

class ConnectionAssignmentResponse(BaseModel):
    """Modelo para respuesta de asignación"""
    id: str
    agent_id: str
    connection: DBConnectionResponse
    permissions: List[PermissionLevel]
    assigned_at: datetime
    assigned_by: Optional[str] = None

class QueryType(str, Enum):
    """Tipos de consultas"""
    RAG = "rag"                # Consulta RAG tradicional
    DB = "db"                  # Consulta directa a BD
    HYBRID = "hybrid"          # Consulta combinada

class QueryStatus(str, Enum):
    """Estados de una consulta"""
    PENDING = "pending"        # En espera
    PROCESSING = "processing"  # Procesando
    COMPLETED = "completed"    # Completada con éxito
    FAILED = "failed"          # Fallida

class GeneratedQuery(BaseModel):
    """Modelo para una consulta generada"""
    connection_id: str
    query_text: str
    parameters: Dict[str, Any] = {}

class DBQueryExecution(BaseModel):
    """Modelo para ejecución de consulta a BD"""
    id: Optional[str] = None
    user_id: str
    agent_id: str
    query_type: QueryType
    original_query: str
    generated_queries: List[GeneratedQuery] = []
    rag_used: bool = False
    status: QueryStatus = QueryStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

class DBQueryRequest(BaseModel):
    """Modelo para solicitud de consulta a BD"""
    agent_id: str
    query: str
    connections: List[str] = []
    options: Dict[str, Any] = {}

class DBQueryResponse(BaseModel):
    """Modelo para respuesta de consulta a BD"""
    id: str
    query_type: QueryType
    answer: str
    generated_queries: List[GeneratedQuery] = []
    execution_time_ms: int
    has_error: bool = False
    error_message: Optional[str] = None
    timestamp: datetime

class QueryHistoryItem(BaseModel):
    """Modelo para item de historial de consultas"""
    id: str
    original_query: str
    query_type: QueryType
    status: QueryStatus
    execution_time_ms: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None