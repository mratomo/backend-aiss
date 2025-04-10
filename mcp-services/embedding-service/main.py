
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
    logger.info("Starting Embedding Service",
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

    # Verificar conexión a la base de datos vectorial
    logger.info(f"Connecting to Vector DB ({settings.vector_db})...")
    try:
        status = await vectordb_service.get_status()
        logger.info(f"Successfully connected to {settings.vector_db}", status=status)
    except Exception as e:
        logger.error(f"Error connecting to {settings.vector_db}", error=str(e))
        logger.warning("Continuing startup despite Vector DB connection failure")
        # No propagamos la excepción para permitir que la aplicación continúe funcionando

    # Inicializar modelos de embeddings
    try:
        await embedding_service.initialize_models()
        logger.info("Embedding models initialized successfully")

        # Verificar disponibilidad de GPU
        if embedding_service.gpu_available:
            logger.info("GPU detected and will be used", gpu_info=embedding_service.gpu_info)
            
            # Información detallada de GPU
            import torch
            if torch.cuda.is_available():
                device_count = torch.cuda.device_count()
                for i in range(device_count):
                    device_props = torch.cuda.get_device_properties(i)
                    logger.info(f"GPU device {i} info",
                               name=device_props.name,
                               memory_gb=f"{device_props.total_memory / (1024**3):.2f}",
                               compute_capability=f"{device_props.major}.{device_props.minor}",
                               cuda_version=torch.version.cuda)
        else:
            logger.warning("No GPU detected, using CPU for embeddings")
    except Exception as e:
        logger.error("Error initializing embedding models", error=str(e))
        raise


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
        "version": "1.1.0",
        "timestamp": datetime.utcnow().isoformat(),
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
    
    # Verificar base de datos vectorial
    try:
        vectordb_status = await vectordb_service.get_status()
        health_status["vectordb"] = {
            "type": settings.vector_db,
            "status": vectordb_status
        }
    except Exception as e:
        health_status["vectordb"] = {
            "type": settings.vector_db,
            "status": f"error: {str(e)}"
        }
        health_status["status"] = "degraded"
    
    # Verificar GPU
    health_status["gpu"] = {
        "available": embedding_service.gpu_available,
        "info": embedding_service.gpu_info
    }
    
    # Añadir información de memoria si está disponible
    if psutil_available:
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            health_status["memory_usage"] = {
                "rss_bytes": memory_info.rss,
                "rss_mb": round(memory_info.rss / (1024 * 1024), 2)
            }
            
            # Añadir uso de CPU
            cpu_percent = process.cpu_percent(interval=0.1)
            health_status["cpu_usage"] = {
                "percent": cpu_percent
            }
        except Exception as e:
            health_status["resource_monitor"] = {"error": str(e)}
    
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