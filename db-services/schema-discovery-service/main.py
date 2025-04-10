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

# Inicializamos referencias a cliente HTTP y servicios para evitar errores al crear el cliente
# de HTTP fuera de un evento async
http_client = None
discovery_service = None 
vectorization_service = None
analysis_service = None
graph_extraction_service = None

# Los servicios se inicializarán en el evento startup cuando estemos en un contexto async

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
    global http_client, discovery_service, vectorization_service, analysis_service, graph_extraction_service
    
    # Registrar variables de entorno y versión
    logger.info("Starting Schema Discovery Service",
                version="1.1.0",
                python_version=platform.python_version(),
                uvloop_enabled=uvloop_available,
                structlog_enabled=structlog_available)
    
    # Registrar variables de configuración críticas
    logger.info(f"Configuration settings:",
                db_connection_url=settings.db_connection_url,
                embedding_service_url=settings.embedding_service_url,
                neo4j_uri=settings.neo4j_uri)
    
    # Almacenar timestamp de inicio para el uptime
    os.environ["UPTIME"] = datetime.utcnow().isoformat()
    
    # Inicializar cliente HTTP con mejor manejo de errores y configuración
    try:
        if HTTPX_AVAILABLE:
            import httpx
            # Inicializar sin HTTP/2 para evitar errores con configuración mejorada
            http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout=30.0, connect=10.0, read=30.0, write=10.0),
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
                http2=False,
                follow_redirects=True
            )
            logger.info("Initialized httpx client for HTTP requests with improved settings")
        else:
            # Fallback a aiohttp con configuración mejorada
            conn = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300, force_close=False)
            http_client = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=30),
                connector=conn,
                raise_for_status=True
            )
            logger.info("Initialized aiohttp client with improved connection settings")
    except Exception as e:
        logger.error(f"Error initializing HTTP client: {e}, using basic aiohttp as fallback")
        # Fallback básico como último recurso
        http_client = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        logger.warning("Using basic aiohttp client with default settings - performance may be impacted")
    
    # Inicializar servicios con el cliente HTTP con manejo de errores específicos
    # para cada servicio para facilitar diagnóstico
    try:
        # Inicializar servicio de descubrimiento
        discovery_service = SchemaDiscoveryService(http_client, settings)
        logger.info("Schema Discovery Service initialized successfully")
        
        # Inicializar servicio de vectorización
        vectorization_service = SchemaVectorizationService(http_client, settings)
        logger.info("Schema Vectorization Service initialized successfully")
        
        # Inicializar servicio de análisis
        analysis_service = SchemaAnalysisService(settings)
        logger.info("Schema Analysis Service initialized successfully")
        
        # Inicializar servicio de extracción de grafos
        from services.graph_extraction_service import GraphExtractionService
        graph_extraction_service = GraphExtractionService(settings)
        logger.info("Graph Extraction Service initialized successfully")
        
        logger.info("All services initialized successfully and ready to handle requests")
    except Exception as e:
        logger.error(f"Error initializing services: {e}")
        # Mostrar un log específico según el servicio que falló
        if discovery_service is None:
            logger.error("Failed to initialize SchemaDiscoveryService - service will not function correctly")
        elif vectorization_service is None:
            logger.error("Failed to initialize SchemaVectorizationService - vectorization features will not work")
        elif analysis_service is None:
            logger.error("Failed to initialize SchemaAnalysisService - analysis features will not work")
        elif graph_extraction_service is None:
            logger.error("Failed to initialize GraphExtractionService - graph features will not work")
        
        # Lanzar excepción para reiniciar el servicio
        raise
    
    # Iniciar tarea de actualización de métricas
    asyncio.create_task(update_metrics())
    logger.info("Metrics monitoring started successfully")

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

