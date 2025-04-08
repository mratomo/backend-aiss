import logging
import os
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
import platform

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Query, Path, Body, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.exceptions import RequestValidationError
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

try:
    import uvloop
    uvloop.install()
    uvloop_available = True
except ImportError:
    uvloop_available = False

from config.settings import Settings
from models.models import (
    DBConnection, DBConnectionResponse, DBConnectionUpdate,
    DBAgent, DBAgentUpdate, AgentPrompts, ConnectionAssignment,
    ConnectionAssignmentResponse, DBQueryRequest, DBQueryResponse,
    QueryHistoryItem
)
from services.connection_service import ConnectionService
from services.agent_service import AgentService
from services.encryption_service import EncryptionService
from services.security_service import SecurityService

# Configurar logging estructurado
try:
    import structlog
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logger = structlog.get_logger("db_connection_service")
    structlog_available = True
except ImportError:
    # Fallback a logging tradicional
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("db_connection_service")
    structlog_available = False

# Métricas para Prometheus
HTTP_REQUESTS = Counter('http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'status'])
HTTP_REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP Request Duration', ['method', 'endpoint'])
DB_OPERATIONS = Counter('db_operations_total', 'Total Database Operations', ['operation', 'status'])
DB_OPERATION_DURATION = Histogram('db_operation_duration_seconds', 'Database Operation Duration', ['operation'])

# Cargar configuración
settings = Settings()

# Crear aplicación FastAPI con respuestas optimizadas
app = FastAPI(
    title="DB Connection Service",
    description="Servicio de gestión de conexiones a bases de datos",
    version="1.1.0",
    default_response_class=ORJSONResponse,
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware para métricas
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    
    # Extraer información de la ruta
    path = request.url.path
    method = request.method
    
    try:
        # Procesar la solicitud
        response = await call_next(request)
        status_code = response.status_code
        
    except Exception as e:
        status_code = 500
        raise e
    finally:
        # Registrar métricas
        duration = time.time() - start_time
        HTTP_REQUESTS.labels(method=method, endpoint=path, status=status_code).inc()
        HTTP_REQUEST_DURATION.labels(method=method, endpoint=path).observe(duration)
        
    return response

# Inicializar servicios con reintentos
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception)
)
def init_mongodb_client():
    return AsyncIOMotorClient(
        settings.mongodb.uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        maxPoolSize=50,
        minPoolSize=10
    )

# Inicializar servicios
motor_client = init_mongodb_client()
db = motor_client[settings.mongodb.database]
encryption_service = EncryptionService(settings.db_connections.encryption_key)
security_service = SecurityService(settings.security)
connection_service = ConnectionService(db, encryption_service, security_service, settings)
agent_service = AgentService(db, connection_service, settings)

@app.on_event("startup")
async def startup_db_client():
    """Inicializar cliente de MongoDB al iniciar la aplicación"""
    logger.info("Starting DB Connection Service",
                version="1.1.0",
                python_version=platform.python_version(),
                uvloop_enabled=uvloop_available,
                structlog_enabled=structlog_available)
    
    logger.info("Connecting to MongoDB...")
    try:
        # Usar tenacity para reintentos de conexión
        for attempt in range(1, 6):
            try:
                await motor_client.admin.command("ping")
                logger.info("Successfully connected to MongoDB")
                break
            except Exception as e:
                if attempt < 5:
                    wait_time = 2 ** attempt  # Espera exponencial
                    logger.warning(f"MongoDB connection attempt {attempt} failed. Retrying in {wait_time}s...", error=str(e))
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to MongoDB after 5 attempts", error=str(e))
                    raise
    except Exception as e:
        logger.error(f"Error connecting to MongoDB", error=str(e))
        raise

@app.on_event("shutdown")
async def shutdown_db_client():
    """Cerrar cliente de MongoDB al detener la aplicación"""
    logger.info("Shutting down DB Connection Service...")
    try:
        motor_client.close()
        logger.info("MongoDB connection closed")
    except Exception as e:
        logger.error("Error during MongoDB connection close", error=str(e))

