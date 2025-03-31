import logging
import asyncio
import time
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException, Depends, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config.settings import settings
from models.suggestion import SuggestionRequest, SuggestionResponse, Suggestion
from services.suggestion_service import SuggestionService
from services.llm_service import LLMService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Terminal Suggestion Service",
    description="Service for generating intelligent terminal command suggestions",
    version="1.0.0",
)

# Security
security = HTTPBearer()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services
suggestion_service = SuggestionService()
llm_service = LLMService()

# Background tasks
@app.on_event("startup")
async def startup_event():
    # Start cleanup task
    asyncio.create_task(cleanup_task())

async def cleanup_task():
    """Background task to periodically clean up suggestion cache"""
    while True:
        try:
            count = await suggestion_service.cleanup_cache()
            if count > 0:
                logger.info(f"Cleaned up {count} expired cache entries")
        except Exception as e:
            logger.error(f"Error during cache cleanup: {str(e)}")
        
        # Run every 15 minutes
        await asyncio.sleep(15 * 60)

# API Key validation
async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    """Verify API key if configured"""
    if settings.API_KEY and settings.API_KEY != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return True

# Auth validation
async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify JWT token"""
    # In a real implementation, you would verify the JWT token
    # For now, we'll just check if it exists
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return credentials.credentials

# Health check endpoint
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok", 
        "service": "terminal-suggestion-service",
    }

# API endpoints
@app.post(
    f"{settings.API_PREFIX}/suggest",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_api_key)],
)
async def generate_suggestions(
    request: SuggestionRequest, 
    auth_token: str = Depends(verify_token)
):
    """Generate suggestions for terminal command and output"""
    try:
        start_time = time.time()
        
        result = await suggestion_service.get_suggestions(
            session_id=request.session_id,
            user_id=request.user_id,
            command=request.command,
            output=request.output,
            exit_code=request.exit_code,
            context=request.context,
        )
        
        return result
        
    except Exception as e:
        logger.exception(f"Error generating suggestions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating suggestions: {str(e)}",
        )

@app.get(
    f"{settings.API_PREFIX}/types",
    response_model=Dict[str, List[str]],
    dependencies=[Depends(verify_api_key)],
)
async def get_suggestion_types(auth_token: str = Depends(verify_token)):
    """Get available suggestion types and risk levels"""
    from models.suggestion import SuggestionType, SuggestionRisk
    
    return {
        "types": [t.value for t in SuggestionType],
        "risk_levels": [r.value for r in SuggestionRisk],
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host=settings.HOST, 
        port=settings.PORT,
        reload=settings.DEBUG
    )