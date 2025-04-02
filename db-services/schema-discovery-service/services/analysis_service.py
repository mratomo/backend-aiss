import logging
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime

from config.settings import Settings
from models.models import (
    DatabaseSchema, SchemaInsight, SchemaQuerySuggestion, TableSchema, ColumnSchema
)

logger = logging.getLogger(__name__)

class SchemaAnalysisService:
    """Servicio para análisis de esquemas de bases de datos"""
    
    def __init__(self, settings: Settings):
        """
        Inicializar servicio de análisis
        
        Args:
            settings: Configuración global
        """
        self.settings = settings
        
    async def generate_insights(self, schema: DatabaseSchema) -> List[SchemaInsight]:
        """
        Generar insights sobre el esquema
        
        Args:
            schema: Esquema a analizar
            
        Returns:
            Lista de insights generados
        """
        insights = []
        
        # Verificar si hay tablas
        if not schema.tables:
            insights.append(SchemaInsight(
                type="warning",
                title="Esquema vacío",
                description="No se encontraron tablas en el esquema de la base de datos."
            ))
            return insights
            
        # Analizar estructura general
        tables_count = len(schema.tables)
        total_columns = sum(len(table.columns) if table.columns else 0 for table in schema.tables)
        empty_tables = [table.name for table in schema.tables if table.rows_count == 0]
        
        # Insight sobre tamaño del esquema
        insights.append(SchemaInsight(
            type="info",
            title="Tamaño del esquema",
            description=f"El esquema contiene {tables_count} tablas y {total_columns} columnas en total."
        ))
        
        # Insight sobre tablas vacías
        if empty_tables:
            empty_tables_str = ", ".join(empty_tables[:5])
            if len(empty_tables) > 5:
                empty_tables_str += f" y {len(empty_tables) - 5} más"
                
            insights.append(SchemaInsight(
                type="warning",
                title="Tablas vacías",
                description=f"Se encontraron {len(empty_tables)} tablas sin datos: {empty_tables_str}"
            ))
            
        # Analizar estructura de claves
        missing_pk_tables = []
        potential_relations = []
        
        for table in schema.tables:
            # Verificar si falta clave primaria
            has_pk = any(col.is_primary for col in table.columns) if table.columns else False
            
            if not has_pk and schema.type != "mongodb":  # MongoDB siempre tiene _id
                missing_pk_tables.append(table.name)
                
            # Detectar posibles relaciones no declaradas
            potential_rel = self._find_potential_relations(table, schema.tables)
            potential_relations.extend(potential_rel)
            
        # Insight sobre tablas sin clave primaria
        if missing_pk_tables:
            missing_pk_str = ", ".join(missing_pk_tables[:5])
            if len(missing_pk_tables) > 5:
                missing_pk_str += f" y {len(missing_pk_tables) - 5} más"
                
            insights.append(SchemaInsight(
                type="warning",
                title="Tablas sin clave primaria",
                description=f"Se encontraron {len(missing_pk_tables)} tablas sin clave primaria: {missing_pk_str}"
            ))
            
        # Insight sobre posibles relaciones no declaradas
        if potential_relations:
            rel_str = "; ".join(potential_relations[:3])
            if len(potential_relations) > 3:
                rel_str += f" y {len(potential_relations) - 3} más"
                
            insights.append(SchemaInsight(
                type="suggestion",
                title="Posibles relaciones no declaradas",
                description=f"Se detectaron posibles relaciones no declaradas: {rel_str}"
            ))
            
        # Analizar tipos de datos
        text_columns_count = 0
        large_text_columns = []
        numeric_columns_count = 0
        date_columns_count = 0
        
        for table in schema.tables:
            for column in table.columns:
                data_type = column.data_type.lower()
                
                # Contar tipos de columnas
                if any(text_type in data_type for text_type in ["char", "text", "string"]):
                    text_columns_count += 1
                    
                    # Detectar campos de texto grandes
                    if any(large_type in data_type for large_type in ["text", "blob", "clob"]):
                        large_text_columns.append(f"{table.name}.{column.name}")
                        
                elif any(num_type in data_type for num_type in ["int", "float", "double", "numeric", "decimal"]):
                    numeric_columns_count += 1
                    
                elif any(date_type in data_type for date_type in ["date", "time", "timestamp"]):
                    date_columns_count += 1
                    
        # Insight sobre distribución de tipos de datos
        insights.append(SchemaInsight(
            type="info",
            title="Distribución de tipos de datos",
            description=f"El esquema contiene {text_columns_count} columnas de texto, {numeric_columns_count} numéricas y {date_columns_count} de fecha/hora."
        ))
        
        # Insight sobre columnas de texto grandes
        if large_text_columns:
            large_text_str = ", ".join(large_text_columns[:5])
            if len(large_text_columns) > 5:
                large_text_str += f" y {len(large_text_columns) - 5} más"
                
            insights.append(SchemaInsight(
                type="performance",
                title="Columnas de texto grandes",
                description=f"Se encontraron {len(large_text_columns)} columnas de texto grande que podrían afectar el rendimiento: {large_text_str}"
            ))
            
        # Analizar índices y rendimiento
        if schema.type in ["postgresql", "mysql"]:
            non_indexed_fk_columns = []
            
            for table in schema.tables:
                for column in table.columns:
                    # Detectar claves foráneas sin índice
                    if column.is_foreign and not column.is_primary:
                        # Normalmente las FK deberían tener índice
                        non_indexed_fk_columns.append(f"{table.name}.{column.name}")
                        
            # Insight sobre claves foráneas sin índice
            if non_indexed_fk_columns:
                non_indexed_str = ", ".join(non_indexed_fk_columns[:5])
                if len(non_indexed_fk_columns) > 5:
                    non_indexed_str += f" y {len(non_indexed_fk_columns) - 5} más"
                    
                insights.append(SchemaInsight(
                    type="performance",
                    title="Claves foráneas sin índice",
                    description=f"Se detectaron claves foráneas que podrían no tener índice: {non_indexed_str}"
                ))
                
        return insights
    
    async def generate_query_suggestions(self, schema: DatabaseSchema) -> List[SchemaQuerySuggestion]:
        """
        Generar sugerencias de consultas
        
        Args:
            schema: Esquema a analizar
            
        Returns:
            Lista de sugerencias de consultas
        """
        suggestions = []
        
        # Si no hay tablas, no podemos generar sugerencias
        if not schema.tables:
            return suggestions
        
        # Generar consultas básicas basadas en el tipo de base de datos
        if schema.type in ["postgresql", "mysql"]:
            # Para tablas con más filas
            largest_tables = sorted(
                schema.tables, 
                key=lambda t: t.rows_count, 
                reverse=True
            )[:3]
            
            for table in largest_tables:
                # Selección básica
                select_cols = ", ".join([col.name for col in table.columns[:5]] if table.columns else ["*"])
                suggestions.append(SchemaQuerySuggestion(
                    title=f"Consultar datos de {table.name}",
                    description=f"Obtener registros de la tabla {table.name}",
                    sql_query=f"SELECT {select_cols} FROM {table.name} LIMIT 100;"
                ))
                
                # Conteo de registros
                suggestions.append(SchemaQuerySuggestion(
                    title=f"Contar registros en {table.name}",
                    description=f"Contar el número de registros en la tabla {table.name}",
                    sql_query=f"SELECT COUNT(*) FROM {table.name};"
                ))
                
            # Generar JOINs para tablas relacionadas
            relations = self._find_db_relations(schema.tables)
            for relation in relations[:3]:  # Limitar a 3 sugerencias de joins
                parent_table, parent_col, child_table, child_col = relation
                
                # Seleccionar algunas columnas de cada tabla
                parent_cols = [col.name for col in next((t.columns for t in schema.tables if t.name == parent_table), [])][:3]
                child_cols = [col.name for col in next((t.columns for t in schema.tables if t.name == child_table), [])][:3]
                
                select_cols = ", ".join([f"{parent_table}.{col}" for col in parent_cols] + 
                                       [f"{child_table}.{col}" for col in child_cols])
                
                # Consulta con JOIN
                suggestions.append(SchemaQuerySuggestion(
                    title=f"Unir {parent_table} con {child_table}",
                    description=f"Consulta que une {parent_table} y {child_table} por sus relaciones",
                    sql_query=f"SELECT {select_cols} FROM {parent_table} "
                              f"JOIN {child_table} ON {parent_table}.{parent_col} = {child_table}.{child_col} "
                              f"LIMIT 100;"
                ))
                
        elif schema.type == "mongodb":
            # Sugerencias para MongoDB
            for collection in schema.tables[:3]:
                suggestions.append(SchemaQuerySuggestion(
                    title=f"Consultar documentos en {collection.name}",
                    description=f"Obtener documentos de la colección {collection.name}",
                    sql_query=f"db.{collection.name}.find().limit(100)"
                ))
                
                # Agregación básica
                if collection.columns:
                    # Buscar una columna numérica para agregar
                    numeric_cols = [col.name for col in collection.columns 
                                    if any(num_type in col.data_type.lower() 
                                         for num_type in ["int", "double", "number"])]
                    
                    if numeric_cols:
                        suggestions.append(SchemaQuerySuggestion(
                            title=f"Agregación en {collection.name}",
                            description=f"Estadísticas agregadas de {numeric_cols[0]} en {collection.name}",
                            sql_query=f"db.{collection.name}.aggregate([\n"
                                     f"  {{ $group: {{ \n"
                                     f"    _id: null, \n"
                                     f"    total: {{ $sum: 1 }}, \n"
                                     f"    avg_{numeric_cols[0]}: {{ $avg: '${numeric_cols[0]}' }}, \n"
                                     f"    max_{numeric_cols[0]}: {{ $max: '${numeric_cols[0]}' }}, \n"
                                     f"    min_{numeric_cols[0]}: {{ $min: '${numeric_cols[0]}' }} \n"
                                     f"  }} }}\n"
                                     f"])"
                        ))
                
        return suggestions
    
    def _find_potential_relations(self, table: TableSchema, all_tables: List[TableSchema]) -> List[str]:
        """
        Encontrar posibles relaciones no declaradas entre tablas
        
        Args:
            table: Tabla a analizar
            all_tables: Todas las tablas del esquema
            
        Returns:
            Lista de posibles relaciones
        """
        potential_relations = []
        
        # Si no hay columnas, no podemos detectar relaciones
        if not table.columns:
            return potential_relations
            
        # Buscar columnas que podrían ser claves foráneas por su nombre
        for column in table.columns:
            # Ignorar si ya es clave foránea
            if column.is_foreign:
                continue
                
            # Posibles sufijos de ID
            id_suffixes = ["_id", "id", "_code", "code", "_key", "key"]
            
            # Verificar si el nombre sugiere que es un ID
            is_id_column = any(column.name.lower().endswith(suffix) for suffix in id_suffixes)
            
            if is_id_column:
                # Determinar posible tabla a la que hace referencia
                prefix = column.name.lower()
                for suffix in id_suffixes:
                    if prefix.endswith(suffix):
                        prefix = prefix[:-len(suffix)]
                        break
                
                # Si el prefijo es un nombre de tabla, podría ser una relación
                for ref_table in all_tables:
                    if ref_table.name.lower() == prefix:
                        # Verificar si la columna de referencia existe y es PK
                        pk_column = next((col.name for col in ref_table.columns if col.is_primary), None)
                        if pk_column:
                            potential_relations.append(
                                f"{table.name}.{column.name} podría referirse a {ref_table.name}.{pk_column}"
                            )
                            break
        
        return potential_relations
    
    def _find_db_relations(self, tables: List[TableSchema]) -> List[Tuple[str, str, str, str]]:
        """
        Encontrar relaciones declaradas entre tablas
        
        Args:
            tables: Tablas del esquema
            
        Returns:
            Lista de tuplas (tabla_padre, columna_padre, tabla_hija, columna_hija)
        """
        relations = []
        
        for child_table in tables:
            if not child_table.columns:
                continue
                
            for column in child_table.columns:
                if column.is_foreign and column.references:
                    # Formato esperado: tabla.columna
                    parts = column.references.split(".")
                    if len(parts) == 2:
                        parent_table, parent_column = parts
                        relations.append((parent_table, parent_column, child_table.name, column.name))
        
        return relations