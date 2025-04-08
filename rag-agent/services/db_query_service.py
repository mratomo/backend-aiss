# services/db_query_service.py
import asyncio
import logging
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

import aiohttp
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Intentar usar structlog para logging estructurado si está disponible
try:
    import structlog
    logger = structlog.get_logger("db_query_service")
    structlog_available = True
except ImportError:
    logger = logging.getLogger("db_query_service")
    structlog_available = False

from config.settings import Settings
from models.query import QueryResult
from services.llm_service import LLMService
from services.retrieval_service import RetrievalService

class DBQueryService:
    """Servicio para procesar consultas de base de datos con LLMs"""

    def __init__(self, db: AsyncIOMotorDatabase, llm_service: LLMService, 
                 retrieval_service: RetrievalService, settings: Settings):
        """
        Inicializar servicio con la base de datos y servicios dependientes
        
        Args:
            db: Instancia de la base de datos MongoDB
            llm_service: Servicio para generar texto con LLMs
            retrieval_service: Servicio para recuperar información relevante
            settings: Configuración de la aplicación
        """
        self.db = db
        self.queries_collection = db.db_queries
        self.llm_service = llm_service
        self.retrieval_service = retrieval_service
        self.settings = settings
        # No inicializar el HTTP client aquí para evitar problemas de cierre
        # Se inicializará bajo demanda en los métodos que lo requieran
        self.http_client = None
    
    async def close(self):
        """Cerrar recursos al finalizar"""
        if self.http_client is not None:
            await self.http_client.close()
    
    async def process_query(self, user_id: str, agent_id: str, query: str, 
                           connections: Optional[List[str]] = None,
                           options: Optional[Dict[str, Any]] = None) -> QueryResult:
        """
        Procesar una consulta de base de datos con un agente
        
        Args:
            user_id: ID del usuario que realiza la consulta
            agent_id: ID del agente a utilizar
            query: Consulta en lenguaje natural
            connections: IDs de conexiones específicas a usar (opcional)
            options: Opciones adicionales para la consulta
            
        Returns:
            Resultado de la consulta
            
        Raises:
            ValueError: Si hay errores en los parámetros
            Exception: Si ocurre algún error durante el procesamiento
        """
        start_time = time.time()
        
        try:
            # Obtener detalles del agente
            agent = await self._get_agent(agent_id)
            if not agent:
                raise ValueError(f"Agente no encontrado: {agent_id}")
            
            # Verificar si el agente está activo
            if not agent.get("active", True):
                raise ValueError(f"El agente {agent_id} no está activo")
            
            # Obtener conexiones asignadas al agente
            agent_connections = await self._get_agent_connections(agent_id, connections)
            if not agent_connections:
                raise ValueError(f"El agente {agent_id} no tiene conexiones asignadas o las conexiones especificadas no son válidas")
            
            # Registrar consulta en la base de datos
            query_id = await self._create_query_record(user_id, agent_id, query, agent_connections)
            
            # Analizar si la consulta requiere acceso a base de datos
            requires_db, reasoning = await self._evaluate_query_type(agent, query)
            
            if not requires_db:
                # Procesar como consulta RAG convencional
                logger.info(f"Procesando consulta como RAG convencional: {query[:50]}...")
                result = await self._process_rag_query(query_id, agent, query, user_id)
            else:
                # Procesar como consulta a base de datos
                logger.info(f"Procesando consulta a DB: {query[:50]}...")
                result = await self._process_db_query(query_id, agent, query, agent_connections, options)
            
            # Actualizar registro de consulta con resultado
            elapsed_time = int((time.time() - start_time) * 1000)
            await self._update_query_record(query_id, result, elapsed_time)
            
            # Devolver resultado
            return result
        except Exception as e:
            logger.error(f"Error procesando consulta: {e}")
            
            # Registrar error si se creó el registro de consulta
            try:
                if 'query_id' in locals():
                    elapsed_time = int((time.time() - start_time) * 1000)
                    await self._update_query_record(
                        query_id, 
                        QueryResult(
                            id=str(query_id),
                            query=query,
                            answer=f"Error procesando consulta: {str(e)}",
                            has_error=True,
                            error_message=str(e),
                            query_type="unknown",
                            execution_time_ms=elapsed_time,
                            timestamp=datetime.utcnow()
                        ),
                        elapsed_time
                    )
            except Exception:
                pass
            
            raise
    
    async def get_query_history(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Obtener historial de consultas de un usuario
        
        Args:
            user_id: ID del usuario
            limit: Número máximo de resultados
            offset: Índice desde donde empezar
            
        Returns:
            Lista de consultas realizadas
        """
        cursor = self.queries_collection.find(
            {"user_id": user_id}
        ).sort(
            "created_at", -1
        ).skip(offset).limit(limit)
        
        # Convertir a lista y formatear
        history = []
        async for doc in cursor:
            history.append({
                "id": str(doc["_id"]),
                "query": doc["original_query"],
                "query_type": doc.get("query_type", "unknown"),
                "status": doc.get("status", "unknown"),
                "execution_time_ms": doc.get("execution_time_ms"),
                "created_at": doc.get("created_at"),
                "completed_at": doc.get("completed_at")
            })
        
        return history
    
    async def get_query_detail(self, query_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtener detalle de una consulta específica
        
        Args:
            query_id: ID de la consulta
            user_id: ID del usuario (para verificar permisos)
            
        Returns:
            Detalle de la consulta o None si no existe o no tiene permisos
        """
        try:
            obj_id = ObjectId(query_id)
        except Exception:
            return None
        
        # Obtener consulta y verificar permisos
        query = await self.queries_collection.find_one({
            "_id": obj_id,
            "user_id": user_id
        })
        
        if not query:
            return None
        
        # Formatear respuesta
        result = {
            "id": str(query["_id"]),
            "query": query["original_query"],
            "query_type": query.get("query_type", "unknown"),
            "status": query.get("status", "unknown"),
            "result": query.get("result"),
            "generated_queries": query.get("generated_queries", []),
            "execution_time_ms": query.get("execution_time_ms"),
            "error": query.get("error"),
            "created_at": query.get("created_at"),
            "completed_at": query.get("completed_at"),
            "agent": {
                "id": query.get("agent_id"),
                "name": query.get("agent_name")
            }
        }
        
        return result
    
    async def _get_http_client(self):
        """
        Obtener o crear cliente HTTP bajo demanda
        
        Returns:
            Cliente HTTP inicializado
        """
        if self.http_client is None:
            timeout = aiohttp.ClientTimeout(total=60)
            self.http_client = aiohttp.ClientSession(timeout=timeout)
        return self.http_client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def _get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtener información de un agente desde el servicio de conexiones
        
        Args:
            agent_id: ID del agente
            
        Returns:
            Información del agente o None si no existe
        """
        try:
            http_client = await self._get_http_client()
            async with http_client.get(f"{self.settings.db_connections_url}/agents/{agent_id}") as response:
                if response.status == 200:
                    return await response.json()
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Error de conexión obteniendo agente {agent_id}: {e}")
            raise  # Será capturado por retry
        except Exception as e:
            logger.error(f"Error obteniendo agente {agent_id}: {e}")
            return None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def _get_agent_connections(self, agent_id: str, requested_connections: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Obtener conexiones asignadas a un agente
        
        Args:
            agent_id: ID del agente
            requested_connections: IDs de conexiones específicas a filtrar
            
        Returns:
            Lista de conexiones disponibles para el agente
        """
        try:
            http_client = await self._get_http_client()
            async with http_client.get(
                f"{self.settings.db_connections_url}/agents/{agent_id}/connections",
                timeout=aiohttp.ClientTimeout(total=30)  # Timeout específico para esta operación
            ) as response:
                if response.status == 200:
                    connections = await response.json()
                    
                    # Filtrar conexiones específicas si se solicitan
                    if requested_connections:
                        connections = [
                            conn for conn in connections 
                            if conn.get("connection", {}).get("id") in requested_connections
                        ]
                    
                    return connections
                return []
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Error de conexión obteniendo conexiones para agente {agent_id}: {e}")
            raise  # Será capturado por retry
        except Exception as e:
            logger.error(f"Error obteniendo conexiones para agente {agent_id}: {e}")
            return []
    
    async def _create_query_record(self, user_id: str, agent_id: str, query: str, connections: List[Dict[str, Any]]) -> ObjectId:
        """
        Crear registro de consulta en la base de datos
        
        Args:
            user_id: ID del usuario
            agent_id: ID del agente
            query: Consulta en lenguaje natural
            connections: Conexiones a utilizar
            
        Returns:
            ID del registro creado
        """
        # Crear documento
        doc = {
            "user_id": user_id,
            "agent_id": agent_id,
            "original_query": query,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "connections": [conn.get("connection", {}).get("id") for conn in connections]
        }
        
        # Insertar en la base de datos
        result = await self.queries_collection.insert_one(doc)
        return result.inserted_id
    
    async def _update_query_record(self, query_id: ObjectId, result: QueryResult, execution_time_ms: int) -> None:
        """
        Actualizar registro de consulta con el resultado
        
        Args:
            query_id: ID del registro
            result: Resultado de la consulta
            execution_time_ms: Tiempo de ejecución en milisegundos
        """
        update = {
            "status": "completed",
            "query_type": result.query_type,
            "result": result.answer,
            "has_error": result.has_error,
            "error_message": result.error_message if result.has_error else None,
            "execution_time_ms": execution_time_ms,
            "completed_at": datetime.utcnow()
        }
        
        # Si hay consultas generadas, guardarlas
        if hasattr(result, 'generated_queries') and result.generated_queries:
            update["generated_queries"] = result.generated_queries
        
        # Actualizar en la base de datos
        await self.queries_collection.update_one(
            {"_id": query_id},
            {"$set": update}
        )
    
    async def _evaluate_query_type(self, agent: Dict[str, Any], query: str) -> Tuple[bool, str]:
        """
        Evaluar si una consulta requiere acceso a base de datos o RAG
        
        Args:
            agent: Información del agente
            query: Consulta en lenguaje natural
            
        Returns:
            Tupla (bool, str): True si requiere DB, False si es RAG, y el razonamiento
        """
        # Obtener prompt de evaluación
        prompts = agent.get("prompts", {})
        evaluation_prompt = prompts.get("query_evaluation_prompt")
        
        if not evaluation_prompt:
            # Usar prompt predeterminado
            evaluation_prompt = """
            Evalúa si esta consulta requiere acceso a base de datos o puede resolverse con RAG convencional.
            
            Ejemplos que requieren BD:
            - "Consulta el estado actual de la máquina SRV-2023-089"
            - "Muéstrame las últimas alertas de seguridad"
            - "¿Cuántos usuarios se registraron ayer?"
            - "Dame un reporte de ventas del último mes"
            
            Ejemplos que NO requieren BD:
            - "Explícame el procedimiento de mantenimiento en el manual"
            - "Resume la política de seguridad del documento X"
            - "¿Cómo configuro mi cuenta?"
            - "Explica cómo funciona el proceso de onboarding"
            
            Consulta: "{query}"
            
            Responde solo con 'DB' o 'RAG' seguido de un breve razonamiento.
            """
        
        # Preparar prompt
        prompt = evaluation_prompt.replace("{query}", query)
        
        # Obtener sistema de LLM a usar
        model_id = agent.get("model_id")
        
        # Llamar al LLM para evaluar
        response = await self.llm_service.generate_text(
            prompt=prompt,
            system_prompt="Eres un analizador de consultas que determina si una consulta requiere acceso a base de datos en tiempo real o puede responderse con documentación estática.",
            provider_id=model_id,
            max_tokens=100,
            temperature=0
        )
        
        # Analizar respuesta
        response_text = response.get("text", "").strip()
        
        # Determinar tipo de consulta
        requires_db = response_text.upper().startswith("DB")
        
        # Extraer razonamiento
        reasoning = response_text[2:].strip() if requires_db else response_text[3:].strip()
        
        return requires_db, reasoning
    
    async def _process_rag_query(self, query_id: ObjectId, agent: Dict[str, Any], query: str, user_id: str) -> QueryResult:
        """
        Procesar consulta como RAG convencional
        
        Args:
            query_id: ID del registro de consulta
            agent: Información del agente
            query: Consulta en lenguaje natural
            user_id: ID del usuario
            
        Returns:
            Resultado de la consulta
        """
        # Obtener información relevante
        context = await self.retrieval_service.retrieve_relevant_context(query, user_id)
        
        # Obtener sistema de LLM a usar
        model_id = agent.get("model_id")
        
        # Obtener prompt predeterminado
        system_prompt = agent.get("default_system_prompt") or self.settings.rag_prompt_template
        
        # Generar respuesta
        rag_prompt = self.settings.rag_prompt_template.format(
            context=context,
            query=query
        )
        
        response = await self.llm_service.generate_text(
            prompt=rag_prompt,
            system_prompt=system_prompt,
            provider_id=model_id,
            max_tokens=500,
            temperature=0.2
        )
        
        # Crear resultado
        result = QueryResult(
            id=str(query_id),
            query=query,
            answer=response.get("text", ""),
            query_type="rag",
            has_error=False,
            error_message=None,
            execution_time_ms=0,  # Se actualizará después
            timestamp=datetime.utcnow()
        )
        
        return result
    
    async def _process_db_query(self, query_id: ObjectId, agent: Dict[str, Any], query: str, 
                               connections: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> QueryResult:
        """
        Procesar consulta a base de datos
        
        Args:
            query_id: ID del registro de consulta
            agent: Información del agente
            query: Consulta en lenguaje natural
            connections: Conexiones disponibles
            options: Opciones adicionales
            
        Returns:
            Resultado de la consulta
        """
        # Obtener prompts para generación de consultas
        prompts = agent.get("prompts", {})
        generation_prompt = prompts.get("query_generation_prompt")
        result_formatting_prompt = prompts.get("result_formatting_prompt")
        
        # Usar prompts predeterminados si no existen
        if not generation_prompt:
            generation_prompt = """
            Convierte la siguiente consulta en lenguaje natural a una consulta estructurada para {db_type}.
            
            Información del esquema:
            {schema_info}
            
            Consulta en lenguaje natural: "{query}"
            
            Genera solo la consulta SQL/NoSQL sin explicaciones adicionales.
            """
        
        if not result_formatting_prompt:
            result_formatting_prompt = """
            Formatea los resultados de la consulta de manera clara y concisa para el usuario.
            
            Consulta original: "{query}"
            
            Resultados de la consulta:
            {results}
            
            Por favor, formatea estos resultados de manera clara y concisa, incluyendo tablas si es apropiado.
            """
        
        # Obtener sistema de LLM a usar
        model_id = agent.get("model_id")
        
        # Obtener información de esquemas para las conexiones
        schemas_info = await self._get_schemas_info(connections)
        
        # Generar consultas para cada conexión relevante
        generated_queries = []
        query_results = []
        
        for connection in connections:
            try:
                conn_details = connection.get("connection", {})
                conn_id = conn_details.get("id")
                db_type = conn_details.get("type")
                
                # Obtener esquema para esta conexión
                schema_info = schemas_info.get(conn_id, "Esquema no disponible")
                
                # Preparar prompt para generar consulta
                prompt = generation_prompt.replace("{db_type}", db_type)
                prompt = prompt.replace("{schema_info}", schema_info)
                prompt = prompt.replace("{query}", query)
                
                # Generar consulta
                response = await self.llm_service.generate_text(
                    prompt=prompt,
                    system_prompt="Eres un especialista en bases de datos que convierte consultas en lenguaje natural a consultas estructuradas.",
                    provider_id=model_id,
                    max_tokens=300,
                    temperature=0.2
                )
                
                # Extraer consulta generada
                generated_query = response.get("text", "").strip()
                
                # Verificar si la consulta es válida
                if not generated_query:
                    continue
                
                # Ejecutar consulta
                query_result = await self._execute_db_query(conn_id, generated_query)
                
                # Guardar consulta y resultado
                generated_queries.append({
                    "connection_id": conn_id,
                    "connection_name": conn_details.get("name"),
                    "query_text": generated_query
                })
                
                query_results.append({
                    "connection_id": conn_id,
                    "connection_name": conn_details.get("name"),
                    "result": query_result
                })
            except Exception as e:
                logger.error(f"Error procesando consulta para conexión {connection.get('connection', {}).get('id')}: {e}")
                # Continuar con la siguiente conexión
        
        # Formatear resultados
        if not query_results:
            return QueryResult(
                id=str(query_id),
                query=query,
                answer="No se pudo generar una consulta válida para ninguna de las conexiones disponibles.",
                query_type="db",
                has_error=True,
                error_message="No se pudieron generar consultas válidas",
                execution_time_ms=0,  # Se actualizará después
                timestamp=datetime.utcnow(),
                generated_queries=generated_queries
            )
        
        # Preparar información de resultados para formateo
        results_info = json.dumps(query_results, indent=2)
        
        # Formatear resultados
        prompt = result_formatting_prompt.replace("{query}", query)
        prompt = prompt.replace("{results}", results_info)
        
        response = await self.llm_service.generate_text(
            prompt=prompt,
            system_prompt="Eres un especialista en análisis de datos que formatea resultados de consultas de manera clara y concisa.",
            provider_id=model_id,
            max_tokens=800,
            temperature=0.3
        )
        
        # Crear resultado final
        result = QueryResult(
            id=str(query_id),
            query=query,
            answer=response.get("text", ""),
            query_type="db",
            has_error=False,
            error_message=None,
            execution_time_ms=0,  # Se actualizará después
            timestamp=datetime.utcnow(),
            generated_queries=generated_queries
        )
        
        return result
    
    async def _get_schemas_info(self, connections: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Obtener información de esquemas para conexiones
        
        Args:
            connections: Lista de conexiones
            
        Returns:
            Diccionario con información de esquemas por ID de conexión
        """
        schemas = {}
        
        for connection in connections:
            conn_id = connection.get("connection", {}).get("id")
            
            try:
                async with self.http_client.get(f"{self.settings.schema_discovery_url}/schema/{conn_id}") as response:
                    if response.status == 200:
                        schema = await response.json()
                        
                        # Simplificar esquema para prompt
                        simplified = self._simplify_schema(schema)
                        schemas[conn_id] = simplified
                    else:
                        schemas[conn_id] = "Esquema no disponible"
            except Exception as e:
                logger.error(f"Error obteniendo esquema para conexión {conn_id}: {e}")
                schemas[conn_id] = "Error obteniendo esquema"
        
        return schemas
    
    def _simplify_schema(self, schema: Dict[str, Any]) -> str:
        """
        Simplificar esquema para incluir en prompt
        
        Args:
            schema: Esquema completo
            
        Returns:
            Esquema simplificado en formato texto
        """
        try:
            result = []
            
            # Verificar que el esquema tiene la estructura esperada
            if not isinstance(schema, dict):
                return "Error: El esquema no tiene el formato esperado"
            
            # Información general
            db_name = schema.get('name', 'Desconocido')
            db_type = schema.get('type', 'Desconocido')
            result.append(f"Base de datos: {db_name} ({db_type})")
            result.append("")
            
            # Tablas
            tables = schema.get("tables", [])
            if not isinstance(tables, list):
                tables = []
                
            result.append(f"Tablas ({len(tables)}):")
            
            for table in tables:
                if not isinstance(table, dict):
                    continue
                    
                table_name = table.get("name", "unknown")
                schema_name = table.get("schema")
                full_name = f"{schema_name}.{table_name}" if schema_name else table_name
                
                result.append(f"- {full_name}")
                
                # Columnas
                columns = table.get("columns", [])
                if not isinstance(columns, list):
                    columns = []
                    
                for column in columns:
                    if not isinstance(column, dict):
                        continue
                        
                    pk = "*" if column.get("primary_key") else " "
                    nullable = "NULL" if column.get("nullable") else "NOT NULL"
                    col_name = column.get("name", "unknown")
                    data_type = column.get("data_type", "unknown")
                    result.append(f"  {pk} {col_name} ({data_type}) {nullable}")
                
                # Foreign keys si existen
                foreign_keys = table.get("foreign_keys", [])
                if foreign_keys and isinstance(foreign_keys, list):
                    result.append("  Foreign keys:")
                    for fk in foreign_keys:
                        if not isinstance(fk, dict):
                            continue
                            
                        col = fk.get("column", "unknown")
                        ref_table = fk.get("referenced_table", "unknown")
                        ref_col = fk.get("referenced_column", "unknown")
                        result.append(f"  - {col} -> {ref_table}.{ref_col}")
                
                result.append("")
            
            return "\n".join(result)
        except Exception as e:
            logger.error("Error simplificando esquema", error=str(e))
            return f"Error procesando el esquema: {str(e)}"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def _execute_db_query(self, connection_id: str, query: str) -> Any:
        """
        Ejecutar consulta en una conexión
        
        Args:
            connection_id: ID de la conexión
            query: Consulta a ejecutar
            
        Returns:
            Resultado de la consulta
            
        Raises:
            Exception: Si hay error durante la ejecución
        """
        try:
            # Llamar al servicio de conexiones para ejecutar la consulta
            http_client = await self._get_http_client()
            
            # Timeout más largo para consultas de BD (pueden tardar más)
            timeout = aiohttp.ClientTimeout(total=90)
            
            async with http_client.post(
                f"{self.settings.db_connections_url}/connections/{connection_id}/execute",
                json={
                    "query": query,
                    "params": {}
                },
                timeout=timeout
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    error_msg = f"Error ejecutando consulta (status {response.status}): {error}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Error de conexión ejecutando consulta en {connection_id}: {e}")
            raise  # Será capturado por retry
        except Exception as e:
            logger.error(f"Error ejecutando consulta en conexión {connection_id}: {e}")
            raise