import logging
import os
import asyncio
import platform
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from functools import wraps

import aiohttp
import uvicorn

# Soporte para múltiples clientes HTTP
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query, Path, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from cachetools import TTLCache, cached

try:
    import uvloop
    uvloop.install()
    uvloop_available = True
except ImportError:
    uvloop_available = False

from config.settings import Settings
from models.models import (
    DatabaseSchema, SchemaDiscoveryRequest, SchemaDiscoveryResponse,
    SchemaDiscoveryStatus, SchemaAnalysisResponse, SchemaInsight,
    SchemaQuerySuggestion
)
from services.discovery_service import SchemaDiscoveryService
from services.vectorization_service import SchemaVectorizationService
from services.analysis_service import SchemaAnalysisService

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
    logger = structlog.get_logger("schema_discovery_service")
    structlog_available = True
except ImportError:
    # Fallback a logging tradicional
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("schema_discovery_service")
    structlog_available = False

# Métricas para Prometheus
HTTP_REQUESTS = Counter('http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'status'])
HTTP_REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP Request Duration', ['method', 'endpoint'])
SCHEMA_JOBS = Counter('schema_jobs_total', 'Total Schema Discovery Jobs', ['status'])
SCHEMA_JOB_DURATION = Histogram('schema_job_duration_seconds', 'Schema Discovery Job Duration')
ACTIVE_JOBS_GAUGE = Gauge('active_jobs', 'Number of Active Jobs')
MEMORY_USAGE = Gauge('memory_usage_bytes', 'Memory Usage in Bytes')

# Cargar configuración
settings = Settings()

# Crear aplicación FastAPI con respuestas optimizadas
app = FastAPI(
    title="Schema Discovery Service",
    description="Servicio optimizado para descubrimiento y análisis de esquemas de bases de datos",
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

# Jobs activos con lock para proteger acceso concurrente
active_jobs: Dict[str, Dict[str, Any]] = {}
active_jobs_lock = asyncio.Lock()  # Lock para proteger acceso concurrente a active_jobs

# Caché para resultados frecuentes
schema_cache = TTLCache(maxsize=100, ttl=300)  # Caché de 5 minutos

# Inicializar servicios con cliente HTTP mejorado
http_client = None
try:
    # Intentar usar httpx con fallback a aiohttp
    if HTTPX_AVAILABLE:
        http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
            http2=True
        )
        logger.info("Using httpx client for HTTP requests")
    else:
        # Fallback a aiohttp
        http_client = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        logger.info("Falling back to aiohttp client")
except Exception as e:
    logger.error(f"Error initializing HTTP client: {e}, falling back to aiohttp")
    http_client = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    )

# Inicializar servicios
discovery_service = SchemaDiscoveryService(http_client, settings)
vectorization_service = SchemaVectorizationService(http_client, settings)
analysis_service = SchemaAnalysisService(settings)

# Función para actualizar métricas periódicamente
async def update_metrics():
    while True:
        try:
            # Actualizar métrica de jobs activos
            async with active_jobs_lock:
                ACTIVE_JOBS_GAUGE.set(len(active_jobs))
            
            # Actualizar métrica de uso de memoria
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            MEMORY_USAGE.set(memory_info.rss)
            
            # Ejecutar cada 15 segundos
            await asyncio.sleep(15)
        except Exception as e:
            logger.error("Error updating metrics", error=str(e))
            await asyncio.sleep(30)  # Esperar más tiempo si hay un error

@app.on_event("startup")
async def startup_event():
    """Inicializar servicios al iniciar la aplicación"""
    logger.info("Starting Schema Discovery Service",
                version="1.1.0",
                python_version=platform.python_version(),
                uvloop_enabled=uvloop_available,
                structlog_enabled=structlog_available)
    
    # Iniciar tarea de actualización de métricas
    asyncio.create_task(update_metrics())