# Endpoint para métricas de Prometheus
@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Endpoint de health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    start_time = time.time()
    health_status = {
        "status": "ok",
        "service": "db-connection-service",
        "version": "1.1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": os.getenv("UPTIME", "unknown"),
        "mongodb": "unknown",
        "encryption": encryption_service.is_available,
    }
    
    try:
        await motor_client.admin.command("ping")
        health_status["mongodb"] = "ok"
        DB_OPERATIONS.labels(operation="ping", status="success").inc()
    except Exception as e:
        health_status["mongodb"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
        DB_OPERATIONS.labels(operation="ping", status="error").inc()
    
    # Agregar métricas de rendimiento
    duration = time.time() - start_time
    health_status["response_time_ms"] = round(duration * 1000, 2)
    DB_OPERATION_DURATION.labels(operation="health_check").observe(duration)
    
    return health_status

# --- Rutas para conexiones a BD ---

@app.get("/connections", response_model=List[DBConnectionResponse], tags=["Connections"])
async def get_connections():
    """Obtener todas las conexiones a BD"""
    return await connection_service.get_all_connections()

@app.get("/connections/{connection_id}", response_model=DBConnectionResponse, tags=["Connections"])
async def get_connection(connection_id: str):
    """Obtener una conexión específica por ID"""
    connection = await connection_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    return connection

@app.post("/connections", response_model=DBConnectionResponse, status_code=status.HTTP_201_CREATED, tags=["Connections"])
async def create_connection(connection: DBConnection):
    """Crear una nueva conexión a BD"""
    try:
        return await connection_service.create_connection(connection)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/connections/{connection_id}", response_model=DBConnectionResponse, tags=["Connections"])
async def update_connection(connection_id: str, connection_update: DBConnectionUpdate):
    """Actualizar una conexión existente"""
    try:
        updated = await connection_service.update_connection(connection_id, connection_update)
        if not updated:
            raise HTTPException(status_code=404, detail="Conexión no encontrada")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Connections"])
async def delete_connection(connection_id: str):
    """Eliminar una conexión"""
    deleted = await connection_service.delete_connection(connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    return None

@app.post("/connections/{connection_id}/test", tags=["Connections"])
async def test_connection(connection_id: str):
    """Probar una conexión a BD"""
    try:
        result = await connection_service.test_connection(connection_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error probando conexión: {str(e)}")

# --- Rutas para agentes DB ---

@app.get("/agents", response_model=List[DBAgent], tags=["Agents"])
async def get_agents():
    """Obtener todos los agentes DB"""
    return await agent_service.get_all_agents()

@app.get("/agents/{agent_id}", response_model=DBAgent, tags=["Agents"])
async def get_agent(agent_id: str):
    """Obtener un agente específico por ID"""
    agent = await agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return agent

@app.post("/agents", response_model=DBAgent, status_code=status.HTTP_201_CREATED, tags=["Agents"])
async def create_agent(agent: DBAgent):
    """Crear un nuevo agente DB"""
    try:
        return await agent_service.create_agent(agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/agents/{agent_id}", response_model=DBAgent, tags=["Agents"])
async def update_agent(agent_id: str, agent_update: DBAgentUpdate):
    """Actualizar un agente existente"""
    try:
        updated = await agent_service.update_agent(agent_id, agent_update)
        if not updated:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Agents"])
async def delete_agent(agent_id: str):
    """Eliminar un agente"""
    deleted = await agent_service.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return None

# --- Rutas para prompts de agentes ---

@app.get("/agents/{agent_id}/prompts", response_model=AgentPrompts, tags=["Agent Prompts"])
async def get_agent_prompts(agent_id: str):
    """Obtener los prompts configurados para un agente"""
    prompts = await agent_service.get_agent_prompts(agent_id)
    if not prompts:
        raise HTTPException(status_code=404, detail="Agente no encontrado o no tiene prompts configurados")
    return prompts

@app.put("/agents/{agent_id}/prompts", response_model=AgentPrompts, tags=["Agent Prompts"])
async def update_agent_prompts(agent_id: str, prompts: AgentPrompts):
    """Actualizar los prompts para un agente"""
    try:
        updated = await agent_service.update_agent_prompts(agent_id, prompts)
        if not updated:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Rutas para asignación de conexiones a agentes ---

@app.get("/agents/{agent_id}/connections", response_model=List[ConnectionAssignmentResponse], tags=["Agent Connections"])
async def get_agent_connections(agent_id: str):
    """Obtener las conexiones asignadas a un agente"""
    connections = await agent_service.get_agent_connections(agent_id)
    return connections

@app.post("/agents/{agent_id}/connections", response_model=ConnectionAssignmentResponse, tags=["Agent Connections"])
async def assign_connection(agent_id: str, assignment: ConnectionAssignment):
    """Asignar una conexión a un agente"""
    try:
        assignment.agent_id = agent_id  # Asegurarse de que el ID del agente sea el correcto
        result = await agent_service.assign_connection(assignment)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/agents/{agent_id}/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Agent Connections"])
async def remove_connection(agent_id: str, connection_id: str):
    """Eliminar una conexión de un agente"""
    deleted = await agent_service.remove_connection(agent_id, connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    return None

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8086")),
        reload=settings.environment == "development",
    )