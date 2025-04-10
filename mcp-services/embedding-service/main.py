
import asyncio
import logging
import os
import time
import platform
from datetime import datetime
from typing import Optional, Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from fastapi.responses import ORJSONResponse  # Respuestas JSON más rápidas

# Mejoras de rendimiento
try:
    import uvloop
    uvloop.install()
    uvloop_available = True
except ImportError:
    uvloop_available = False

# Métricas y monitoreo
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
    from prometheus_client.core import CounterMetricFamily, HistogramMetricFamily
    import prometheus_client
    prometheus_available = True
    
    # Crear un registry limpio para evitar conflictos
    # Este es el cambio clave: usar un registry personalizado en lugar del global
    custom_registry = prometheus_client.CollectorRegistry(auto_describe=True)
    
    # Definir métricas con el registry personalizado
    HTTP_REQUESTS = Counter(
        'embedding_http_requests_total', 
        'Total HTTP Requests', 
        ['method', 'endpoint', 'status'],
        registry=custom_registry
    )
    
    HTTP_REQUEST_DURATION = Histogram(
        'embedding_http_request_duration_seconds', 
        'HTTP Request Duration', 
        ['method', 'endpoint'],
        registry=custom_registry
    )
    
    DB_OPERATIONS = Counter(
        'embedding_db_operations_total', 
        'Total Database Operations', 
        ['operation', 'status'],
        registry=custom_registry
    )
    
    EMBEDDING_GENERATIONS = Counter(
        'embedding_generations_total', 
        'Total Embedding Generations', 
        ['type', 'status'],
        registry=custom_registry
    )
    
    VECTOR_SEARCHES = Counter(
        'embedding_vector_searches_total', 
        'Total Vector Searches', 
        ['status'],
        registry=custom_registry
    )
    
except ImportError:
    prometheus_available = False
    custom_registry = None

# Monitoreo de recursos
try:
    import psutil
    psutil_available = True
    if prometheus_available:
        MEMORY_USAGE = Gauge('embedding_memory_usage_bytes', 'Memory Usage in Bytes', registry=custom_registry)
        CPU_USAGE = Gauge('embedding_cpu_usage_percent', 'CPU Usage Percentage', registry=custom_registry)
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
    logger = structlog.get_logger("embedding_service")
    structlog_available = True
except ImportError:
    # Fallback a logging tradicional
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("embedding_service")
    structlog_available = False

from config.settings import Settings
from models.embedding import (
    EmbeddingRequest, EmbeddingResponse, EmbeddingBatchRequest,
    EmbeddingBatchResponse, EmbeddingType
)
from services.embedding_service import EmbeddingService
from services.vectordb_factory import VectorDBFactory

# Cargar configuración
settings = Settings()

