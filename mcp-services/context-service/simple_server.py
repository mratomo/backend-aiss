#!/usr/bin/env python3
import logging
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear la app de FastAPI
app = FastAPI(title="MCP Context Service - Simple Server")

# Endpoint de health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "context-service (simple)"}

# Iniciar servidor
if __name__ == "__main__":
    uvicorn.run("simple_server:app", host="0.0.0.0", port=8083, reload=True)