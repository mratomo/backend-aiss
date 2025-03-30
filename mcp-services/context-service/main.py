import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Union, Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from fastmcp import MountMCP  # Nuevo: importar MountMCP

from config.settings import Settings
from models.area import Area, AreaCreate, AreaResponse, AreaUpdate
from models.context import Context, ContextCreate, ContextResponse
from services.area_service import AreaService
from services.context_service import ContextService
from services.mcp_service import MCPService
from services.embedding_service_client import EmbeddingServiceClient

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
    title="MCP Context Service",
    description="Servicio de gestión de contextos para Model Context Protocol",
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
area_service = AreaService(db)
context_service = ContextService(db)
embedding_client = EmbeddingServiceClient(settings)
mcp_service = MCPService(settings, area_service, embedding_client)

# Montar servidor MCP usando FastMCP
MountMCP(app, mcp_service.server, settings.mcp.api_route)

@app.on_event("startup")
async def startup_db_client():
    """Inicializar cliente de MongoDB al iniciar la aplicación"""
    logger.info("Connecting to MongoDB...")
    try:
        await motor_client.admin.command("ping")
        logger.info("Successfully connected to MongoDB")
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_db_client():
    """Cerrar cliente de MongoDB al detener la aplicación"""
    logger.info("Closing MongoDB connection...")
    motor_client.close()
    logger.info("MongoDB connection closed")


# Endpoint de health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    return {"status": "ok"}


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