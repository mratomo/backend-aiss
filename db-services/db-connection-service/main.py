import logging
import os
from typing import List, Optional, Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Query, Path, Body, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

from config.settings import Settings
from models.models import (
    DBConnection, DBConnectionResponse, DBConnectionUpdate,
    DBAgent, DBAgentUpdate, AgentPrompts, ConnectionAssignment,
    ConnectionAssignmentResponse, DBQueryRequest, DBQueryResponse,
    QueryHistoryItem
)
from services.connection_service import ConnectionService
from services.agent_service import AgentService
from services.encryption_service import EncryptionService
from services.security_service import SecurityService

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
    title="DB Connection Service",
    description="Servicio de gestión de conexiones a bases de datos",
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

# Inicializar servicios
motor_client = AsyncIOMotorClient(settings.mongodb.uri)
db = motor_client[settings.mongodb.database]
encryption_service = EncryptionService(settings.db_connections.encryption_key)
security_service = SecurityService(settings.security)
connection_service = ConnectionService(db, encryption_service, security_service, settings)
agent_service = AgentService(db, connection_service, settings)

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
    try:
        await motor_client.admin.command("ping")
        mongo_status = "ok"
    except Exception as e:
        mongo_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "mongodb": mongo_status,
        "encryption": encryption_service.is_available,
    }

# --- Rutas para conexiones a BD ---

@app.get("/connections", response_model=List[DBConnectionResponse], tags=["Connections"])
async def get_connections():
    """Obtener todas las conexiones a BD"""
    return await connection_service.get_all_connections()

@app.get("/connections/{connection_id}", response_model=DBConnectionResponse, tags=["Connections"])
async def get_connection(connection_id: str):
    """Obtener una conexión específica por ID"""
    connection = await connection_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    return connection

@app.post("/connections", response_model=DBConnectionResponse, status_code=status.HTTP_201_CREATED, tags=["Connections"])
async def create_connection(connection: DBConnection):
    """Crear una nueva conexión a BD"""
    try:
        return await connection_service.create_connection(connection)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/connections/{connection_id}", response_model=DBConnectionResponse, tags=["Connections"])
async def update_connection(connection_id: str, connection_update: DBConnectionUpdate):
    """Actualizar una conexión existente"""
    try:
        updated = await connection_service.update_connection(connection_id, connection_update)
        if not updated:
            raise HTTPException(status_code=404, detail="Conexión no encontrada")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Connections"])
async def delete_connection(connection_id: str):
    """Eliminar una conexión"""
    deleted = await connection_service.delete_connection(connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    return None

@app.post("/connections/{connection_id}/test", tags=["Connections"])
async def test_connection(connection_id: str):
    """Probar una conexión a BD"""
    try:
        result = await connection_service.test_connection(connection_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error probando conexión: {str(e)}")

# --- Rutas para agentes DB ---

@app.get("/agents", response_model=List[DBAgent], tags=["Agents"])
async def get_agents():
    """Obtener todos los agentes DB"""
    return await agent_service.get_all_agents()

@app.get("/agents/{agent_id}", response_model=DBAgent, tags=["Agents"])
async def get_agent(agent_id: str):
    """Obtener un agente específico por ID"""
    agent = await agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return agent

@app.post("/agents", response_model=DBAgent, status_code=status.HTTP_201_CREATED, tags=["Agents"])
async def create_agent(agent: DBAgent):
    """Crear un nuevo agente DB"""
    try:
        return await agent_service.create_agent(agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/agents/{agent_id}", response_model=DBAgent, tags=["Agents"])
async def update_agent(agent_id: str, agent_update: DBAgentUpdate):
    """Actualizar un agente existente"""
    try:
        updated = await agent_service.update_agent(agent_id, agent_update)
        if not updated:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Agents"])
async def delete_agent(agent_id: str):
    """Eliminar un agente"""
    deleted = await agent_service.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return None

# --- Rutas para prompts de agentes ---

@app.get("/agents/{agent_id}/prompts", response_model=AgentPrompts, tags=["Agent Prompts"])
async def get_agent_prompts(agent_id: str):
    """Obtener los prompts configurados para un agente"""
    prompts = await agent_service.get_agent_prompts(agent_id)
    if not prompts:
        raise HTTPException(status_code=404, detail="Agente no encontrado o no tiene prompts configurados")
    return prompts

@app.put("/agents/{agent_id}/prompts", response_model=AgentPrompts, tags=["Agent Prompts"])
async def update_agent_prompts(agent_id: str, prompts: AgentPrompts):
    """Actualizar los prompts para un agente"""
    try:
        updated = await agent_service.update_agent_prompts(agent_id, prompts)
        if not updated:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Rutas para asignación de conexiones a agentes ---

@app.get("/agents/{agent_id}/connections", response_model=List[ConnectionAssignmentResponse], tags=["Agent Connections"])
async def get_agent_connections(agent_id: str):
    """Obtener las conexiones asignadas a un agente"""
    connections = await agent_service.get_agent_connections(agent_id)
    return connections

@app.post("/agents/{agent_id}/connections", response_model=ConnectionAssignmentResponse, tags=["Agent Connections"])
async def assign_connection(agent_id: str, assignment: ConnectionAssignment):
    """Asignar una conexión a un agente"""
    try:
        assignment.agent_id = agent_id  # Asegurarse de que el ID del agente sea el correcto
        result = await agent_service.assign_connection(assignment)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/agents/{agent_id}/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Agent Connections"])
async def remove_connection(agent_id: str, connection_id: str):
    """Eliminar una conexión de un agente"""
    deleted = await agent_service.remove_connection(agent_id, connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    return None

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8086")),
        reload=settings.environment == "development",
    )