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

# Configurar logging primero para tener mejores mensajes de error
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("context_service")

# Importación directa de FastMCP - CRÍTICO: debe estar disponible
try:
    import mcp
    from fastmcp import FastMCP
    from fastapi import FastAPI
    
    # Verificar la versión de las bibliotecas
    mcp_version = getattr(mcp, "__version__", "desconocida")
    fastmcp_version = getattr(FastMCP, "__version__", "desconocida")
    
    logger.info(f"MCP importado correctamente (versión: {mcp_version})")
    logger.info(f"FastMCP importado correctamente (versión: {fastmcp_version})")
    
    # Validar que FastMCP funcione como app montable en FastAPI
    # Verificamos que tenga las características necesarias
    is_valid_app = hasattr(FastMCP, "__init__") and hasattr(FastMCP, "__call__")
    USE_FASTMCP = is_valid_app
    
    if USE_FASTMCP:
        logger.info("FastMCP parece compatible con FastAPI")
    else:
        logger.warning("FastMCP está instalado pero no parece compatible con FastAPI")
except ImportError as e:
    logger.error(f"Error importando MCP o FastMCP: {e}")
    USE_FASTMCP = False

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

# Configuración de integración MCP con FastAPI
# Usamos implementación Starlette/FastAPI - MCP
from fastapi import APIRouter

if USE_FASTMCP:
    try:
        logger.info(f"Configurando MCP como router FastAPI en ruta: {settings.mcp.api_route}")
        
        # Crear un router FastAPI dedicado para los endpoints MCP
        mcp_router = APIRouter(prefix=settings.mcp.api_route, tags=["MCP"])
        
        # Crear una instancia de FastMCP para gestionar herramientas
        mcp_app = FastMCP(name="MCP Knowledge Server")
        
        # Registrar herramientas en FastMCP
        @mcp_app.tool(name="store_document", 
                  description="Almacena un texto en la base de conocimiento vectorial")
        async def store_document_tool(information: str, metadata: dict = None):
            """Almacena un texto en la base de conocimiento"""
            if not metadata:
                metadata = {}
            
            # Llamamos a la implementación existente
            for tool in mcp_service.server.tools:
                if tool.name == "store_document":
                    return await tool.func(information=information, metadata=metadata)
            
            return "Herramienta no disponible"
        
        @mcp_app.tool(name="find_relevant", 
                  description="Busca en la base de conocimiento los textos más similares a una consulta")
        async def find_relevant_tool(query: str, embedding_type: str = "general", 
                       owner_id: str = None, area_id: str = None, limit: int = 5):
            """Busca información relevante para una consulta"""
            for tool in mcp_service.server.tools:
                if tool.name == "find_relevant":
                    return await tool.func(
                        query=query, 
                        embedding_type=embedding_type, 
                        owner_id=owner_id, 
                        area_id=area_id, 
                        limit=limit
                    )
            
            return ["Herramienta no disponible"]
        
        # Almacenar referencia a FastMCP en servicio MCP
        mcp_service.fastmcp = mcp_app
        
        # Implementar endpoints MCP estándar como rutas FastAPI
        
        # Endpoint de estado
        @mcp_router.get("/status")
        async def mcp_status():
            """Obtener estado del servidor MCP"""
            try:
                # Obtener información básica de estado
                status = mcp_service.get_status()
                # La función list_tools es asincrónica en FastMCP, debemos esperarla
                try:
                    tools = await mcp_app.list_tools()
                    status["tools"] = tools
                except Exception as tool_error:
                    logger.error(f"Error obteniendo herramientas: {tool_error}")
                    status["tools"] = []
                return status
            except Exception as e:
                logger.error(f"Error en endpoint MCP status: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(e)
                )
        
        # Endpoint de herramientas
        @mcp_router.get("/tools")
        async def mcp_tools():
            """Listar herramientas MCP disponibles"""
            try:
                # list_tools es asincrónica, debemos esperarla
                tools = await mcp_app.list_tools()
                return {"tools": tools}
            except Exception as e:
                logger.error(f"Error en endpoint MCP tools: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(e)
                )
        
        # Endpoint para contextos activos
        @mcp_router.get("/active-contexts")
        async def mcp_active_contexts():
            """Obtener contextos activos MCP"""
            try:
                return mcp_service.get_active_contexts()
            except Exception as e:
                logger.error(f"Error en endpoint MCP active-contexts: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(e)
                )
        
        # Endpoint para llamar a herramientas
        @mcp_router.post("/tools/{tool_name}")
        async def call_tool(tool_name: str, request: Request):
            """Llamar a una herramienta MCP por nombre"""
            try:
                # Recibir datos del request
                data = await request.json()
                
                # Transformar el formato del nombre de la herramienta
                # Las URLs pueden tener guión, pero nuestras herramientas usan guión bajo
                tool_name_normalized = tool_name.replace("-", "_")
                logger.info(f"Comprobando herramienta: {tool_name} (normalizado a: {tool_name_normalized})")
                
                # Simplificamos la verificación de herramientas
                # Nos limitamos a las herramientas conocidas
                if tool_name_normalized in ["store_document", "find_relevant"]:
                    tool_exists = True
                    # Usaremos el nombre normalizado para buscar la herramienta
                    tool_name = tool_name_normalized
                else:
                    tool_exists = False
                    logger.warning(f"Herramienta desconocida: {tool_name}")
                
                if not tool_exists:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Tool not found: {tool_name}"
                    )
                
                logger.info(f"Llamando a herramienta {tool_name} con parámetros: {data}")
                
                # Las herramientas registradas directamente en MCPService
                if tool_name == "store_document":
                    for tool in mcp_service.server.tools:
                        if tool.name == "store_document":
                            result = await tool.func(
                                information=data.get("information", ""), 
                                metadata=data.get("metadata", {})
                            )
                            return {"result": result}
                            
                elif tool_name == "find_relevant":
                    for tool in mcp_service.server.tools:
                        if tool.name == "find_relevant":
                            result = await tool.func(
                                query=data.get("query", ""),
                                embedding_type=data.get("embedding_type", "general"),
                                owner_id=data.get("owner_id"),
                                area_id=data.get("area_id"),
                                limit=data.get("limit", 5)
                            )
                            return {"result": result}
                
                # Si no se ha manejado por las funciones anteriores,
                # intentar llamar a través de FastMCP
                try:
                    result = await mcp_app.call_tool(tool_name, **data)
                    return {"result": result}
                except Exception as tool_err:
                    logger.error(f"Error usando FastMCP call_tool: {tool_err}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error en call_tool: {str(tool_err)}"
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error calling tool {tool_name}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(e)
                )
        
        # Incluir el router MCP en la aplicación principal
        app.include_router(mcp_router)
        logger.info("MCP Router incluido en FastAPI correctamente")
        
    except Exception as e:
        logger.error(f"Error configurando MCP en FastAPI: {str(e)}")
        logger.error(f"Detalle del error: {type(e).__name__}: {str(e)}")
        USE_FASTMCP = False