# Crear aplicación FastAPI con respuestas optimizadas
app = FastAPI(
    title="Embedding Service",
    description="Servicio de generación de embeddings con soporte para modelos Nomic y HuggingFace",
    version="1.2.0",
    default_response_class=ORJSONResponse  # Usar orjson para respuestas más rápidas
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
        # Ignorar endpoints internos para evitar métricas innecesarias
        path = request.url.path
        if path.endswith(("/health", "/metrics")):
            return await call_next(request)
            
        start_time = time.time()
        method = request.method
        
        try:
            # Procesar la solicitud
            response = await call_next(request)
            status_code = response.status_code
            
        except Exception as e:
            status_code = 500
            raise e
        finally:
            # Registrar métricas solo si no son endpoints internos
            duration = time.time() - start_time
            try:
                HTTP_REQUESTS.labels(method=method, endpoint=path, status=status_code).inc()
                HTTP_REQUEST_DURATION.labels(method=method, endpoint=path).observe(duration)
            except Exception as metrics_error:
                # Evitar que errores de métricas interrumpan el servicio
                pass
            
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
                
                # Actualizar métrica de uso de CPU
                cpu_percent = process.cpu_percent(interval=1)
                CPU_USAGE.set(cpu_percent)
                
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

# Inicializar servicios usando la fábrica para seleccionar la implementación correcta
vectordb_service = VectorDBFactory.create(settings)
embedding_service = EmbeddingService(db, vectordb_service, settings)


@app.on_event("startup")
async def startup_event():
    """Inicializar servicios al iniciar la aplicación"""
    startup_status = {
        "mongodb": {"status": "pending"},
        "vectordb": {"status": "pending"},
        "embedding_models": {"status": "pending"},
        "mcp_service": {"status": "pending"}
    }
    
    logger.info("Starting Embedding Service",
               version="1.2.0",
               python_version=platform.python_version(),
               uvloop_enabled=uvloop_available,
               structlog_enabled=structlog_available,
               prometheus_enabled=prometheus_available)
    
    # Iniciar tarea de monitoreo si está disponible
    if prometheus_available and psutil_available:
        asyncio.create_task(update_metrics())
        logger.info("Metrics monitoring started")

    # Verificar conexión a MongoDB (crítica - sin ella no podemos proceder)
    logger.info("Connecting to MongoDB...")
    try:
        for attempt in range(1, 6):
            try:
                await motor_client.admin.command("ping")
                logger.info("Successfully connected to MongoDB")
                startup_status["mongodb"] = {"status": "ok"}
                if prometheus_available:
                    DB_OPERATIONS.labels(operation="connect", status="success").inc()
                break
            except Exception as e:
                if attempt < 5:
                    wait_time = 2 ** attempt  # Espera exponencial
                    logger.warning(f"MongoDB connection attempt {attempt} failed. Retrying in {wait_time}s...", error=str(e))
                    await asyncio.sleep(wait_time)
                else:
                    error_msg = f"Failed to connect to MongoDB after 5 attempts: {str(e)}"
                    logger.error(error_msg)
                    startup_status["mongodb"] = {"status": "error", "message": error_msg}
                    if prometheus_available:
                        DB_OPERATIONS.labels(operation="connect", status="error").inc()
                    raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Critical error connecting to MongoDB: {str(e)}"
        logger.error(error_msg)
        startup_status["mongodb"] = {"status": "error", "message": error_msg}
        raise ValueError(error_msg)

    # Verificar conexión a la base de datos vectorial (crítica para búsqueda de embeddings)
    logger.info(f"Connecting to Vector DB ({settings.vector_db})...")
    try:
        status = await vectordb_service.get_status()
        logger.info(f"Successfully connected to {settings.vector_db}", status=status)
        startup_status["vectordb"] = {"status": "ok", "type": settings.vector_db}
    except Exception as e:
        error_msg = f"Error connecting to {settings.vector_db}: {str(e)}"
        logger.error(error_msg)
        startup_status["vectordb"] = {"status": "error", "message": error_msg}
        # Este error es crítico para la búsqueda vectorial
        raise ValueError(error_msg)

    # Inicializar modelos de embeddings (crítico para operación)
    try:
        await embedding_service.initialize_models()
        logger.info("Embedding models initialized successfully")
        startup_status["embedding_models"] = {"status": "ok"}

        # Verificar disponibilidad de GPU
        if embedding_service.gpu_available:
            logger.info("GPU detected and will be used", gpu_info=embedding_service.gpu_info)
            startup_status["embedding_models"]["gpu"] = "available"
            startup_status["embedding_models"]["gpu_info"] = embedding_service.gpu_info
            
            # Información detallada de GPU
            import torch
            if torch.cuda.is_available():
                device_count = torch.cuda.device_count()
                gpu_devices = []
                for i in range(device_count):
                    device_props = torch.cuda.get_device_properties(i)
                    gpu_info = {
                        "id": i,
                        "name": device_props.name,
                        "memory_gb": f"{device_props.total_memory / (1024**3):.2f}",
                        "compute_capability": f"{device_props.major}.{device_props.minor}"
                    }
                    gpu_devices.append(gpu_info)
                    logger.info(f"GPU device {i} info",
                               name=device_props.name,
                               memory_gb=gpu_info["memory_gb"],
                               compute_capability=gpu_info["compute_capability"],
                               cuda_version=torch.version.cuda)
                startup_status["embedding_models"]["gpu_devices"] = gpu_devices
        else:
            logger.warning("No GPU detected, using CPU for embeddings")
            startup_status["embedding_models"]["gpu"] = "unavailable"
            startup_status["embedding_models"]["device"] = "cpu"
    except Exception as e:
        error_msg = f"Error initializing embedding models: {str(e)}"
        logger.error(error_msg)
        startup_status["embedding_models"] = {"status": "error", "message": error_msg}
        raise ValueError(error_msg)
    
    # Verificar conexión con el servicio MCP Context (crítico para operación completa)
    logger.info("Checking MCP Context Service connectivity...")
    try:
        service_available, health_info = await embedding_service.check_context_service_health()
        if service_available:
            logger.info("Successfully connected to MCP Context Service")
            startup_status["mcp_service"] = {"status": "ok", "details": health_info}
        else:
            error_msg = f"MCP Context Service unavailable: {health_info.get('message', 'unknown error')}"
            logger.error(error_msg)
            startup_status["mcp_service"] = {"status": "error", "message": error_msg}
            # Este es un error crítico para el funcionamiento completo
            raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Error connecting to MCP Context Service: {str(e)}"
        logger.error(error_msg)
        startup_status["mcp_service"] = {"status": "error", "message": error_msg}
        raise ValueError(error_msg)
    
    # Guardar estado de inicio para el endpoint de health
    app.state.startup_status = startup_status
    logger.info("Embedding Service started successfully", startup_status=startup_status)


@app.on_event("shutdown")
async def shutdown_event():
    """Limpiar recursos al detener la aplicación"""
    logger.info("Shutting down Embedding Service...")
    
    try:
        # Cerrar conexión a MongoDB
        motor_client.close()
        logger.info("MongoDB connection closed")
        
        # Cerrar servicio de embeddings
        await embedding_service.close()
        logger.info("Embedding service resources released")
        
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))


