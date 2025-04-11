# main.py
import logging
import os
import asyncio
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware

from motor.motor_asyncio import AsyncIOMotorClient

from pydantic import BaseModel, Field, SecretStr



from config.settings import Settings
from models.embedding import (
    EmbeddingRequest, EmbeddingResponse, EmbeddingBatchRequest,
    EmbeddingBatchResponse, EmbeddingType, SearchResult
)
from models.system_prompt import AreaSystemPromptUpdate
from services.embedding_service import EmbeddingService, ModelStatus
from services.vectordb_factory import VectorDBFactory

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Intentar configurar logging estructurado si está disponible
try:
    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logger = structlog.get_logger(__name__)
    logger.info("Configuración de structlog aplicada")
except ImportError:
    logger.info("structlog no está disponible, usando logging estándar")

# Intentar configurar Prometheus si está disponible
custom_registry = None
try:
    from prometheus_client import Counter, Gauge, CollectorRegistry

    custom_registry = CollectorRegistry()

    # Definir métricas básicas
    REQUEST_COUNT = Counter(
        'embedding_request_count',
        'Número de solicitudes al servicio de embeddings',
        ['endpoint', 'status'],
        registry=custom_registry
    )

    EMBEDDING_LATENCY = Gauge(
        'embedding_generation_latency',
        'Tiempo de generación de embeddings en segundos',
        registry=custom_registry
    )

    logger.info("Configuración de Prometheus aplicada")
except ImportError:
    logger.info("prometheus_client no está disponible, no se registrarán métricas")

# Crear la aplicación FastAPI
app = FastAPI(
    title="Embedding Service API",
    description="API para generar embeddings a partir de textos usando modelos de Hugging Face",
    version="1.0.0"
)

# Variables globales para la aplicación
settings = Settings()
mongo_client = None
embedding_service = None

# Definir middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Modelos para endpoints ---

class HFTokenUpdate(BaseModel):
    """Modelo para actualizar el token de Hugging Face"""
    token: SecretStr = Field(..., description="Nuevo token de Hugging Face")


class ModelInfo(BaseModel):
    """Información sobre el modelo activo"""
    model_name: str
    dimension: int


class ModelChangeRequest(BaseModel):
    """Solicitud para cambiar el modelo activo"""
    model_name: str


class ModelStatusResponse(BaseModel):
    """Respuesta con el estado actual del modelo"""
    status: str
    current_model_name: Optional[str] = None
    error: Optional[str] = None
    device: Optional[str] = None
    gpu_info: Optional[str] = None
    vector_dimension: Optional[int] = None


class SearchRequest(BaseModel):
    """Solicitud de búsqueda de embeddings"""
    query: str
    embedding_type: EmbeddingType
    owner_id: Optional[str] = None
    area_id: Optional[str] = None
    limit: int = 10


class SearchResponse(BaseModel):
    """Respuesta de búsqueda de embeddings"""
    results: List[Dict[str, Any]]


# --- Inicialización de dependencias ---
@app.on_event("startup")
async def startup_event():
    global mongo_client, embedding_service

    logger.info("Iniciando servicio de embeddings...")

    # Conectar a MongoDB
    logger.info(f"Conectando a MongoDB: {settings.mongodb_uri}")
    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    database = mongo_client[settings.mongodb_database]

    # Crear servicio vectorial según la configuración
    vectordb_service = VectorDBFactory.create(settings)

    # Inicializar servicio de embeddings
    embedding_service = EmbeddingService(database, vectordb_service, settings)

    # Inicializar configuración de hardware (sin cargar modelos)
    await embedding_service.initialize_models()

    logger.info("Servicio de embeddings iniciado exitosamente")


    # Cargar token guardado si existe
    token_file = os.path.join(os.path.dirname(__file__), "hf_token.cfg")
    if os.path.exists(token_file):
        try:
            with open(token_file, "r") as f:
                saved_token = f.read().strip()
            if saved_token:
                # Usar el token guardado si no hay uno en las variables de entorno
                if "HF_TOKEN" not in os.environ or not os.environ["HF_TOKEN"]:
                    os.environ["HF_TOKEN"] = saved_token
                    logger.info("Token de Hugging Face cargado desde archivo local")

                # Intentar autenticar con Hugging Face
                try:
                    import huggingface_hub
                    huggingface_hub.login(token=os.environ["HF_TOKEN"], add_to_git_credential=False)
                    logger.info("Autenticación con Hugging Face exitosa")
                except Exception as e:
                    logger.warning(f"No se pudo autenticar con Hugging Face: {e}")
        except Exception as e:
            logger.warning(f"Error cargando token guardado: {e}")