# Endpoint de health check optimizado y ampliado
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio y sus componentes"""
    start_time = time.time()
    
    # Preparar respuesta base
    health_status = {
        "status": "ok",
        "service": "schema-discovery-service",
        "version": "1.1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": os.getenv("UPTIME", "unknown"),
    }
    
    # Verificar que todos los servicios estén inicializados
    required_services = {
        "discovery_service": discovery_service,
        "vectorization_service": vectorization_service, 
        "analysis_service": analysis_service,
        "graph_extraction_service": graph_extraction_service,
        "http_client": http_client
    }
    
    missing_services = [name for name, service in required_services.items() if service is None]
    if missing_services:
        health_status["status"] = "critical"
        health_status["missing_services"] = missing_services
        health_status["service_error"] = "Critical services not initialized"
    
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
        
        # Verificar umbral crítico de uso de memoria (>90% del sistema disponible)
        system_memory = psutil.virtual_memory()
        if memory_info.rss > system_memory.total * 0.9:
            health_status["status"] = "critical"
            health_status["memory_warning"] = "Service is using more than 90% of system memory"
            logger.warning("Memory usage critical", rss_mb=round(memory_info.rss / (1024 * 1024), 2))
    except Exception as e:
        logger.error("Error getting memory info", error=str(e))
        health_status["memory_usage"] = {"error": str(e)}
    
    # Verificar conexión con servicios dependientes
    dependencies_status = {}
    try:
        # Verificar conexión con DB Connection Service
        if http_client:
            try:
                async with http_client.request(
                    "GET", 
                    f"{settings.db_connection_url}/health", 
                    timeout=2
                ) as resp:
                    if hasattr(resp, 'status_code'):  # httpx
                        dependencies_status["db_connection"] = "ok" if resp.status_code < 400 else "error"
                    else:  # aiohttp
                        dependencies_status["db_connection"] = "ok" if resp.status < 400 else "error"
            except Exception as e:
                dependencies_status["db_connection"] = {"status": "error", "message": str(e)}
                # Degradar estado pero no marcar como crítico, ya que puede funcionar sin esta dependencia
                if health_status["status"] == "ok":
                    health_status["status"] = "degraded"
    except Exception as e:
        dependencies_status["error"] = str(e)
    
    health_status["dependencies"] = dependencies_status
    
    # Añadir información de rendimiento
    duration = time.time() - start_time
    health_status["response_time_ms"] = round(duration * 1000, 2)
    
    # Determinar código de status HTTP basado en el estado del servicio
    status_code = 200
    if health_status["status"] == "critical":
        status_code = 503  # Service Unavailable
    elif health_status["status"] == "degraded":
        status_code = 207  # Multi-Status
        
    return Response(
        content=json.dumps(health_status),
        media_type="application/json",
        status_code=status_code
    )

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

@app.get("/schema/{connection_id}/graph", tags=["Graph Knowledge"])
async def extract_schema_graph(connection_id: str):
    """
    Extraer grafo de conocimiento del esquema en Neo4j
    
    Genera una representación en grafo del esquema de base de datos para GraphRAG
    """
    try:
        # Verificar si tenemos el esquema
        schema = await discovery_service.get_schema(connection_id)
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
        
        if schema.status != SchemaDiscoveryStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Schema discovery not completed")
        
        # Extraer grafo y almacenarlo en Neo4j
        graph_result = graph_extraction_service.extract_schema_graph(schema)
        
        # Generar descripción textual del grafo para incluir en la respuesta
        graph_description = graph_extraction_service.get_graph_description(connection_id)
        
        return {
            "status": "success",
            "connection_id": connection_id,
            "nodes_count": graph_result.get("nodes_count", 0),
            "edges_count": graph_result.get("edges_count", 0),
            "communities_count": graph_result.get("communities_count", 0),
            "description": graph_description
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting schema graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/{connection_id}/graph/info", tags=["Graph Knowledge"])
async def get_graph_info(connection_id: str):
    """
    Obtener información detallada del grafo de conocimiento
    
    Devuelve estadísticas y metadatos sobre el grafo de conocimiento extraído
    """
    try:
        # Verificar si tenemos el esquema
        schema = await discovery_service.get_schema(connection_id)
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
        
        # Obtener estadísticas del grafo
        graph_stats = graph_extraction_service._get_graph_stats(connection_id)
        
        # Obtener información de comunidades
        communities = graph_extraction_service._calculate_communities(schema)
        
        # Obtener información adicional
        summary = graph_extraction_service.generate_graph_summary(connection_id)
        
        return {
            "status": "success",
            "connection_id": connection_id,
            "stats": graph_stats,
            "communities": communities,
            "summary": summary
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting graph info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/{connection_id}/graph/export", tags=["Graph Knowledge"])
async def export_graph(connection_id: str):
    """
    Exportar grafo completo como JSON para visualización
    
    Devuelve una representación completa del grafo para su visualización en herramientas externas
    """
    try:
        # Verificar conexión a Neo4j
        if graph_extraction_service.driver is None:
            raise HTTPException(status_code=503, detail="Neo4j connection not available")
        
        # Exportar grafo
        async with graph_extraction_service.driver.session() as session:
            # Obtener nodos
            nodes_result = await session.run("""
            MATCH (n)
            WHERE (n:Database AND n.connection_id = $connection_id) OR 
                  (n:Table AND n.table_id CONTAINS $connection_id) OR
                  (n:Column AND n.column_id CONTAINS $connection_id)
            RETURN n, labels(n) as labels
            """, connection_id=connection_id)
            
            nodes_data = await nodes_result.data()
            
            # Obtener relaciones
            rels_result = await session.run("""
            MATCH (n)-[r]->(m)
            WHERE (n:Database AND n.connection_id = $connection_id) OR 
                  (n:Table AND n.table_id CONTAINS $connection_id) OR
                  (n:Column AND n.column_id CONTAINS $connection_id)
            RETURN id(n) as source, id(m) as target, type(r) as type, properties(r) as properties
            """, connection_id=connection_id)
            
            rels_data = await rels_result.data()
            
            # Formatear resultados para visualización
            formatted_nodes = []
            for node in nodes_data:
                n_data = dict(node["n"])
                n_data["labels"] = node["labels"]
                n_data["id"] = n_data.get("table_id", n_data.get("column_id", n_data.get("connection_id", "")))
                formatted_nodes.append(n_data)
                
            formatted_rels = []
            for rel in rels_data:
                formatted_rels.append({
                    "source": rel["source"],
                    "target": rel["target"],
                    "type": rel["type"],
                    "properties": rel["properties"]
                })
            
            return {
                "nodes": formatted_nodes,
                "relationships": formatted_rels
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/{connection_id}/graph/visualize", tags=["Graph Knowledge"])
async def visualize_graph(connection_id: str):
    """
    Obtener datos del grafo en formato optimizado para visualización con D3.js
    
    Devuelve una representación del grafo adaptada específicamente para visualización en el frontend
    """
    try:
        # Verificar conexión a Neo4j
        if graph_extraction_service.driver is None:
            raise HTTPException(status_code=503, detail="Neo4j connection not available")
        
        # Obtener datos para visualización
        async with graph_extraction_service.driver.session() as session:
            # Obtener todas las tablas (nodos principales)
            tables_result = await session.run("""
            MATCH (t:Table)
            WHERE t.table_id CONTAINS $connection_id
            OPTIONAL MATCH (t)-[r:RELATES_TO]-(related:Table)
            WITH t, count(r) AS rel_count, collect(DISTINCT related.name) AS related_tables
            RETURN t.name AS id, t.name AS label, t.schema AS group, t.description AS title,
                   rel_count as value, related_tables
            """, connection_id=connection_id)
            
            tables_data = await tables_result.data()
            
            # Obtener todas las relaciones entre tablas
            rels_result = await session.run("""
            MATCH (t1:Table)-[r:RELATES_TO]->(t2:Table)
            WHERE t1.table_id CONTAINS $connection_id AND t2.table_id CONTAINS $connection_id
            RETURN t1.name AS source, t2.name AS target, r.via_column AS label,
                   'table_relation' AS type, 1 AS value
            """, connection_id=connection_id)
            
            rels_data = await rels_result.data()
            
            # Formatear para D3.js
            nodes = []
            links = []
            
            # Añadir nodos
            for table in tables_data:
                nodes.append({
                    "id": table["id"],
                    "label": table["label"],
                    "group": table["group"] or "default",
                    "title": table["title"] or table["label"],
                    "value": table["value"] or 1,
                    "related": table["related_tables"]
                })
                
            # Añadir links
            for rel in rels_data:
                links.append({
                    "source": rel["source"],
                    "target": rel["target"],
                    "label": rel["label"],
                    "type": rel["type"],
                    "value": rel["value"]
                })
                
            # Añadir información de comunidades si está disponible
            communities = graph_extraction_service._calculate_communities(await discovery_service.get_schema(connection_id))
            
            return {
                "nodes": nodes,
                "links": links,
                "communities": communities
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error visualizing graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/schema/{connection_id}/graph/relationship", tags=["Graph Knowledge"])
async def update_graph_relationship(
    connection_id: str, 
    relationship: Dict[str, Any]
):
    """
    Actualizar o crear una relación en el grafo de conocimiento
    
    Permite a los administradores modificar las relaciones entre entidades del grafo
    """
    try:
        # Verificar conexión a Neo4j
        if graph_extraction_service.driver is None:
            raise HTTPException(status_code=503, detail="Neo4j connection not available")
        
        # Validar datos de la relación
        if not relationship.get("source_id") or not relationship.get("target_id"):
            raise HTTPException(status_code=400, detail="Source and target IDs are required")
        
        # Actualizar o crear relación
        async with graph_extraction_service.driver.session() as session:
            # Verificar que los nodos existen
            nodes_check = await session.run("""
            MATCH (s:Table {name: $source_name}), (t:Table {name: $target_name})
            WHERE s.table_id CONTAINS $connection_id AND t.table_id CONTAINS $connection_id
            RETURN count(*) AS nodes_found
            """, 
            connection_id=connection_id,
            source_name=relationship["source_id"],
            target_name=relationship["target_id"])
            
            nodes_data = await nodes_check.data()
            
            if not nodes_data or nodes_data[0]["nodes_found"] == 0:
                raise HTTPException(status_code=404, detail="Source or target node not found")
            
            # Actualizar o crear relación
            rel_type = relationship.get("relationship_type", "RELATES_TO")
            properties = relationship.get("properties", {})
            
            update_result = await session.run("""
            MATCH (s:Table {name: $source_name}), (t:Table {name: $target_name})
            WHERE s.table_id CONTAINS $connection_id AND t.table_id CONTAINS $connection_id
            MERGE (s)-[r:RELATES_TO]->(t)
            SET r += $properties
            RETURN s.name AS source, t.name AS target, type(r) AS type
            """, 
            connection_id=connection_id,
            source_name=relationship["source_id"],
            target_name=relationship["target_id"],
            properties=properties)
            
            update_data = await update_result.data()
            
            if not update_data:
                raise HTTPException(status_code=500, detail="Failed to update relationship")
                
            return {
                "status": "success",
                "relationship": update_data[0]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating graph relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/schema/{connection_id}/graph/node", tags=["Graph Knowledge"])
async def update_graph_node(
    connection_id: str, 
    node_update: Dict[str, Any]
):
    """
    Actualizar metadatos de un nodo en el grafo
    
    Permite a los administradores modificar propiedades y metadatos de los nodos
    """
    try:
        # Verificar conexión a Neo4j
        if graph_extraction_service.driver is None:
            raise HTTPException(status_code=503, detail="Neo4j connection not available")
        
        # Validar datos del nodo
        if not node_update.get("node_id"):
            raise HTTPException(status_code=400, detail="Node ID is required")
        
        # Obtener propiedades a actualizar
        properties = node_update.get("properties", {})
        
        # Actualizar nodo
        async with graph_extraction_service.driver.session() as session:
            # Verificar que el nodo existe
            node_check = await session.run("""
            MATCH (n:Table {name: $node_name})
            WHERE n.table_id CONTAINS $connection_id
            RETURN count(*) AS node_found
            """, 
            connection_id=connection_id,
            node_name=node_update["node_id"])
            
            node_data = await node_check.data()
            
            if not node_data or node_data[0]["node_found"] == 0:
                raise HTTPException(status_code=404, detail="Node not found")
            
            # Actualizar propiedades del nodo
            update_result = await session.run("""
            MATCH (n:Table {name: $node_name})
            WHERE n.table_id CONTAINS $connection_id
            SET n += $properties
            RETURN n.name AS name, n.schema AS schema, properties(n) AS properties
            """, 
            connection_id=connection_id,
            node_name=node_update["node_id"],
            properties=properties)
            
            update_data = await update_result.data()
            
            if not update_data:
                raise HTTPException(status_code=500, detail="Failed to update node")
                
            return {
                "status": "success",
                "node": update_data[0]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating graph node: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/schema/{connection_id}/graph/node", tags=["Graph Knowledge"])
async def add_graph_node(
    connection_id: str, 
    node_data: Dict[str, Any]
):
    """
    Añadir un nuevo nodo al grafo de conocimiento
    
    Permite a los administradores añadir nuevas entidades al grafo
    """
    try:
        # Verificar conexión a Neo4j
        if graph_extraction_service.driver is None:
            raise HTTPException(status_code=503, detail="Neo4j connection not available")
        
        # Validar datos del nodo
        if not node_data.get("name"):
            raise HTTPException(status_code=400, detail="Node name is required")
        
        # Verificar que el esquema existe
        schema = await discovery_service.get_schema(connection_id)
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
        
        # Preparar datos del nodo
        node_schema = node_data.get("schema", "custom")
        node_type = node_data.get("type", "table")
        node_description = node_data.get("description", "")
        properties = node_data.get("properties", {})
        
        # Crear nodo
        async with graph_extraction_service.driver.session() as session:
            # Verificar si el nodo ya existe
            node_check = await session.run("""
            MATCH (n:Table {name: $node_name})
            WHERE n.table_id CONTAINS $connection_id
            RETURN count(*) AS node_exists
            """, 
            connection_id=connection_id,
            node_name=node_data["name"])
            
            node_check_data = await node_check.data()
            
            if node_check_data and node_check_data[0]["node_exists"] > 0:
                raise HTTPException(status_code=409, detail="Node already exists")
            
            # Crear ID único para la tabla
            table_id = f"{connection_id}:{node_schema}:{node_data['name']}"
            
            # Crear nodo
            create_result = await session.run("""
            MATCH (db:Database {connection_id: $connection_id})
            CREATE (t:Table {
                table_id: $table_id,
                name: $name,
                schema: $schema,
                description: $description,
                type: $type
            })
            SET t += $additional_properties
            CREATE (db)-[:CONTAINS]->(t)
            RETURN t.name AS name, t.schema AS schema, t.description AS description
            """, 
            connection_id=connection_id,
            table_id=table_id,
            name=node_data["name"],
            schema=node_schema,
            description=node_description,
            type=node_type,
            additional_properties=properties)
            
            create_data = await create_result.data()
            
            if not create_data:
                raise HTTPException(status_code=500, detail="Failed to create node")
                
            return {
                "status": "success",
                "node": create_data[0]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding graph node: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/{connection_id}/graph/community", tags=["Graph Knowledge"])
async def get_graph_communities(connection_id: str):
    """
    Obtener información de comunidades del grafo de conocimiento
    
    Devuelve las comunidades detectadas y su composición
    """
    try:
        # Verificar si tenemos el esquema
        schema = await discovery_service.get_schema(connection_id)
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
            
        # Obtener comunidades
        communities = graph_extraction_service._calculate_communities(schema)
        
        return {
            "status": "success",
            "connection_id": connection_id,
            "communities_count": len(communities),
            "communities": communities
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting graph communities: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/{connection_id}/graph/path", tags=["Graph Knowledge"])
async def find_path_between_tables(
    connection_id: str, 
    from_table: str = Query(..., description="Nombre de la tabla de origen"),
    to_table: str = Query(..., description="Nombre de la tabla de destino"),
    max_depth: int = Query(3, description="Profundidad máxima de búsqueda")
):
    """
    Encontrar caminos en el grafo entre dos tablas
    
    Útil para entender cómo se relacionan las tablas en la base de datos
    """
    try:
        # Verificar si tenemos el esquema
        schema = await discovery_service.get_schema(connection_id)
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
            
        # Buscar caminos
        paths = graph_extraction_service.find_paths(connection_id, from_table, to_table, max_depth)
        
        return {
            "status": "success",
            "connection_id": connection_id,
            "from_table": from_table,
            "to_table": to_table,
            "paths_found": len(paths),
            "paths": paths
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding paths: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/{connection_id}/graph/related", tags=["Graph Knowledge"])
async def find_related_tables(
    connection_id: str, 
    table_name: str = Query(..., description="Nombre de la tabla"),
    max_depth: int = Query(2, description="Profundidad máxima de búsqueda")
):
    """
    Encontrar tablas relacionadas con una tabla dada
    
    Útil para explorar el contexto de una tabla en la base de datos
    """
    try:
        # Verificar si tenemos el esquema
        schema = await discovery_service.get_schema(connection_id)
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
            
        # Buscar tablas relacionadas
        related_tables = graph_extraction_service.find_related_tables(connection_id, table_name, max_depth)
        
        return {
            "status": "success",
            "connection_id": connection_id,
            "table_name": table_name,
            "related_tables_count": len(related_tables),
            "related_tables": related_tables
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding related tables: {e}")
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