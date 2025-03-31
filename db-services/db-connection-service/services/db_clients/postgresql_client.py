# services/db_clients/postgresql_client.py
import asyncio
from typing import Dict, Any, List
import logging

import asyncpg

from models.models import DBConnection
from .base_client import BaseDBClient

logger = logging.getLogger(__name__)

class PostgreSQLClient(BaseDBClient):
    """Cliente para PostgreSQL"""
    
    async def test_connection(self, connection: DBConnection) -> bool:
        """
        Probar conexión a PostgreSQL
        
        Args:
            connection: Conexión a probar
            
        Returns:
            True si la conexión es exitosa
            
        Raises:
            Exception: Si hay error de conexión
        """
        conn = None
        try:
            # Construir DSN
            dsn = self._build_dsn(connection)
            
            # Conectar
            conn = await asyncpg.connect(dsn)
            
            # Ejecutar consulta simple
            version = await conn.fetchval("SELECT version()")
            logger.info(f"Conexión exitosa a PostgreSQL: {version}")
            
            return True
        finally:
            # Cerrar conexión
            if conn:
                await conn.close()
    
    async def execute_query(self, connection: DBConnection, query: str, params: Dict[str, Any] = None) -> Any:
        """
        Ejecutar una consulta en PostgreSQL
        
        Args:
            connection: Conexión a la BD
            query: Consulta a ejecutar
            params: Parámetros para la consulta
            
        Returns:
            Resultado de la consulta
            
        Raises:
            Exception: Si hay error durante la ejecución
        """
        conn = None
        try:
            # Construir DSN
            dsn = self._build_dsn(connection)
            
            # Conectar
            conn = await asyncpg.connect(dsn)
            
            # Convertir parámetros si es necesario
            if params:
                # PostgreSQL usa parámetros posicionales ($1, $2, etc.)
                # Convertir dict a list según el orden de aparición en la consulta
                param_list = []
                for key, value in params.items():
                    query = query.replace(f":{key}", f"${len(param_list) + 1}")
                    param_list.append(value)
                
                # Ejecutar consulta con parámetros
                if query.strip().upper().startswith("SELECT"):
                    result = await conn.fetch(query, *param_list)
                    return [dict(r) for r in result]
                else:
                    return await conn.execute(query, *param_list)
            else:
                # Ejecutar consulta sin parámetros
                if query.strip().upper().startswith("SELECT"):
                    result = await conn.fetch(query)
                    return [dict(r) for r in result]
                else:
                    return await conn.execute(query)
        finally:
            # Cerrar conexión
            if conn:
                await conn.close()
    
    async def get_schema(self, connection: DBConnection) -> Dict[str, Any]:
        """
        Obtener esquema de PostgreSQL
        
        Args:
            connection: Conexión a la BD
            
        Returns:
            Información del esquema
            
        Raises:
            Exception: Si hay error durante la obtención
        """
        conn = None
        try:
            # Construir DSN
            dsn = self._build_dsn(connection)
            
            # Conectar
            conn = await asyncpg.connect(dsn)
            
            # Obtener tablas
            tables_query = """
                SELECT 
                    t.table_schema,
                    t.table_name,
                    obj_description(pg_class.oid) as table_comment
                FROM 
                    information_schema.tables t
                JOIN 
                    pg_class ON pg_class.relname = t.table_name
                WHERE 
                    t.table_schema NOT IN ('pg_catalog', 'information_schema')
                    AND t.table_type = 'BASE TABLE'
                ORDER BY 
                    t.table_schema, t.table_name
            """
            tables = await conn.fetch(tables_query)
            
            schema_info = {
                "database": connection.database,
                "tables": []
            }
            
            # Para cada tabla, obtener columnas
            for table in tables:
                table_schema = table["table_schema"]
                table_name = table["table_name"]
                
                columns_query = """
                    SELECT 
                        column_name,
                        data_type,
                        is_nullable,
                        column_default,
                        col_description(pg_class.oid, ordinal_position) as column_comment
                    FROM 
                        information_schema.columns c
                    JOIN 
                        pg_class ON pg_class.relname = c.table_name
                    WHERE 
                        table_schema = $1
                        AND table_name = $2
                    ORDER BY 
                        ordinal_position
                """
                columns = await conn.fetch(columns_query, table_schema, table_name)
                
                # Obtener claves primarias
                pk_query = """
                    SELECT 
                        kcu.column_name
                    FROM 
                        information_schema.table_constraints tc
                    JOIN 
                        information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    WHERE 
                        tc.constraint_type = 'PRIMARY KEY'
                        AND tc.table_schema = $1
                        AND tc.table_name = $2
                """
                pks = await conn.fetch(pk_query, table_schema, table_name)
                primary_keys = [pk["column_name"] for pk in pks]
                
                # Obtener índices
                index_query = """
                    SELECT 
                        indexname,
                        indexdef
                    FROM 
                        pg_indexes
                    WHERE 
                        schemaname = $1
                        AND tablename = $2
                """
                indices = await conn.fetch(index_query, table_schema, table_name)
                
                # Construir información de la tabla
                table_info = {
                    "schema": table_schema,
                    "name": table_name,
                    "description": table["table_comment"],
                    "columns": [
                        {
                            "name": col["column_name"],
                            "type": col["data_type"],
                            "nullable": col["is_nullable"] == "YES",
                            "default": col["column_default"],
                            "description": col["column_comment"],
                            "primary_key": col["column_name"] in primary_keys
                        }
                        for col in columns
                    ],
                    "primary_keys": primary_keys,
                    "indices": [
                        {
                            "name": idx["indexname"],
                            "definition": idx["indexdef"]
                        }
                        for idx in indices
                    ]
                }
                
                schema_info["tables"].append(table_info)
            
            return schema_info
        finally:
            # Cerrar conexión
            if conn:
                await conn.close()
    
    def _build_dsn(self, connection: DBConnection) -> str:
        """
        Construir DSN para PostgreSQL
        
        Args:
            connection: Conexión a la BD
            
        Returns:
            DSN para conexión
        """
        dsn = f"postgresql://{connection.username}"
        
        if connection.password:
            dsn += f":{connection.password}"
        
        dsn += f"@{connection.host}:{connection.port}/{connection.database}"
        
        # Añadir opciones SSL si es necesario
        if connection.ssl:
            dsn += "?sslmode=require"
        
        return dsn