@app.on_event("shutdown")
async def shutdown_event():
    global mongo_client, embedding_service

    logger.info("Deteniendo servicio de embeddings...")

    # Cerrar servicios
    if embedding_service:
        await embedding_service.close()

    # Cerrar conexión a MongoDB
    if mongo_client:
        mongo_client.close()

    logger.info("Servicio de embeddings detenido exitosamente")


# --- Endpoints API ---
@app.get("/health", tags=["System"])
async def health_check():
    """
    Verificar la salud del servicio

    Returns:
        Estado de salud del servicio
    """
    try:
        # Verificar conexión a MongoDB
        await mongo_client.admin.command('ping')
        mongodb_status = "ok"
    except Exception as e:
        mongodb_status = f"error: {str(e)}"

    # Verificar conexión a la base de datos vectorial
    vectordb_status = await embedding_service.vectordb_service.get_status()

    # Obtener estado del modelo actual
    model_status = await embedding_service.get_model_status()

    # Verificar salud del servicio de contexto MCP si está configurado
    mcp_status = {"status": "not_configured"}
    if embedding_service.settings.mcp_service_url:
        try:
            is_healthy, details = await embedding_service.check_context_service_health()
            mcp_status = {
                "status": "ok" if is_healthy else "error",
                "details": details
            }
        except Exception as e:
            mcp_status = {
                "status": "error",
                "message": str(e)
            }

    return {
        "status": "ok",
        "version": "1.0.0",
        "dependencies": {
            "mongodb": mongodb_status,
            "vector_db": vectordb_status,
            "mcp_service": mcp_status
        },
        "model": model_status,
        "environment": settings.environment
    }


# --- Endpoints para gestión de modelos ---
@app.get("/models/status", tags=["Models"])
async def get_model_status():
    """
    Obtiene el estado actual del modelo

    Returns:
        Estado del modelo, nombre y error si existe
    """
    status = await embedding_service.get_model_status()
    return ModelStatusResponse(**status)


@app.put("/models/hf-token", tags=["Models"])
async def update_hugging_face_token(token_update: HFTokenUpdate):
    """
    Actualiza el token de autenticación de Hugging Face

    Args:
        token_update: Nuevo token de Hugging Face

    Returns:
        Confirmación de actualización
    """
    try:
        # Obtener el token del request (como string)
        new_token = token_update.token.get_secret_value()

        # Actualizar variable de entorno (tendrá efecto solo en esta instancia)
        os.environ["HF_TOKEN"] = new_token

        # Intentar autenticar con Hugging Face
        try:
            import huggingface_hub
            huggingface_hub.login(token=new_token, add_to_git_credential=False)
            token_is_valid = True
        except Exception as e:
            logger.warning(f"No se pudo verificar el token con Hugging Face: {e}")
            token_is_valid = False

        # Guardar el token en un archivo seguro (opcional para persistencia)
        token_file = os.path.join(os.path.dirname(__file__), "hf_token.cfg")
        try:
            with open(token_file, "w") as f:
                f.write(new_token)
            os.chmod(token_file, 0o600)  # Solo el propietario puede leer/escribir
            token_is_persisted = True
        except Exception as e:
            logger.warning(f"No se pudo guardar el token: {e}")
            token_is_persisted = False

        return {
            "status": "success",
            "message": "Token de Hugging Face actualizado",
            "verified": token_is_valid,
            "persisted": token_is_persisted
        }
    except Exception as e:
        logger.error(f"Error al actualizar token de Hugging Face: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al actualizar token de Hugging Face: {str(e)}"
        )


