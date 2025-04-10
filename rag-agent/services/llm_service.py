import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

import aiohttp
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from services.google_gemini import generate_google, generate_google_mcp
from services.llm_service_area_llm import get_area_primary_llm

# Intentar cargar httpx para cliente HTTP alternativo
try:
    import httpx
    httpx_available = True
except ImportError:
    httpx_available = False

# Intentar usar structlog para logging estructurado
try:
    import structlog
    logger = structlog.get_logger("llm_service")
    structlog_available = True
except ImportError:
    logger = logging.getLogger("llm_service")
    structlog_available = False

# Intentar cargar metricas
try:
    from prometheus_client import Counter, Histogram, Gauge
    prometheus_available = True
    
    # Definir métricas
    LLM_REQUESTS = Counter('llm_requests_total', 'Total LLM Requests', ['provider_type', 'status'])
    LLM_REQUEST_DURATION = Histogram('llm_request_duration_seconds', 'LLM Request Duration', ['provider_type'])
    
except ImportError:
    prometheus_available = False

from config.settings import Settings
from models.llm_provider import LLMProvider, LLMProviderCreate, LLMProviderUpdate, LLMProviderType

class LLMService:
    """Servicio para gestionar y utilizar proveedores LLM con soporte MCP"""

    def __init__(self, database: AsyncIOMotorDatabase, settings: Settings):
        """Inicializar servicio con la base de datos y configuración"""
        self.db = database
        self.collection = database.llm_providers
        self.settings = settings
        self.providers = {}  # Cache de proveedores (id -> provider)
        self.default_provider_id = None
        
        # Sistema de limitación de tasa para prevenir uso excesivo
        self.rate_limits = {
            # id_proveedor -> {contador, timestamp_ultimo_reset, limite_por_hora}
            # Se inicializará para cada proveedor cuando se carguen
        }
        
        # Tiempo entre resets de contadores de uso (1 hora)
        self.rate_limit_reset_interval = 3600  # segundos

        # Nuevo: Cliente MCP para gestión de contextos
        self.mcp_client = None
        self.has_store_tool = False
        self.has_find_tool = False

    async def initialize(self):
        """Inicializar servicio, proveedores y cliente MCP"""
        await self.load_providers()

        # Inicializar cliente MCP
        try:
            from mcp import Client
            self.mcp_client = Client()
            try:
                # Conectar con servidor MCP usando SSE
                mcp_service_url = self.settings.mcp.context_service_url
                await self.mcp_client.connect_sse(f"{mcp_service_url}/mcp/sse")

                # Verificar herramientas disponibles
                tools = await self.mcp_client.list_tools()
                tool_names = [t.name for t in tools]
                logger.info(f"Conectado a MCP. Herramientas disponibles: {tool_names}")

                # Verificar herramientas específicas
                self.has_store_tool = "store_document" in tool_names
                self.has_find_tool = "find_relevant" in tool_names

                if not (self.has_store_tool and self.has_find_tool):
                    logger.warning(f"Algunas herramientas MCP no están disponibles. Encontradas: {tool_names}")
            except Exception as e:
                logger.error(f"Error conectando con servidor MCP: {e}")
                self.mcp_client = None
        except ImportError:
            logger.warning("Librería MCP no instalada. El cliente no estará disponible.")
            self.mcp_client = None

    async def load_providers(self):
        """Cargar proveedores desde la base de datos"""
        providers = await self.collection.find().to_list(length=100)

        for provider_dict in providers:
            provider = LLMProvider(**provider_dict)
            provider_id = str(provider.id)
            self.providers[provider_id] = provider

            if provider.default:
                self.default_provider_id = provider_id
                
            # Inicializar limitación de tasa para este proveedor
            # Obtener límite por hora de los metadatos o usar un valor predeterminado según el tipo
            rate_limit_per_hour = provider.metadata.get("rate_limit_per_hour", 0)
            
            # Si no hay límite configurado, establecer valores predeterminados según el proveedor
            if rate_limit_per_hour <= 0:
                if provider.type == LLMProviderType.OPENAI:
                    rate_limit_per_hour = 100  # Límite conservador para OpenAI
                elif provider.type == LLMProviderType.ANTHROPIC:
                    rate_limit_per_hour = 60   # Límite conservador para Anthropic
                elif provider.type == LLMProviderType.AZURE_OPENAI:
                    rate_limit_per_hour = 200  # Límite más alto para Azure (configurable)
                else:
                    rate_limit_per_hour = 30   # Valor predeterminado conservador
            
            # Registrar límite en estructura de control
            self.rate_limits[provider_id] = {
                "count": 0,
                "last_reset": time.time(),
                "limit_per_hour": rate_limit_per_hour
            }

        # Si no hay proveedor por defecto pero hay proveedores, usar el primero
        if not self.default_provider_id and self.providers:
            self.default_provider_id = next(iter(self.providers.keys()))

        # Log para diagnosticar proveedores cargados
        logger.info(f"Loaded {len(self.providers)} LLM providers. Default provider: {self.default_provider_id}")
        for provider_id, provider in self.providers.items():
            rate_limit = self.rate_limits[provider_id]["limit_per_hour"]
            logger.info(f"Provider {provider_id}: {provider.name} ({provider.type}), model: {provider.model}, " +
                        f"rate limit: {rate_limit} calls/hour")

    def _get_provider(self, provider_id: Optional[str] = None) -> LLMProvider:
        """
        Obtener un proveedor LLM por su ID o el proveedor por defecto

        Args:
            provider_id: ID del proveedor (opcional)

        Returns:
            Proveedor LLM

        Raises:
            HTTPException: Si no se encuentra el proveedor
        """
        if not provider_id:
            if not self.default_provider_id:
                logger.error("No LLM provider available. Make sure to add at least one provider.")
                raise HTTPException(
                    status_code=404,
                    detail="No default LLM provider configured"
                )
            provider_id = self.default_provider_id

        provider = self.providers.get(provider_id)
        if not provider:
            logger.error(f"LLM provider not found: {provider_id}")
            logger.info(f"Available providers: {list(self.providers.keys())}")
            raise HTTPException(
                status_code=404,
                detail=f"LLM provider not found: {provider_id}"
            )

        return provider

    async def list_providers(self) -> List[LLMProvider]:
        """
        Listar todos los proveedores LLM

        Returns:
            Lista de proveedores
        """
        try:
            providers = await self.collection.find().to_list(length=100)
            return [LLMProvider(**p) for p in providers]
        except Exception as e:
            logger.error(f"Error listing providers: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error listing providers: {str(e)}"
            )

    async def add_provider(self, provider_data: LLMProviderCreate) -> LLMProvider:
        """
        Añadir un nuevo proveedor LLM

        Args:
            provider_data: Datos del proveedor

        Returns:
            Proveedor creado
        """
        # Validar campos según el tipo de proveedor
        if provider_data.type in [LLMProviderType.OPENAI, LLMProviderType.ANTHROPIC]:
            if not provider_data.api_key:
                raise HTTPException(
                    status_code=400,
                    detail=f"API key is required for {provider_data.type} providers"
                )
            
            # Validar formato de API key
            self._validate_api_key_format(provider_data.type, provider_data.api_key)

        if provider_data.type == LLMProviderType.AZURE_OPENAI:
            if not provider_data.api_key or not provider_data.api_endpoint:
                raise HTTPException(
                    status_code=400,
                    detail="API key and endpoint are required for Azure OpenAI providers"
                )
            
            # Validar formato de API key de Azure
            self._validate_api_key_format(provider_data.type, provider_data.api_key)
            
            # Validar URL del endpoint
            if not provider_data.api_endpoint.startswith(("https://", "http://")):
                raise HTTPException(
                    status_code=400,
                    detail="API endpoint must be a valid URL starting with http:// or https://"
                )

        if provider_data.type == LLMProviderType.OLLAMA:
            if not provider_data.api_endpoint:
                raise HTTPException(
                    status_code=400,
                    detail="API endpoint is required for Ollama providers"
                )
            
            # Validar URL del endpoint
            if not provider_data.api_endpoint.startswith(("https://", "http://")):
                raise HTTPException(
                    status_code=400,
                    detail="API endpoint must be a valid URL starting with http:// or https://"
                )

        try:
            # Si es proveedor por defecto, desactivar otros proveedores por defecto
            if provider_data.default:
                await self.collection.update_many(
                    {"default": True},
                    {"$set": {"default": False, "updated_at": datetime.utcnow()}}
                )

            # Crear proveedor
            now = datetime.utcnow()
            provider_dict = provider_data.dict()
            provider_dict["created_at"] = now
            provider_dict["updated_at"] = now

            # Insertar en la base de datos
            result = await self.collection.insert_one(provider_dict)

            # Obtener proveedor creado
            created_provider = await self.collection.find_one({"_id": result.inserted_id})
            provider = LLMProvider(**created_provider)

            # Actualizar cache
            self.providers[str(provider.id)] = provider

            # Actualizar proveedor por defecto si es necesario
            if provider.default:
                self.default_provider_id = str(provider.id)

            logger.info(f"Provider added successfully: {provider.name} ({provider.type}), ID: {provider.id}")
            return provider
        except Exception as e:
            logger.error(f"Error adding provider: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error adding provider: {str(e)}"
            )

    async def update_provider(self, provider_id: str, provider_update: LLMProviderUpdate) -> Optional[LLMProvider]:
        """
        Actualizar un proveedor LLM existente

        Args:
            provider_id: ID del proveedor
            provider_update: Datos a actualizar

        Returns:
            Proveedor actualizado o None si no existe
        """
        try:
            obj_id = ObjectId(provider_id)
        except Exception as e:
            logger.error(f"Invalid provider ID format: {provider_id}, error: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid provider ID format"
            )

        try:
            # Verificar si el proveedor existe
            existing = await self.collection.find_one({"_id": obj_id})
            if not existing:
                logger.warning(f"Provider not found for update: {provider_id}")
                return None

            # Preparar actualización
            update_data = {k: v for k, v in provider_update.dict().items() if v is not None}
            update_data["updated_at"] = datetime.utcnow()

            # Si actualiza a proveedor por defecto, desactivar otros
            if "default" in update_data and update_data["default"]:
                await self.collection.update_many(
                    {"_id": {"$ne": obj_id}, "default": True},
                    {"$set": {"default": False, "updated_at": datetime.utcnow()}}
                )

            # Actualizar en la base de datos
            await self.collection.update_one(
                {"_id": obj_id},
                {"$set": update_data}
            )

            # Obtener proveedor actualizado
            updated_provider_dict = await self.collection.find_one({"_id": obj_id})
            updated_provider = LLMProvider(**updated_provider_dict)

            # Actualizar cache
            self.providers[provider_id] = updated_provider

            # Actualizar proveedor por defecto si es necesario
            if updated_provider.default:
                self.default_provider_id = provider_id
            elif self.default_provider_id == provider_id and not updated_provider.default:
                # Si era el proveedor por defecto y ya no lo es, encontrar otro
                default_providers = await self.collection.find({"default": True}).to_list(length=1)
                if default_providers:
                    self.default_provider_id = str(default_providers[0]["_id"])
                else:
                    self.default_provider_id = None

            logger.info(f"Provider updated successfully: {updated_provider.name} ({provider_id})")
            return updated_provider
        except Exception as e:
            logger.error(f"Error updating provider: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error updating provider: {str(e)}"
            )

    async def delete_provider(self, provider_id: str) -> bool:
        """
        Eliminar un proveedor LLM

        Args:
            provider_id: ID del proveedor

        Returns:
            True si se eliminó correctamente
        """
        try:
            obj_id = ObjectId(provider_id)
        except Exception as e:
            logger.error(f"Invalid provider ID format: {provider_id}, error: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid provider ID format"
            )

        try:
            # Verificar si es el proveedor por defecto
            provider = await self.collection.find_one({"_id": obj_id})
            is_default = provider and provider.get("default", False)

            # Eliminar de la base de datos
            result = await self.collection.delete_one({"_id": obj_id})

            if result.deleted_count == 0:
                logger.warning(f"Provider not found for deletion: {provider_id}")
                return False

            # Eliminar de la cache
            if provider_id in self.providers:
                del self.providers[provider_id]

            # Si era el proveedor por defecto, encontrar otro
            if is_default:
                default_provider = None
                if self.providers:
                    # Seleccionar el primer proveedor disponible como nuevo default
                    first_provider_id = next(iter(self.providers.keys()))
                    await self.collection.update_one(
                        {"_id": ObjectId(first_provider_id)},
                        {"$set": {"default": True, "updated_at": datetime.utcnow()}}
                    )
                    self.providers[first_provider_id].default = True
                    self.default_provider_id = first_provider_id
                    default_provider = self.providers[first_provider_id].name
                else:
                    self.default_provider_id = None

                logger.info(f"Deleted default provider {provider_id}. New default: {default_provider}")
            else:
                logger.info(f"Provider deleted successfully: {provider_id}")

            return True
        except Exception as e:
            logger.error(f"Error deleting provider: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error deleting provider: {str(e)}"
            )

    def _validate_api_key_format(self, provider_type: LLMProviderType, api_key: str) -> bool:
        """
        Validación de formato de API keys
        
        Args:
            provider_type: Tipo de proveedor LLM
            api_key: API key a validar
            
        Returns:
            True si el formato es válido, de lo contrario lanza una excepción
            
        Raises:
            HTTPException: Si el formato de la API key no es válido
        """
        if not api_key or len(api_key.strip()) < 8:
            raise HTTPException(
                status_code=400,
                detail=f"API key for {provider_type} is too short or invalid"
            )
            
        if provider_type == LLMProviderType.OPENAI:
            # OpenAI API keys comienzan con "sk-" y tienen un largo estándar
            if not api_key.startswith("sk-") or len(api_key) < 30:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid OpenAI API key format. Keys should start with 'sk-' and be at least 30 characters"
                )
        
        elif provider_type == LLMProviderType.ANTHROPIC:
            # Anthropic API keys generalmente comienzan con "sk-ant-" o tienen formato específico
            if not (api_key.startswith("sk-ant-") or api_key.startswith("a-")) or len(api_key) < 20:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid Anthropic API key format. Keys should start with 'sk-ant-' or 'a-'"
                )
                
        elif provider_type == LLMProviderType.AZURE_OPENAI:
            # Azure API keys tienen un formato específico (generalmente alfanumérico)
            if not api_key.replace("-", "").isalnum() or len(api_key) < 20:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid Azure OpenAI API key format"
                )
        
        # Si pasó todas las validaciones
        return True
    
    async def test_provider(self, provider_id: str, prompt: str) -> Dict[str, Any]:
        """
        Probar un proveedor LLM con un prompt simple

        Args:
            provider_id: ID del proveedor
            prompt: Prompt de prueba

        Returns:
            Respuesta del proveedor
        """
        provider = self._get_provider(provider_id)
        logger.info(f"Testing provider {provider.name} ({provider_id}) with prompt: '{prompt[:50]}...'")

        try:
            # Ejecutar llamada al LLM
            start_time = time.time()
            response = await self.generate_text(
                prompt=prompt,
                system_prompt="Eres un asistente útil y conciso.",
                provider=provider
            )
            end_time = time.time()

            # Calcular latencia
            latency_ms = int((end_time - start_time) * 1000)

            # Añadir información de latencia
            response["latency_ms"] = latency_ms

            logger.info(f"Test successful. Latency: {latency_ms}ms")
            return response
        except Exception as e:
            logger.error(f"Error testing provider {provider_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error testing provider: {str(e)}"
            )

    async def _check_rate_limit(self, provider_id: str) -> bool:
        """
        Verifica y actualiza los límites de tasa para un proveedor
        
        Args:
            provider_id: ID del proveedor
            
        Returns:
            True si se permite la solicitud, False si se excedió el límite
            
        Raises:
            HTTPException: Si se excedió el límite de tasa
        """
        # Si no existe en rate_limits, inicializarlo
        if provider_id not in self.rate_limits:
            self.rate_limits[provider_id] = {
                "count": 0,
                "last_reset": time.time(),
                "limit_per_hour": 50  # Valor conservador por defecto
            }
            
        rate_limit_info = self.rate_limits[provider_id]
        current_time = time.time()
        
        # Comprobar si es hora de reiniciar el contador
        if current_time - rate_limit_info["last_reset"] >= self.rate_limit_reset_interval:
            # Reiniciar contador
            rate_limit_info["count"] = 0
            rate_limit_info["last_reset"] = current_time
            logger.info(f"Rate limit counter reset for provider {provider_id}")
        
        # Verificar si excedió el límite
        if rate_limit_info["count"] >= rate_limit_info["limit_per_hour"]:
            next_reset = rate_limit_info["last_reset"] + self.rate_limit_reset_interval
            time_remaining = int(next_reset - current_time)
            
            logger.warning(f"Rate limit exceeded for provider {provider_id}. " +
                           f"Limit: {rate_limit_info['limit_per_hour']} requests/hour. " +
                           f"Reset in {time_remaining} seconds.")
            
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {time_remaining} seconds or use another provider."
            )
        
        # Incrementar contador
        rate_limit_info["count"] += 1
        
        # Si está llegando al 80% del límite, registrar advertencia
        if rate_limit_info["count"] >= 0.8 * rate_limit_info["limit_per_hour"]:
            logger.warning(f"Provider {provider_id} at {rate_limit_info['count']}/{rate_limit_info['limit_per_hour']} " +
                           f"requests ({int(rate_limit_info['count'] * 100 / rate_limit_info['limit_per_hour'])}% of hourly limit)")
        
        return True
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(aiohttp.ClientError)
    )
    async def generate_text(self,
                            prompt: str,
                            system_prompt: str,
                            provider: Optional[LLMProvider] = None,
                            provider_id: Optional[str] = None,
                            max_tokens: Optional[int] = None,
                            temperature: Optional[float] = None,
                            advanced_settings: Optional[Dict[str, Any]] = None,
                            active_contexts: Optional[List[str]] = None,
                            area_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generar texto utilizando un proveedor LLM con soporte para contextos MCP

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema
            provider: Proveedor LLM (opcional si se especifica provider_id)
            provider_id: ID del proveedor (opcional si se especifica provider)
            max_tokens: Número máximo de tokens (anula configuración del proveedor)
            temperature: Temperatura (anula configuración del proveedor)
            advanced_settings: Configuraciones avanzadas para la generación
            active_contexts: Lista de IDs de contextos MCP a activar (nuevo)
            area_id: ID del área de conocimiento (para usar su LLM específico)

        Returns:
            Respuesta del LLM
        """
        # Si tenemos un area_id, intentamos obtener su LLM específico
        if area_id:
            # Consultamos el área para ver si tiene un LLM primario configurado
            try:
                logger.debug(f"Consultando LLM específico para el área {area_id}")
                area_provider_id = await get_area_primary_llm(self, area_id, self.settings.mcp.context_service_url)
                if area_provider_id:
                    logger.info(f"Usando proveedor LLM específico {area_provider_id} para el área {area_id}")
                    provider = self._get_provider(area_provider_id)
            except Exception as e:
                logger.warning(f"Error al obtener LLM específico para el área {area_id}: {e}")
                # Si hay error, continuamos con el provider proporcionado o default
        
        if not provider:
            provider = self._get_provider(provider_id)
            
        # Obtener y validar el provider_id
        current_provider_id = str(provider.id)
        
        # Verificar límite de tasa antes de proceder
        await self._check_rate_limit(current_provider_id)

        # Usar la configuración del proveedor si no se especifica
        actual_max_tokens = max_tokens if max_tokens is not None else provider.max_tokens
        actual_temperature = temperature if temperature is not None else provider.temperature

        # Preparar respuesta base
        response = {
            "provider_id": str(provider.id),
            "provider_name": provider.name,
            "model": provider.model,
            "text": ""
        }

        # Log de diagnóstico
        logger.debug(f"Generating text with provider {provider.name} ({provider.type}), model: {provider.model}")

        # Nuevo: Activar contextos MCP si están especificados
        active_mcp_contexts = []
        if active_contexts and self.mcp_client:
            for context_id in active_contexts:
                try:
                    await self.mcp_client.activate_context(context_id)
                    active_mcp_contexts.append(context_id)
                    logger.debug(f"Contexto MCP activado: {context_id}")
                except Exception as e:
                    logger.warning(f"Error activando contexto MCP {context_id}: {e}")

        try:
            # Verificar si el proveedor tiene soporte nativo para MCP
            has_mcp_native_support = provider.metadata.get("mcp_native", False)

            # Ejecutar según el tipo de proveedor
            if provider.type == LLMProviderType.OPENAI:
                if has_mcp_native_support and active_mcp_contexts:
                    # Usar API con soporte MCP nativo
                    response["text"] = await self._generate_openai_mcp(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        provider=provider,
                        active_contexts=active_mcp_contexts,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        advanced_settings=advanced_settings
                    )
                else:
                    # Usar API estándar
                    response["text"] = await self._generate_openai(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        provider=provider,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        advanced_settings=advanced_settings
                    )

            elif provider.type == LLMProviderType.AZURE_OPENAI:
                if has_mcp_native_support and active_mcp_contexts:
                    # Implementación para Azure con MCP
                    response["text"] = await self._generate_azure_openai_mcp(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        provider=provider,
                        active_contexts=active_mcp_contexts,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        advanced_settings=advanced_settings
                    )
                else:
                    response["text"] = await self._generate_azure_openai(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        provider=provider,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        advanced_settings=advanced_settings
                    )

            elif provider.type == LLMProviderType.ANTHROPIC:
                if has_mcp_native_support and active_mcp_contexts:
                    # Anthropic Claude con soporte MCP
                    response["text"] = await self._generate_anthropic_mcp(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        provider=provider,
                        active_contexts=active_mcp_contexts,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        advanced_settings=advanced_settings
                    )
                else:
                    response["text"] = await self._generate_anthropic(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        provider=provider,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        advanced_settings=advanced_settings
                    )

            elif provider.type == LLMProviderType.GOOGLE:
                if has_mcp_native_support and active_mcp_contexts:
                    # Google Gemini con soporte MCP
                    response["text"] = await generate_google_mcp(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        provider=provider,
                        active_contexts=active_mcp_contexts,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        timeout_seconds=self.settings.google.timeout_seconds,
                        advanced_settings=advanced_settings
                    )
                else:
                    response["text"] = await generate_google(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        provider=provider,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        timeout_seconds=self.settings.google.timeout_seconds,
                        advanced_settings=advanced_settings
                    )

            elif provider.type == LLMProviderType.OLLAMA:
                response["text"] = await self._generate_ollama(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    provider=provider,
                    max_tokens=actual_max_tokens,
                    temperature=actual_temperature,
                    advanced_settings=advanced_settings
                )

            # Esta sección es redundante ya que los tipos ya están manejados arriba, pero se mantiene para compatibilidad
            # Se eliminará en una futura actualización
            
            elif provider.type == "ollama":
                # Ollama no admite MCP nativo, usar siempre API estándar
                logger.info(f"Using standard API for Ollama (MCP not supported)")
                response["text"] = await self._generate_ollama(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    provider=provider,
                    max_tokens=actual_max_tokens,
                    temperature=actual_temperature,
                    advanced_settings=advanced_settings
                )
            else:
                logger.error(f"Unsupported provider type: {provider.type}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported provider type: {provider.type}"
                )

            # Log de éxito
            logger.debug(f"Successfully generated text with {provider.name}. Response length: {len(response['text'])}")

            return response

        except aiohttp.ClientError as e:
            logger.error(f"Network error with {provider.type}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error generating text with {provider.type}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error generating text: {str(e)}"
            )
        finally:
            # Desactivar contextos MCP al finalizar
            if active_mcp_contexts and self.mcp_client:
                for context_id in active_mcp_contexts:
                    try:
                        await self.mcp_client.deactivate_context(context_id)
                    except Exception as e:
                        logger.warning(f"Error desactivando contexto MCP {context_id}: {e}")

    async def _generate_openai(self,
                               prompt: str,
                               system_prompt: str,
                               provider: LLMProvider,
                               max_tokens: int,
                               temperature: float,
                               advanced_settings: Optional[Dict[str, Any]] = None) -> str:
        """
        Generar texto con OpenAI

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema
            provider: Proveedor OpenAI
            max_tokens: Número máximo de tokens
            temperature: Temperatura
            advanced_settings: Configuraciones avanzadas para la generación

        Returns:
            Texto generado
        """
        if not provider.api_key:
            raise ValueError("API key is required for OpenAI")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider.api_key}"
        }

        # Añadir Organization ID si está presente en metadatos
        if "organization_id" in provider.metadata:
            headers["OpenAI-Organization"] = provider.metadata["organization_id"]

        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        # Incorporar configuraciones avanzadas si se proporcionan
        if advanced_settings:
            for key, value in advanced_settings.items():
                # Evitar sobrescribir campos críticos
                if key not in ["model", "messages"]:
                    payload[key] = value

        timeout = aiohttp.ClientTimeout(total=self.settings.openai.timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers,
                        json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenAI API error: {response.status} - {error_text}")
                        raise ValueError(f"OpenAI API error: {response.status} - {error_text}")

                    response_json = await response.json()
                    return response_json["choices"][0]["message"]["content"]
            except aiohttp.ClientResponseError as e:
                logger.error(f"OpenAI API response error: {e.status} - {e.message}")
                raise ValueError(f"OpenAI API error: {e.status} - {e.message}")
            except aiohttp.ClientError as e:
                logger.error(f"OpenAI API connection error: {str(e)}")
                raise

    async def _generate_openai_mcp(self,
                                   prompt: str,
                                   system_prompt: str,
                                   provider: LLMProvider,
                                   active_contexts: List[str],
                                   max_tokens: int,
                                   temperature: float,
                                   advanced_settings: Optional[Dict[str, Any]] = None) -> str:
        """Generar texto con OpenAI usando conectividad MCP nativa"""
        if not provider.api_key:
            raise ValueError("API key is required for OpenAI")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider.api_key}"
        }

        # Añadir Organization ID si está presente en metadatos
        if "organization_id" in provider.metadata:
            headers["OpenAI-Organization"] = provider.metadata["organization_id"]

        # Crear referencias a contextos MCP
        context_refs = [{"id": ctx_id} for ctx_id in active_contexts]

        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            # Incluir contextos MCP si hay (OpenAI con soporte MCP usa el campo "tools")
            "tools": [
                {
                    "type": "mcp_context",
                    "contexts": context_refs
                }
            ]
        }

        # Eliminar campo tools si no hay contextos
        if not context_refs:
            del payload["tools"]

        # Incorporar configuraciones avanzadas si se proporcionan
        if advanced_settings:
            for key, value in advanced_settings.items():
                # Evitar sobrescribir campos críticos
                if key not in ["model", "messages", "tools"]:
                    payload[key] = value

        timeout = aiohttp.ClientTimeout(total=self.settings.openai.timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers,
                        json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenAI API error: {response.status} - {error_text}")
                        raise ValueError(f"OpenAI API error: {response.status} - {error_text}")

                    response_json = await response.json()
                    return response_json["choices"][0]["message"]["content"]
            except aiohttp.ClientResponseError as e:
                logger.error(f"OpenAI API response error: {e.status} - {e.message}")
                raise ValueError(f"OpenAI API error: {e.status} - {e.message}")
            except aiohttp.ClientError as e:
                logger.error(f"OpenAI API connection error: {str(e)}")
                raise

    async def _generate_azure_openai(self,
                                     prompt: str,
                                     system_prompt: str,
                                     provider: LLMProvider,
                                     max_tokens: int,
                                     temperature: float,
                                     advanced_settings: Optional[Dict[str, Any]] = None) -> str:
        """
        Generar texto con Azure OpenAI

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema
            provider: Proveedor Azure OpenAI
            max_tokens: Número máximo de tokens
            temperature: Temperatura
            advanced_settings: Configuraciones avanzadas para la generación

        Returns:
            Texto generado
        """
        if not provider.api_key or not provider.api_endpoint:
            raise ValueError("API key and endpoint are required for Azure OpenAI")

        # Extraer deployment ID de los metadatos
        deployment_id = provider.metadata.get("deployment_id", provider.model)
        api_version = provider.metadata.get("api_version", "2023-05-15")

        # URL para Azure OpenAI
        url = f"{provider.api_endpoint}/openai/deployments/{deployment_id}/chat/completions?api-version={api_version}"

        headers = {
            "Content-Type": "application/json",
            "api-key": provider.api_key
        }

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        # Incorporar configuraciones avanzadas si se proporcionan
        if advanced_settings:
            for key, value in advanced_settings.items():
                if key not in ["messages"]:
                    payload[key] = value

        timeout = aiohttp.ClientTimeout(total=self.settings.openai.timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(
                        url,
                        headers=headers,
                        json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Azure OpenAI API error: {response.status} - {error_text}")
                        raise ValueError(f"Azure OpenAI API error: {response.status} - {error_text}")

                    response_json = await response.json()
                    return response_json["choices"][0]["message"]["content"]
            except aiohttp.ClientResponseError as e:
                logger.error(f"Azure OpenAI API response error: {e.status} - {e.message}")
                raise ValueError(f"Azure OpenAI API error: {e.status} - {e.message}")
            except aiohttp.ClientError as e:
                logger.error(f"Azure OpenAI API connection error: {str(e)}")
                raise

    async def _generate_anthropic_mcp(self,
                                       prompt: str,
                                       system_prompt: str,
                                       provider: LLMProvider,
                                       active_contexts: List[str],
                                       max_tokens: int,
                                       temperature: float,
                                       advanced_settings: Optional[Dict[str, Any]] = None) -> str:
        """Generar texto con Anthropic Claude usando conectividad MCP nativa"""
        if not provider.api_key:
            raise ValueError("API key is required for Anthropic")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": provider.api_key,
            "anthropic-version": "2023-06-01"
        }

        # Crear referencias a contextos MCP
        context_refs = [{"id": ctx_id} for ctx_id in active_contexts]

        # Configurar el payload para Anthropic
        payload = {
            "model": provider.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "metadata": {
                "mcp_contexts": context_refs
            }
        }

        # Añadir configuraciones avanzadas si existen
        if advanced_settings:
            for key, value in advanced_settings.items():
                if key not in payload:
                    payload[key] = value

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_data = await response.text()
                        logger.error(f"Anthropic API error: {response.status} - {error_data}")
                        raise ValueError(f"Anthropic API error: {response.status} - {error_data}")
                    
                    response_data = await response.json()
                    
                    # Extraemos solo el texto del mensaje para mantener consistencia con otras implementaciones
                    if "content" in response_data and response_data["content"]:
                        for content_item in response_data["content"]:
                            if content_item.get("type") == "text":
                                return content_item.get("text", "")
                        
                    # Fallback en caso de formato inesperado    
                    return ""
        except aiohttp.ClientError as e:
            logger.error(f"Anthropic API connection error: {str(e)}")
            raise
            
    async def _generate_azure_openai_mcp(self,
                                         prompt: str,
                                         system_prompt: str,
                                         provider: LLMProvider,
                                         active_contexts: List[str],
                                         max_tokens: int,
                                         temperature: float,
                                         advanced_settings: Optional[Dict[str, Any]] = None) -> str:
        """Generar texto con Azure OpenAI usando conectividad MCP nativa"""
        if not provider.api_key or not provider.api_endpoint:
            raise ValueError("API key and endpoint are required for Azure OpenAI")

        # Extraer deployment ID de los metadatos
        deployment_id = provider.metadata.get("deployment_id", provider.model)
        api_version = provider.metadata.get("api_version", "2023-05-15")

        # URL para Azure OpenAI
        url = f"{provider.api_endpoint}/openai/deployments/{deployment_id}/chat/completions?api-version={api_version}"

        headers = {
            "Content-Type": "application/json",
            "api-key": provider.api_key
        }

        # Crear referencias a contextos MCP
        context_refs = [{"id": ctx_id} for ctx_id in active_contexts]

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        # Incluir contextos MCP si hay (formato específico para Azure OpenAI)
        if context_refs:
            payload["tools"] = [
                {
                    "type": "mcp_context",
                    "contexts": context_refs
                }
            ]

        # Incorporar configuraciones avanzadas
        if advanced_settings:
            for key, value in advanced_settings.items():
                if key not in ["messages", "tools"]:
                    payload[key] = value

        timeout = aiohttp.ClientTimeout(total=self.settings.openai.timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(
                        url,
                        headers=headers,
                        json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Azure OpenAI API error: {response.status} - {error_text}")
                        raise ValueError(f"Azure OpenAI API error: {response.status} - {error_text}")

                    response_json = await response.json()
                    return response_json["choices"][0]["message"]["content"]
            except aiohttp.ClientResponseError as e:
                logger.error(f"Azure OpenAI API response error: {e.status} - {e.message}")
                raise ValueError(f"Azure OpenAI API error: {e.status} - {e.message}")
            except aiohttp.ClientError as e:
                logger.error(f"Azure OpenAI API connection error: {str(e)}")
                raise

    async def _generate_anthropic(self,
                                  prompt: str,
                                  system_prompt: str,
                                  provider: LLMProvider,
                                  max_tokens: int,
                                  temperature: float,
                                  advanced_settings: Optional[Dict[str, Any]] = None) -> str:
        """
        Generar texto con Anthropic

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema
            provider: Proveedor Anthropic
            max_tokens: Número máximo de tokens
            temperature: Temperatura
            advanced_settings: Configuraciones avanzadas para la generación

        Returns:
            Texto generado
        """
        if not provider.api_key:
            raise ValueError("API key is required for Anthropic")

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": provider.api_key,
            "anthropic-version": "2023-06-01"
        }

        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        # Incorporar configuraciones avanzadas si se proporcionan
        if advanced_settings:
            for key, value in advanced_settings.items():
                if key not in ["model", "messages"]:
                    payload[key] = value

        timeout = aiohttp.ClientTimeout(total=self.settings.anthropic.timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Anthropic API error: {response.status} - {error_text}")
                        raise ValueError(f"Anthropic API error: {response.status} - {error_text}")

                    response_json = await response.json()
                    if "content" in response_json and response_json["content"]:
                        for content_item in response_json["content"]:
                            if content_item.get("type") == "text":
                                return content_item.get("text", "")

                    # Fallback en caso de formato inesperado
                    return str(response_json.get("content", [{"text": ""}])[0].get("text", ""))
            except aiohttp.ClientResponseError as e:
                logger.error(f"Anthropic API response error: {e.status} - {e.message}")
                raise ValueError(f"Anthropic API error: {e.status} - {e.message}")
            except aiohttp.ClientError as e:
                logger.error(f"Anthropic API connection error: {str(e)}")
                raise

    # Esta sección del código se eliminó porque era una duplicación de otra implementación

    async def _generate_ollama(self,
                               prompt: str,
                               system_prompt: str,
                               provider: LLMProvider,
                               max_tokens: int,
                               temperature: float,
                               advanced_settings: Optional[Dict[str, Any]] = None) -> str:
        """
        Generar texto con Ollama (local)

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema
            provider: Proveedor Ollama
            max_tokens: Número máximo de tokens
            temperature: Temperatura
            advanced_settings: Configuraciones avanzadas para la generación

        Returns:
            Texto generado
        """
        if not provider.api_endpoint:
            raise ValueError("API endpoint is required for Ollama")

        # Construir URL completa
        api_url = provider.api_endpoint
        if not api_url.endswith("/api/chat"):
            # Comprobar si termina con /
            if not api_url.endswith("/"):
                api_url = f"{api_url}/"
            api_url = f"{api_url}api/chat"

        headers = {
            "Content-Type": "application/json"
        }

        # Opciones básicas - simplemente pasar las opciones proporcionadas
        # sin añadir configuración de GPU (eso debe configurarse en el servidor Ollama remoto)
        options = {
            "num_predict": max_tokens,
            "temperature": temperature
        }
        
        # Pasar opciones avanzadas si están en los metadatos del proveedor
        if advanced_settings and "options" in advanced_settings:
            options.update(advanced_settings["options"])
        
        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "options": options
        }

        # Incorporar configuraciones avanzadas si se proporcionan
        if advanced_settings:
            for key, value in advanced_settings.items():
                if key == "options" and isinstance(value, dict):
                    payload["options"].update(value)
                elif key not in ["model", "messages", "options"]:
                    payload[key] = value

        timeout = aiohttp.ClientTimeout(total=self.settings.ollama.timeout_seconds)

        logger.debug(f"Connecting to Ollama at {api_url}")

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(
                        api_url,
                        headers=headers,
                        json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama API error: {response.status} - {error_text}")
                        raise ValueError(f"Ollama API error: {response.status} - {error_text}")

                    response_json = await response.json()
                    return response_json["message"]["content"]
            except aiohttp.ClientResponseError as e:
                logger.error(f"Ollama API response error: {e.status} - {e.message}")
                raise ValueError(f"Ollama API error: {e.status} - {e.message}")
            except aiohttp.ClientError as e:
                logger.error(f"Ollama API connection error: {str(e)}")
                raise

    # Implementación para buscar información relevante con herramienta find_relevant
    async def find_relevant_information(self, query: str, embedding_type: str = "general",
                                        owner_id: Optional[str] = None, area_id: Optional[str] = None,
                                        limit: int = 5) -> List[str]:
        """
        Buscar información relevante usando la herramienta MCP find_relevant

        Args:
            query: Consulta para buscar información
            embedding_type: Tipo de embedding (general o personal)
            owner_id: ID del propietario (para conocimiento personal)
            area_id: ID del área (para filtrar por área)
            limit: Número máximo de resultados

        Returns:
            Lista de resultados relevantes o mensaje de error
        """
        if not self.mcp_client or not self.has_find_tool:
            logger.warning("MCP client not available or find_relevant tool not found")
            return ["[MCP tools not available for retrieval]"]

        try:
            # Preparar parámetros para la herramienta
            tool_params = {
                "query": query,
                "embedding_type": embedding_type,
                "limit": limit
            }

            if owner_id:
                tool_params["owner_id"] = owner_id

            if area_id:
                tool_params["area_id"] = area_id

            # Llamar a la herramienta find_relevant
            results = await self.mcp_client.call_tool("find_relevant", tool_params)
            return results
        except Exception as e:
            logger.error(f"Error calling find_relevant MCP tool: {e}")
            return [f"Error retrieving information: {str(e)}"]

    # Implementación para almacenar documento con herramienta store_document
    async def store_document(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Almacenar documento usando la herramienta MCP store_document

        Args:
            text: Texto a almacenar
            metadata: Metadatos adicionales

        Returns:
            Confirmación o mensaje de error
        """
        if not self.mcp_client or not self.has_store_tool:
            logger.warning("MCP client not available or store_document tool not found")
            return "[MCP tools not available for storage]"

        try:
            # Preparar parámetros para la herramienta
            tool_params = {
                "information": text
            }

            if metadata:
                tool_params["metadata"] = metadata

            # Llamar a la herramienta store_document
            result = await self.mcp_client.call_tool("store_document", tool_params)
            return result
        except Exception as e:
            logger.error(f"Error calling store_document MCP tool: {e}")
            return f"Error storing document: {str(e)}"