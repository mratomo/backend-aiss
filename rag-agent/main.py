import asyncio
import logging
import os
import time
import platform
from datetime import datetime
from typing import Dict, List, Optional, Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Path, Query, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Mejoras de rendimiento
try:
    import uvloop
    uvloop.install()
    uvloop_available = True
except ImportError:
    uvloop_available = False

# Optimizaciones JSON
try:
    import orjson
    orjson_available = True
except ImportError:
    orjson_available = False

# Monitoreo y métricas
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    prometheus_available = True
    
    # Definir métricas
    HTTP_REQUESTS = Counter('rag_http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'status'])
    HTTP_REQUEST_DURATION = Histogram('rag_http_request_duration_seconds', 'HTTP Request Duration', ['method', 'endpoint'])
    
except ImportError:
    prometheus_available = False

# Monitoreo de recursos
try:
    import psutil
    psutil_available = True
    if prometheus_available:
        MEMORY_USAGE = Gauge('rag_memory_usage_bytes', 'Memory Usage in Bytes')
        CPU_USAGE = Gauge('rag_cpu_usage_percent', 'CPU Usage Percentage')
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
    logger = structlog.get_logger("rag_agent")
    structlog_available = True
except ImportError:
    # Fallback a logging tradicional
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("rag_agent")
    structlog_available = False

from config.settings import Settings
from models.query import QueryRequest, AreaQueryRequest, PersonalQueryRequest, QueryResponse, GraphQueryRequest, QueryType
from models.llm_settings import GlobalSystemPromptUpdate
from services.llm_service import LLMService
from services.llm_settings_service import LLMSettingsService
from services.mcp_service import MCPService
from services.query_service import QueryService
from services.retrieval_service import RetrievalService
from models.llm_provider import LLMProvider, LLMProviderCreate, LLMProviderUpdate, LLMProviderType

# Inicialización de componentes DB necesarios
from services.db_query_service import DBQueryService

# Importar nuevo servicio de Ollama MCP
from services.ollama_mcp_service import OllamaMCPService
from services.ollama_mcp_server import create_ollama_mcp_server

# Cargar configuración
settings = Settings()

# Verificar si debemos ejecutar en modo servidor MCP standalone
if os.getenv("RUN_STANDALONE_MCP_SERVER", "").lower() in ("true", "1", "yes"):
    # Crear y ejecutar el servidor MCP standalone para Ollama
    mcp_server_port = int(os.getenv("PORT", "8095"))
    logger.info(f"Starting Ollama MCP Server in standalone mode on port {mcp_server_port}")
    
    mcp_server_app = create_ollama_mcp_server(settings)
    
    # Configurar CORS para el servidor MCP
    mcp_server_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Crear endpoint de health para el servidor MCP
    @mcp_server_app.get("/health")
    async def mcp_server_health():
        """Verificar salud del servidor MCP para Ollama"""
        try:
            # Verificar conexión con Ollama
            ollama_service = OllamaMCPService(settings)
            health_result = await ollama_service.health_check()
            
            return {
                "status": "ok" if health_result.get("status") == "ok" else "degraded",
                "service": "ollama-mcp-server",
                "timestamp": datetime.utcnow().isoformat(),
                "ollama": health_result
            }
        except Exception as e:
            logger.error(f"Error checking Ollama health: {e}")
            return {
                "status": "degraded",
                "service": "ollama-mcp-server",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
    
    # Si estamos en modo standalone, usar esta app en lugar de la principal
    app = mcp_server_app
    
    # No hay necesidad de más inicialización, detener aquí y ejecutar la app MCP
    if os.getenv("DISABLE_MAIN_APP", "").lower() in ("true", "1", "yes"):
        # No seguir con la inicialización de la app principal
        logger.info("Main application disabled, running only as MCP server")
else:
    # Modo normal: Crear aplicación FastAPI con respuestas optimizadas
    app = FastAPI(
        title="RAG Agent",
        description="Agente para consultas con Retrieval-Augmented Generation",
        version="1.1.0",
        default_response_class=ORJSONResponse if orjson_available else None
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
                    
                    # Actualizar métrica de uso de CPU
                    cpu_percent = process.cpu_percent(interval=1)
                    CPU_USAGE.set(cpu_percent)
                    
                    # Ejecutar cada 15 segundos
                    await asyncio.sleep(15)
                except Exception as e:
                    logger.error("Error updating metrics", error=str(e))
                    await asyncio.sleep(30)  # Esperar más tiempo si hay un error

    # Conexión a MongoDB con reintentos
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
    mcp_service = MCPService(settings)
    llm_service = LLMService(db, settings)
    retrieval_service = RetrievalService(db, settings)
    llm_settings_service = LLMSettingsService(db, settings)

    # Inicializar nuevo servicio de Ollama MCP
    ollama_service = OllamaMCPService(settings)
    
    # Inicializar servicio GraphRAG para consultas basadas en grafos
    from services.graph_rag_service import GraphRAGService
    graph_rag_service = GraphRAGService(db, llm_service, retrieval_service, mcp_service, settings)

    # Inicializar servicio de consultas con el servicio de Ollama
    query_service = QueryService(db, llm_service, retrieval_service, mcp_service, settings, ollama_service=ollama_service)

@app.on_event("startup")
async def startup_event():
    """Inicializar servicios al iniciar la aplicación"""
    logger.info("Starting RAG Agent",
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
                    # En un entorno real, se registraría en un contador de DB_OPERATIONS
                    pass
                break
            except Exception as e:
                if attempt < 5:
                    wait_time = 2 ** attempt  # Espera exponencial
                    logger.warning(f"MongoDB connection attempt {attempt} failed. Retrying in {wait_time}s...", error=str(e))
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to MongoDB after 5 attempts", error=str(e))
                    raise
    except Exception as e:
        logger.error("Error connecting to MongoDB", error=str(e))
        raise

    # Inicializar servicios
    await llm_service.initialize()  # Método que inicializa proveedores y cliente MCP
    await llm_settings_service.initialize()
    
    logger.info("RAG Agent started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Limpiar recursos al detener la aplicación"""
    logger.info("Shutting down RAG Agent...")
    
    try:
        # Cerrar conexión a MongoDB
        motor_client.close()
        logger.info("MongoDB connection closed")
        
        # Cerrar servicio Ollama si está disponible
        if ollama_service:
            await ollama_service.close()
            logger.info("Ollama service closed")
        
        # Cerrar servicio GraphRAG si está disponible
        if graph_rag_service:
            await graph_rag_service.close()
            logger.info("GraphRAG service closed")
        
        # Cerrar otros servicios que puedan tener recursos abiertos
        # Por ejemplo, si query_service tiene un db_query_service inicializado
        if hasattr(query_service, 'db_query_service') and query_service.db_query_service:
            await query_service.db_query_service.close()
            
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
        "service": "rag-agent",
        "version": "1.1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": os.getenv("UPTIME", "unknown")
    }
    
    # Verificar MongoDB
    try:
        await motor_client.admin.command("ping")
        health_status["mongodb"] = "ok"
    except Exception as e:
        health_status["mongodb"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Verificar MCP
    try:
        mcp_status = await mcp_service.get_status()
        health_status["mcp"] = mcp_status
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

# Rutas para consultas RAG
@app.post("/query", response_model=QueryResponse, tags=["Queries"])
async def query_knowledge(request: QueryRequest):
    """
    Realizar una consulta RAG general.
    """
    return await query_service.process_query(
        query=request.query,
        user_id=request.user_id,
        include_personal=request.include_personal,
        area_ids=request.area_ids,
        llm_provider_id=request.llm_provider_id,
        max_sources=request.max_sources,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )

@app.post("/query/area/{area_id}", response_model=QueryResponse, tags=["Queries"])
async def query_specific_area(area_id: str, request: AreaQueryRequest):
    """
    Realizar una consulta RAG en un área específica.
    """
    return await query_service.process_area_query(
        query=request.query,
        user_id=request.user_id,
        area_id=area_id,
        llm_provider_id=request.llm_provider_id,
        max_sources=request.max_sources,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )

@app.post("/query/personal", response_model=QueryResponse, tags=["Queries"])
async def query_personal_knowledge(request: PersonalQueryRequest):
    """
    Realizar una consulta RAG en conocimiento personal.
    """
    return await query_service.process_personal_query(
        query=request.query,
        user_id=request.user_id,
        llm_provider_id=request.llm_provider_id,
        max_sources=request.max_sources,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )


@app.post("/query/graph", response_model=QueryResponse, tags=["Queries"])
async def query_graph_knowledge(request: QueryRequest):
    """
    Realizar una consulta utilizando GraphRAG para mejorar los resultados.
    
    Utiliza un grafo de conocimiento estructurado en Neo4j para enriquecer el contexto de la consulta.
    Especialmente útil para consultas sobre relaciones entre entidades en bases de datos.
    """
    # Si hay área específica, usar su connection_id
    connection_id = None
    if request.area_ids and len(request.area_ids) > 0:
        area = await mcp_service.get_area(request.area_ids[0])
        if area and area.get("metadata", {}).get("connection_id"):
            connection_id = area["metadata"]["connection_id"]
    
    response = await graph_rag_service.process_query_with_graph(
        query=request.query,
        connection_id=connection_id,
        user_id=request.user_id,
        area_id=request.area_ids[0] if request.area_ids else None,
        llm_provider_id=request.llm_provider_id,
        max_sources=request.max_sources,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )
    
    # Establecer el tipo de consulta como GRAPH
    response.query_type = QueryType.GRAPH
    
    return response

@app.post("/query/graph/advanced", response_model=QueryResponse, tags=["Queries"])
async def query_graph_knowledge_advanced(request: GraphQueryRequest):
    """
    Realizar una consulta GraphRAG avanzada con parámetros específicos para el grafo.
    
    Permite controlar aspectos más detallados del procesamiento del grafo, como:
    - Profundidad de exploración
    - Inclusión de comunidades
    - Inclusión de caminos entre entidades
    - Conexión específica de base de datos
    
    Especialmente útil para consultas complejas sobre estructura y relaciones en bases de datos.
    """
    # Determinar connection_id basado en area_id si no se proporciona
    connection_id = request.connection_id
    if not connection_id and request.area_id:
        area = await mcp_service.get_area(request.area_id)
        if area and area.get("metadata", {}).get("connection_id"):
            connection_id = area["metadata"]["connection_id"]
    
    # Opciones avanzadas para el procesamiento del grafo
    options = {
        "exploration_depth": request.exploration_depth,
        "include_communities": request.include_communities,
        "include_paths": request.include_paths
    }
    
    response = await graph_rag_service.process_query_with_graph(
        query=request.query,
        connection_id=connection_id,
        user_id=request.user_id,
        area_id=request.area_id,
        llm_provider_id=request.llm_provider_id,
        max_sources=request.max_sources,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        options=options
    )
    
    # Establecer el tipo de consulta como GRAPH
    response.query_type = QueryType.GRAPH
    
    return response

@app.get("/query/history", tags=["Queries"])
async def get_query_history(user_id: str, limit: int = 10, offset: int = 0):
    """
    Obtener el historial de consultas de un usuario.
    """
    return await query_service.get_query_history(
        user_id=user_id,
        limit=limit,
        offset=offset
    )

# Rutas para proveedores LLM
@app.get("/providers", tags=["LLM Providers"])
async def list_providers():
    """
    Listar todos los proveedores LLM configurados.
    """
    return await llm_service.list_providers()

@app.post("/providers", tags=["LLM Providers"])
async def add_provider(provider_data: LLMProviderCreate):
    """
    Añadir un nuevo proveedor LLM.
    """
    return await llm_service.add_provider(provider_data)

@app.put("/providers/{provider_id}", tags=["LLM Providers"])
async def update_provider(provider_id: str, provider_update: LLMProviderUpdate):
    """
    Actualizar un proveedor LLM existente.
    """
    provider = await llm_service.update_provider(provider_id, provider_update)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider

@app.delete("/providers/{provider_id}", tags=["LLM Providers"])
async def delete_provider(provider_id: str):
    """
    Eliminar un proveedor LLM.
    """
    result = await llm_service.delete_provider(provider_id)
    if not result:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"success": True}

@app.post("/providers/{provider_id}/test", tags=["LLM Providers"])
async def test_provider(provider_id: str, prompt: str = "Responde con un '¡Hola mundo!'"):
    """
    Probar un proveedor LLM con un prompt simple.
    """
    return await llm_service.test_provider(provider_id, prompt)

# Nuevos endpoints para gestionar información de contexto MCP
@app.get("/mcp/status", tags=["MCP Status"])
async def get_mcp_status():
    """
    Obtener el estado actual de la integración MCP
    """
    try:
        # Estado del cliente MCP
        client_status = {
            "available": llm_service.mcp_client is not None,
            "find_tool_available": getattr(llm_service, "has_find_tool", False),
            "store_tool_available": getattr(llm_service, "has_store_tool", False)
        }

        # Estado del servicio MCP
        service_status = await mcp_service.get_status()

        return {
            "client": client_status,
            "service": service_status,
            "using_mcp_tools": settings.use_mcp_tools,
            "prefer_direct_mcp": settings.prefer_direct_mcp
        }
    except Exception as e:
        logger.error(f"Error getting MCP status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting MCP status: {str(e)}")

# Rutas para Ollama MCP
@app.get("/ollama/models", tags=["Ollama"])
async def list_ollama_models():
    """
    Listar modelos disponibles en Ollama
    """
    if not ollama_service:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    models = await ollama_service.list_models()
    return {"models": models}

@app.post("/ollama/generate", tags=["Ollama"])
async def generate_with_ollama(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: str = Query("llama3", description="Modelo de Ollama a utilizar"),
    max_tokens: int = Query(2048, description="Número máximo de tokens a generar"),
    temperature: float = Query(0.2, description="Temperatura para la generación"),
    use_mcp: bool = Query(True, description="Usar integración MCP si está disponible")
):
    """
    Generar texto con Ollama utilizando integración MCP si está disponible
    """
    if not ollama_service:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    # Determinar si usaremos MCP
    mcp_context_ids = None
    if use_mcp and ollama_service.mcp_initialized:
        # En un caso real, podrías obtener contextos relevantes
        active_contexts = await mcp_service.get_active_contexts()
        mcp_context_ids = [ctx.get("id") for ctx in active_contexts]
    
    result = await ollama_service.generate_text(
        prompt=prompt,
        system_prompt=system_prompt or "Eres un asistente útil.",
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        mcp_context_ids=mcp_context_ids
    )
    
    return result

@app.get("/ollama/health", tags=["Ollama"])
async def check_ollama_health():
    """
    Verificar el estado del servicio Ollama
    """
    if not ollama_service:
        return {"status": "unavailable", "message": "Ollama service not initialized"}
    
    health_info = await ollama_service.health_check()
    
    # Añadir información sobre la instancia remota
    health_info["config"] = {
        "api_url": settings.ollama.api_url,
        "mcp_url": settings.ollama.mcp_url,
        "is_remote": settings.ollama.is_remote,
        "default_model": settings.ollama.default_model
    }
    
    return health_info

# Rutas para configuración de system prompts
@app.get("/settings/system-prompt", tags=["Settings"])
async def get_system_prompt():
    """
    Obtener el prompt de sistema global actual.
    """
    settings = await llm_settings_service.get_settings()
    return {
        "system_prompt": settings.default_system_prompt,
        "last_updated": settings.last_updated,
        "updated_by": settings.updated_by
    }

@app.put("/settings/system-prompt", tags=["Settings"])
async def update_system_prompt(update: GlobalSystemPromptUpdate, user_id: Optional[str] = Query(None)):
    """
    Actualizar el prompt de sistema global.
    """
    updated_settings = await llm_settings_service.update_system_prompt(
        system_prompt=update.system_prompt,
        user_id=user_id
    )
    return {
        "system_prompt": updated_settings.default_system_prompt,
        "last_updated": updated_settings.last_updated,
        "updated_by": updated_settings.updated_by
    }

@app.post("/settings/system-prompt/reset", tags=["Settings"])
async def reset_system_prompt(user_id: Optional[str] = Query(None)):
    """
    Restablecer el prompt de sistema global a valores predeterminados.
    """
    reset_settings = await llm_settings_service.reset_to_defaults(user_id=user_id)
    return {
        "system_prompt": reset_settings.default_system_prompt,
        "last_updated": reset_settings.last_updated,
        "updated_by": reset_settings.updated_by
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8085")),
        reload=settings.environment == "development",
    )