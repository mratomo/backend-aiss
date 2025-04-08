import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from functools import lru_cache

from neo4j import GraphDatabase, Session, Driver
from neo4j.exceptions import ServiceUnavailable

from config.settings import Settings
from models.models import DatabaseSchema, TableSchema, ColumnSchema

logger = logging.getLogger(__name__)

class GraphExtractionService:
    """
    Servicio para construir y gestionar grafos de conocimiento sobre esquemas de bases de datos.
    Utiliza Neo4j para representar la estructura y relaciones entre tablas y columnas.
    """

    def __init__(self, settings: Settings):
        """
        Inicializar servicio con conexión a Neo4j
        
        Args:
            settings: Configuración global
        """
        self.settings = settings
        
        # Inicializar conexión a Neo4j (lazy loading)
        self._driver = None
        self._init_driver()
        
    def _init_driver(self) -> None:
        """Inicializar driver de Neo4j de forma segura"""
        try:
            uri = self.settings.neo4j_uri
            username = self.settings.neo4j_username
            password = self.settings.neo4j_password
            
            if not uri or not username or not password:
                logger.warning("Neo4j configuration incomplete, Graph functionality will be limited")
                return
                
            self._driver = GraphDatabase.driver(uri, auth=(username, password))
            
            # Verificar la conexión
            with self._driver.session() as session:
                result = session.run("RETURN 'Neo4j connection successful' AS message")
                message = result.single()["message"]
                logger.info(f"Neo4j connection: {message}")
                
        except ServiceUnavailable as e:
            logger.error(f"Neo4j connection failed: {e}")
            self._driver = None
        except Exception as e:
            logger.error(f"Error initializing Neo4j driver: {e}")
            self._driver = None
    
    @property
    def driver(self) -> Optional[Driver]:
        """Obtener driver de Neo4j, reintentar conexión si es necesario"""
        if self._driver is None:
            self._init_driver()
        return self._driver
    
    def extract_schema_graph(self, schema: DatabaseSchema) -> Dict[str, Any]:
        """
        Extraer y almacenar un grafo de conocimiento en Neo4j basado en un esquema de base de datos
        
        Args:
            schema: Esquema de la base de datos
            
        Returns:
            Diccionario con información del grafo generado
        """
        if self.driver is None:
            logger.warning("Neo4j driver not available, returning empty graph")
            return {"nodes": [], "edges": [], "metadata": {"error": "Neo4j connection not available"}}
        
        start_time = time.time()
        connection_id = schema.connection_id
        
        # Crear índices y restricciones si no existen
        self._ensure_constraints()
        
        # Crear nodo de base de datos
        self._create_database_node(schema)
        
        # Crear nodos de tablas
        tables_count = self._create_table_nodes(schema)
        
        # Crear nodos de columnas
        columns_count = self._create_column_nodes(schema)
        
        # Crear relaciones
        relationships_count = self._create_relationships(schema)
        
        # Calcular comunidades 
        communities = self._calculate_communities(schema)
        
        # Estadísticas del grafo
        graph_stats = self._get_graph_stats(connection_id)
        
        # Tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Crear resultado
        result = {
            "connection_id": connection_id,
            "db_name": schema.name,
            "db_type": schema.type,
            "nodes_count": graph_stats.get("nodes_count", 0),
            "edges_count": graph_stats.get("relationships_count", 0),
            "communities_count": len(communities),
            "processing_time_seconds": round(processing_time, 2),
            "communities": communities,
            "metadata": {
                "extraction_date": datetime.utcnow().isoformat(),
                "tables_count": tables_count,
                "columns_count": columns_count,
                "relationships_count": relationships_count
            }
        }
        
        return result
    
    def _ensure_constraints(self) -> None:
        """Crear índices y restricciones en Neo4j para mejorar el rendimiento"""
        if self.driver is None:
            return
            
        with self.driver.session() as session:
            try:
                # Verificar si las restricciones ya existen
                constraints = session.run("SHOW CONSTRAINTS").data()
                
                # Crear restricciones si no existen
                existing_names = [c.get("name", "") for c in constraints]
                
                # Restricciones para unicidad
                if "unique_database_id" not in existing_names:
                    session.run("""
                    CREATE CONSTRAINT unique_database_id IF NOT EXISTS
                    FOR (d:Database)
                    REQUIRE d.connection_id IS UNIQUE
                    """)
                
                if "unique_table_id" not in existing_names:
                    session.run("""
                    CREATE CONSTRAINT unique_table_id IF NOT EXISTS
                    FOR (t:Table)
                    REQUIRE t.table_id IS UNIQUE
                    """)
                    
                if "unique_column_id" not in existing_names:
                    session.run("""
                    CREATE CONSTRAINT unique_column_id IF NOT EXISTS
                    FOR (c:Column)
                    REQUIRE c.column_id IS UNIQUE
                    """)
                
                # Índices para búsqueda rápida
                indices = session.run("SHOW INDEXES").data()
                existing_indices = [idx.get("name", "") for idx in indices]
                
                if "database_name_index" not in existing_indices:
                    session.run("""
                    CREATE INDEX database_name_index IF NOT EXISTS
                    FOR (d:Database)
                    ON (d.name)
                    """)
                    
                if "table_name_index" not in existing_indices:
                    session.run("""
                    CREATE INDEX table_name_index IF NOT EXISTS
                    FOR (t:Table)
                    ON (t.name)
                    """)
                    
                if "column_name_index" not in existing_indices:
                    session.run("""
                    CREATE INDEX column_name_index IF NOT EXISTS
                    FOR (c:Column)
                    ON (c.name)
                    """)
                    
            except Exception as e:
                logger.error(f"Error creating Neo4j constraints: {e}")
    
    def _create_database_node(self, schema: DatabaseSchema) -> None:
        """
        Crear nodo de base de datos en Neo4j
        
        Args:
            schema: Esquema de la base de datos
        """
        if self.driver is None:
            return
            
        with self.driver.session() as session:
            try:
                # Combinar propiedades
                properties = {
                    "connection_id": schema.connection_id,
                    "name": schema.name,
                    "db_type": schema.type,
                    "discovery_date": schema.discovery_date.isoformat() if schema.discovery_date else datetime.utcnow().isoformat(),
                    "description": schema.description or "",
                    "version": schema.version or ""
                }
                
                # Crear o actualizar nodo de base de datos con propiedades
                session.run("""
                MERGE (db:Database {connection_id: $connection_id})
                SET db = $properties
                """, connection_id=schema.connection_id, properties=properties)
                
            except Exception as e:
                logger.error(f"Error creating database node: {e}")
    
    def _create_table_nodes(self, schema: DatabaseSchema) -> int:
        """
        Crear nodos de tablas en Neo4j
        
        Args:
            schema: Esquema de la base de datos
            
        Returns:
            Número de tablas creadas
        """
        if self.driver is None or not schema.tables:
            return 0
            
        tables_count = 0
        
        with self.driver.session() as session:
            # Usar transacción para mejorar rendimiento
            with session.begin_transaction() as tx:
                try:
                    for table in schema.tables:
                        # Crear ID único para la tabla
                        table_id = f"{schema.connection_id}:{table.schema or 'public'}:{table.name}"
                        
                        # Propiedades de la tabla
                        properties = {
                            "table_id": table_id,
                            "name": table.name,
                            "schema": table.schema or "public",
                            "description": table.description or "",
                            "rows_count": table.rows_count,
                            "is_collection": getattr(table, "is_collection", False)
                        }
                        
                        # Crear o actualizar nodo de tabla
                        tx.run("""
                        MERGE (t:Table {table_id: $table_id})
                        SET t = $properties
                        """, table_id=table_id, properties=properties)
                        
                        # Crear relación con la base de datos
                        tx.run("""
                        MATCH (db:Database {connection_id: $connection_id})
                        MATCH (t:Table {table_id: $table_id})
                        MERGE (db)-[:CONTAINS]->(t)
                        """, connection_id=schema.connection_id, table_id=table_id)
                        
                        tables_count += 1
                        
                    # Commit de la transacción
                    tx.commit()
                    
                except Exception as e:
                    logger.error(f"Error creating table nodes: {e}")
                    tx.rollback()
                    
        return tables_count
    
    def _create_column_nodes(self, schema: DatabaseSchema) -> int:
        """
        Crear nodos de columnas en Neo4j
        
        Args:
            schema: Esquema de la base de datos
            
        Returns:
            Número de columnas creadas
        """
        if self.driver is None or not schema.tables:
            return 0
            
        columns_count = 0
        
        with self.driver.session() as session:
            # Usar transacción para mejorar rendimiento
            with session.begin_transaction() as tx:
                try:
                    for table in schema.tables:
                        if not table.columns:
                            continue
                            
                        table_id = f"{schema.connection_id}:{table.schema or 'public'}:{table.name}"
                        
                        for column in table.columns:
                            # Crear ID único para la columna
                            column_id = f"{table_id}:{column.name}"
                            
                            # Propiedades de la columna
                            properties = {
                                "column_id": column_id,
                                "name": column.name,
                                "data_type": column.data_type,
                                "nullable": column.nullable,
                                "is_primary": column.is_primary,
                                "is_foreign": column.is_foreign,
                                "references": column.references or "",
                                "description": column.description or ""
                            }
                            
                            # Crear o actualizar nodo de columna
                            tx.run("""
                            MERGE (c:Column {column_id: $column_id})
                            SET c = $properties
                            """, column_id=column_id, properties=properties)
                            
                            # Crear relación con la tabla
                            tx.run("""
                            MATCH (t:Table {table_id: $table_id})
                            MATCH (c:Column {column_id: $column_id})
                            MERGE (t)-[:HAS_COLUMN]->(c)
                            """, table_id=table_id, column_id=column_id)
                            
                            columns_count += 1
                            
                    # Commit de la transacción
                    tx.commit()
                    
                except Exception as e:
                    logger.error(f"Error creating column nodes: {e}")
                    tx.rollback()
                    
        return columns_count
    
    def _create_relationships(self, schema: DatabaseSchema) -> int:
        """
        Crear relaciones entre columnas en Neo4j basadas en claves foráneas
        
        Args:
            schema: Esquema de la base de datos
            
        Returns:
            Número de relaciones creadas
        """
        if self.driver is None or not schema.tables:
            return 0
            
        relationships_count = 0
        
        with self.driver.session() as session:
            # Usar transacción para mejorar rendimiento
            with session.begin_transaction() as tx:
                try:
                    for table in schema.tables:
                        if not table.columns:
                            continue
                            
                        table_schema = table.schema or "public"
                        table_id = f"{schema.connection_id}:{table_schema}:{table.name}"
                        
                        for column in table.columns:
                            if not column.is_foreign or not column.references:
                                continue
                                
                            column_id = f"{table_id}:{column.name}"
                            
                            # Parsear la referencia (formato: schema.table.column)
                            ref_parts = column.references.split(".")
                            if len(ref_parts) < 2:
                                continue  # Referencia inválida
                                
                            # Determinar esquema, tabla y columna referenciada
                            if len(ref_parts) >= 3:
                                ref_schema, ref_table, ref_column = ref_parts
                            else:
                                ref_schema = table_schema
                                ref_table, ref_column = ref_parts
                                
                            ref_table_id = f"{schema.connection_id}:{ref_schema}:{ref_table}"
                            ref_column_id = f"{ref_table_id}:{ref_column}"
                            
                            # Crear relación entre columnas
                            tx.run("""
                            MATCH (source:Column {column_id: $source_id})
                            MATCH (target:Column {column_id: $target_id})
                            MERGE (source)-[:REFERENCES]->(target)
                            """, source_id=column_id, target_id=ref_column_id)
                            
                            # Crear relación directa entre tablas (para facilitar navegación)
                            tx.run("""
                            MATCH (source:Table {table_id: $source_id})
                            MATCH (target:Table {table_id: $target_id})
                            MERGE (source)-[r:RELATES_TO]->(target)
                            ON CREATE SET r.via_column = $via_column, r.to_column = $to_column
                            ON MATCH SET r.via_column = r.via_column + ', ' + $via_column,
                                        r.to_column = r.to_column + ', ' + $to_column
                            """, 
                            source_id=table_id, 
                            target_id=ref_table_id,
                            via_column=column.name,
                            to_column=ref_column)
                            
                            relationships_count += 1
                            
                    # Commit de la transacción
                    tx.commit()
                    
                except Exception as e:
                    logger.error(f"Error creating relationships: {e}")
                    tx.rollback()
                    
        return relationships_count
    
    def _calculate_communities(self, schema: DatabaseSchema) -> List[Dict[str, Any]]:
        """
        Detectar comunidades en el grafo utilizando algoritmos de Neo4j Graph Data Science
        
        Args:
            schema: Esquema de la base de datos
            
        Returns:
            Lista de comunidades detectadas
        """
        if self.driver is None:
            return []
            
        communities = []
        
        try:
            with self.driver.session() as session:
                # Verificar si GDS está disponible
                gds_check = session.run("CALL gds.list() YIELD name RETURN count(*) AS count").single()
                if not gds_check or gds_check["count"] == 0:
                    logger.warning("Neo4j Graph Data Science library not available, skipping community detection")
                    
                    # Fallback: agrupar por esquema (más simple pero menos preciso)
                    communities = self._group_by_schema(schema)
                    return communities
                
                # Proyecto de grafo para GDS
                session.run("""
                CALL gds.graph.project.cypher(
                    'schema_graph',
                    'MATCH (t:Table) WHERE t.table_id CONTAINS $connection_id RETURN id(t) AS id, t.name AS name, t.schema AS schema, t.description AS description, labels(t) AS labels',
                    'MATCH (t1:Table)-[:RELATES_TO]->(t2:Table) WHERE t1.table_id CONTAINS $connection_id AND t2.table_id CONTAINS $connection_id RETURN id(t1) AS source, id(t2) AS target',
                    {validateRelationships: false}
                )
                """, connection_id=schema.connection_id)
                
                # Ejecutar algoritmo de detección de comunidades (Louvain)
                session.run("""
                CALL gds.louvain.write('schema_graph', {
                    writeProperty: 'community',
                    relationshipWeightProperty: null,
                    includeIntermediateCommunities: false
                })
                """)
                
                # Obtener comunidades y sus miembros
                community_results = session.run("""
                MATCH (t:Table)
                WHERE t.table_id CONTAINS $connection_id AND EXISTS(t.community)
                RETURN t.community AS community_id, collect({id: t.table_id, name: t.name, schema: t.schema}) AS members
                ORDER BY community_id
                """, connection_id=schema.connection_id).data()
                
                # Formatear comunidades
                for idx, group in enumerate(community_results):
                    members = group["members"]
                    if not members:
                        continue
                        
                    # Identificar esquema predominante
                    schemas = {}
                    for member in members:
                        schema_name = member.get("schema", "unknown")
                        schemas[schema_name] = schemas.get(schema_name, 0) + 1
                    
                    predominant_schema = max(schemas.items(), key=lambda x: x[1])[0] if schemas else "unknown"
                    
                    # Formatear comunidad
                    community = {
                        "id": f"community_{idx}",
                        "name": f"Group: {predominant_schema}",
                        "tables_count": len(members),
                        "tables": [m.get("name") for m in members],
                        "description": f"Tables related in schema {predominant_schema}"
                    }
                    
                    communities.append(community)
                
                # Limpieza: eliminar proyecto de grafo
                session.run("CALL gds.graph.drop('schema_graph')")
                
        except Exception as e:
            logger.error(f"Error calculating communities: {e}")
            # Fallback: agrupar por esquema
            communities = self._group_by_schema(schema)
            
        return communities
    
    def _group_by_schema(self, schema: DatabaseSchema) -> List[Dict[str, Any]]:
        """
        Agrupar tablas por esquema como fallback simple para detección de comunidades
        
        Args:
            schema: Esquema de la base de datos
            
        Returns:
            Lista de comunidades (agrupadas por esquema)
        """
        if not schema.tables:
            return []
            
        # Agrupar tablas por esquema
        schemas = {}
        for table in schema.tables:
            schema_name = table.schema or "public"
            if schema_name not in schemas:
                schemas[schema_name] = []
            schemas[schema_name].append(table.name)
        
        # Formatear comunidades
        communities = []
        for idx, (schema_name, tables) in enumerate(schemas.items()):
            community = {
                "id": f"schema_{idx}",
                "name": f"Schema: {schema_name}",
                "tables_count": len(tables),
                "tables": tables,
                "description": f"Tables in schema {schema_name}"
            }
            communities.append(community)
            
        return communities
    
    def _get_graph_stats(self, connection_id: str) -> Dict[str, int]:
        """
        Obtener estadísticas del grafo para una conexión
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            Diccionario con estadísticas
        """
        if self.driver is None:
            return {"nodes_count": 0, "relationships_count": 0}
            
        stats = {"nodes_count": 0, "relationships_count": 0}
        
        with self.driver.session() as session:
            try:
                # Contar nodos
                nodes_result = session.run("""
                MATCH (n)
                WHERE (n:Database AND n.connection_id = $connection_id) OR 
                      (n:Table AND n.table_id CONTAINS $connection_id) OR
                      (n:Column AND n.column_id CONTAINS $connection_id)
                RETURN count(n) AS nodes_count
                """, connection_id=connection_id).single()
                
                if nodes_result:
                    stats["nodes_count"] = nodes_result["nodes_count"]
                
                # Contar relaciones
                rels_result = session.run("""
                MATCH (n)-[r]->(m)
                WHERE (n:Database AND n.connection_id = $connection_id) OR 
                      (n:Table AND n.table_id CONTAINS $connection_id) OR
                      (n:Column AND n.column_id CONTAINS $connection_id)
                RETURN count(r) AS relationships_count
                """, connection_id=connection_id).single()
                
                if rels_result:
                    stats["relationships_count"] = rels_result["relationships_count"]
                
            except Exception as e:
                logger.error(f"Error getting graph stats: {e}")
                
        return stats
    
    def get_graph_description(self, connection_id: str) -> str:
        """
        Generar descripción textual del grafo para una conexión
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            Descripción textual del grafo
        """
        if self.driver is None:
            return "Neo4j connection not available, graph description unavailable."
            
        with self.driver.session() as session:
            try:
                # Obtener información de la base de datos
                db_info = session.run("""
                MATCH (db:Database {connection_id: $connection_id})
                RETURN db.name AS name, db.db_type AS type, db.version AS version, db.description AS description
                """, connection_id=connection_id).single()
                
                if not db_info:
                    return f"No database found with connection ID: {connection_id}"
                
                # Comenzar descripción
                lines = [
                    f"Database: {db_info['name']}",
                    f"Type: {db_info['type']}",
                    f"Version: {db_info.get('version', 'Unknown')}"
                ]
                
                if db_info.get('description'):
                    lines.append(f"Description: {db_info['description']}")
                
                # Obtener resumen de tablas y relaciones
                stats = session.run("""
                MATCH (db:Database {connection_id: $connection_id})-[:CONTAINS]->(t:Table)
                OPTIONAL MATCH (t)-[r:RELATES_TO]->(t2:Table)
                RETURN count(DISTINCT t) AS tables_count, count(DISTINCT r) AS relationships_count
                """, connection_id=connection_id).single()
                
                if stats:
                    lines.append(f"\nStructure Summary:")
                    lines.append(f"Tables: {stats['tables_count']}")
                    lines.append(f"Relationships: {stats['relationships_count']}")
                
                # Obtener tablas principales (top 10)
                tables = session.run("""
                MATCH (db:Database {connection_id: $connection_id})-[:CONTAINS]->(t:Table)
                OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column {is_primary: true})
                RETURN t.name AS name, t.schema AS schema, t.description AS description, 
                       count(c) AS primary_keys
                ORDER BY primary_keys DESC
                LIMIT 10
                """, connection_id=connection_id).data()
                
                if tables:
                    lines.append("\nMain Tables:")
                    for table in tables:
                        lines.append(f"\n- {table['name']} (Schema: {table.get('schema', 'public')})")
                        if table.get('description'):
                            lines.append(f"  Description: {table['description']}")
                    
                    # Señalar si hay más tablas
                    if stats and stats['tables_count'] > 10:
                        lines.append(f"\n... and {stats['tables_count'] - 10} more tables")
                
                # Añadir información de comunidades si están detectadas
                communities = session.run("""
                MATCH (t:Table)
                WHERE t.table_id CONTAINS $connection_id AND EXISTS(t.community)
                RETURN t.community AS community_id, count(*) AS tables_count
                ORDER BY tables_count DESC
                """, connection_id=connection_id).data()
                
                if communities:
                    lines.append("\nCommunities/Groups:")
                    for comm in communities:
                        lines.append(f"- Community {comm['community_id']}: {comm['tables_count']} tables")
                
                return "\n".join(lines)
                
            except Exception as e:
                logger.error(f"Error generating graph description: {e}")
                return f"Error generating graph description: {str(e)}"
    
    def find_paths(self, connection_id: str, from_table: str, to_table: str, max_depth: int = 5) -> List[Dict[str, Any]]:
        """
        Encontrar caminos en el grafo entre dos tablas
        
        Args:
            connection_id: ID de la conexión
            from_table: Nombre de la tabla de origen
            to_table: Nombre de la tabla de destino
            max_depth: Profundidad máxima de búsqueda
            
        Returns:
            Lista de caminos encontrados
        """
        if self.driver is None:
            return []
            
        paths = []
        
        with self.driver.session() as session:
            try:
                # Encontrar caminos entre tablas
                path_results = session.run("""
                MATCH (source:Table), (target:Table)
                WHERE source.table_id CONTAINS $connection_id 
                AND target.table_id CONTAINS $connection_id
                AND source.name = $from_table 
                AND target.name = $to_table
                AND source <> target
                CALL apoc.path.expandConfig(source, {
                    relationshipFilter: "RELATES_TO",
                    minLevel: 1,
                    maxLevel: $max_depth,
                    terminatorNodes: [target],
                    uniqueness: "NODE_PATH"
                })
                YIELD path
                WITH path, [node IN nodes(path) | node.name] AS table_names
                RETURN table_names,
                       [rel IN relationships(path) | {from: startNode(rel).name, to: endNode(rel).name, via: rel.via_column}] AS relationships
                LIMIT 5
                """, 
                connection_id=connection_id,
                from_table=from_table,
                to_table=to_table,
                max_depth=max_depth
                ).data()
                
                # Formatear caminos
                for idx, path in enumerate(path_results):
                    formatted_path = {
                        "id": f"path_{idx}",
                        "tables": path["table_names"],
                        "relationships": path["relationships"],
                        "length": len(path["table_names"]) - 1
                    }
                    paths.append(formatted_path)
                
            except Exception as e:
                logger.error(f"Error finding paths: {e}")
                
        return paths
    
    def find_related_tables(self, connection_id: str, table_name: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Encontrar tablas relacionadas con una tabla dada
        
        Args:
            connection_id: ID de la conexión
            table_name: Nombre de la tabla
            max_depth: Profundidad máxima de búsqueda
            
        Returns:
            Lista de tablas relacionadas con sus relaciones
        """
        if self.driver is None:
            return []
            
        related_tables = []
        
        with self.driver.session() as session:
            try:
                # Encontrar tablas relacionadas
                related_results = session.run("""
                MATCH (source:Table)
                WHERE source.table_id CONTAINS $connection_id AND source.name = $table_name
                CALL apoc.path.expandConfig(source, {
                    relationshipFilter: "RELATES_TO",
                    minLevel: 1,
                    maxLevel: $max_depth,
                    uniqueness: "NODE_GLOBAL"
                })
                YIELD path
                WITH DISTINCT last(nodes(path)) AS related_table, source
                MATCH (source)-[r:RELATES_TO*1..{max_depth}]->(related_table)
                RETURN related_table.name AS name, 
                       related_table.schema AS schema,
                       related_table.description AS description,
                       min(length(r)) AS distance,
                       collect(DISTINCT r[0].via_column) AS via_columns
                ORDER BY distance ASC
                """, 
                connection_id=connection_id,
                table_name=table_name,
                max_depth=max_depth
                ).data()
                
                # Formatear tablas relacionadas
                for rel in related_results:
                    related = {
                        "name": rel["name"],
                        "schema": rel.get("schema", "public"),
                        "description": rel.get("description", ""),
                        "distance": rel["distance"],
                        "via_columns": rel["via_columns"]
                    }
                    related_tables.append(related)
                
            except Exception as e:
                logger.error(f"Error finding related tables: {e}")
                
        return related_tables
    
    def generate_graph_summary(self, connection_id: str) -> Dict[str, Any]:
        """
        Generar resumen del grafo para una conexión para uso en RAG
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            Resumen del grafo
        """
        if self.driver is None:
            return {"error": "Neo4j connection not available"}
            
        summary = {
            "connection_id": connection_id,
            "description": "",
            "main_tables": [],
            "key_relationships": [],
            "communities": []
        }
        
        with self.driver.session() as session:
            try:
                # Obtener información básica
                db_info = session.run("""
                MATCH (db:Database {connection_id: $connection_id})
                RETURN db.name AS name, db.db_type AS type, db.version AS version, db.description AS description
                """, connection_id=connection_id).single()
                
                if not db_info:
                    return {"error": f"No database found with connection ID: {connection_id}"}
                
                summary["name"] = db_info["name"]
                summary["type"] = db_info["type"]
                summary["version"] = db_info.get("version", "Unknown")
                summary["description"] = db_info.get("description", "")
                
                # Obtener tablas principales (con más relaciones)
                main_tables = session.run("""
                MATCH (db:Database {connection_id: $connection_id})-[:CONTAINS]->(t:Table)
                OPTIONAL MATCH (t)-[r:RELATES_TO]-(other:Table)
                WITH t, count(r) AS rel_count
                RETURN t.name AS name, t.schema AS schema, t.description AS description, rel_count
                ORDER BY rel_count DESC, t.name
                LIMIT 10
                """, connection_id=connection_id).data()
                
                summary["main_tables"] = main_tables
                
                # Obtener relaciones clave (más referenciadas)
                key_relationships = session.run("""
                MATCH (t1:Table)-[r:RELATES_TO]->(t2:Table)
                WHERE t1.table_id CONTAINS $connection_id
                RETURN t1.name AS source_table, t2.name AS target_table, 
                       r.via_column AS via_column, r.to_column AS to_column
                LIMIT 15
                """, connection_id=connection_id).data()
                
                summary["key_relationships"] = key_relationships
                
                # Obtener comunidades
                communities = session.run("""
                MATCH (t:Table)
                WHERE t.table_id CONTAINS $connection_id AND EXISTS(t.community)
                WITH t.community AS community_id, collect(t.name) AS tables
                RETURN community_id, tables
                ORDER BY size(tables) DESC
                LIMIT 10
                """, connection_id=connection_id).data()
                
                summary["communities"] = communities
                
            except Exception as e:
                logger.error(f"Error generating graph summary: {e}")
                summary["error"] = str(e)
                
        return summary
    
    def close(self):
        """Cerrar conexiones a Neo4j"""
        if self._driver is not None:
            try:
                self._driver.close()
                logger.info("Neo4j driver closed")
            except Exception as e:
                logger.error(f"Error closing Neo4j driver: {e}")
            finally:
                self._driver = None