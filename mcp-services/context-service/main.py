import asyncio
import json
import logging
import os
import time
import platform
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from fastmcp import MountMCP

# Mejoras de rendimiento
try:
    import uvloop
    uvloop.install()
    uvloop_available = True
except ImportError:
    uvloop_available = False

# Métricas y monitoreo
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    prometheus_available = True
    
    # Definir métricas
    HTTP_REQUESTS = Counter('context_http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'status'])
    HTTP_REQUEST_DURATION = Histogram('context_http_request_duration_seconds', 'HTTP Request Duration', ['method', 'endpoint'])
    DB_OPERATIONS = Counter('context_db_operations_total', 'Total Database Operations', ['operation', 'status'])
    EMBEDDING_REQUESTS = Counter('context_embedding_requests_total', 'Requests to Embedding Service', ['status'])
    
except ImportError:
    prometheus_available = False

# Monitoreo de recursos
try:
    import psutil
    psutil_available = True
    if prometheus_available:
        MEMORY_USAGE = Gauge('context_memory_usage_bytes', 'Memory Usage in Bytes')
except ImportError:
    psutil_available = False

# Logging estructurado
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
    logger = structlog.get_logger("context_service")
    structlog_available = True
except ImportError:
    # Fallback a logging tradicional
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("context_service")
    structlog_available = False

from config.settings import Settings
from models.area import Area, AreaCreate, AreaResponse, AreaUpdate
from models.context import Context, ContextCreate, ContextResponse
from services.area_service import AreaService
from services.context_service import ContextService
from services.mcp_service import MCPService
from services.embedding_service_client import EmbeddingServiceClient

# Cargar configuración
settings = Settings()

# Crear aplicación FastAPI con respuestas optimizadas
app = FastAPI(
    title="MCP Context Service",
    description="Servicio de gestión de contextos para Model Context Protocol",
    version="1.1.0",
    default_response_class=ORJSONResponse,  # Usar orjson para respuestas más rápidas
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware para métricas si están disponibles
if prometheus_available:
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

# Función para actualizar métricas periódicamente
async def update_metrics():
    if prometheus_available and psutil_available:
        while True:
            try:
                # Actualizar métrica de uso de memoria
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                MEMORY_USAGE.set(memory_info.rss)
                
                # Ejecutar cada 15 segundos
                await asyncio.sleep(15)
            except Exception as e:
                logger.error("Error updating metrics", error=str(e))
                await asyncio.sleep(30)  # Esperar más tiempo si hay un error

# Conexión a MongoDB con reintentos
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception)
)
def init_mongodb_client():
    return AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        maxPoolSize=50,
        minPoolSize=10
    )

# Inicializar cliente MongoDB
motor_client = init_mongodb_client()
db = motor_client[settings.mongodb_database]

# Inicializar servicios
area_service = AreaService(db)
context_service = ContextService(db)
embedding_client = EmbeddingServiceClient(settings)
mcp_service = MCPService(settings, area_service, embedding_client)

# Montar servidor MCP usando FastMCP
MountMCP(app, mcp_service.server, settings.mcp.api_route)