@app.post("/models/load", status_code=202, tags=["Models"])
async def load_model(request: ModelChangeRequest, background_tasks: BackgroundTasks):
    """
    Carga un modelo de embedding desde Hugging Face Hub

    El proceso de carga se realiza en segundo plano.

    Args:
        request: Solicitud con el nombre del modelo a cargar
        background_tasks: Tareas en segundo plano

    Returns:
        Estado aceptado y mensaje informativo
    """
    # Validar que el nombre del modelo no esté vacío
    if not request.model_name:
        raise HTTPException(
            status_code=400,
            detail="Nombre de modelo inválido"
        )

    # Verificar si ya hay una operación de carga en curso
    if embedding_service.model_status == ModelStatus.LOADING:
        raise HTTPException(
            status_code=409,
            detail="Ya hay una operación de carga en curso. Espere a que termine antes de solicitar otra."
        )

    # Iniciar carga en segundo plano
    background_tasks.add_task(
        embedding_service.change_active_model,
        request.model_name
    )

    return {
        "status": "accepted",
        "message": f"Iniciada carga del modelo {request.model_name}. Este proceso puede tardar varios segundos.",
        "requested_model": request.model_name
    }


@app.delete("/models/unload", status_code=202, tags=["Models"])
async def unload_model(background_tasks: BackgroundTasks):
    """
    Descarga el modelo actualmente cargado para liberar memoria

    El proceso se realiza en segundo plano.

    Args:
        background_tasks: Tareas en segundo plano

    Returns:
        Estado aceptado y mensaje informativo
    """
    # Verificar si hay un modelo cargado
    if embedding_service.current_model_instance is None:
        return {
            "status": "success",
            "message": "No hay modelo cargado para descargar."
        }

    # Verificar si ya hay una operación en curso
    if embedding_service.model_status == ModelStatus.LOADING:
        raise HTTPException(
            status_code=409,
            detail="Hay una operación de carga en curso. Espere a que termine antes de descargar."
        )

    # Obtener el nombre del modelo actual para el mensaje
    current_model = embedding_service.current_model_name

    # Iniciar descarga en segundo plano
    background_tasks.add_task(
        embedding_service.unload_model
    )

    return {
        "status": "accepted",
        "message": f"Iniciada descarga del modelo {current_model}. Este proceso puede tardar algunos segundos.",
        "model_being_unloaded": current_model
    }


@app.get("/models/active", tags=["Models"])
async def get_active_model():
    """
    Obtiene información sobre el modelo de embedding actualmente activo

    Returns:
        Información sobre el modelo activo (nombre y dimensión)
    """
    try:
        if embedding_service.current_model_name is None or embedding_service.current_model_dim is None:
            raise HTTPException(
                status_code=409,
                detail="No hay un modelo activo inicializado. Use el endpoint /models/load primero."
            )

        return ModelInfo(
            model_name=embedding_service.current_model_name,
            dimension=embedding_service.current_model_dim
        )
    except Exception as e:
        logger.error(f"Error obteniendo modelo activo: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo modelo activo: {str(e)}"
        )


# --- Endpoints para crear embeddings ---
@app.post("/embeddings", response_model=EmbeddingResponse, tags=["Embeddings"])
async def create_embedding(embedding_request: EmbeddingRequest):
    """
    Generar embedding para un texto

    Args:
        embedding_request: Datos para generar el embedding

    Returns:
        Información del embedding generado
    """
    try:
        # _get_model_instance() lanzará HTTPException 409 si no hay modelo
        embedding_service._get_model_instance()

        return await embedding_service.create_embedding(
            text=embedding_request.text,
            embedding_type=embedding_request.embedding_type,
            doc_id=embedding_request.doc_id,
            owner_id=embedding_request.owner_id,
            area_id=embedding_request.area_id,
            metadata=embedding_request.metadata
        )
    except HTTPException:
        # Reenviar excepciones de HTTPException
        raise
    except Exception as e:
        logger.error(f"Error generando embedding: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generando embedding: {str(e)}"
        )