@app.on_event("shutdown")
async def shutdown_event():
    """Limpiar recursos al detener la aplicación"""
    logger.info("Shutting down Schema Discovery Service")
    
    try:
        # Cerrar cliente HTTP correctamente según su tipo
        if http_client is not None:
            if HTTPX_AVAILABLE and isinstance(http_client, httpx.AsyncClient):
                await http_client.aclose()
            else:
                await http_client.close()
            logger.info("HTTP client closed successfully")
        
        # Limpiar trabajos activos
        async with active_jobs_lock:
            job_count = len(active_jobs)
            active_jobs.clear()
            logger.info("Cleaned active jobs", count=job_count)
            
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))

# Endpoint para métricas de Prometheus
@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Endpoint de health check optimizado
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    start_time = time.time()
    
    # Preparar respuesta base
    health_status = {
        "status": "ok",
        "service": "schema-discovery-service",
        "version": "1.1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": os.getenv("UPTIME", "unknown"),
    }
    
    # Verificar estado de memoria y eliminar jobs antiguos si es necesario
    try:
        async with active_jobs_lock:
            # Obtener información de jobs
            jobs_count = len(active_jobs)
            health_status["active_jobs"] = jobs_count
            
            # Limpiar trabajos antiguos para prevenir fugas de memoria
            current_time = datetime.utcnow()
            old_jobs = [job_id for job_id, job_info in active_jobs.items() 
                        if "started_at" in job_info and 
                        (current_time - job_info["started_at"]).total_seconds() > 86400]  # 24 horas
            
            # Eliminar trabajos antiguos
            for job_id in old_jobs:
                del active_jobs[job_id]
                
            # Reportar limpieza si ocurrió
            cleaned_jobs = len(old_jobs)
            if cleaned_jobs > 0:
                logger.info("Cleaned old jobs during health check", cleaned_count=cleaned_jobs)
                health_status["cleaned_jobs"] = cleaned_jobs
    except Exception as e:
        logger.error("Error cleaning old jobs", error=str(e))
        health_status["status"] = "degraded"
        health_status["errors"] = [str(e)]
    
    # Añadir información de memoria
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        health_status["memory_usage"] = {
            "rss_bytes": memory_info.rss,
            "rss_mb": round(memory_info.rss / (1024 * 1024), 2),
            "active_jobs_count": len(active_jobs),
        }
    except Exception as e:
        logger.error("Error getting memory info", error=str(e))
        health_status["memory_usage"] = {"error": str(e)}
    
    # Añadir información de rendimiento
    duration = time.time() - start_time
    health_status["response_time_ms"] = round(duration * 1000, 2)
    
    return health_status

@app.get("/schema/{connection_id}", response_model=DatabaseSchema, tags=["Schema Discovery"])
async def get_schema(connection_id: str):
    """
    Obtener esquema descubierto para una conexión
    
    Si el esquema no existe, inicia el proceso de descubrimiento automáticamente
    """
    try:
        # Verificar si ya tenemos el esquema
        schema = await discovery_service.get_schema(connection_id)
        
        # Si está en proceso, devolver estado actual
        if schema:
            return schema
        
        # Si no existe, iniciar descubrimiento en segundo plano
        # y devolver estado pendiente
        job_id = f"job_{connection_id}_{datetime.utcnow().timestamp()}"
        
        # Crear estructura base de respuesta
        schema = DatabaseSchema(
            connection_id=connection_id,
            name="Pending Discovery",
            type="unknown",
            status=SchemaDiscoveryStatus.PENDING,
            discovery_date=datetime.utcnow()
        )
        
        # Guardar esquema inicial
        await discovery_service.save_schema(schema)
        
        # Iniciar tarea en segundo plano
        background_tasks = BackgroundTasks()
        background_tasks.add_task(
            discover_schema_background,
            job_id,
            connection_id,
            None  # Opciones por defecto
        )
        
        return schema
    except Exception as e:
        logger.error(f"Error retrieving schema for connection {connection_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/schema/discover", response_model=SchemaDiscoveryResponse, tags=["Schema Discovery"])