@app.on_event("startup")
async def startup_event():
    """Inicializar recursos al iniciar la aplicación"""
    logger.info("Starting MCP Context Service",
               version="1.1.0",
               python_version=platform.python_version(),
               uvloop_enabled=uvloop_available,
               structlog_enabled=structlog_available,
               prometheus_enabled=prometheus_available)
    
    # Iniciar tarea de monitoreo si está disponible
    if prometheus_available and psutil_available:
        asyncio.create_task(update_metrics())
        logger.info("Metrics monitoring started")
    
    # Verificar conexión a MongoDB
    logger.info("Connecting to MongoDB...")
    try:
        for attempt in range(1, 6):
            try:
                await motor_client.admin.command("ping")
                logger.info("Successfully connected to MongoDB")
                if prometheus_available:
                    DB_OPERATIONS.labels(operation="connect", status="success").inc()
                break
            except Exception as e:
                if attempt < 5:
                    wait_time = 2 ** attempt  # Espera exponencial
                    logger.warning(f"MongoDB connection attempt {attempt} failed. Retrying in {wait_time}s...", error=str(e))
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to MongoDB after 5 attempts", error=str(e))
                    if prometheus_available:
                        DB_OPERATIONS.labels(operation="connect", status="error").inc()
                    raise
    except Exception as e:
        logger.error("Error connecting to MongoDB", error=str(e))
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Limpiar recursos al detener la aplicación"""
    logger.info("Shutting down MCP Context Service...")
    
    try:
        # Cerrar conexión a MongoDB
        motor_client.close()
        logger.info("MongoDB connection closed")
        
        # Liberar otros recursos si es necesario
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))


# Endpoint para métricas de Prometheus
if prometheus_available:
    @app.get("/metrics", tags=["Monitoring"])
    async def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Endpoint de health check optimizado
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    start_time = time.time()
    
    health_status = {
        "status": "ok",
        "service": "mcp-context-service",
        "version": "1.1.0",
        "timestamp": datetime.utcnow().isoformat() if 'datetime' in globals() else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uptime": os.getenv("UPTIME", "unknown")
    }
    
    # Verificar MongoDB
    try:
        await motor_client.admin.command("ping")
        health_status["mongodb"] = "ok"
        if prometheus_available:
            DB_OPERATIONS.labels(operation="ping", status="success").inc()
    except Exception as e:
        health_status["mongodb"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
        if prometheus_available:
            DB_OPERATIONS.labels(operation="ping", status="error").inc()
    
    # Verificar MCP
    try:
        mcp_status = mcp_service.get_status()
        health_status["mcp"] = {
            "server_name": mcp_status.get("name"),
            "contexts_count": mcp_status.get("contexts_count", 0),
            "active_contexts": mcp_status.get("active_contexts", 0)
        }
    except Exception as e:
        health_status["mcp"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Añadir información de memoria si está disponible
    if psutil_available:
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            health_status["memory_usage"] = {
                "rss_bytes": memory_info.rss,
                "rss_mb": round(memory_info.rss / (1024 * 1024), 2)
            }
        except Exception as e:
            health_status["memory_usage"] = {"error": str(e)}
    
    # Añadir tiempo de respuesta
    duration = time.time() - start_time
    health_status["response_time_ms"] = round(duration * 1000, 2)
    
    return health_status


# ----- Rutas para Áreas de Conocimiento -----

@app.post("/areas", response_model=AreaResponse, status_code=status.HTTP_201_CREATED, tags=["Areas"])
async def create_area(area: AreaCreate):
    """Crear una nueva área de conocimiento con su contexto MCP"""
    try:
        # Crear área en la base de datos
        db_area = await area_service.create_area(area)

        # Crear contexto MCP para el área
        context_id = await mcp_service.create_context(
            name=area.name,
            description=area.description,
            metadata={"area_id": str(db_area.id)}
        )

        # Actualizar área con el ID de contexto MCP
        await area_service.update_area_context(str(db_area.id), context_id)
        db_area.mcp_context_id = context_id

        return AreaResponse.from_db_model(db_area)
    except Exception as e:
        logger.error(f"Error creating area: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating area: {str(e)}"
        )


@app.get("/areas", response_model=List[AreaResponse], tags=["Areas"])
async def list_areas(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000)
):
    """Listar todas las áreas de conocimiento"""
    try:
        areas = await area_service.list_areas(skip, limit)
        return [AreaResponse.from_db_model(area) for area in areas]
    except Exception as e:
        logger.error(f"Error listing areas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing areas: {str(e)}"
        )


@app.get("/areas/{area_id}", response_model=AreaResponse, tags=["Areas"])
async def get_area(area_id: str = Path(...)):
    """Obtener un área de conocimiento por su ID"""
    try:
        area = await area_service.get_area(area_id)
        if not area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Area not found: {area_id}"
            )
        return AreaResponse.from_db_model(area)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting area: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting area: {str(e)}"
        )


@app.put("/areas/{area_id}", response_model=AreaResponse, tags=["Areas"])
async def update_area(area_id: str, area_update: AreaUpdate):
    """Actualizar un área de conocimiento"""
    try:
        # Verificar si el área existe
        existing_area = await area_service.get_area(area_id)
        if not existing_area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Area not found: {area_id}"
            )

        # Actualizar área en la base de datos
        updated_area = await area_service.update_area(area_id, area_update)

        # Actualizar contexto MCP si es necesario
        if existing_area.mcp_context_id and (
                area_update.name is not None or area_update.description is not None
        ):
            await mcp_service.update_context(
                context_id=existing_area.mcp_context_id,
                name=area_update.name,
                description=area_update.description
            )

        return AreaResponse.from_db_model(updated_area)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating area: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating area: {str(e)}"
        )


@app.delete("/areas/{area_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Areas"])
async def delete_area(area_id: str):
    """Eliminar un área de conocimiento"""
    try:
        # Verificar si el área existe
        existing_area = await area_service.get_area(area_id)
        if not existing_area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Area not found: {area_id}"
            )

        # Eliminar contexto MCP si existe
        if existing_area.mcp_context_id:
            await mcp_service.delete_context(existing_area.mcp_context_id)

        # Eliminar área de la base de datos
        await area_service.delete_area(area_id)

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting area: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting area: {str(e)}"
        )


# ----- Endpoints para prompt de sistema en Áreas -----

class SystemPromptUpdateRequest(BaseModel):
    system_prompt: str = Field(..., description="Nuevo prompt de sistema para el área")

@app.put("/areas/{area_id}/system-prompt", response_model=AreaResponse, tags=["Areas"])
async def update_area_system_prompt(area_id: str, request: SystemPromptUpdateRequest):
    """
    Actualizar el prompt de sistema de un área de conocimiento
    """
    try:
        updated_area = await area_service.update_area_system_prompt(area_id, request.system_prompt)
        return AreaResponse.from_db_model(updated_area)
    except Exception as e:
        logger.error(f"Error updating area system prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating area system prompt: {str(e)}"
        )

@app.get("/areas/{area_id}/system-prompt", tags=["Areas"])
async def get_area_system_prompt(area_id: str = Path(..., description="ID del área")):
    """
    Obtener el prompt de sistema de un área de conocimiento
    """
    try:
        system_prompt = await area_service.get_area_system_prompt(area_id)
        return {"area_id": area_id, "system_prompt": system_prompt}
    except Exception as e:
        logger.error(f"Error getting area system prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting area system prompt: {str(e)}"
        )


# ----- Rutas para Contextos MCP -----

@app.get("/contexts", response_model=List[ContextResponse], tags=["Contexts"])
async def list_contexts(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000)
):
    """Listar todos los contextos MCP"""
    try:
        # Obtener contextos de la base de datos
        contexts = await context_service.list_contexts(skip, limit)
        return [ContextResponse.from_db_model(ctx) for ctx in contexts]
    except Exception as e:
        logger.error(f"Error listing contexts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing contexts: {str(e)}"
        )


@app.get("/contexts/{context_id}", response_model=ContextResponse, tags=["Contexts"])
async def get_context(context_id: str = Path(...)):
    """Obtener un contexto MCP por su ID"""
    try:
        # Obtener contexto de la base de datos
        context = await context_service.get_context(context_id)
        if not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Context not found: {context_id}"
            )
        return ContextResponse.from_db_model(context)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting context: {str(e)}"
        )


@app.post("/contexts/{context_id}/activate", tags=["Contexts"])
async def activate_context(context_id: str = Path(...)):
    """Activar un contexto MCP"""
    try:
        # Verificar si el contexto existe
        context = await context_service.get_context(context_id)
        if not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Context not found: {context_id}"
            )

        # Activar contexto en MCP
        activation_info = await mcp_service.activate_context(context_id)
        return activation_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error activating context: {str(e)}"
        )


@app.post("/contexts/{context_id}/deactivate", tags=["Contexts"])
async def deactivate_context(context_id: str = Path(...)):
    """Desactivar un contexto MCP"""
    try:
        # Verificar si el contexto existe
        context = await context_service.get_context(context_id)
        if not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Context not found: {context_id}"
            )

        # Desactivar contexto en MCP
        deactivation_info = await mcp_service.deactivate_context(context_id)
        return deactivation_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deactivating context: {str(e)}"
        )


# ----- Rutas para obtener información de estado MCP -----

@app.get("/mcp/status", tags=["MCP"])
async def get_mcp_status():
    """Obtener el estado actual de MCP"""
    try:
        status_info = mcp_service.get_status()
        return status_info
    except Exception as e:
        logger.error(f"Error getting MCP status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting MCP status: {str(e)}"
        )


@app.get("/mcp/active-contexts", tags=["MCP"])
async def get_active_contexts():
    """Obtener los contextos activos en MCP"""
    try:
        active_contexts = mcp_service.get_active_contexts()
        return active_contexts
    except Exception as e:
        logger.error(f"Error getting active contexts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting active contexts: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8083")),
        reload=settings.environment == "development",
    )