# Si no podemos usar FastMCP o falló el montaje, implementamos manualmente
if not USE_FASTMCP:
    logger.info(f"Implementando rutas MCP manualmente en: {settings.mcp.api_route}")
    
    # Status endpoint
    @app.get(f"{settings.mcp.api_route}/status", tags=["MCP"])
    async def mcp_status():
        """Obtener estado del servidor MCP"""
        try:
            return mcp_service.get_status()
        except Exception as e:
            logger.error(f"Error al obtener estado MCP: {str(e)}")
            return {
                "name": "MCP Knowledge Server",
                "version": settings.mcp.server_version,
                "status": "error",
                "error": str(e)
            }
    
    # Active contexts endpoint
    @app.get(f"{settings.mcp.api_route}/active-contexts", tags=["MCP"])
    async def mcp_active_contexts():
        """Obtener contextos activos"""
        try:
            return mcp_service.get_active_contexts()
        except Exception as e:
            logger.error(f"Error al obtener contextos activos MCP: {str(e)}")
            return []
    
    # Store document tool
    @app.post(f"{settings.mcp.api_route}/tools/store-document", tags=["MCP Tools"])
    async def mcp_store_document(request: Request):
        """Almacenar documento en MCP"""
        try:
            data = await request.json()
            information = data.get("information", "")
            metadata = data.get("metadata", {})
            
            # Buscar la herramienta por nombre
            for tool in mcp_service.server.tools:
                if tool.name == "store_document":
                    result = await tool.func(information=information, metadata=metadata)
                    return {"result": result}
            
            return {"error": "Herramienta store_document no encontrada"}
        except Exception as e:
            logger.error(f"Error al almacenar documento: {str(e)}")
            return {"error": str(e)}
    
    # Find relevant tool
    @app.post(f"{settings.mcp.api_route}/tools/find-relevant", tags=["MCP Tools"])
    async def mcp_find_relevant(request: Request):
        """Buscar información relevante en MCP"""
        try:
            data = await request.json()
            query = data.get("query", "")
            embedding_type = data.get("embedding_type", "general")
            owner_id = data.get("owner_id")
            area_id = data.get("area_id")
            limit = data.get("limit", 5)
            
            # Obtener herramienta directamente
            for tool in mcp_service.server.tools:
                if tool.name == "find_relevant":
                    result = await tool.func(
                        query=query, 
                        embedding_type=embedding_type, 
                        owner_id=owner_id, 
                        area_id=area_id, 
                        limit=limit
                    )
                    return {"results": result}
            
            return {"error": "Herramienta find_relevant no encontrada"}
        except Exception as e:
            logger.error(f"Error al buscar información relevante: {str(e)}")
            return {"error": str(e)}


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
    
    # Verificar conexión a MongoDB con mayor tolerancia a fallos
    logger.info("Connecting to MongoDB...")
    connected = False
    max_attempts = 10  # Aumentamos número de intentos
    
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                await motor_client.admin.command("ping")
                logger.info(f"Successfully connected to MongoDB on attempt {attempt}")
                if prometheus_available:
                    DB_OPERATIONS.labels(operation="connect", status="success").inc()
                connected = True
                break
            except Exception as e:
                if attempt < max_attempts:
                    wait_time = min(2 ** attempt, 30)  # Espera exponencial con máximo de 30 segundos
                    logger.warning(f"MongoDB connection attempt {attempt}/{max_attempts} failed. Retrying in {wait_time}s...", error=str(e))
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to MongoDB after {max_attempts} attempts", error=str(e))
                    if prometheus_available:
                        DB_OPERATIONS.labels(operation="connect", status="error").inc()
        
        # Si después de todos los intentos aún no se ha conectado pero no queremos fallar completamente
        if not connected:
            logger.warning("Unable to establish initial MongoDB connection; service will continue and retry later")
            # No lanzamos excepción para permitir que el servicio continúe y reintente en las operaciones
            
    except Exception as e:
        logger.error("Unexpected error connecting to MongoDB", error=str(e))
        # No lanzamos excepción para permitir que el servicio continúe
        logger.warning("Service will continue despite MongoDB connection issues")


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

