from fastapi import FastAPI, HTTPException
import uvicorn
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import json
import hashlib
import uuid
import time

app = FastAPI(title="Mock Embedding Service")

class EmbeddingRequest(BaseModel):
    text: str
    embedding_type: str
    doc_id: str
    owner_id: str
    area_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class SearchRequest(BaseModel):
    query: str
    embedding_type: str = "general"
    owner_id: Optional[str] = None
    area_id: Optional[str] = None
    limit: int = 5

@app.get("/health")
async def health():
    """Endpoint de salud para el servicio mock"""
    return {
        "status": "ok",
        "service": "mock-embedding-service",
        "version": "1.0.0-mock",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gpu_status": "mocked",
        "embedding_model": "mocked-model",
        "response_time_ms": 0.5
    }

@app.post("/embeddings")
async def create_embedding(request: EmbeddingRequest):
    """Endpoint mock para crear embeddings"""
    try:
        # Generar un ID determinista basado en el texto
        hash_obj = hashlib.md5(request.text.encode())
        embedding_id = f"mock_{hash_obj.hexdigest()[:16]}"
        
        # Crear respuesta simulada
        result = {
            "embedding_id": embedding_id,
            "id": embedding_id,
            "doc_id": request.doc_id,
            "owner_id": request.owner_id,
            "embedding_type": request.embedding_type,
            "text_snippet": request.text[:100] + ("..." if len(request.text) > 100 else ""),
            "vector_id": str(uuid.uuid4()),
            "metadata": request.metadata or {},
            "status": "success",
            "is_mock": True
        }
        
        if request.area_id:
            result["area_id"] = request.area_id
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error simulado: {str(e)}")

@app.get("/search")
async def search(query: str, embedding_type: str = "general", owner_id: Optional[str] = None, 
               area_id: Optional[str] = None, limit: int = 5):
    """Endpoint mock para buscar embeddings similares"""
    try:
        # Generar respuestas simuladas
        results = []
        for i in range(min(limit, 3)):  # Simulamos hasta 3 resultados
            hash_val = hashlib.md5(f"{query}_{i}".encode()).hexdigest()[:8]
            results.append({
                "id": f"mock_result_{hash_val}",
                "text": f"Este es un resultado simulado {i+1} para la consulta: {query}",
                "score": 0.95 - (i * 0.1),
                "doc_id": f"doc_{hash_val}",
                "owner_id": owner_id or "mock_owner",
                "is_mock": True
            })
            
            if area_id:
                results[-1]["area_id"] = area_id
                
        return {
            "query": query,
            "embedding_type": embedding_type,
            "limit": limit,
            "results": results,
            "total_results": len(results),
            "is_mock": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error simulado: {str(e)}")

@app.post("/search")
async def search_post(request: SearchRequest):
    """Endpoint mock para buscar embeddings similares (POST)"""
    return await search(
        query=request.query,
        embedding_type=request.embedding_type,
        owner_id=request.owner_id,
        area_id=request.area_id,
        limit=request.limit
    )

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8084, reload=False)