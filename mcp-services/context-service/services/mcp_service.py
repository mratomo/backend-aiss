# services/mcp_service.py
import logging
import json
from typing import Dict, List, Optional, Any, Union
import asyncio

import aiohttp
from fastapi import HTTPException
from mcp import Server, Tool, Context, ContextType

from config.settings import Settings
from services.area_service import AreaService
from services.embedding_service_client import EmbeddingServiceClient

logger = logging.getLogger(__name__)

class MCPService:
    """Servicio para gestionar el servidor Model Context Protocol (MCP)"""

    def __init__(self, settings: Settings, area_service: AreaService, embedding_client: EmbeddingServiceClient):
        """
        Inicializar servicio MCP con configuraciones y dependencias
        
        Args:
            settings: Configuración general
            area_service: Servicio para gestionar áreas de conocimiento
            embedding_client: Cliente para el servicio de embeddings
        """
        self.settings = settings
        self.area_service = area_service
        self.embedding_client = embedding_client

        # Inicializar servidor MCP
        self.server = Server(
            name=settings.mcp.server_name,
            version=settings.mcp.server_version
        )

        # Registrar herramientas
        self._register_tools()

    def _register_tools(self):
        """Registrar herramientas MCP disponibles"""

        # Herramienta para almacenar documento
        @self.server.tool(
            name="store_document",
            description="Almacena un texto en la base de conocimiento vectorial",
            input_schema={
                "information": {"type": "string", "description": "Texto/contenido a almacenar"},
                "metadata": {"type": "object", "description": "Metadatos adicionales (opcional)"}
            }
        )
        async def store_document(information: str, metadata: Optional[Dict[str, Any]] = None) -> str:
            """
            Almacena un texto en la base de conocimiento y genera su embedding
            
            Args:
                information: Texto a almacenar
                metadata: Metadatos opcionales (título, fuente, etc.)
                
            Returns:
                Confirmación o ID del documento almacenado
            """
            try:
                if not metadata:
                    metadata = {}

                # Determinar tipo de embedding y propietario
                embedding_type = "general"  # Por defecto general
                owner_id = metadata.get("owner_id", "system")
                doc_id = metadata.get("doc_id", f"mcp_doc_{len(information)%1000}")
                area_id = metadata.get("area_id")

                # Si hay area_id, asegurarse de que existe
                if area_id:
                    area = await self.area_service.get_area(area_id)
                    if not area:
                        return f"Error: Área con ID {area_id} no encontrada"

                # Almacenar texto usando el servicio de embeddings
                response = await self.embedding_client.create_embedding(
                    text=information,
                    embedding_type=embedding_type,
                    doc_id=doc_id,
                    owner_id=owner_id,
                    area_id=area_id,
                    metadata=metadata
                )

                return f"Documento almacenado con ID: {response.get('embedding_id')}"
            except Exception as e:
                logger.error(f"Error en herramienta store_document: {e}")
                return f"Error almacenando documento: {str(e)}"

        # Herramienta para buscar información relevante
        @self.server.tool(
            name="find_relevant",
            description="Busca en la base de conocimiento los textos más similares a una consulta",
            input_schema={
                "query": {"type": "string", "description": "Consulta o pregunta"},
                "embedding_type": {"type": "string", "description": "Tipo de embedding (general o personal)", "default": "general"},
                "owner_id": {"type": "string", "description": "ID del propietario (para conocimiento personal)", "default": None},
                "area_id": {"type": "string", "description": "ID del área (para filtrar por área)", "default": None},
                "limit": {"type": "integer", "description": "Número máximo de resultados", "default": 5}
            }
        )
        async def find_relevant(
                query: str,
                embedding_type: str = "general",
                owner_id: Optional[str] = None,
                area_id: Optional[str] = None,
                limit: int = 5
        ) -> List[str]:
            """
            Busca información relevante para una consulta
            
            Args:
                query: Consulta o pregunta
                embedding_type: Tipo de embedding (general o personal)
                owner_id: ID del propietario para filtrar (para personal)
                area_id: ID del área para filtrar
                limit: Número máximo de resultados
                
            Returns:
                Lista de fragmentos de texto relevantes
            """
            try:
                # Validar tipo de embedding
                if embedding_type not in ["general", "personal"]:
                    embedding_type = "general"

                # Validar límite
                limit = min(max(1, limit), 20)  # Entre 1 y 20

                # Buscar usando el servicio de embeddings
                results = await self.embedding_client.search(
                    query=query,
                    embedding_type=embedding_type,
                    owner_id=owner_id,
                    area_id=area_id,
                    limit=limit
                )

                # Formatear resultados
                formatted_results = []
                for i, result in enumerate(results.get("results", [])):
                    score = result.get("score", 0)
                    text = result.get("text", "")
                    doc_id = result.get("doc_id", "")

                    if text:
                        formatted_text = f"[Doc {i+1}] ({score:.2f}): {text}"
                        formatted_results.append(formatted_text)

                if not formatted_results:
                    return ["No se encontró información relevante para la consulta."]

                return formatted_results
            except Exception as e:
                logger.error(f"Error en herramienta find_relevant: {e}")
                return [f"Error buscando información: {str(e)}"]

        # Aquí se pueden registrar más herramientas MCP según sea necesario
        logger.info(f"Herramientas MCP registradas: {[t.name for t in self.server.tools]}")

    async def create_context(self, name: str, description: str, metadata: Optional[Dict[str, str]] = None) -> str:
        """
        Crear un nuevo contexto MCP
        
        Args:
            name: Nombre del contexto
            description: Descripción del contexto
            metadata: Metadatos adicionales
            
        Returns:
            ID del contexto creado
        """
        try:
            # Crear contexto en el servidor MCP
            context = Context(
                name=name,
                description=description,
                metadata=metadata or {},
                type=ContextType.KNOWLEDGE
            )

            # Registrar contexto y obtener ID
            context_id = self.server.register_context(context)
            logger.info(f"Contexto MCP creado: {context_id} - {name}")

            return context_id
        except Exception as e:
            logger.error(f"Error creando contexto MCP: {e}")
            raise HTTPException(status_code=500, detail=f"Error creando contexto MCP: {str(e)}")

    def update_context(self, context_id: str, name: Optional[str] = None, description: Optional[str] = None) -> bool:
        """
        Actualizar un contexto MCP existente
        
        Args:
            context_id: ID del contexto a actualizar
            name: Nuevo nombre (opcional)
            description: Nueva descripción (opcional)
            
        Returns:
            True si se actualizó correctamente
        """
        try:
            # Verificar si el contexto existe
            context = self.server.get_context(context_id)
            if not context:
                logger.warning(f"Contexto MCP no encontrado: {context_id}")
                return False

            # Actualizar campos si se proporcionan
            if name is not None:
                context.name = name
            if description is not None:
                context.description = description

            logger.info(f"Contexto MCP actualizado: {context_id}")
            return True
        except Exception as e:
            logger.error(f"Error actualizando contexto MCP: {e}")
            return False

    def delete_context(self, context_id: str) -> bool:
        """
        Eliminar un contexto MCP
        
        Args:
            context_id: ID del contexto a eliminar
            
        Returns:
            True si se eliminó correctamente
        """
        try:
            # Eliminar contexto
            result = self.server.deregister_context(context_id)

            if result:
                logger.info(f"Contexto MCP eliminado: {context_id}")
            else:
                logger.warning(f"Contexto MCP no encontrado para eliminar: {context_id}")

            return result
        except Exception as e:
            logger.error(f"Error eliminando contexto MCP: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Obtener estado del servidor MCP
        
        Returns:
            Información de estado
        """
        return {
            "name": self.server.name,
            "version": self.server.version,
            "tools_count": len(self.server.tools),
            "contexts_count": len(self.server.contexts),
            "active_contexts": len([c for c in self.server.contexts.values() if c.active])
        }

    def get_active_contexts(self) -> List[Dict[str, Any]]:
        """
        Obtener lista de contextos activos
        
        Returns:
            Lista de contextos activos
        """
        active_contexts = []

        for context_id, context in self.server.contexts.items():
            if context.active:
                active_contexts.append({
                    "id": context_id,
                    "name": context.name,
                    "description": context.description,
                    "type": context.type.value if hasattr(context.type, 'value') else str(context.type),
                    "metadata": context.metadata
                })

        return active_contexts

    # Lock global para operaciones de activación/desactivación de contextos
    _contexts_lock = asyncio.Lock()
    
    async def activate_context(self, context_id: str) -> Dict[str, Any]:
        """
        Activar un contexto MCP
        
        Args:
            context_id: ID del contexto a activar
            
        Returns:
            Información de activación
        """
        try:
            # Adquirir lock para evitar race conditions al modificar el estado de los contextos
            async with self._contexts_lock:
                # Verificar si el contexto existe
                context = self.server.get_context(context_id)
                if not context:
                    logger.warning(f"Contexto MCP no encontrado: {context_id}")
                    raise HTTPException(status_code=404, detail=f"Contexto MCP no encontrado: {context_id}")

                # Activar contexto de forma thread-safe
                context.active = True

                logger.info(f"Contexto MCP activado: {context_id} - {context.name}")

                # Crear una copia segura de la información para devolver
                result = {
                    "id": context_id,
                    "name": context.name,
                    "active": True,
                    "status": "activated"
                }
                
            # Devolver el resultado fuera del lock
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error activando contexto MCP: {e}")
            raise HTTPException(status_code=500, detail=f"Error activando contexto MCP: {str(e)}")

    async def deactivate_context(self, context_id: str) -> Dict[str, Any]:
        """
        Desactivar un contexto MCP
        
        Args:
            context_id: ID del contexto a desactivar
            
        Returns:
            Información de desactivación
        """
        try:
            # Adquirir lock para evitar race conditions al modificar el estado de los contextos
            # Usar el mismo lock que en activate_context para asegurar la exclusión mutua
            async with self._contexts_lock:
                # Verificar si el contexto existe
                context = self.server.get_context(context_id)
                if not context:
                    logger.warning(f"Contexto MCP no encontrado: {context_id}")
                    raise HTTPException(status_code=404, detail=f"Contexto MCP no encontrado: {context_id}")

                # Desactivar contexto de forma thread-safe
                context.active = False

                logger.info(f"Contexto MCP desactivado: {context_id} - {context.name}")

                # Crear una copia segura de la información para devolver
                result = {
                    "id": context_id,
                    "name": context.name,
                    "active": False,
                    "status": "deactivated"
                }
                
            # Devolver el resultado fuera del lock
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error desactivando contexto MCP: {e}")
            raise HTTPException(status_code=500, detail=f"Error desactivando contexto MCP: {str(e)}")

    async def get_area_system_prompt(self, area_id: str) -> Optional[str]:
        """
        Obtener el prompt de sistema para un área específica
        
        Args:
            area_id: ID del área
            
        Returns:
            Prompt de sistema o None si no está configurado
        """
        try:
            # Obtener área
            area = await self.area_service.get_area(area_id)
            if not area:
                logger.warning(f"Área no encontrada: {area_id}")
                return None

            # Obtener prompt de sistema específico del área
            system_prompt = area.get("system_prompt")

            # Si no hay prompt específico, usar el predeterminado
            if not system_prompt:
                return self.settings.mcp.default_system_prompt

            return system_prompt
        except Exception as e:
            logger.error(f"Error al obtener prompt de sistema para área {area_id}: {e}")
            return None