async def discover_schema(request: SchemaDiscoveryRequest, background_tasks: BackgroundTasks):
    """
    Iniciar descubrimiento de esquema para una conexión
    
    Inicia el proceso en segundo plano y devuelve un ID de trabajo
    """
    try:
        # Generar ID de trabajo
        job_id = f"job_{request.connection_id}_{datetime.utcnow().timestamp()}"
        
        # Registrar trabajo (thread-safe con lock)
        start_time = datetime.utcnow()
        estimated_completion = start_time + timedelta(seconds=settings.schema.schema_discovery_timeout)
        
        # Adquirir lock para modificar active_jobs
        async with active_jobs_lock:
            active_jobs[job_id] = {
                "connection_id": request.connection_id,
                "status": SchemaDiscoveryStatus.PENDING,
                "started_at": start_time,
                "estimated_completion": estimated_completion
            }
        
        # Iniciar tarea en segundo plano
        background_tasks.add_task(
            discover_schema_background,
            job_id,
            request.connection_id,
            request.options
        )
        
        # Devolver respuesta inmediata
        return SchemaDiscoveryResponse(
            job_id=job_id,
            connection_id=request.connection_id,
            status=SchemaDiscoveryStatus.PENDING,
            started_at=start_time,
            estimated_completion_time=estimated_completion
        )
    except Exception as e:
        logger.error(f"Error starting schema discovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/jobs/{job_id}", response_model=SchemaDiscoveryResponse, tags=["Schema Discovery"])
async def get_job_status(job_id: str):
    """Obtener estado de un trabajo de descubrimiento"""
    # Acceso thread-safe con lock
    async with active_jobs_lock:
        if job_id not in active_jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Hacer una copia del job para evitar race conditions
        job = dict(active_jobs[job_id])
    
    return SchemaDiscoveryResponse(
        job_id=job_id,
        connection_id=job["connection_id"],
        status=job["status"],
        started_at=job["started_at"],
        estimated_completion_time=job["estimated_completion"]
    )