# ----- Endpoints para gestión del LLM principal en Áreas -----

class PrimaryLLMUpdateRequest(BaseModel):
    llm_provider_id: str = Field(..., description="ID del proveedor LLM principal para el área")

@app.put("/areas/{area_id}/primary-llm", response_model=AreaResponse, tags=["Areas"])
async def update_area_primary_llm(area_id: str, request: PrimaryLLMUpdateRequest):
    """
    Asignar o actualizar el proveedor LLM principal de un área de conocimiento
    """
    try:
        updated_area = await area_service.update_area_primary_llm(area_id, request.llm_provider_id)
        return AreaResponse.from_db_model(updated_area)
    except Exception as e:
        logger.error(f"Error updating area primary LLM: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating area primary LLM: {str(e)}"
        )

@app.get("/areas/{area_id}/primary-llm", tags=["Areas"])
async def get_area_primary_llm(area_id: str = Path(..., description="ID del área")):
    """
    Obtener el proveedor LLM principal de un área de conocimiento
    """
    try:
        area = await area_service.get_area(area_id)
        if not area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Area not found: {area_id}"
            )
        return {"area_id": area_id, "primary_llm_provider_id": area.primary_llm_provider_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting area primary LLM: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting area primary LLM: {str(e)}"
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


# ----- Extensiones MCP para integración con terminal -----

class TerminalContextRequest(BaseModel):
    """
    Request model for terminal context retrieval
    
    Esta es una extensión del protocolo MCP estándar para permitir
    la recuperación de contexto específico para terminales.
    """
    query: str
    context: Dict[str, Any]
    max_results: Optional[int] = Field(default=5)

@app.post("/api/v1/context/retrieve", tags=["MCP-Extension"])
async def retrieve_terminal_context(request: TerminalContextRequest):
    """
    Retrieve relevant context for a terminal command/query
    
    This is an MCP extension designed to work with the terminal context aggregator.
    It provides a standardized way to retrieve relevant context for terminal commands
    and integrates with the MCP standard tools.
    """
    try:
        query = request.query
        terminal_context = request.context.get("terminal_context", {})
        user_id = request.context.get("user_id")
        
        # Check if we have the information we need
        if not query or not user_id:
            return {
                "relevant_context": [],
                "context_score": 0,
                "message": "Missing required information in request"
            }
        
        # Construct a rich query combining the query with terminal context
        rich_query = f"""Query: {query}
Current directory: {terminal_context.get('current_directory')}
Current user: {terminal_context.get('current_user')}
Recent commands: {terminal_context.get('command_history', '')}
"""
        
        # Use the MCP find_relevant tool to find relevant information
        try:
            # Find any contexts associated with the user
            contexts = await mcp_service.server.tools[0].func(
                query=rich_query,
                embedding_type="general",
                limit=request.max_results
            )
            
            if isinstance(contexts, list) and contexts:
                return {
                    "relevant_context": contexts,
                    "context_score": 0.8,
                    "message": "Found relevant context using MCP"
                }
            else:
                # Try a more generic search if user-specific search yields no results
                contexts = await mcp_service.server.tools[0].func(
                    query=query,
                    embedding_type="general",
                    limit=request.max_results
                )
                
                return {
                    "relevant_context": contexts if isinstance(contexts, list) else [],
                    "context_score": 0.5,
                    "message": "Found general context"
                }
                
        except Exception as e:
            logger.error(f"Error using MCP tools for terminal context: {e}")
            # Provide empty results rather than failing
            return {
                "relevant_context": [],
                "context_score": 0,
                "message": f"Error searching context: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"Error in retrieve_terminal_context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving terminal context: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8083")),
        reload=settings.environment == "development",
    )