@app.post("/embeddings/batch", response_model=EmbeddingBatchResponse, tags=["Embeddings"])
async def create_embeddings_batch(batch_request: EmbeddingBatchRequest):
    """
    Generar embeddings para múltiples textos en batch

    Args:
        batch_request: Datos para generar los embeddings

    Returns:
        Información de los embeddings generados
    """
    try:
        # _get_model_instance() lanzará HTTPException 409 si no hay modelo
        embedding_service._get_model_instance()

        embedding_responses = await embedding_service.create_embeddings_batch(
            texts=batch_request.texts,
            embedding_type=batch_request.embedding_type,
            doc_ids=batch_request.doc_ids,
            owner_id=batch_request.owner_id,
            area_id=batch_request.area_id,
            metadata=batch_request.metadata
        )

        return EmbeddingBatchResponse(embeddings=embedding_responses)
    except HTTPException:
        # Reenviar excepciones de HTTPException
        raise
    except Exception as e:
        logger.error(f"Error generando embeddings batch: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generando embeddings batch: {str(e)}"
        )


@app.post("/embeddings/document", response_model=EmbeddingResponse, tags=["Embeddings"])
async def create_document_embedding(
        file: UploadFile = File(...),
        embedding_type: str = Form(...),
        doc_id: str = Form(...),
        owner_id: str = Form(...),
        area_id: Optional[str] = Form(None),
        metadata: Optional[str] = Form(None)
):
    """
    Generar embedding para un documento (PDF, Word, texto, etc.)

    Args:
        file: Archivo a procesar
        embedding_type: Tipo de embedding ('general' o 'personal')
        doc_id: ID del documento
        owner_id: ID del propietario
        area_id: ID del área (opcional)
        metadata: Metadatos en formato JSON (opcional)

    Returns:
        Información del embedding generado
    """
    try:
        # _get_model_instance() lanzará HTTPException 409 si no hay modelo
        embedding_service._get_model_instance()

        # Leer contenido del archivo
        document_content = await file.read()

        # Parsear metadatos si se proporcionan
        parsed_metadata = None
        if metadata:
            try:
                import json
                parsed_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail="Formato de metadatos inválido. Debe ser un JSON válido."
                )

        # Convertir tipo de embedding a enum
        try:
            embedding_type_enum = EmbeddingType(embedding_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de embedding inválido: {embedding_type}. Debe ser 'general' o 'personal'."
            )

        return await embedding_service.create_document_embedding(
            document=document_content,
            filename=file.filename,
            content_type=file.content_type,
            embedding_type=embedding_type_enum,
            doc_id=doc_id,
            owner_id=owner_id,
            area_id=area_id,
            metadata=parsed_metadata
        )
    except HTTPException:
        # Reenviar excepciones de HTTPException
        raise
    except Exception as e:
        logger.error(f"Error generando embedding para documento: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generando embedding para documento: {str(e)}"
        )


@app.post("/search", response_model=SearchResponse, tags=["Search"])
async def search_embeddings(search_request: SearchRequest):
    """
    Buscar textos similares a una consulta

    Args:
        search_request: Datos para la búsqueda

    Returns:
        Resultados de la búsqueda
    """
    try:
        # _get_model_instance() lanzará HTTPException 409 si no hay modelo
        embedding_service._get_model_instance()

        results = await embedding_service.search(
            query=search_request.query,
            embedding_type=search_request.embedding_type,
            owner_id=search_request.owner_id,
            area_id=search_request.area_id,
            limit=search_request.limit
        )

        return SearchResponse(results=results)
    except HTTPException:
        # Reenviar excepciones de HTTPException
        raise
    except Exception as e:
        logger.error(f"Error en búsqueda: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error en búsqueda: {str(e)}"
        )


@app.delete("/embeddings/{embedding_id}", tags=["Embeddings"])
async def delete_embedding(embedding_id: str):
    """
    Eliminar un embedding por su ID

    Args:
        embedding_id: ID del embedding a eliminar

    Returns:
        Confirmación de eliminación
    """
    try:
        embedding = await embedding_service.get_embedding(embedding_id)
        if not embedding:
            raise HTTPException(
                status_code=404,
                detail=f"Embedding con ID {embedding_id} no encontrado"
            )

        success = await embedding_service.delete_embedding(embedding_id)

        if success:
            return {"status": "success", "message": f"Embedding {embedding_id} eliminado correctamente"}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo eliminar el embedding {embedding_id}"
            )
    except HTTPException:
        # Reenviar excepciones de HTTPException
        raise
    except Exception as e:
        logger.error(f"Error eliminando embedding: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando embedding: {str(e)}"
        )