@app.get("/schema/{connection_id}/analyze", response_model=SchemaAnalysisResponse, tags=["Schema Analysis"])
async def analyze_schema(connection_id: str):
    """
    Analizar esquema de una base de datos
    
    Genera insights y sugerencias basadas en el esquema
    """
    try:
        # Verificar si tenemos el esquema
        schema = await discovery_service.get_schema(connection_id)
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
        
        if schema.status != SchemaDiscoveryStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Schema discovery not completed")
        
        # Analizar esquema
        insights = await analysis_service.generate_insights(schema)
        suggestions = await analysis_service.generate_query_suggestions(schema)
        
        return SchemaAnalysisResponse(
            connection_id=connection_id,
            insights=insights,
            query_suggestions=suggestions,
            analysis_date=datetime.utcnow()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/{connection_id}/vectorize", tags=["Schema Vectorization"])
async def vectorize_schema(connection_id: str):
    """
    Vectorizar esquema para búsqueda semántica
    
    Genera y almacena embedding del esquema
    """
    try:
        # Verificar si tenemos el esquema
        schema = await discovery_service.get_schema(connection_id)
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
        
        if schema.status != SchemaDiscoveryStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Schema discovery not completed")
        
        # Vectorizar esquema asegurando que la sesión HTTP se cierre correctamente
        async with aiohttp.ClientSession() as session:
            vector_id = await vectorization_service.vectorize_schema(schema, session)
        
        return {
            "status": "success",
            "connection_id": connection_id,
            "vector_id": vector_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error vectorizing schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Función para ejecutar descubrimiento en segundo plano con mejoras
async def discover_schema_background(job_id: str, connection_id: str, options: Optional[Any] = None):
    """
    Ejecutar descubrimiento de esquema en segundo plano con soporte mejorado para:
    - Reintentos automáticos
    - Monitoreo de memoria
    - Métricas detalladas
    - Mejora del manejo de errores
    
    Args:
        job_id: ID del trabajo
        connection_id: ID de la conexión
        options: Opciones de descubrimiento
    """
    # Establecer límite de tiempo para el job
    job_timeout = settings.schema.schema_discovery_timeout + 120  # Timeout base + margen adicional
    start_time = datetime.utcnow()
    process_start_time = time.time()
    
    # Establecer job con intentos de reintento
    retry_count = 0
    max_retries = 3
    schema = None
    
    try:
        # Actualizar estado (thread-safe)
        async with active_jobs_lock:
            if job_id in active_jobs:
                active_jobs[job_id]["status"] = SchemaDiscoveryStatus.IN_PROGRESS
                active_jobs[job_id]["memory_usage"] = 0
                active_jobs[job_id]["start_time"] = process_start_time
                
                # Registrar memoria inicial
                try:
                    process = psutil.Process(os.getpid())
                    memory_info = process.memory_info()
                    active_jobs[job_id]["initial_memory"] = memory_info.rss
                except Exception:
                    pass
        
        # Bucle de intentos con reintentos automáticos para errores transitorios
        while retry_count <= max_retries:
            try:
                # Si es reintento, registrar
                if retry_count > 0:
                    logger.info(
                        "Retrying schema discovery",
                        job_id=job_id,
                        connection_id=connection_id,
                        attempt=retry_count + 1,
                        max_attempts=max_retries + 1
                    )
                    
                    # Actualizar estado de reintento en el job
                    async with active_jobs_lock:
                        if job_id in active_jobs:
                            active_jobs[job_id]["retry_count"] = retry_count
                            active_jobs[job_id]["retry_at"] = datetime.utcnow().isoformat()
                
                # Iniciar descubrimiento con timeout
                schema = await asyncio.wait_for(
                    discovery_service.discover_schema(connection_id, options),
                    timeout=job_timeout
                )
                
                # Si se completó correctamente, se sale del bucle de reintentos
                if schema and schema.status == SchemaDiscoveryStatus.COMPLETED:
                    # Incrementar métrica de trabajos exitosos
                    SCHEMA_JOBS.labels(status="success").inc()
                    break
                    
                # Si no se completó correctamente pero sin excepción, se reintenta
                retry_count += 1
                if retry_count <= max_retries:
                    # Espera exponencial para reintentos
                    wait_time = 2 ** retry_count
                    logger.warning(
                        "Schema discovery incomplete, retrying",
                        job_id=job_id,
                        status=schema.status if schema else "unknown",
                        retry_count=retry_count,
                        wait_time=wait_time
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Se agotaron los reintentos
                    logger.error(
                        "Schema discovery incomplete after max retries",
                        job_id=job_id,
                        connection_id=connection_id,
                        max_retries=max_retries
                    )
                    # Incrementar métrica de trabajos fallidos
                    SCHEMA_JOBS.labels(status="failed").inc()
                    break
                    
            except asyncio.TimeoutError:
                logger.error(
                    "Schema discovery timeout",
                    job_id=job_id,
                    connection_id=connection_id,
                    timeout_seconds=job_timeout,
                    retry_count=retry_count
                )
                
                # Incrementar métrica de timeouts
                SCHEMA_JOBS.labels(status="timeout").inc()
                
                # Actualizar estado con timeout (thread-safe)
                async with active_jobs_lock:
                    if job_id in active_jobs:
                        active_jobs[job_id]["status"] = SchemaDiscoveryStatus.FAILED
                        active_jobs[job_id]["error"] = f"Job timed out after {job_timeout} seconds"
                
                # Crear objeto de esquema con error
                schema = DatabaseSchema(
                    connection_id=connection_id,
                    name=f"Timeout: {connection_id}",
                    type="unknown",
                    status=SchemaDiscoveryStatus.FAILED,
                    discovery_date=datetime.utcnow(),
                    error=f"Schema discovery timed out after {job_timeout} seconds (attempt {retry_count+1}/{max_retries+1})"
                )
                
                # Si aún hay reintentos disponibles, continuar
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(
                        "Retrying after timeout",
                        job_id=job_id,
                        retry_count=retry_count,
                        wait_time=wait_time
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Guardar esquema con error de timeout final
                    await discovery_service.save_schema(schema)
                    break
                    
            except Exception as e:
                # Otros errores durante el descubrimiento
                logger.error(
                    "Error during schema discovery",
                    job_id=job_id,
                    connection_id=connection_id,
                    error=str(e),
                    retry_count=retry_count
                )
                
                # Incrementar métrica de errores
                SCHEMA_JOBS.labels(status="error").inc()
                
                # Crear objeto de esquema con error
                schema = DatabaseSchema(
                    connection_id=connection_id,
                    name="Discovery Error",
                    type="unknown",
                    status=SchemaDiscoveryStatus.FAILED,
                    discovery_date=datetime.utcnow(),
                    error=f"Error: {str(e)} (attempt {retry_count+1}/{max_retries+1})"
                )
                
                # Determinar si el error es transitorio o permanente
                error_msg = str(e).lower()
                is_transient = (
                    "timeout" in error_msg or 
                    "connection" in error_msg or 
                    "unavailable" in error_msg or
                    "temporary" in error_msg
                )
                
                # Si el error es transitorio y hay reintentos disponibles
                retry_count += 1
                if is_transient and retry_count <= max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(
                        "Retrying after transient error",
                        job_id=job_id,
                        retry_count=retry_count,
                        wait_time=wait_time,
                        error=str(e)
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Error permanente o sin reintentos disponibles
                    await discovery_service.save_schema(schema)
                    break
        
        # Procesamiento post-descubrimiento (solo si schema se descubrió correctamente)
        if schema and schema.status == SchemaDiscoveryStatus.COMPLETED:
            try:
                # Vectorización con reintentos automáticos
                vectorization_timeout = 120  # 2 minutos
                vector_id = None
                
                for v_attempt in range(1, 4):  # Hasta 3 intentos
                    try:
                        # Crear cliente HTTP específico para vectorizar con timeout adecuado
                        vector_id = await asyncio.wait_for(
                            vectorization_service.vectorize_schema(schema, http_client),
                            timeout=vectorization_timeout
                        )
                        
                        if vector_id:
                            # Actualizar esquema con ID del vector
                            schema.vector_id = vector_id
                            await discovery_service.save_schema(schema)
                            logger.info(
                                "Schema vectorization successful",
                                job_id=job_id,
                                connection_id=connection_id,
                                vector_id=vector_id
                            )
                            break
                            
                    except asyncio.TimeoutError:
                        if v_attempt < 3:
                            logger.warning(
                                "Timeout vectorizing schema, retrying",
                                job_id=job_id,
                                attempt=v_attempt,
                                timeout=vectorization_timeout
                            )
                            # Incrementar timeout para siguiente intento
                            vectorization_timeout += 60
                        else:
                            logger.error(
                                "Vectorization failed after max retries",
                                job_id=job_id,
                                connection_id=connection_id
                            )
                    except Exception as e:
                        if v_attempt < 3:
                            logger.warning(
                                "Error vectorizing schema, retrying",
                                job_id=job_id,
                                attempt=v_attempt,
                                error=str(e)
                            )
                        else:
                            logger.error(
                                "Vectorization failed with error",
                                job_id=job_id,
                                connection_id=connection_id,
                                error=str(e)
                            )
                
                # Guardamos esquema final aún si vectorización falló
                if not vector_id:
                    schema.vector_id = None
                    schema.vectorization_error = "Failed to vectorize schema after multiple attempts"
                    await discovery_service.save_schema(schema)
                
            except Exception as e:
                logger.error(
                    "Unhandled error during vectorization",
                    job_id=job_id,
                    connection_id=connection_id,
                    error=str(e)
                )
                # Guardamos esquema aunque falle la vectorización
                await discovery_service.save_schema(schema)
        
        # Actualizar estado final del trabajo
        async with active_jobs_lock:
            if job_id in active_jobs:
                active_jobs[job_id]["status"] = schema.status if schema else SchemaDiscoveryStatus.FAILED
                active_jobs[job_id]["completed_at"] = datetime.utcnow()
                active_jobs[job_id]["retry_count"] = retry_count
                
                # Intentar capturar uso de memoria final
                try:
                    process = psutil.Process(os.getpid())
                    memory_info = process.memory_info()
                    active_jobs[job_id]["final_memory"] = memory_info.rss
                    # Calcular delta de memoria
                    if "initial_memory" in active_jobs[job_id]:
                        memory_delta = memory_info.rss - active_jobs[job_id]["initial_memory"]
                        active_jobs[job_id]["memory_delta"] = memory_delta
                except Exception:
                    pass
            
    except Exception as e:
        logger.error(
            "Unhandled error in schema discovery job",
            job_id=job_id,
            connection_id=connection_id,
            error=str(e)
        )
        
        # Actualizar estado con error (thread-safe)
        async with active_jobs_lock:
            if job_id in active_jobs:
                active_jobs[job_id]["status"] = SchemaDiscoveryStatus.FAILED
                active_jobs[job_id]["error"] = str(e)
                active_jobs[job_id]["completed_at"] = datetime.utcnow()
        
        # Guardar esquema con error no manejado
        if not schema:
            schema_error = DatabaseSchema(
                connection_id=connection_id,
                name="Unhandled Error",
                type="unknown",
                status=SchemaDiscoveryStatus.FAILED,
                discovery_date=datetime.utcnow(),
                error=f"Unhandled error in job execution: {str(e)}"
            )
            try:
                await discovery_service.save_schema(schema_error)
            except Exception as save_error:
                logger.error(
                    "Failed to save error schema",
                    job_id=job_id,
                    error=str(save_error)
                )
    finally:
        # Calcular tiempo de ejecución
        execution_time = time.time() - process_start_time
        logger.info(
            "Job completed",
            job_id=job_id,
            connection_id=connection_id,
            status=schema.status if schema else "unknown",
            duration_seconds=round(execution_time, 2),
            retry_count=retry_count
        )
        
        # Registrar métrica de duración
        SCHEMA_JOB_DURATION.observe(execution_time)
        
        # Reducir el tiempo de retención de jobs completados o fallidos
        # para evitar acumular demasiados en memoria
        retention_time = 3600  # 1 hora por defecto
        if execution_time > 300:  # Si tomó más de 5 minutos
            # Menor retención para jobs largos (10 minutos)
            retention_time = 600
        elif retry_count > 0:
            # Retención extendida para jobs con reintentos (para análisis)
            retention_time = 7200  # 2 horas
        
        # Mantener el job en memoria por el tiempo de retención
        try:
            retention_task = asyncio.create_task(asyncio.sleep(retention_time))
            await retention_task
        except asyncio.CancelledError:
            logger.info("Job retention sleep cancelled", job_id=job_id)
        
        # Eliminar job de manera thread-safe
        async with active_jobs_lock:
            if job_id in active_jobs:
                # Capturar estado final para logging
                final_status = active_jobs[job_id].get("status", "unknown")
                final_memory = active_jobs[job_id].get("memory_delta", "unknown")
                
                # Eliminar job
                del active_jobs[job_id]
                
                # Actualizar métrica de jobs activos
                ACTIVE_JOBS_GAUGE.set(len(active_jobs))
                
                logger.info(
                    "Removed job from memory",
                    job_id=job_id,
                    final_status=final_status,
                    memory_delta_mb=round(final_memory / (1024 * 1024), 2) if isinstance(final_memory, int) else "unknown"
                )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8087")),
        reload=settings.environment == "development",
    )