# Endpoint para métricas de Prometheus
if prometheus_available:
    @app.get("/metrics", tags=["Monitoring"])
    async def metrics():
        # Usar el registry personalizado en lugar del predeterminado
        return Response(content=generate_latest(custom_registry), media_type=CONTENT_TYPE_LATEST)


# Endpoint de health check optimizado
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    start_time = time.time()
    
    health_status = {
        "status": "ok",
        "service": "embedding-service",
        "version": "1.2.0",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": os.getenv("UPTIME", "unknown")
    }
    
    # Incluir información del startup si está disponible
    if hasattr(app.state, "startup_status"):
        health_status["startup_status"] = app.state.startup_status
    
    # Verificar MongoDB
    try:
        await motor_client.admin.command("ping")
        health_status["mongodb"] = {"status": "ok"}
        if prometheus_available:
            DB_OPERATIONS.labels(operation="ping", status="success").inc()
    except Exception as e:
        error_msg = str(e)
        health_status["mongodb"] = {"status": "error", "message": error_msg}
        health_status["status"] = "degraded"
        if prometheus_available:
            DB_OPERATIONS.labels(operation="ping", status="error").inc()
    
    # Verificar base de datos vectorial
    try:
        vectordb_status = await vectordb_service.get_status()
        health_status["vectordb"] = {
            "type": settings.vector_db,
            "status": "ok",
            "details": vectordb_status
        }
    except Exception as e:
        error_msg = str(e)
        health_status["vectordb"] = {
            "type": settings.vector_db,
            "status": "error",
            "message": error_msg
        }
        health_status["status"] = "degraded"
    
    # Verificar servicio MCP Context
    try:
        mcp_available, mcp_info = await embedding_service.check_context_service_health()
        if mcp_available:
            health_status["mcp_service"] = {
                "status": "ok",
                "details": mcp_info
            }
        else:
            health_status["mcp_service"] = {
                "status": "error",
                "message": "MCP Context Service unavailable",
                "details": mcp_info
            }
            health_status["status"] = "degraded"
    except Exception as e:
        error_msg = str(e)
        health_status["mcp_service"] = {
            "status": "error",
            "message": error_msg
        }
        health_status["status"] = "degraded"
    
    # Verificar GPU
    health_status["gpu"] = {
        "available": embedding_service.gpu_available,
        "info": embedding_service.gpu_info,
        "device": embedding_service.device
    }
    
    # Verificar modelos
    health_status["models"] = {
        "loaded": len(embedding_service.models) > 0,
        "types": list(embedding_service.models.keys())
    }
    
    # Añadir información de memoria si está disponible
    if psutil_available:
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            health_status["resources"] = {
                "memory": {
                    "rss_bytes": memory_info.rss,
                    "rss_mb": round(memory_info.rss / (1024 * 1024), 2)
                }
            }
            
            # Añadir uso de CPU
            cpu_percent = process.cpu_percent(interval=0.1)
            health_status["resources"]["cpu"] = {
                "percent": cpu_percent
            }
            
            # Si hay GPU disponible, añadir información de memoria GPU
            if embedding_service.gpu_available:
                try:
                    import torch
                    gpu_memory_allocated = torch.cuda.memory_allocated(0)
                    gpu_memory_reserved = torch.cuda.memory_reserved(0)
                    health_status["resources"]["gpu"] = {
                        "memory_allocated_mb": round(gpu_memory_allocated / (1024 * 1024), 2),
                        "memory_reserved_mb": round(gpu_memory_reserved / (1024 * 1024), 2)
                    }
                except Exception as e:
                    health_status["resources"]["gpu"] = {"error": str(e)}
        except Exception as e:
            health_status["resources"] = {"error": str(e)}
    
    # Determinar el estado general
    if "degraded" in health_status["status"]:
        # Ya está marcado como degradado por alguno de los componentes
        pass
    elif not mcp_available:
        # MCP es esencial, si no está disponible, el servicio está degradado
        health_status["status"] = "degraded"
    
    # Añadir tiempo de respuesta
    duration = time.time() - start_time
    health_status["response_time_ms"] = round(duration * 1000, 2)
    
    return health_status


