
import logging
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from config.settings import Settings
from models.embedding import (
    EmbeddingRequest, EmbeddingResponse, EmbeddingBatchRequest,
    EmbeddingBatchResponse, EmbeddingType
)
from services.embedding_service import EmbeddingService
from services.vectordb_service import VectorDBService

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Cargar configuración
settings = Settings()

# Crear aplicación FastAPI
app = FastAPI(
    title="Embedding Service",
    description="Servicio de generación de embeddings con soporte GPU",
    version="1.0.0",
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexión a MongoDB
motor_client = AsyncIOMotorClient(settings.mongodb_uri)
db = motor_client[settings.mongodb_database]

# Inicializar servicios
vectordb_service = VectorDBService(settings)
embedding_service = EmbeddingService(db, vectordb_service, settings)


@app.on_event("startup")
async def startup_event():
    """Inicializar servicios al iniciar la aplicación"""
    logger.info("Starting Embedding Service...")

    # Verificar conexión a MongoDB
    try:
        await motor_client.admin.command("ping")
        logger.info("Successfully connected to MongoDB")
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        raise

    # Verificar conexión a Qdrant
    try:
        status = await vectordb_service.get_status()
        logger.info(f"Successfully connected to Vector DB: {status}")
    except Exception as e:
        logger.error(f"Error connecting to Vector DB: {e}")
        raise

    # Inicializar modelos de embeddings
    try:
        await embedding_service.initialize_models()
        logger.info("Embedding models initialized successfully")

        # Verificar disponibilidad de GPU
        if embedding_service.gpu_available:
            logger.info(f"GPU detected and will be used: {embedding_service.gpu_info}")
        else:
            logger.warning("No GPU detected, using CPU for embeddings")
    except Exception as e:
        logger.error(f"Error initializing embedding models: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Limpiar recursos al detener la aplicación"""
    logger.info("Shutting down Embedding Service...")
    motor_client.close()
    await embedding_service.close()


# Endpoint de health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    # Verificar MongoDB
    try:
        await motor_client.admin.command("ping")
        mongo_status = "ok"
    except Exception as e:
        mongo_status = f"error: {str(e)}"

    # Verificar Qdrant
    try:
        qdrant_status = await vectordb_service.get_status()
    except Exception as e:
        qdrant_status = f"error: {str(e)}"

    # Verificar GPU
    gpu_status = "available" if embedding_service.gpu_available else "not available"

    return {
        "status": "ok",
        "mongodb.js": mongo_status,
        "vectordb": qdrant_status,
        "gpu": gpu_status,
        "gpu_info": embedding_service.gpu_info
    }


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
        reload=settings.environment == "development",
    )