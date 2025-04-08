import logging
import asyncio
import time
import jwt
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
    allow_origins=settings.ALLOWED_ORIGINS,  # Get from settings
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Services
suggestion_service = SuggestionService()
llm_service = LLMService()

# Background tasks
cleanup_task_obj = None

@app.on_event("startup")
async def startup_event():
    # Start cleanup task
    global cleanup_task_obj
    cleanup_task_obj = asyncio.create_task(cleanup_task())
    logger.info("Started suggestion cache cleanup background task")

@app.on_event("shutdown")
async def shutdown_event():
    # Cancel cleanup task
    global cleanup_task_obj
    if cleanup_task_obj:
        cleanup_task_obj.cancel()
        try:
            await cleanup_task_obj
        except asyncio.CancelledError:
            logger.info("Suggestion cache cleanup task cancelled")
        logger.info("Background tasks stopped")

async def cleanup_task():
    """Background task to periodically clean up suggestion cache"""
    try:
        while True:
            try:
                count = await suggestion_service.cleanup_cache()
                if count > 0:
                    logger.info(f"Cleaned up {count} expired cache entries")
            except Exception as e:
                logger.error(f"Error during cache cleanup: {str(e)}")
            
            # Run every 15 minutes
            await asyncio.sleep(15 * 60)
    except asyncio.CancelledError:
        logger.info("Cleanup task cancelled during shutdown")
        raise

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
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    
    token = credentials.credentials
    
    try:
        # Decode the JWT token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        # Add basic validation of payload
        if not payload.get("user_id"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing user_id claim",
            )
        
        return token
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )

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