# ----- Rutas para Embeddings -----

@app.post("/embeddings", response_model=EmbeddingResponse, tags=["Embeddings"])
async def create_embedding(request: EmbeddingRequest):
    """
    Generar embedding para un texto

    Este endpoint crea un embedding a partir del texto proporcionado
    y lo almacena en la base de datos vectorial.
    """
    try:
        result = await embedding_service.create_embedding(
            text=request.text,
            embedding_type=request.embedding_type,
            doc_id=request.doc_id,
            owner_id=request.owner_id,
            area_id=request.area_id,
            metadata=request.metadata
        )
        return result
    except Exception as e:
        logger.error(f"Error creating embedding: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating embedding: {str(e)}"
        )


@app.post("/embeddings/batch", response_model=EmbeddingBatchResponse, tags=["Embeddings"])
async def create_embeddings_batch(request: EmbeddingBatchRequest):
    """
    Generar embeddings para múltiples textos en batch

    Este endpoint crea embeddings para todos los textos proporcionados
    y los almacena en la base de datos vectorial.
    """
    try:
        results = await embedding_service.create_embeddings_batch(
            texts=request.texts,
            embedding_type=request.embedding_type,
            doc_ids=request.doc_ids,
            owner_id=request.owner_id,
            area_id=request.area_id,
            metadata=request.metadata
        )
        return EmbeddingBatchResponse(embeddings=results)
    except Exception as e:
        logger.error(f"Error creating embeddings batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating embeddings batch: {str(e)}"
        )


