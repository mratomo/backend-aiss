# Añadir estos nuevos modelos en la sección de importación (probablemente después de la línea "from pydantic import BaseModel, Field")
from pydantic import BaseModel, Field

# --- Añadir estos nuevos modelos ---
class ModelInfo(BaseModel):
    """Información sobre el modelo activo"""
    model_name: str
    dimension: int

class ModelChangeRequest(BaseModel):
    """Solicitud para cambiar el modelo activo"""
    model_name: str
# --- Fin de nuevos modelos ---

# --- Añadir estos nuevos endpoints al final del archivo, antes de la sección "if __name__ == "__main__": ---
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
                status_code=500,
                detail="No hay un modelo activo inicializado"
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

@app.put("/models/active", tags=["Models"])
async def change_active_model(request: ModelChangeRequest, background_tasks: BackgroundTasks):
    """
    Cambia el modelo de embedding activo
    
    El cambio se realiza en segundo plano, devolviendo inmediatamente 202 Accepted
    """
    try:
        # Validar que el nombre del modelo no esté vacío
        if not request.model_name:
            raise HTTPException(
                status_code=400,
                detail="Nombre de modelo inválido"
            )

        # Iniciar cambio de modelo en segundo plano
        background_tasks.add_task(
            embedding_service.change_active_model,
            request.model_name
        )

        return {
            "status": "accepted",
            "message": f"Iniciado cambio de modelo a {request.model_name}. Este proceso puede tardar varios segundos mientras se descarga el modelo actual y se carga el nuevo.",
            "requested_model": request.model_name
        }
    except Exception as e:
        logger.error(f"Error al iniciar cambio de modelo: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al iniciar cambio de modelo: {str(e)}"
        )
