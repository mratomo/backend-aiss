import logging
import asyncio
import jwt
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Security, status, Request
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config.settings import settings
from models.terminal import TerminalCommand, TerminalOutput, TerminalContext, AnalysisRequest, ContextResponse
from services.context_service import ContextService
from services.mcp_service import MCPService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Terminal Context Aggregator",
    description="Service for analyzing terminal sessions and providing context for intelligent suggestions",
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
context_service = ContextService()
mcp_service = MCPService()

# Background tasks
cleanup_task_obj = None

@app.on_event("startup")
async def startup_event():
    # Start cleanup task
    global cleanup_task_obj
    cleanup_task_obj = asyncio.create_task(cleanup_task())
    logger.info("Started context cleanup background task")

@app.on_event("shutdown")
async def shutdown_event():
    # Cancel cleanup task
    global cleanup_task_obj
    if cleanup_task_obj:
        cleanup_task_obj.cancel()
        try:
            await cleanup_task_obj
        except asyncio.CancelledError:
            logger.info("Context cleanup task cancelled")
        logger.info("Background tasks stopped")

async def cleanup_task():
    """Background task to periodically clean up old contexts"""
    try:
        while True:
            try:
                count = await context_service.cleanup_old_contexts()
                if count > 0:
                    logger.info(f"Cleaned up {count} old contexts")
            except Exception as e:
                logger.error(f"Error during context cleanup: {str(e)}")
            
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
        "service": "terminal-context-aggregator",
    }

# API endpoints
@app.post(
    f"{settings.API_PREFIX}/analyze",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_api_key)],
)
async def analyze_terminal(request: AnalysisRequest, auth_token: str = Depends(verify_token)):
    """Analyze terminal command and output, update context"""
    try:
        # Handle command update
        if request.command:
            await context_service.update_context_from_command(request.command)
        
        # Handle output update
        if request.output:
            await context_service.update_context_from_output(request.output)
        
        # Get updated context
        context = await context_service.get_context(
            request.session_id, 
            request.user_id
        )
        
        # Analyze context
        analysis = await context_service._analyze_context(context)
        
        # Optionally get suggestions if there's output
        suggestions = []
        if request.output:
            command_text = request.command.command_text if request.command else ""
            suggestions = await context_service._get_suggestions(
                context, 
                command_text, 
                request.output.output_text
            )
        
        return {
            "session_id": request.session_id,
            "context": context.dict(),
            "analysis": analysis,
            "suggestions": suggestions,
        }
        
    except Exception as e:
        logger.exception(f"Error analyzing terminal: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error analyzing terminal: {str(e)}",
        )

@app.post(
    f"{settings.API_PREFIX}/terminal",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_api_key)],
)
async def process_terminal_output(
    request: Dict[str, Any], 
    auth_token: str = Depends(verify_token)
):
    """Process terminal output without structured request/response"""
    try:
        session_id = request.get("session_id")
        user_id = request.get("user_id")
        command = request.get("command", "")
        output = request.get("output", "")
        exit_code = request.get("exit_code", 0)
        
        if not session_id or not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_id and user_id are required",
            )
            
        result = await context_service.analyze_terminal_output(
            session_id=session_id,
            user_id=user_id,
            command_text=command,
            output_text=output,
            exit_code=exit_code,
        )
        
        return result
        
    except Exception as e:
        logger.exception(f"Error processing terminal output: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing terminal output: {str(e)}",
        )

@app.get(
    f"{settings.API_PREFIX}/context/{{session_id}}",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_api_key)],
)
async def get_terminal_context(
    session_id: str, 
    user_id: str, 
    auth_token: str = Depends(verify_token)
):
    """Get terminal context for a session"""
    try:
        context = await context_service.get_context(session_id, user_id)
        return {
            "session_id": session_id,
            "context": context.dict(),
        }
        
    except Exception as e:
        logger.exception(f"Error getting terminal context: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting terminal context: {str(e)}",
        )

@app.post(
    f"{settings.API_PREFIX}/enrich",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_api_key)],
)
async def enrich_with_mcp(
    request: Dict[str, Any], 
    auth_token: str = Depends(verify_token)
):
    """Enrich terminal context with MCP information"""
    try:
        session_id = request.get("session_id")
        user_id = request.get("user_id")
        query = request.get("query", "")
        
        if not session_id or not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_id and user_id are required",
            )
            
        # Get context
        context = await context_service.get_context(session_id, user_id)
        
        # Enrich with MCP
        enrichment = await mcp_service.enrich_context(context, query)
        
        return {
            "session_id": session_id,
            "context": context.dict(),
            "enrichment": enrichment,
        }
        
    except Exception as e:
        logger.exception(f"Error enriching with MCP: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error enriching with MCP: {str(e)}",
        )

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host=settings.HOST, 
        port=settings.PORT,
        reload=settings.DEBUG
    )