# --- Endpoints de contexto MCP ---
@app.get("/contexts", tags=["MCP Integration"])
async def list_contexts():
    """
    Listar contextos MCP disponibles

    Returns:
        Lista de contextos MCP
    """
    try:
        # Verificar que el servicio MCP está configurado
        if not embedding_service.settings.mcp_service_url:
            raise HTTPException(
                status_code=501,
                detail="Integración con servicio MCP no configurada"
            )

        return await embedding_service.list_contexts()
    except HTTPException:
        # Reenviar excepciones de HTTPException
        raise
    except Exception as e:
        logger.error(f"Error listando contextos: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listando contextos: {str(e)}"
        )


@app.post("/contexts/{context_id}/activate", tags=["MCP Integration"])
async def activate_context(context_id: str):
    """
    Activar un contexto MCP

    Args:
        context_id: ID del contexto a activar

    Returns:
        Confirmación de activación
    """
    try:
        # Verificar que el servicio MCP está configurado
        if not embedding_service.settings.mcp_service_url:
            raise HTTPException(
                status_code=501,
                detail="Integración con servicio MCP no configurada"
            )

        return await embedding_service.activate_context(context_id)
    except HTTPException:
        # Reenviar excepciones de HTTPException
        raise
    except Exception as e:
        logger.error(f"Error activando contexto: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error activando contexto: {str(e)}"
        )


@app.post("/contexts/{context_id}/deactivate", tags=["MCP Integration"])
async def deactivate_context(context_id: str):
    """
    Desactivar un contexto MCP

    Args:
        context_id: ID del contexto a desactivar

    Returns:
        Confirmación de desactivación
    """
    try:
        # Verificar que el servicio MCP está configurado
        if not embedding_service.settings.mcp_service_url:
            raise HTTPException(
                status_code=501,
                detail="Integración con servicio MCP no configurada"
            )

        return await embedding_service.deactivate_context(context_id)
    except HTTPException:
        # Reenviar excepciones de HTTPException
        raise
    except Exception as e:
        logger.error(f"Error desactivando contexto: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error desactivando contexto: {str(e)}"
        )


@app.put("/areas/{area_id}/system-prompt", tags=["MCP Integration"])
async def update_area_system_prompt(area_id: str, update: AreaSystemPromptUpdate):
    """
    Actualizar el prompt de sistema de un área

    Args:
        area_id: ID del área
        update: Datos para la actualización

    Returns:
        Confirmación de actualización
    """
    # Este endpoint debería implementarse cuando se tenga la estructura en el servicio de embedding
    raise HTTPException(
        status_code=501,
        detail="Endpoint no implementado"
    )


# --- Métricas ---
@app.get("/metrics", tags=["System"])
async def get_metrics():
    """
    Obtener métricas del servicio

    Returns:
        Métricas en formato Prometheus
    """
    if custom_registry is None:
        raise HTTPException(
            status_code=501,
            detail="Métricas no habilitadas. Instale prometheus-client para habilitar esta funcionalidad."
        )

    try:
        from prometheus_client import generate_latest
        metrics = generate_latest(custom_registry).decode("utf-8")

        # Añadir métricas del servicio
        status = await embedding_service.get_model_status()
        metrics += f"""
# HELP embedding_service_model_loaded Is model loaded (1=yes, 0=no)
# TYPE embedding_service_model_loaded gauge
embedding_service_model_loaded {1 if status["status"] == 'loaded' else 0}

# HELP embedding_service_gpu_available Is GPU available (1=yes, 0=no)
# TYPE embedding_service_gpu_available gauge
embedding_service_gpu_available {1 if embedding_service.gpu_available else 0}
"""

        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(metrics, media_type="text/plain")
    except Exception as e:
        logger.error(f"Error generando métricas: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generando métricas: {str(e)}"
        )


# Iniciar servidor directamente si se ejecuta este archivo
if __name__ == "__main__":
    import uvicorn

    # Obtener puerto de la configuración o variables de entorno
    port = int(os.environ.get("PORT", str(settings.port)))

    # Iniciar el servidor
    logger.info(f"Iniciando servidor en puerto {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)