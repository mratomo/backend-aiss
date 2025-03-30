import asyncio
import logging
import os
from typing import Dict, List, Optional, Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from config.settings import Settings
from models.query import QueryRequest, AreaQueryRequest, PersonalQueryRequest, QueryResponse
from services.llm_service import LLMService
from services.llm_settings_service import LLMSettingsService
from services.mcp_service import MCPService
from services.query_service import QueryService
from services.retrieval_service import RetrievalService
from models.llm_provider import LLMProvider, LLMProviderCreate, LLMProviderUpdate, LLMProviderType

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
    title="RAG Agent",
    description="Agente para consultas con Retrieval-Augmented Generation",
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
mcp_service = MCPService(settings)
llm_service = LLMService(db, settings)
retrieval_service = RetrievalService(db, settings)
llm_settings_service = LLMSettingsService(db, settings)
query_service = QueryService(db, llm_service, retrieval_service, mcp_service, settings)

@app.on_event("startup")
async def startup_event():
    """Inicializar servicios al iniciar la aplicación"""
    logger.info("Starting RAG Agent...")

    # Verificar conexión a MongoDB
    try:
        await motor_client.admin.command("ping")
        logger.info("Successfully connected to MongoDB")
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        raise

    # Inicializar servicios
    await llm_service.initialize()  # Nuevo método que inicializa proveedores y cliente MCP
    await llm_settings_service.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    """Limpiar recursos al detener la aplicación"""
    logger.info("Shutting down RAG Agent...")
    motor_client.close()

# Endpoint de health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    return {"status": "ok"}

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

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8085")),
        reload=settings.environment == "development",
    )