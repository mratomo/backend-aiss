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

# Jobs activos con lock para proteger acceso concurrente
active_jobs: Dict[str, Dict[str, Any]] = {}
active_jobs_lock = asyncio.Lock()  # Lock para proteger acceso concurrente a active_jobs

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
    
    try:
        # Cerrar cliente HTTP correctamente
        await http_client.close()
        logger.info("HTTP client closed successfully")
        
        # Limpiar trabajos activos
        async with active_jobs_lock:
            job_count = len(active_jobs)
            active_jobs.clear()
            logger.info(f"Cleared {job_count} active jobs")
            
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Endpoint de health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Verificar salud del servicio"""
    # Verificar estado de memoria y eliminar jobs antiguos si es necesario
    try:
        async with active_jobs_lock:
            # Limpiar trabajos antiguos para prevenir fugas de memoria
            current_time = datetime.utcnow()
            jobs_count = len(active_jobs)
            old_jobs = [job_id for job_id, job_info in active_jobs.items() 
                        if "started_at" in job_info and 
                        (current_time - job_info["started_at"]).total_seconds() > 86400]  # 24 horas
            
            # Eliminar trabajos antiguos
            for job_id in old_jobs:
                del active_jobs[job_id]
                
            # Reportar limpieza si ocurrió
            cleaned_jobs = len(old_jobs)
            if cleaned_jobs > 0:
                logger.info(f"Cleaned up {cleaned_jobs} old jobs during health check")
    except Exception as e:
        logger.error(f"Error cleaning old jobs: {e}")
    
    # Devolver estado del servicio
    return {
        "status": "ok",
        "active_jobs": len(active_jobs),
        "memory_usage": {
            "active_jobs_count": len(active_jobs),
        },
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

# Función para ejecutar descubrimiento en segundo plano
async def discover_schema_background(job_id: str, connection_id: str, options: Optional[Any] = None):
    """
    Ejecutar descubrimiento de esquema en segundo plano
    
    Args:
        job_id: ID del trabajo
        connection_id: ID de la conexión
        options: Opciones de descubrimiento
    """
    # Establecer límite de tiempo para el job
    job_timeout = settings.schema.schema_discovery_timeout + 120  # Timeout base + margen adicional
    start_time = datetime.utcnow()
    
    try:
        # Actualizar estado (thread-safe)
        async with active_jobs_lock:
            if job_id in active_jobs:
                active_jobs[job_id]["status"] = SchemaDiscoveryStatus.IN_PROGRESS
                active_jobs[job_id]["memory_usage"] = 0  # Inicializar tracking de memoria
        
        try:
            # Iniciar descubrimiento con timeout
            schema = await asyncio.wait_for(
                discovery_service.discover_schema(connection_id, options),
                timeout=job_timeout
            )
            
            # Si se completó correctamente, vectorizar
            if schema and schema.status == SchemaDiscoveryStatus.COMPLETED:
                try:
                    # Crear una sesión específica para vectorizar con timeout y asegurar que se cierre
                    async with aiohttp.ClientSession() as session:
                        vector_id = await asyncio.wait_for(
                            vectorization_service.vectorize_schema(schema, session),
                            timeout=60  # 1 minuto para vectorización
                        )
                        
                        # Actualizar esquema con ID del vector
                        schema.vector_id = vector_id
                        await discovery_service.save_schema(schema)
                except asyncio.TimeoutError:
                    logger.error(f"Timeout vectorizing schema for job {job_id}")
                    # Continuar sin vectorizar
                except Exception as e:
                    logger.error(f"Error vectorizing schema for job {job_id}: {e}")
                    # Continuar sin vectorizar
            
            # Actualizar estado del trabajo (thread-safe)
            async with active_jobs_lock:
                if job_id in active_jobs:
                    active_jobs[job_id]["status"] = schema.status if schema else SchemaDiscoveryStatus.FAILED
                    active_jobs[job_id]["completed_at"] = datetime.utcnow()
                    
        except asyncio.TimeoutError:
            logger.error(f"Job {job_id} timed out after {job_timeout} seconds")
            
            # Actualizar estado con timeout (thread-safe)
            async with active_jobs_lock:
                if job_id in active_jobs:
                    active_jobs[job_id]["status"] = SchemaDiscoveryStatus.FAILED
                    active_jobs[job_id]["error"] = f"Job timed out after {job_timeout} seconds"
            
            # Guardar esquema con error de timeout
            schema_timeout = DatabaseSchema(
                connection_id=connection_id,
                name=f"Timeout: {connection_id}",
                type="unknown",
                status=SchemaDiscoveryStatus.FAILED,
                discovery_date=datetime.utcnow(),
                error=f"Schema discovery timed out after {job_timeout} seconds"
            )
            await discovery_service.save_schema(schema_timeout)
            
    except Exception as e:
        logger.error(f"Error in schema discovery job {job_id}: {e}")
        
        # Actualizar estado con error (thread-safe)
        async with active_jobs_lock:
            if job_id in active_jobs:
                active_jobs[job_id]["status"] = SchemaDiscoveryStatus.FAILED
                active_jobs[job_id]["error"] = str(e)
                active_jobs[job_id]["completed_at"] = datetime.utcnow()
        
        # Guardar esquema con error
        schema_error = DatabaseSchema(
            connection_id=connection_id,
            name="Discovery Failed",
            type="unknown",
            status=SchemaDiscoveryStatus.FAILED,
            discovery_date=datetime.utcnow(),
            error=str(e)
        )
        await discovery_service.save_schema(schema_error)
    finally:
        # Calcular tiempo de ejecución
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Job {job_id} completed in {execution_time:.2f} seconds")
        
        # Reducir el tiempo de retención de jobs completados o fallidos
        # para evitar acumular demasiados en memoria
        retention_time = 3600  # 1 hora por defecto
        if execution_time > 300:  # Si tomó más de 5 minutos
            # Menor retención para jobs largos (10 minutos)
            retention_time = 600
        
        # Mantener el job en memoria por el tiempo de retención
        try:
            await asyncio.sleep(retention_time)
        except asyncio.CancelledError:
            logger.info(f"Job retention sleep cancelled for {job_id}")
        
        # Eliminar job de manera thread-safe
        async with active_jobs_lock:
            if job_id in active_jobs:
                # Capturar estado final para logging
                final_status = active_jobs[job_id].get("status", "unknown")
                del active_jobs[job_id]
                logger.info(f"Removed job {job_id} from memory (final status: {final_status})")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8087")),
        reload=settings.environment == "development",
    )