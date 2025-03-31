import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import aiohttp
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query, Path
from fastapi.middleware.cors import CORSMiddleware

from config.settings import Settings
from models.models import (
    DatabaseSchema, SchemaDiscoveryRequest, SchemaDiscoveryResponse,
    SchemaDiscoveryStatus, SchemaAnalysisResponse, SchemaInsight,
    SchemaQuerySuggestion
)
from services.discovery_service import SchemaDiscoveryService
from services.vectorization_service import SchemaVectorizationService
from services.analysis_service import SchemaAnalysisService

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
    title="Schema Discovery Service",
    description="Servicio de descubrimiento y análisis de esquemas de bases de datos",
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

# Jobs activos
active_jobs: Dict[str, Dict[str, Any]] = {}

# Inicializar servicios
http_client = aiohttp.ClientSession()
discovery_service = SchemaDiscoveryService(http_client, settings)
vectorization_service = SchemaVectorizationService(http_client, settings)
analysis_service = SchemaAnalysisService(settings)

@app.on_event("startup")
async def startup_event():
    """Inicializar servicios al iniciar la aplicación"""
    logger.info("Starting Schema Discovery Service")

@app.on_event("shutdown")
async def shutdown_event():
    """Limpiar recursos al detener la aplicación"""
    logger.info("Shutting down Schema Discovery Service")
    await http_client.close()

# Endpoint de health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    return {
        "status": "ok",
        "active_jobs": len(active_jobs),
        "timestamp": datetime.utcnow()
    }

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
        
        # Registrar trabajo
        start_time = datetime.utcnow()
        estimated_completion = start_time + timedelta(seconds=settings.schema.schema_discovery_timeout)
        
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
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = active_jobs[job_id]
    
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
        
        # Vectorizar esquema
        vector_id = await vectorization_service.vectorize_schema(schema)
        
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

# Función para ejecutar descubrimiento en segundo plano
async def discover_schema_background(job_id: str, connection_id: str, options: Optional[Any] = None):
    """
    Ejecutar descubrimiento de esquema en segundo plano
    
    Args:
        job_id: ID del trabajo
        connection_id: ID de la conexión
        options: Opciones de descubrimiento
    """
    try:
        # Actualizar estado
        active_jobs[job_id]["status"] = SchemaDiscoveryStatus.IN_PROGRESS
        
        # Iniciar descubrimiento
        schema = await discovery_service.discover_schema(connection_id, options)
        
        # Si se completó correctamente, vectorizar
        if schema.status == SchemaDiscoveryStatus.COMPLETED:
            try:
                vector_id = await vectorization_service.vectorize_schema(schema)
                
                # Actualizar esquema con ID del vector
                schema.vector_id = vector_id
                await discovery_service.save_schema(schema)
            except Exception as e:
                logger.error(f"Error vectorizing schema: {e}")
        
        # Actualizar estado del trabajo
        active_jobs[job_id]["status"] = schema.status
    except Exception as e:
        logger.error(f"Error in schema discovery job {job_id}: {e}")
        
        # Actualizar estado con error
        active_jobs[job_id]["status"] = SchemaDiscoveryStatus.FAILED
        active_jobs[job_id]["error"] = str(e)
        
        # Guardar esquema con error
        schema = DatabaseSchema(
            connection_id=connection_id,
            name="Discovery Failed",
            type="unknown",
            status=SchemaDiscoveryStatus.FAILED,
            discovery_date=datetime.utcnow(),
            error=str(e)
        )
        await discovery_service.save_schema(schema)
    finally:
        # Limpiar trabajo después de un tiempo
        await asyncio.sleep(3600)  # Mantener en memoria por 1 hora
        if job_id in active_jobs:
            del active_jobs[job_id]

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8087")),
        reload=settings.environment == "development",
    )