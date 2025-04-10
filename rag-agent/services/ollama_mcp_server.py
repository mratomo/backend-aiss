import asyncio
import os
import logging
from typing import Dict, List, Optional, Any, Union

import httpx

# Importamos correctamente FastMCP
from fastmcp import FastMCP
            
# Función para crear el servidor MCP
def create_ollama_mcp_server(settings):
    """
    Crea y configura un servidor MCP para Ollama
    
    Args:
        settings: Configuración global de la aplicación
        
    Returns:
        FastAPI app con el servidor MCP configurado
    """
    from fastapi import FastAPI
    app = FastAPI(title="Ollama MCP Server")
    
    # Crear instancia de OllamaMCPServer
    server = OllamaMCPServer(api_url=settings.ollama_api_base)
    
    # Configurar FastMCP con FastAPI
    mcp_server = FastMCP.create_fastapi_app(
        name="ollama_mcp",
        description="Ollama MCP Server for LLM operations",
        server=server.mcp
    )
    
    # Incluir la aplicación MCP en la app principal
    app.mount("/mcp", mcp_server)
    
    @app.get("/")
    async def root():
        return {"message": "Ollama MCP Server is running", "endpoints": ["/mcp"]}
    
    return app

try:
    import structlog
    logger = structlog.get_logger("ollama_mcp_server")
    structlog_available = True
except ImportError:
    logger = logging.getLogger("ollama_mcp_server")
    structlog_available = False

class OllamaMCPServer:
    """Servidor MCP para Ollama"""
    
    def __init__(self, api_url: str = "http://localhost:11434"):
        """
        Inicializar servidor MCP para Ollama
        
        Args:
            api_url: URL de la API de Ollama
        """
        self.api_url = api_url
        self.mcp = FastMCP("ollama_service")
        self._setup_tools()
        
    def _setup_tools(self):
        """Configurar herramientas MCP para Ollama"""
        
        @self.mcp.tool()
        async def ollama_list_models() -> List[Dict[str, Any]]:
            """
            Listar todos los modelos disponibles en Ollama
            
            Returns:
                Lista de modelos disponibles
            """
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.api_url}/api/tags")
                    response.raise_for_status()
                    return response.json().get("models", [])
            except Exception as e:
                logger.error(f"Error listing Ollama models: {e}")
                raise ValueError(f"Error listing models: {str(e)}")
        
        @self.mcp.tool()
        async def ollama_generate_text(
            prompt: str,
            system_prompt: Optional[str] = None,
            model: str = "llama3",
            max_tokens: int = 2048,
            temperature: float = 0.2
        ) -> str:
            """
            Generar texto usando un modelo de Ollama
            
            Args:
                prompt: Texto para generar la respuesta
                system_prompt: Instrucciones para el sistema (opcional)
                model: Nombre del modelo a utilizar
                max_tokens: Número máximo de tokens a generar
                temperature: Temperatura para la generación (0.0 a 1.0)
                
            Returns:
                Texto generado por el modelo
            """
            try:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature
                    },
                    "stream": False
                }
                
                # Añadir system prompt si está presente
                if system_prompt:
                    payload["system"] = system_prompt
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/api/generate",
                        json=payload,
                        timeout=120.0
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result.get("response", "")
            except Exception as e:
                logger.error(f"Error generating text with Ollama: {e}")
                raise ValueError(f"Error generating text: {str(e)}")
        
        @self.mcp.tool()
        async def ollama_chat(
            messages: List[Dict[str, str]],
            model: str = "llama3",
            max_tokens: int = 2048,
            temperature: float = 0.2
        ) -> str:
            """
            Conversar con un modelo de Ollama usando el formato de chat
            
            Args:
                messages: Lista de mensajes en formato [{role: "user|system|assistant", content: "..."}]
                model: Nombre del modelo a utilizar
                max_tokens: Número máximo de tokens a generar
                temperature: Temperatura para la generación (0.0 a 1.0)
                
            Returns:
                Respuesta generada por el modelo
            """
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature
                    },
                    "stream": False
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/api/chat",
                        json=payload,
                        timeout=120.0
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result.get("message", {}).get("content", "")
            except Exception as e:
                logger.error(f"Error in chat with Ollama: {e}")
                raise ValueError(f"Error in chat: {str(e)}")
        
        @self.mcp.tool()
        async def ollama_embeddings(
            prompt: str,
            model: str = "llama3"
        ) -> List[float]:
            """
            Generar embeddings para un texto usando un modelo de Ollama
            
            Args:
                prompt: Texto para generar embeddings
                model: Nombre del modelo a utilizar
                
            Returns:
                Vector de embeddings
            """
            try:
                payload = {
                    "model": model,
                    "prompt": prompt
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/api/embeddings",
                        json=payload
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result.get("embedding", [])
            except Exception as e:
                logger.error(f"Error generating embeddings with Ollama: {e}")
                raise ValueError(f"Error generating embeddings: {str(e)}")
    
    def run(self, host: str = "0.0.0.0", port: int = 8090):
        """
        Iniciar el servidor MCP
        
        Args:
            host: Host donde escuchar
            port: Puerto donde escuchar
        """
        self.mcp.run(host=host, port=port)

# Función para ejecutar el servidor como un script independiente
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Servidor MCP para Ollama")
    parser.add_argument("--host", default="0.0.0.0", help="Host donde escuchar")
    parser.add_argument("--port", type=int, default=8090, help="Puerto donde escuchar")
    parser.add_argument("--api_url", default="http://localhost:11434", help="URL de la API de Ollama")
    
    args = parser.parse_args()
    
    server = OllamaMCPServer(api_url=args.api_url)
    server.run(host=args.host, port=args.port)

if __name__ == "__main__":
    main()