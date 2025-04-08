import logging
import json
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from pydantic import BaseModel, Field

# Neo4j driver
from neo4j import AsyncGraphDatabase, AsyncSession, AsyncDriver
from neo4j.exceptions import ServiceUnavailable

# LangGraph para flujos complejos
from langgraph.graph import StateGraph, END
import networkx as nx
import operator

# Servicios existentes
from config.settings import Settings
from models.embedding import EmbeddingType
from models.query import Source, QueryResponse
from services.llm_service import LLMService
from services.retrieval_service import RetrievalService, DocumentInfo
from services.mcp_service import MCPService

logger = logging.getLogger(__name__)

# Definiciones Pydantic para el estado del grafo
class Entity(BaseModel):
    """Entidad identificada en el grafo de conocimiento"""
    id: str
    name: str
    type: str = "table"
    schema: Optional[str] = None
    description: Optional[str] = ""
    relevance: float = 0.0

class Relation(BaseModel):
    """Relación entre entidades"""
    source: str
    target: str
    type: str = "relates_to"
    via_column: Optional[str] = None

class Subquery(BaseModel):
    """Subconsulta generada para un nodo del grafo"""
    text: str
    focus_entity: Optional[str] = None
    result: Optional[str] = None
    processed: bool = False

class GraphContext(BaseModel):
    """Contexto enriquecido con conocimiento del grafo"""
    query_type: str = "direct"  # direct, exploration, or analysis
    entities: List[Entity] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    subqueries: List[Subquery] = Field(default_factory=list)
    related_tables: List[Dict[str, Any]] = Field(default_factory=list)
    paths: List[Dict[str, Any]] = Field(default_factory=list)
    community_summaries: Dict[str, str] = Field(default_factory=dict)
    vector_results: List[str] = Field(default_factory=list)

class GraphRAGState(BaseModel):
    """Estado completo del flujo GraphRAG"""
    query: str
    connection_id: Optional[str] = None
    user_id: Optional[str] = None
    area_id: Optional[str] = None
    llm_provider_id: Optional[str] = None
    original_documents: List[DocumentInfo] = Field(default_factory=list)
    graph_context: GraphContext = Field(default_factory=GraphContext)
    response: Optional[str] = None
    sources: List[Source] = Field(default_factory=list)
    processing_info: Dict[str, Any] = Field(default_factory=dict)
    
    def add_entity(self, entity: Entity) -> None:
        """Añadir entidad al contexto evitando duplicados"""
        existing_ids = {e.id for e in self.graph_context.entities}
        if entity.id not in existing_ids:
            self.graph_context.entities.append(entity)
    
    def add_relation(self, relation: Relation) -> None:
        """Añadir relación al contexto evitando duplicados"""
        existing_relations = {(r.source, r.target, r.type) for r in self.graph_context.relations}
        relation_key = (relation.source, relation.target, relation.type)
        if relation_key not in existing_relations:
            self.graph_context.relations.append(relation)
    
    def get_entity_by_id(self, entity_id: str) -> Optional[Entity]:
        """Obtener entidad por ID"""
        for entity in self.graph_context.entities:
            if entity.id == entity_id:
                return entity
        return None
    
    def get_entity_by_name(self, name: str) -> Optional[Entity]:
        """Obtener entidad por nombre"""
        for entity in self.graph_context.entities:
            if entity.name.lower() == name.lower():
                return entity
        return None
    
    def add_subquery(self, subquery: Subquery) -> None:
        """Añadir subconsulta al contexto"""
        self.graph_context.subqueries.append(subquery)

