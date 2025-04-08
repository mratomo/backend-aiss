"""
Google Gemini API integration for the RAG Agent.
This module provides functions to generate text using Google Gemini models through the API.
"""

import time
import json
import logging
from typing import Dict, List, Optional, Any

import aiohttp
from fastapi import HTTPException

from models.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Check if prometheus is available
try:
    from prometheus_client import Counter, Histogram, Gauge
    prometheus_available = True
    
    # Define metrics
    LLM_REQUEST_DURATION = Histogram('llm_google_request_duration_seconds', 'Google Gemini Request Duration')
    
except ImportError:
    prometheus_available = False


async def generate_google(
    prompt: str,
    system_prompt: str,
    provider: LLMProvider,
    max_tokens: int,
    temperature: float,
    timeout_seconds: int = 60,
    advanced_settings: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate text using Google Gemini API
    
    Args:
        prompt: The user prompt
        system_prompt: The system prompt
        provider: The LLM provider configuration
        max_tokens: Maximum tokens to generate
        temperature: Temperature for generation
        timeout_seconds: Timeout in seconds
        advanced_settings: Additional settings
        
    Returns:
        Generated text
    """
    start_time = time.time()
    
    try:
        # Get API key
        api_key = provider.api_key
        if not api_key:
            raise ValueError("Google Gemini API key is required")
        
        # Get base endpoint
        api_base = provider.api_endpoint
        if not api_base:
            raise ValueError("Google Gemini API endpoint is required")
            
        # Build full endpoint
        model = provider.model
        endpoint = f"{api_base}/models/{model}:generateContent"
        
        # Configure parameters
        top_p = advanced_settings.get("top_p", 0.95) if advanced_settings else 0.95
        
        # Build payload
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": top_p
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_ONLY_HIGH"
                }
            ]
        }
        
        # Add system prompt if present
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [
                    {"text": system_prompt}
                ]
            }
        
        # Make request to API
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout_seconds
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Google API error: {response.status} - {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Google API error: {error_text}"
                    )
                
                result = await response.json()
                
                # Process response
                try:
                    # La respuesta de Gemini con herramientas puede incluir información 
                    # de contexto en tool_outputs, que hay que procesar
                    candidates = result.get("candidates", [])
                    if not candidates:
                        raise ValueError("Empty candidates list in Google Gemini response")
                        
                    candidate = candidates[0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])
                    
                    if not parts:
                        raise ValueError("Empty response from Google Gemini API")
                        
                    text_parts = [part.get("text", "") for part in parts if "text" in part]
                    generated_text = "".join(text_parts)
                    
                    return generated_text
                except (KeyError, IndexError) as e:
                    logger.error(f"Error parsing Google Gemini response: {e}")
                    logger.debug(f"Response: {result}")
                    raise ValueError(f"Error parsing Google Gemini response: {e}")
            
    except (aiohttp.ClientError, json.JSONDecodeError) as e:
        logger.error(f"Error calling Google Gemini API: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calling Google Gemini API: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error with Google Gemini: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error with Google Gemini: {str(e)}"
        )
    finally:
        end_time = time.time()
        if prometheus_available:
            duration = end_time - start_time
            LLM_REQUEST_DURATION.observe(duration)


async def generate_google_mcp(
    prompt: str,
    system_prompt: str,
    provider: LLMProvider,
    active_contexts: List[str],
    max_tokens: int,
    temperature: float,
    timeout_seconds: int = 60,
    advanced_settings: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate text using Google Gemini API with MCP support
    
    Google Gemini implementa el protocolo MCP de manera diferente a otros proveedores.
    En lugar de usar metadatos o campos específicos en los mensajes, Gemini utiliza su sistema de
    "tools" y "tool_config" para implementar funciones como MCP. Las herramientas se definen
    mediante JSON Schema y luego se configuran para ejecución mediante el bloque tool_config.
    
    Args:
        prompt: The user prompt
        system_prompt: The system prompt
        provider: The LLM provider configuration
        active_contexts: Active MCP context IDs
        max_tokens: Maximum tokens to generate
        temperature: Temperature for generation
        timeout_seconds: Timeout in seconds
        advanced_settings: Additional settings
        
    Returns:
        Generated text
    """
    start_time = time.time()
    
    try:
        # Get API key
        api_key = provider.api_key
        if not api_key:
            raise ValueError("Google Gemini API key is required")
        
        # Get base endpoint
        api_base = provider.api_endpoint
        if not api_base:
            raise ValueError("Google Gemini API endpoint is required")
            
        # Build full endpoint
        model = provider.model
        endpoint = f"{api_base}/models/{model}:generateContent"
        
        # Configure parameters
        top_p = advanced_settings.get("top_p", 0.95) if advanced_settings else 0.95
        
        # Create context references
        context_refs = [{"id": ctx_id} for ctx_id in active_contexts]
        
        # Build payload
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": top_p
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_ONLY_HIGH"
                }
            ],
            # Definimos la herramienta MCP para Gemini
            # La sintaxis de definición de herramientas en Gemini sigue el formato JSON Schema
            "tools": [
                {
                    "function_declarations": [
                        {
                            "name": "mcp_context",
                            "description": "Access and use information from Model Context Protocol contexts",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "contexts": {
                                        "type": "array",
                                        "description": "Array of context references to activate",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "id": { 
                                                    "type": "string",
                                                    "description": "Unique identifier for a context" 
                                                }
                                            },
                                            "required": ["id"]
                                        }
                                    }
                                },
                                "required": ["contexts"]
                            }
                        }
                    ]
                }
            ],
            # En Gemini, la configuración de herramientas para MCP es diferente
            # a otros proveedores. Utilizamos la extensión "tool_use" para especificar
            # cómo queremos que se usen las herramientas y pasar las referencias de contexto.
            "tool_config": {
                "tool_use": {
                    "execute": [{
                        "tool_name": "mcp_context",
                        "args": {
                            "contexts": context_refs
                        }
                    }]
                }
            }
        }
        
        # Add system prompt if present
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [
                    {"text": system_prompt}
                ]
            }
        
        # Make request to API
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout_seconds
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Google API error: {response.status} - {error_text}")
                    # Fallback to standard API if MCP fails
                    logger.info("Falling back to standard Google API")
                    return await generate_google(
                        prompt, system_prompt, provider, max_tokens, temperature, timeout_seconds, advanced_settings
                    )
                
                result = await response.json()
                
                # Process response
                try:
                    # La respuesta de Gemini con herramientas puede incluir información 
                    # de contexto en tool_outputs, que hay que procesar
                    candidates = result.get("candidates", [])
                    if not candidates:
                        raise ValueError("Empty candidates list in Google Gemini response")
                        
                    candidate = candidates[0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])
                    
                    # También hay que revisar si hay tool_outputs con información de contextos MCP
                    if "toolUseResults" in candidate:
                        tool_results = candidate.get("toolUseResults", [])
                        for tool_result in tool_results:
                            if tool_result.get("tool") == "mcp_context":
                                logger.debug(f"Found MCP context tool result: {tool_result}")
                    
                    if not parts:
                        raise ValueError("Empty response from Google Gemini API")
                        
                    text_parts = [part.get("text", "") for part in parts if "text" in part]
                    generated_text = "".join(text_parts)
                    
                    return generated_text
                except (KeyError, IndexError) as e:
                    logger.error(f"Error parsing Google Gemini response: {e}")
                    logger.debug(f"Response: {result}")
                    raise ValueError(f"Error parsing Google Gemini response: {e}")
            
    except (aiohttp.ClientError, json.JSONDecodeError) as e:
        logger.error(f"Error calling Google Gemini API with MCP: {e}")
        # Fallback to standard API
        logger.info("Falling back to standard Google API")
        return await generate_google(
            prompt, system_prompt, provider, max_tokens, temperature, timeout_seconds, advanced_settings
        )
    except Exception as e:
        logger.error(f"Unexpected error with Google Gemini MCP: {e}")
        # Fallback to standard API
        logger.info("Falling back to standard Google API")
        return await generate_google(
            prompt, system_prompt, provider, max_tokens, temperature, timeout_seconds, advanced_settings
        )
    finally:
        end_time = time.time()
        if prometheus_available:
            duration = end_time - start_time
            LLM_REQUEST_DURATION.observe(duration)