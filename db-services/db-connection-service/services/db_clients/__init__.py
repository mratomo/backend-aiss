# services/db_clients/__init__.py
from typing import Dict, Type

from models.models import DBType
from .base_client import BaseDBClient
from .postgresql_client import PostgreSQLClient
from .weaviate_client import WeaviateClient
# Importamos solo los clientes disponibles
# from .mysql_client import MySQLClient
# from .mongodb_client import MongoDBClient
# from .sqlserver_client import SQLServerClient
# from .elasticsearch_client import ElasticsearchClient
# from .influxdb_client import InfluxDBClient

# Registro de clientes por tipo de BD
_DB_CLIENTS: Dict[DBType, Type[BaseDBClient]] = {
    DBType.POSTGRESQL: PostgreSQLClient,
    DBType.WEAVIATE: WeaviateClient,
    # Solo habilitamos los clientes disponibles
    # DBType.MYSQL: MySQLClient,
    # DBType.MONGODB: MongoDBClient,
    # DBType.SQLSERVER: SQLServerClient,
    # DBType.ELASTICSEARCH: ElasticsearchClient,
    # DBType.INFLUXDB: InfluxDBClient,
}

def get_db_client(db_type: DBType) -> BaseDBClient:
    """
    Obtener cliente para un tipo de BD
    
    Args:
        db_type: Tipo de BD
        
    Returns:
        Cliente para la BD
        
    Raises:
        ValueError: Si el tipo de BD no está soportado
    """
    if db_type not in _DB_CLIENTS:
        raise ValueError(f"Tipo de BD no soportado: {db_type}")
    
    client_class = _DB_CLIENTS[db_type]
    return client_class()