@app.post("/embeddings/document", response_model=EmbeddingResponse, tags=["Embeddings"])
async def create_document_embedding(
        file: UploadFile = File(...),
        doc_id: str = Form(...),
        owner_id: str = Form(...),
        embedding_type: EmbeddingType = Form(...),
        area_id: Optional[str] = Form(None),
        metadata: Optional[str] = Form(None)
):
    """
    Generar embedding para un documento

    Este endpoint crea un embedding a partir del contenido extraído
    del documento proporcionado y lo almacena en la base de datos vectorial.
    """
    try:
        # Leer contenido del archivo
        content = await file.read()

        # Convertir metadata de string JSON a dict si existe
        meta_dict = {}
        if metadata:
            import json
            try:
                meta_dict = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format in metadata"
                )

        # Añadir información del archivo a los metadatos
        meta_dict.update({
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content)
        })

        # Generar embedding
        result = await embedding_service.create_document_embedding(
            document=content,
            filename=file.filename,
            content_type=file.content_type,
            embedding_type=embedding_type,
            doc_id=doc_id,
            owner_id=owner_id,
            area_id=area_id,
            metadata=meta_dict
        )
        return result
    except Exception as e:
        logger.error(f"Error creating document embedding: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating document embedding: {str(e)}"
        )


@app.get("/embeddings/{embedding_id}", tags=["Embeddings"])
async def get_embedding(embedding_id: str):
    """
    Obtener información sobre un embedding específico
    """
    try:
        result = await embedding_service.get_embedding(embedding_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Embedding not found: {embedding_id}"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting embedding: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting embedding: {str(e)}"
        )


@app.delete("/embeddings/{embedding_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Embeddings"])
async def delete_embedding(embedding_id: str):
    """
    Eliminar un embedding específico
    """
    try:
        success = await embedding_service.delete_embedding(embedding_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Embedding not found: {embedding_id}"
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting embedding: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting embedding: {str(e)}"
        )


# ----- Rutas para búsqueda semántica -----

@app.get("/search", tags=["Search"])
async def search_embeddings(
        query: str = Query(..., description="Texto de consulta"),
        embedding_type: EmbeddingType = Query(..., description="Tipo de embedding"),
        owner_id: Optional[str] = Query(None, description="ID del propietario para filtrar"),
        area_id: Optional[str] = Query(None, description="ID del área para filtrar"),
        limit: int = Query(10, ge=1, le=100, description="Número máximo de resultados")
):
    """
    Buscar textos similares a la consulta

    Este endpoint realiza una búsqueda semántica usando la base de datos
    vectorial para encontrar textos similares a la consulta.
    """
    try:
        results = await embedding_service.search(
            query=query,
            embedding_type=embedding_type,
            owner_id=owner_id,
            area_id=area_id,
            limit=limit
        )
        return {"results": results}
    except Exception as e:
        logger.error(f"Error searching embeddings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching embeddings: {str(e)}"
        )


# ----- Rutas para contextos MCP -----

@app.get("/contexts", tags=["Contexts"])
async def list_contexts():
    """
    Listar todos los contextos MCP disponibles
    """
    try:
        contexts = await embedding_service.list_contexts()
        return {"contexts": contexts}
    except Exception as e:
        logger.error(f"Error listing contexts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing contexts: {str(e)}"
        )


@app.post("/contexts/{context_id}/activate", tags=["Contexts"])
async def activate_context(context_id: str):
    """
    Activar un contexto MCP específico
    """
    try:
        result = await embedding_service.activate_context(context_id)
        return result
    except Exception as e:
        logger.error(f"Error activating context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error activating context: {str(e)}"
        )


@app.post("/contexts/{context_id}/deactivate", tags=["Contexts"])
async def deactivate_context(context_id: str):
    """
    Desactivar un contexto MCP específico
    """
    try:
        result = await embedding_service.deactivate_context(context_id)
        return result
    except Exception as e:
        logger.error(f"Error deactivating context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deactivating context: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8084")),
        reload=False,  # Desactivar recarga para evitar problemas con Prometheus
    )