class GraphRAGService:
    """
    Servicio para implementar Retrieval-Augmented Generation basado en grafos (GraphRAG).
    
    Utiliza:
    - Neo4j para almacenar y consultar grafos de conocimiento
    - LangGraph para orquestar flujos de razonamiento sobre grafos
    - Servicios existentes (RAG, LLM, MCP) para integración
    """

    def __init__(self, 
                 db, 
                 llm_service: LLMService, 
                 retrieval_service: RetrievalService, 
                 mcp_service: MCPService, 
                 settings: Settings):
        """
        Inicializar servicio GraphRAG
        
        Args:
            db: Base de datos MongoDB
            llm_service: Servicio para LLMs
            retrieval_service: Servicio para recuperación
            mcp_service: Servicio MCP
            settings: Configuración
        """
        self.db = db
        self.llm_service = llm_service
        self.retrieval_service = retrieval_service
        self.mcp_service = mcp_service
        self.settings = settings
        
        # Inicializar Neo4j (AsyncDriver)
        self._driver = None
        self._init_neo4j_driver()
        
        # Construir el grafo LangGraph
        self.graph_app = self._build_graph()
        
        # Colección para caching
        self.history_collection = db.graph_rag_history
        
    def _init_neo4j_driver(self) -> None:
        """Inicializar driver de Neo4j de forma segura"""
        try:
            uri = self.settings.neo4j_uri
            username = self.settings.neo4j_username
            password = self.settings.neo4j_password
            
            if not uri or not username or not password:
                logger.warning("Neo4j configuration incomplete, Graph RAG functionality will be limited")
                return
                
            self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
            logger.info(f"Neo4j driver initialized for {uri}")
                
        except ServiceUnavailable as e:
            logger.error(f"Neo4j connection failed: {e}")
            self._driver = None
        except Exception as e:
            logger.error(f"Error initializing Neo4j driver: {e}")
            self._driver = None
    
    @property
    def driver(self) -> Optional[AsyncDriver]:
        """Obtener driver de Neo4j, reintentar conexión si es necesario"""
        if self._driver is None:
            self._init_neo4j_driver()
        return self._driver
    
    def _build_graph(self) -> StateGraph:
        """
        Construir el grafo de flujo LangGraph para GraphRAG
        
        Returns:
            Aplicación LangGraph compilada
        """
        graph = StateGraph(GraphRAGState)
        
        # Nodos del flujo
        graph.add_node("query_analysis", self.query_analysis_node)
        graph.add_node("schema_retrieval", self.schema_retrieval_node)
        graph.add_node("entity_identification", self.entity_identification_node)
        graph.add_node("graph_exploration", self.graph_exploration_node)
        graph.add_node("subquery_generation", self.subquery_generation_node)
        graph.add_node("context_aggregation", self.context_aggregation_node)
        graph.add_node("response_generation", self.response_generation_node)
        
        # Definir flujo básico
        graph.add_edge("query_analysis", "schema_retrieval")
        graph.add_edge("schema_retrieval", "entity_identification")
        
        # Decidir si explorar el grafo basado en el tipo de consulta
        graph.add_conditional_edges(
            "entity_identification",
            self.should_explore_graph,
            {
                True: "graph_exploration",
                False: "context_aggregation"
            }
        )
        
        # Decidir si generar subconsultas
        graph.add_conditional_edges(
            "graph_exploration",
            self.should_generate_subqueries,
            {
                True: "subquery_generation",
                False: "context_aggregation"
            }
        )
        
        graph.add_edge("subquery_generation", "context_aggregation")
        graph.add_edge("context_aggregation", "response_generation")
        graph.add_edge("response_generation", END)
        
        # Compilar grafo
        compiled_graph = graph.compile()
        return compiled_graph
    
    # Nodos del grafo LangGraph
    
    async def query_analysis_node(self, state: GraphRAGState) -> GraphRAGState:
        """
        Analizar la consulta del usuario para determinar su tipo y objetivos
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            Estado actualizado
        """
        start_time = time.time()
        
        # Prompt para clasificar la consulta
        system_prompt = """
        Tu tarea es analizar la consulta del usuario sobre una base de datos y clasificarla según su tipo.
        Los tipos posibles son:
        
        - "direct": Consulta directa sobre una tabla o entidad específica (ej: "Muestra las columnas de la tabla users")
        - "exploration": Consulta que explora relaciones entre tablas (ej: "¿Cómo se relacionan las tablas orders y customers?")
        - "analysis": Consulta de análisis general sobre la estructura o diseño (ej: "¿Cuáles son las tablas principales del sistema?")
        
        Responde en formato JSON con:
        - "query_type": el tipo de consulta (uno de los anteriores)
        - "focus_tables": lista de nombres de tablas mencionadas en la consulta (si hay)
        - "exploration_depth": nivel recomendado de exploración (1-3) basado en la complejidad de la consulta
        """
        
        try:
            # Generar análisis con el LLM
            response = await self.llm_service.generate_text(
                prompt=state.query,
                system_prompt=system_prompt,
                provider_id=state.llm_provider_id,
                max_tokens=300,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            # Parsear respuesta
            analysis_text = response.get("text", "{}")
            try:
                analysis = json.loads(analysis_text)
                
                # Actualizar estado con el análisis
                state.graph_context.query_type = analysis.get("query_type", "direct")
                
                # Registrar tablas mencionadas
                focus_tables = analysis.get("focus_tables", [])
                exploration_depth = analysis.get("exploration_depth", 1)
                
                # Actualizar información de procesamiento
                state.processing_info["query_analysis"] = {
                    "query_type": state.graph_context.query_type,
                    "focus_tables": focus_tables,
                    "exploration_depth": exploration_depth,
                    "duration_ms": int((time.time() - start_time) * 1000)
                }
                
            except json.JSONDecodeError:
                logger.error(f"Error parsing query analysis JSON: {analysis_text}")
                state.graph_context.query_type = "direct"  # Default fallback
                state.processing_info["query_analysis_error"] = "JSON parse error"
                
        except Exception as e:
            logger.error(f"Error in query analysis: {e}")
            state.processing_info["query_analysis_error"] = str(e)
            
        return state
    
    async def schema_retrieval_node(self, state: GraphRAGState) -> GraphRAGState:
        """
        Recuperar información básica del esquema y vectores relevantes
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            Estado actualizado
        """
        start_time = time.time()
        
        try:
            # Paso 1: Realizar búsqueda vectorial tradicional para contexto inicial
            documents = []
            
            # Si hay un área específica, utilizamos su connection_id
            if state.area_id:
                # Verificar si existe un área con este ID
                area = await self.mcp_service.get_area(state.area_id)
                if area and area.get("metadata", {}).get("connection_id"):
                    # Establecer connection_id en el estado
                    state.connection_id = area["metadata"]["connection_id"]
                
                # Buscar documentos para esa área
                area_docs = await self.retrieval_service.retrieve_documents(
                    query=state.query,
                    embedding_type=EmbeddingType.GENERAL,
                    area_id=state.area_id,
                    limit=5
                )
                documents.extend(area_docs)
            else:
                # Búsqueda general
                general_docs = await self.retrieval_service.retrieve_documents(
                    query=state.query,
                    embedding_type=EmbeddingType.GENERAL,
                    limit=5
                )
                documents.extend(general_docs)
            
            # Si hay un usuario, añadir documentos personales
            if state.user_id:
                personal_docs = await self.retrieval_service.retrieve_documents(
                    query=state.query,
                    embedding_type=EmbeddingType.PERSONAL,
                    owner_id=state.user_id,
                    limit=3
                )
                documents.extend(personal_docs)
            
            # Guardar documentos recuperados y extraer textos
            state.original_documents = documents
            for doc in documents:
                state.graph_context.vector_results.append(doc.content)
            
            # Actualizar información de procesamiento
            state.processing_info["schema_retrieval"] = {
                "documents_retrieved": len(documents),
                "duration_ms": int((time.time() - start_time) * 1000)
            }
            
        except Exception as e:
            logger.error(f"Error in schema retrieval: {e}")
            state.processing_info["schema_retrieval_error"] = str(e)
            
        return state
    
    async def entity_identification_node(self, state: GraphRAGState) -> GraphRAGState:
        """
        Identificar entidades (tablas) mencionadas en la consulta
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            Estado actualizado
        """
        start_time = time.time()
        
        # Si no hay connection_id, no podemos proceder con la identificación de entidades
        if not state.connection_id:
            state.processing_info["entity_identification"] = {
                "status": "skipped",
                "reason": "No connection_id available"
            }
            return state
            
        # Si no hay driver de Neo4j, no podemos proceder
        if self.driver is None:
            state.processing_info["entity_identification"] = {
                "status": "skipped",
                "reason": "Neo4j driver not available"
            }
            return state
            
        try:
            # Realizar búsqueda en Neo4j para identificar tablas 
            async with self.driver.session() as session:
                # Obtener lista de tablas en la base de datos
                tables_result = await session.run("""
                MATCH (db:Database {connection_id: $connection_id})-[:CONTAINS]->(t:Table)
                RETURN t.name AS name, t.schema AS schema, t.description AS description
                """, connection_id=state.connection_id)
                
                tables = await tables_result.data()
                
                # Si no hay tablas, no podemos continuar
                if not tables:
                    state.processing_info["entity_identification"] = {
                        "status": "skipped",
                        "reason": "No tables found for this connection"
                    }
                    return state
                
                # Extraer análisis previo
                analysis = state.processing_info.get("query_analysis", {})
                focus_tables = analysis.get("focus_tables", [])
                
                # Si hay tablas específicas mencionadas, priorizarlas
                if focus_tables:
                    for table_name in focus_tables:
                        # Buscar tabla por nombre (exacto o similar)
                        matching_tables = [t for t in tables if t["name"].lower() == table_name.lower()]
                        
                        if not matching_tables:
                            # Búsqueda fuzzy si no hay match exacto
                            matching_tables = [t for t in tables if table_name.lower() in t["name"].lower()]
                        
                        # Añadir tablas encontradas como entidades
                        for table in matching_tables:
                            entity_id = f"{table['schema'] or 'public'}.{table['name']}"
                            entity = Entity(
                                id=entity_id,
                                name=table["name"],
                                schema=table["schema"],
                                description=table.get("description", ""),
                                relevance=1.0  # Alta relevancia para tablas mencionadas directamente
                            )
                            state.add_entity(entity)
                
                # Si estamos en modo de exploración o análisis y no se encontraron entidades específicas,
                # recuperar tablas principales (con más relaciones) como puntos de entrada
                if (state.graph_context.query_type in ["exploration", "analysis"] 
                        and len(state.graph_context.entities) == 0):
                    
                    main_tables_result = await session.run("""
                    MATCH (db:Database {connection_id: $connection_id})-[:CONTAINS]->(t:Table)
                    OPTIONAL MATCH (t)-[r:RELATES_TO]-(other:Table)
                    WITH t, count(r) AS rel_count
                    RETURN t.name AS name, t.schema AS schema, t.description AS description, rel_count
                    ORDER BY rel_count DESC
                    LIMIT 5
                    """, connection_id=state.connection_id)
                    
                    main_tables = await main_tables_result.data()
                    
                    # Añadir tablas principales como entidades
                    for idx, table in enumerate(main_tables):
                        entity_id = f"{table['schema'] or 'public'}.{table['name']}"
                        entity = Entity(
                            id=entity_id,
                            name=table["name"],
                            schema=table["schema"],
                            description=table.get("description", ""),
                            relevance=0.9 - (idx * 0.1)  # Relevancia decreciente por orden
                        )
                        state.add_entity(entity)
                
                # Si no se encontraron entidades, añadir algunas tablas genéricas
                if len(state.graph_context.entities) == 0:
                    # Tomar hasta 3 tablas (priorizando las que tienen descripción)
                    sorted_tables = sorted(
                        tables, 
                        key=lambda t: len(t.get("description", "")), 
                        reverse=True
                    )[:3]
                    
                    for idx, table in enumerate(sorted_tables):
                        entity_id = f"{table['schema'] or 'public'}.{table['name']}"
                        entity = Entity(
                            id=entity_id,
                            name=table["name"],
                            schema=table["schema"],
                            description=table.get("description", ""),
                            relevance=0.5 - (idx * 0.1)  # Relevancia moderada
                        )
                        state.add_entity(entity)
            
            # Actualizar información de procesamiento
            state.processing_info["entity_identification"] = {
                "entities_identified": len(state.graph_context.entities),
                "entity_names": [e.name for e in state.graph_context.entities],
                "duration_ms": int((time.time() - start_time) * 1000)
            }
            
        except Exception as e:
            logger.error(f"Error in entity identification: {e}")
            state.processing_info["entity_identification_error"] = str(e)
            
        return state
    
    def should_explore_graph(self, state: GraphRAGState) -> bool:
        """
        Decidir si explorar el grafo basado en el tipo de consulta y entidades identificadas
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            True si se debe explorar el grafo, False en caso contrario
        """
        # Si no hay conexión a Neo4j, no podemos explorar
        if self.driver is None:
            return False
            
        # Si no hay connection_id, no podemos explorar
        if not state.connection_id:
            return False
            
        # Si no hay entidades, no tiene sentido explorar
        if len(state.graph_context.entities) == 0:
            return False
            
        # Explorar según el tipo de consulta
        if state.graph_context.query_type in ["exploration", "analysis"]:
            return True
            
        # Para consultas directas, solo explorar si hay múltiples entidades
        if state.graph_context.query_type == "direct" and len(state.graph_context.entities) > 1:
            return True
            
        return False
    
    async def graph_exploration_node(self, state: GraphRAGState) -> GraphRAGState:
        """
        Explorar el grafo para identificar relaciones y contexto adicional
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            Estado actualizado
        """
        start_time = time.time()
        
        # Si no hay driver de Neo4j o no hay connection_id, no podemos proceder
        if self.driver is None or not state.connection_id:
            state.processing_info["graph_exploration"] = {
                "status": "skipped",
                "reason": "Neo4j driver not available or no connection_id"
            }
            return state
            
        try:
            async with self.driver.session() as session:
                # Explorar grafo para cada entidad identificada
                for entity in state.graph_context.entities:
                    # Buscar relaciones para esta entidad
                    relations_result = await session.run("""
                    MATCH (source:Table)-[r:RELATES_TO]->(target:Table)
                    WHERE source.table_id CONTAINS $connection_id
                    AND source.name = $table_name
                    RETURN source.name AS source_name, target.name AS target_name,
                           r.via_column AS via_column
                    """, connection_id=state.connection_id, table_name=entity.name)
                    
                    relations = await relations_result.data()
                    
                    # Añadir relaciones al contexto
                    for relation in relations:
                        relation_obj = Relation(
                            source=relation["source_name"],
                            target=relation["target_name"],
                            type="relates_to",
                            via_column=relation["via_column"]
                        )
                        state.add_relation(relation_obj)
                        
                        # Buscar la entidad destino para añadirla si no existe
                        if not state.get_entity_by_name(relation["target_name"]):
                            # Obtener detalles de la tabla destino
                            target_result = await session.run("""
                            MATCH (t:Table)
                            WHERE t.table_id CONTAINS $connection_id
                            AND t.name = $table_name
                            RETURN t.name AS name, t.schema AS schema, t.description AS description
                            """, connection_id=state.connection_id, table_name=relation["target_name"])
                            
                            target_data = await target_result.data()
                            if target_data:
                                target = target_data[0]
                                entity_id = f"{target['schema'] or 'public'}.{target['name']}"
                                target_entity = Entity(
                                    id=entity_id,
                                    name=target["name"],
                                    schema=target["schema"],
                                    description=target.get("description", ""),
                                    relevance=0.7  # Relevancia media para entidades relacionadas
                                )
                                state.add_entity(target_entity)
                
                # Si hay múltiples entidades, buscar caminos entre ellas
                options = state.processing_info.get("options", {})
                exploration_depth = options.get("exploration_depth", 3)
                include_paths = options.get("include_paths", True)
                
                if len(state.graph_context.entities) > 1 and include_paths:
                    # Tomar las entidades más relevantes (hasta 3)
                    sorted_entities = sorted(
                        state.graph_context.entities, 
                        key=lambda e: e.relevance, 
                        reverse=True
                    )[:3]
                    
                    # Buscar caminos entre cada par de entidades
                    for i in range(len(sorted_entities)):
                        for j in range(i+1, len(sorted_entities)):
                            source = sorted_entities[i]
                            target = sorted_entities[j]
                            
                            # Buscar camino entre source y target
                            path_result = await session.run("""
                            MATCH (source:Table), (target:Table)
                            WHERE source.table_id CONTAINS $connection_id 
                            AND target.table_id CONTAINS $connection_id
                            AND source.name = $source_name 
                            AND target.name = $target_name
                            AND source <> target
                            CALL apoc.path.expandConfig(source, {
                                relationshipFilter: "RELATES_TO",
                                minLevel: 1,
                                maxLevel: $max_depth,
                                terminatorNodes: [target],
                                uniqueness: "NODE_PATH"
                            })
                            YIELD path
                            RETURN [node IN nodes(path) | node.name] AS nodes,
                                   length(path) AS length
                            ORDER BY length ASC
                            LIMIT 1
                            """, 
                            connection_id=state.connection_id,
                            source_name=source.name,
                            target_name=target.name,
                            max_depth=exploration_depth)
                            
                            paths = await path_result.data()
                            
                            # Añadir camino al contexto si existe
                            if paths:
                                path = paths[0]
                                state.graph_context.paths.append({
                                    "source": source.name,
                                    "target": target.name,
                                    "path": path["nodes"],
                                    "length": path["length"]
                                })
                
                # Para consultas de análisis o si se solicitan comunidades explícitamente
                if (state.graph_context.query_type == "analysis" or include_communities):
                    community_result = await session.run("""
                    MATCH (t:Table)
                    WHERE t.table_id CONTAINS $connection_id AND EXISTS(t.community)
                    WITH t.community AS community_id, collect(t.name) AS tables
                    RETURN community_id, tables
                    ORDER BY size(tables) DESC
                    LIMIT 5
                    """, connection_id=state.connection_id)
                    
                    communities = await community_result.data()
                    
                    # Añadir resúmenes de comunidades al contexto
                    for comm in communities:
                        comm_id = str(comm["community_id"])
                        tables = comm["tables"]
                        summary = f"Grupo {comm_id}: {', '.join(tables[:5])}"
                        if len(tables) > 5:
                            summary += f" y {len(tables) - 5} tablas más"
                        state.graph_context.community_summaries[comm_id] = summary
                
                # Actualizar información de procesamiento
                state.processing_info["graph_exploration"] = {
                    "relations_found": len(state.graph_context.relations),
                    "paths_found": len(state.graph_context.paths),
                    "communities_found": len(state.graph_context.community_summaries),
                    "entities_total": len(state.graph_context.entities),
                    "duration_ms": int((time.time() - start_time) * 1000)
                }
                
        except Exception as e:
            logger.error(f"Error in graph exploration: {e}")
            state.processing_info["graph_exploration_error"] = str(e)
            
        return state
    
    def should_generate_subqueries(self, state: GraphRAGState) -> bool:
        """
        Decidir si generar subconsultas basadas en el grafo
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            True si se deben generar subconsultas, False en caso contrario
        """
        # Si es una consulta de exploración o análisis con suficientes elementos, generar subconsultas
        if state.graph_context.query_type in ["exploration", "analysis"]:
            # Si hay suficientes entidades y relaciones
            if len(state.graph_context.entities) >= 2 and len(state.graph_context.relations) >= 1:
                return True
                
        # Si hay caminos entre entidades, generar subconsultas para explorarlos
        if len(state.graph_context.paths) > 0:
            return True
            
        # Por defecto, no generar subconsultas
        return False
    
    async def subquery_generation_node(self, state: GraphRAGState) -> GraphRAGState:
        """
        Generar subconsultas basadas en el grafo para expandir el contexto
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            Estado actualizado
        """
        start_time = time.time()
        
        try:
            # Prompt para generar subconsultas
            system_prompt = """
            Tu tarea es generar subconsultas basadas en el grafo de conocimiento para explorar más a fondo.
            Utilizando la información del esquema de la base de datos y las entidades relacionadas,
            genera 2-3 preguntas específicas que ayuden a comprender mejor la estructura y relaciones.
            
            Responde directamente con las subconsultas, una por línea. Asegúrate de que sean:
            1. Específicas sobre tablas concretas
            2. Orientadas a descubrir información sobre estructura o relaciones
            3. Relevantes para la consulta original
            """
            
            # Construir contexto para el LLM
            context = f"Consulta original: {state.query}\n\n"
            
            # Añadir entidades identificadas
            if state.graph_context.entities:
                context += "Entidades principales:\n"
                for entity in sorted(state.graph_context.entities, key=lambda e: e.relevance, reverse=True)[:5]:
                    context += f"- {entity.name} (schema: {entity.schema or 'public'})"
                    if entity.description:
                        context += f": {entity.description}"
                    context += "\n"
            
            # Añadir relaciones
            if state.graph_context.relations:
                context += "\nRelaciones:\n"
                for relation in state.graph_context.relations[:5]:
                    via = f" (vía {relation.via_column})" if relation.via_column else ""
                    context += f"- {relation.source} → {relation.target}{via}\n"
            
            # Añadir caminos
            if state.graph_context.paths:
                context += "\nCaminos entre tablas:\n"
                for path in state.graph_context.paths:
                    context += f"- {path['source']} → {' → '.join(path['path'][1:-1])} → {path['target']}\n"
            
            # Generar subconsultas
            prompt = f"""
            Genera 2-3 subconsultas basadas en la siguiente información de la base de datos:
            
            {context}
            
            Ejemplos de subconsultas útiles:
            - "¿Cuáles son las columnas clave de la tabla X?"
            - "¿Qué información contiene la tabla Y y cómo se relaciona con Z?"
            - "¿Cómo está estructurada la relación entre A y B?"
            """
            
            response = await self.llm_service.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                provider_id=state.llm_provider_id,
                max_tokens=300,
                temperature=0.3
            )
            
            # Procesar subconsultas
            subqueries_text = response.get("text", "").strip()
            subqueries_list = [sq.strip() for sq in subqueries_text.split("\n") if sq.strip()]
            
            # Añadir subconsultas al estado
            for idx, sq_text in enumerate(subqueries_list[:3]):  # Limitar a 3 máximo
                # Identificar entidad principal en la subconsulta
                focus_entity = None
                for entity in state.graph_context.entities:
                    if entity.name.lower() in sq_text.lower():
                        focus_entity = entity.name
                        break
                
                # Crear subconsulta
                subquery = Subquery(
                    text=sq_text,
                    focus_entity=focus_entity,
                    processed=False
                )
                state.add_subquery(subquery)
            
            # Procesar cada subconsulta para obtener su resultado
            for i, subquery in enumerate(state.graph_context.subqueries):
                if subquery.processed:
                    continue
                    
                # Ejecutar subconsulta
                result = await self._execute_subquery(subquery.text, state.connection_id, state.llm_provider_id)
                
                # Actualizar subconsulta con resultado
                state.graph_context.subqueries[i].result = result
                state.graph_context.subqueries[i].processed = True
            
            # Actualizar información de procesamiento
            state.processing_info["subquery_generation"] = {
                "subqueries_generated": len(state.graph_context.subqueries),
                "subqueries": [sq.text for sq in state.graph_context.subqueries],
                "duration_ms": int((time.time() - start_time) * 1000)
            }
            
        except Exception as e:
            logger.error(f"Error in subquery generation: {e}")
            state.processing_info["subquery_generation_error"] = str(e)
            
        return state
    
    async def context_aggregation_node(self, state: GraphRAGState) -> GraphRAGState:
        """
        Agregar todo el contexto (vectorial + grafo) para la respuesta final
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            Estado actualizado
        """
        start_time = time.time()
        
        try:
            # Construir contexto completo combinando información vectorial y de grafo
            context_blocks = []
            
            # 1. Añadir resultados de búsqueda vectorial
            if state.original_documents:
                vector_context = self.retrieval_service.format_documents_for_context(state.original_documents)
                context_blocks.append("## Información General")
                context_blocks.append(vector_context)
            
            # 2. Añadir información de entidades del grafo
            if state.graph_context.entities:
                context_blocks.append("## Tablas Relevantes")
                for entity in sorted(state.graph_context.entities, key=lambda e: e.relevance, reverse=True)[:5]:
                    context_blocks.append(f"### {entity.name}")
                    if entity.schema:
                        context_blocks.append(f"Schema: {entity.schema}")
                    if entity.description:
                        context_blocks.append(f"Descripción: {entity.description}")
                    
                    # Añadir relaciones de esta entidad
                    entity_relations = [r for r in state.graph_context.relations 
                                     if r.source == entity.name or r.target == entity.name]
                    
                    if entity_relations:
                        context_blocks.append("\nRelaciones:")
                        for relation in entity_relations:
                            via = f" (vía {relation.via_column})" if relation.via_column else ""
                            if relation.source == entity.name:
                                context_blocks.append(f"- → {relation.target}{via}")
                            else:
                                context_blocks.append(f"- ← {relation.source}{via}")
                    
                    context_blocks.append("")  # Línea en blanco para separar
            
            # 3. Añadir información de caminos
            if state.graph_context.paths:
                context_blocks.append("## Conexiones entre Tablas")
                for path in state.graph_context.paths:
                    context_blocks.append(f"- {path['source']} → {' → '.join(path['path'][1:-1])} → {path['target']}")
                context_blocks.append("")
            
            # 4. Añadir resultados de subconsultas
            if state.graph_context.subqueries:
                context_blocks.append("## Información Adicional")
                for subquery in state.graph_context.subqueries:
                    if subquery.result:
                        context_blocks.append(f"### {subquery.text}")
                        context_blocks.append(subquery.result)
                        context_blocks.append("")
            
            # 5. Añadir información de comunidades (para consultas de análisis)
            if state.graph_context.query_type == "analysis" and state.graph_context.community_summaries:
                context_blocks.append("## Grupos de Tablas Relacionadas")
                for comm_id, summary in state.graph_context.community_summaries.items():
                    context_blocks.append(f"- {summary}")
                context_blocks.append("")
            
            # Unir todo el contexto
            combined_context = "\n".join(context_blocks)
            
            # Formatear fuentes para la respuesta
            state.sources = self.retrieval_service.format_sources(state.original_documents)
            
            # Formatear prompt final con el contexto
            prompt = self.settings.rag_prompt_template.format(
                query=state.query,
                context=combined_context
            )
            
            # Guardar el prompt para el siguiente paso
            state.processing_info["final_prompt"] = prompt
            
            # Actualizar información de procesamiento
            state.processing_info["context_aggregation"] = {
                "context_blocks": len(context_blocks),
                "context_length": len(combined_context),
                "sources_count": len(state.sources),
                "duration_ms": int((time.time() - start_time) * 1000)
            }
            
        except Exception as e:
            logger.error(f"Error in context aggregation: {e}")
            state.processing_info["context_aggregation_error"] = str(e)
            
            # En caso de error, usar al menos el contexto vectorial básico
            if state.original_documents:
                vector_context = self.retrieval_service.format_documents_for_context(state.original_documents)
                prompt = self.settings.rag_prompt_template.format(
                    query=state.query,
                    context=vector_context
                )
                state.processing_info["final_prompt"] = prompt
                state.sources = self.retrieval_service.format_sources(state.original_documents)
            
        return state
    
    async def response_generation_node(self, state: GraphRAGState) -> GraphRAGState:
        """
        Generar la respuesta final con el LLM
        
        Args:
            state: Estado actual del grafo
            
        Returns:
            Estado actualizado con la respuesta
        """
        start_time = time.time()
        
        try:
            # Obtener el prompt final
            prompt = state.processing_info.get("final_prompt", "")
            if not prompt:
                # Reconstruir prompt básico si algo falló
                context = "No se encontró información relevante."
                if state.original_documents:
                    context = self.retrieval_service.format_documents_for_context(state.original_documents)
                
                prompt = self.settings.rag_prompt_template.format(
                    query=state.query,
                    context=context
                )
            
            # Determinar system prompt
            system_prompt = """
            Eres un asistente especializado en bases de datos que ayuda a entender y explicar
            estructuras de bases de datos, tablas, relaciones y esquemas.
            
            Basa tus respuestas únicamente en la información proporcionada en el contexto.
            Proporciona explicaciones claras y concisas sobre la estructura de la base de datos.
            Si se mencionan relaciones entre tablas, explícalas con detalle.
            
            Si la información en el contexto no es suficiente para responder completamente,
            menciona qué información falta en lugar de inventar detalles.
            """
            
            # Generar respuesta con el LLM
            response = await self.llm_service.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                provider_id=state.llm_provider_id,
                max_tokens=800,
                temperature=0.3
            )
            
            # Guardar respuesta en el estado
            state.response = response.get("text", "")
            
            # Actualizar información de procesamiento
            state.processing_info["response_generation"] = {
                "model_used": response.get("model", ""),
                "provider": response.get("provider_name", ""),
                "response_length": len(state.response),
                "duration_ms": int((time.time() - start_time) * 1000)
            }
            
            # Registrar en historial para future learning (si hay connection_id)
            if state.connection_id:
                await self._save_to_history(
                    query=state.query,
                    response=state.response,
                    connection_id=state.connection_id,
                    user_id=state.user_id,
                    processing_info=state.processing_info,
                    query_type=state.graph_context.query_type
                )
            
        except Exception as e:
            logger.error(f"Error in response generation: {e}")
            state.processing_info["response_generation_error"] = str(e)
            state.response = "Lo siento, no pude generar una respuesta detallada. Por favor, intenta reformular tu pregunta."
            
        return state
    
    # Métodos auxiliares
    
    async def _execute_subquery(self, query: str, connection_id: Optional[str], provider_id: Optional[str]) -> str:
        """
        Ejecutar una subconsulta contra Neo4j o con el LLM según corresponda
        
        Args:
            query: Consulta a ejecutar
            connection_id: ID de la conexión
            provider_id: ID del proveedor LLM
            
        Returns:
            Resultado de la subconsulta
        """
        if not connection_id or self.driver is None:
            # Si no hay conexión a Neo4j, responder con el LLM
            system_prompt = """
            Eres un asistente especializado en bases de datos. 
            Responde la pregunta de forma concisa y directa, en 2-3 frases como máximo.
            Si no tienes suficiente información para responder con precisión, indícalo claramente.
            """
            
            response = await self.llm_service.generate_text(
                prompt=query,
                system_prompt=system_prompt,
                provider_id=provider_id,
                max_tokens=150,
                temperature=0.3
            )
            
            return response.get("text", "")
        
        # Determinar si la subconsulta es sobre estructura o contenido
        is_schema_query = any(kw in query.lower() for kw in [
            "columna", "tabla", "esquema", "relación", "clave", "estructura", 
            "column", "table", "schema", "relation", "key", "structure"
        ])
        
        try:
            if is_schema_query:
                # Para consultas sobre estructura, intentar responder desde Neo4j
                # Prompt para generar Cypher
                system_prompt = """
                Eres un experto en traducir preguntas sobre bases de datos a consultas Cypher para Neo4j.
                La base de datos tiene nodos :Database, :Table y :Column con relaciones :CONTAINS, :HAS_COLUMN y :RELATES_TO.
                
                Genera SOLO la consulta Cypher, sin explicaciones ni comentarios adicionales.
                Incluye siempre la condición "connection_id = $connection_id" en las consultas.
                
                Por ejemplo, para "¿Qué tablas están relacionadas con la tabla users?", responderías:
                MATCH (t:Table)-[:RELATES_TO]-(related:Table) 
                WHERE t.table_id CONTAINS $connection_id AND t.name = 'users' 
                RETURN related.name AS related_table, related.description AS description
                """
                
                # Generar consulta Cypher
                cypher_response = await self.llm_service.generate_text(
                    prompt=f"Genera una consulta Cypher para responder: {query}",
                    system_prompt=system_prompt,
                    provider_id=provider_id,
                    max_tokens=300,
                    temperature=0.2
                )
                
                cypher_query = cypher_response.get("text", "").strip()
                
                # Ejecutar consulta Cypher
                try:
                    async with self.driver.session() as session:
                        result = await session.run(cypher_query, connection_id=connection_id)
                        data = await result.data()
                        
                        if data:
                            # Formatear resultados como texto
                            result_text = self._format_cypher_results(data)
                            
                            # Generar respuesta en lenguaje natural
                            answer_prompt = f"""
                            La pregunta es: {query}
                            
                            Resultados de la base de datos:
                            {result_text}
                            
                            Proporciona una respuesta concisa que explique estos resultados.
                            """
                            
                            answer_system_prompt = """
                            Eres un asistente especializado en bases de datos que explica resultados de consultas.
                            Proporciona una respuesta concisa (2-4 frases) que explique los resultados de forma clara.
                            No es necesario mencionar todos los detalles, enfócate en lo más relevante para la pregunta.
                            """
                            
                            answer_response = await self.llm_service.generate_text(
                                prompt=answer_prompt,
                                system_prompt=answer_system_prompt,
                                provider_id=provider_id,
                                max_tokens=150,
                                temperature=0.3
                            )
                            
                            return answer_response.get("text", "")
                        else:
                            return "No se encontró información relevante para esta consulta en la base de datos."
                            
                except Exception as e:
                    logger.error(f"Error executing Cypher query: {e}\nQuery: {cypher_query}")
                    # Fallback al LLM
            
            # Para consultas que no son sobre estructura o si falló la ejecución de Cypher,
            # responder con el LLM
            system_prompt = """
            Eres un asistente especializado en bases de datos. 
            Responde la pregunta de forma concisa y directa, en 2-3 frases como máximo.
            Si no tienes suficiente información para responder con precisión, indícalo claramente.
            """
            
            response = await self.llm_service.generate_text(
                prompt=query,
                system_prompt=system_prompt,
                provider_id=provider_id,
                max_tokens=150,
                temperature=0.3
            )
            
            return response.get("text", "")
            
        except Exception as e:
            logger.error(f"Error executing subquery: {e}")
            return "No se pudo obtener información para esta subconsulta."
    
    def _format_cypher_results(self, data: List[Dict[str, Any]]) -> str:
        """
        Formatear resultados de Cypher como texto
        
        Args:
            data: Resultados de la consulta
            
        Returns:
            Texto formateado
        """
        if not data:
            return "No se encontraron resultados."
            
        # Obtener encabezados
        headers = list(data[0].keys())
        
        # Construir tabla
        lines = []
        
        # Añadir encabezados
        lines.append(" | ".join(headers))
        lines.append("-" * (sum(len(h) for h in headers) + 3 * (len(headers) - 1)))
        
        # Añadir filas
        for row in data[:10]:  # Limitar a 10 filas
            row_values = []
            for header in headers:
                value = row.get(header, "")
                # Formatear según el tipo
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                elif value is None:
                    value = ""
                row_values.append(str(value))
            lines.append(" | ".join(row_values))
        
        # Indicar si hay más filas
        if len(data) > 10:
            lines.append(f"... y {len(data) - 10} filas más")
            
        return "\n".join(lines)
    
    async def _save_to_history(self, 
                             query: str, 
                             response: str, 
                             connection_id: str,
                             user_id: Optional[str] = None,
                             processing_info: Optional[Dict[str, Any]] = None,
                             query_type: str = "direct") -> None:
        """
        Guardar consulta y respuesta en el historial
        
        Args:
            query: Consulta del usuario
            response: Respuesta generada
            connection_id: ID de la conexión
            user_id: ID del usuario (opcional)
            processing_info: Información de procesamiento (opcional)
            query_type: Tipo de consulta
        """
        try:
            history_item = {
                "query": query,
                "response": response,
                "connection_id": connection_id,
                "user_id": user_id,
                "query_type": query_type,
                "timestamp": datetime.utcnow(),
                "processing_info": processing_info
            }
            
            await self.history_collection.insert_one(history_item)
            
        except Exception as e:
            logger.error(f"Error saving to history: {e}")
    
    async def process_query_with_graph(self, 
                                     query: str,
                                     connection_id: Optional[str] = None,
                                     user_id: Optional[str] = None,
                                     area_id: Optional[str] = None,
                                     llm_provider_id: Optional[str] = None,
                                     max_sources: int = 5,
                                     temperature: Optional[float] = None,
                                     max_tokens: Optional[int] = None,
                                     options: Optional[Dict[str, Any]] = None) -> QueryResponse:
        """
        Procesar una consulta utilizando GraphRAG
        
        Args:
            query: Consulta del usuario
            connection_id: ID de la conexión (opcional)
            user_id: ID del usuario (opcional)
            area_id: ID del área (opcional)
            llm_provider_id: ID del proveedor LLM (opcional)
            max_sources: Número máximo de fuentes a incluir
            temperature: Temperatura para generación
            max_tokens: Número máximo de tokens
            
        Returns:
            Respuesta a la consulta
        """
        # Generar ID único para la consulta
        query_id = f"graph-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{hash(query) % 10000}"
        
        # Tiempo de inicio para medición
        start_time = datetime.now()
        
        # Inicializar estado
        initial_state = GraphRAGState(
            query=query,
            connection_id=connection_id,
            user_id=user_id,
            area_id=area_id,
            llm_provider_id=llm_provider_id
        )
        
        # Añadir opciones avanzadas si se proporcionan
        if options:
            initial_state.processing_info["options"] = options
        
        # Ejecutar el grafo
        try:
            final_state = await self.graph_app.ainvoke(initial_state)
            
            # Tiempo de procesamiento
            processing_time = (datetime.now() - start_time).total_seconds()
            processing_time_ms = int(processing_time * 1000)
            
            # Obtener información del proveedor LLM
            llm_info = final_state.processing_info.get("response_generation", {})
            
            # Crear respuesta
            response = QueryResponse(
                query=query,
                answer=final_state.response,
                sources=final_state.sources,
                llm_provider=llm_info.get("provider", "unknown"),
                model=llm_info.get("model_used", "unknown"),
                processing_time_ms=processing_time_ms,
                query_id=query_id,
                timestamp=datetime.utcnow()
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error in GraphRAG processing: {e}")
            
            # Fallback a consulta RAG tradicional
            fallback_response = await self._fallback_query(
                query=query,
                user_id=user_id,
                area_id=area_id,
                llm_provider_id=llm_provider_id,
                max_sources=max_sources,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return fallback_response
    
    async def _fallback_query(self,
                            query: str,
                            user_id: Optional[str] = None,
                            area_id: Optional[str] = None,
                            llm_provider_id: Optional[str] = None,
                            max_sources: int = 5,
                            temperature: Optional[float] = None,
                            max_tokens: Optional[int] = None) -> QueryResponse:
        """
        Ejecutar consulta RAG tradicional como fallback
        
        Args:
            query: Consulta del usuario
            user_id: ID del usuario (opcional)
            area_id: ID del área (opcional)
            llm_provider_id: ID del proveedor LLM (opcional)
            max_sources: Número máximo de fuentes
            temperature: Temperatura para generación
            max_tokens: Número máximo de tokens
            
        Returns:
            Respuesta a la consulta
        """
        # Generar ID único para la consulta
        query_id = f"fallback-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{hash(query) % 10000}"
        
        # Tiempo de inicio para medición
        start_time = datetime.now()
        
        try:
            # Recuperar documentos relevantes
            documents = []
            
            # Si hay un área específica
            if area_id:
                area_docs = await self.retrieval_service.retrieve_documents(
                    query=query,
                    embedding_type=EmbeddingType.GENERAL,
                    area_id=area_id,
                    limit=max_sources
                )
                documents.extend(area_docs)
            else:
                # Búsqueda general
                general_docs = await self.retrieval_service.retrieve_documents(
                    query=query,
                    embedding_type=EmbeddingType.GENERAL,
                    limit=max_sources
                )
                documents.extend(general_docs)
            
            # Si hay un usuario, añadir documentos personales
            if user_id:
                personal_docs = await self.retrieval_service.retrieve_documents(
                    query=query,
                    embedding_type=EmbeddingType.PERSONAL,
                    owner_id=user_id,
                    limit=max_sources
                )
                documents.extend(personal_docs)
            
            # Formatear documentos para el contexto
            context = self.retrieval_service.format_documents_for_context(documents)
            
            # Formatear prompt
            prompt = self.settings.rag_prompt_template.format(
                query=query,
                context=context
            )
            
            # Generar respuesta con LLM
            llm_response = await self.llm_service.generate_text(
                prompt=prompt,
                system_prompt=self.settings.mcp.default_system_prompt,
                provider_id=llm_provider_id,
                max_tokens=max_tokens or 800,
                temperature=temperature or 0.3
            )
            
            # Formatear fuentes
            sources = self.retrieval_service.format_sources(documents)
            
            # Tiempo de procesamiento
            processing_time = (datetime.now() - start_time).total_seconds()
            processing_time_ms = int(processing_time * 1000)
            
            # Crear respuesta
            response = QueryResponse(
                query=query,
                answer=llm_response.get("text", ""),
                sources=sources,
                llm_provider=llm_response.get("provider_name", "unknown"),
                model=llm_response.get("model", "unknown"),
                processing_time_ms=processing_time_ms,
                query_id=query_id,
                timestamp=datetime.utcnow()
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error in fallback query: {e}")
            
            # Respuesta de error
            return QueryResponse(
                query=query,
                answer=f"Lo siento, no pude procesar tu consulta debido a un error interno. Por favor, intenta de nuevo más tarde.",
                sources=[],
                llm_provider="error",
                model="error",
                processing_time_ms=0,
                query_id=query_id,
                timestamp=datetime.utcnow()
            )
    
    async def close(self):
        """Cerrar conexiones y recursos"""
        if self._driver is not None:
            try:
                await self._driver.close()
                logger.info("Neo4j driver closed")
            except Exception as e:
                logger.error(f"Error closing Neo4j driver: {e}")
            finally:
                self._driver = None