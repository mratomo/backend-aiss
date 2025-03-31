# services/security_service.py
import re
import logging
from typing import List, Dict, Any

from models.models import DBType
from config.settings import Settings

logger = logging.getLogger(__name__)

class SecurityService:
    """Servicio para validación de seguridad de consultas"""
    
    def __init__(self, security_settings: Settings.SecuritySettings):
        """
        Inicializar servicio con configuración
        
        Args:
            security_settings: Configuración de seguridad
        """
        self.sensitive_keywords = security_settings.sensitive_keywords
        self.injection_patterns = [re.compile(pattern) for pattern in security_settings.injection_patterns]
    
    def validate_query(self, query: str, db_type: DBType) -> bool:
        """
        Validar seguridad de una consulta
        
        Args:
            query: Consulta a validar
            db_type: Tipo de BD
            
        Returns:
            True si la consulta es segura
        """
        if not query or not query.strip():
            return False
        
        # Normalizar query
        normalized_query = query.upper()
        
        # Validar según tipo de BD
        if db_type in [DBType.POSTGRESQL, DBType.MYSQL, DBType.SQLSERVER]:
            return self._validate_sql_query(normalized_query)
        elif db_type == DBType.MONGODB:
            return self._validate_mongodb_query(query)
        elif db_type == DBType.ELASTICSEARCH:
            return self._validate_elasticsearch_query(query)
        elif db_type == DBType.INFLUXDB:
            return self._validate_influxdb_query(normalized_query)
        else:
            logger.warning(f"No validation implemented for DB type: {db_type}")
            return True  # No validación específica, asumir segura
    
    def _validate_sql_query(self, normalized_query: str) -> bool:
        """
        Validar consulta SQL
        
        Args:
            normalized_query: Consulta normalizada
            
        Returns:
            True si la consulta es segura
        """
        # Verificar palabras clave sensibles
        for keyword in self.sensitive_keywords:
            if keyword in normalized_query:
                # Si contiene keyword sensible, verificar si es una operación permitida
                # Por ejemplo, "SELECT * FROM users" contiene "SELECT" pero es permitido
                if keyword == "SELECT" and normalized_query.strip().startswith("SELECT"):
                    continue
                if keyword == "SHOW" and normalized_query.strip().startswith("SHOW"):
                    continue
                if keyword == "DESCRIBE" and normalized_query.strip().startswith("DESCRIBE"):
                    continue
                if keyword == "EXPLAIN" and normalized_query.strip().startswith("EXPLAIN"):
                    continue
                
                # Si es otra operación sensible, rechazar
                logger.warning(f"Query contains sensitive keyword: {keyword}")
                return False
        
        # Verificar patrones de inyección
        for pattern in self.injection_patterns:
            if pattern.search(normalized_query):
                logger.warning(f"Query matches injection pattern: {pattern.pattern}")
                return False
        
        return True
    
    def _validate_mongodb_query(self, query: str) -> bool:
        """
        Validar consulta MongoDB
        
        Args:
            query: Consulta
            
        Returns:
            True si la consulta es segura
        """
        # Para MongoDB, validar formato JSON y operaciones
        try:
            # Si la consulta está en formato JSON, intentar analizarla
            import json
            if query.strip().startswith("{"):
                query_json = json.loads(query)
                
                # Verificar operaciones peligrosas
                if "$where" in query:
                    logger.warning("MongoDB query contains $where operator")
                    return False
                
                # Verificar código JavaScript
                if "$function" in query:
                    logger.warning("MongoDB query contains $function operator")
                    return False
                
                # Si pasa todas las validaciones
                return True
            elif query.strip().startswith("db."):
                # Validar operaciones comunes
                if query.startswith("db.collection.find(") or query.startswith("db.collection.aggregate("):
                    return True
                else:
                    # Buscar operaciones peligrosas
                    dangerous_ops = ["deleteMany", "drop", "dropDatabase"]
                    for op in dangerous_ops:
                        if op in query:
                            logger.warning(f"MongoDB query contains dangerous operation: {op}")
                            return False
                
                return True
            else:
                return True  # Asumir seguro si no se reconoce el formato
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Error validating MongoDB query: {e}")
            return False  # Si hay errores en el formato, rechazar
    
    def _validate_elasticsearch_query(self, query: str) -> bool:
        """
        Validar consulta Elasticsearch
        
        Args:
            query: Consulta
            
        Returns:
            True si la consulta es segura
        """
        # Para Elasticsearch, validar formato JSON y operaciones
        try:
            import json
            
            # Si la consulta está en formato JSON, intentar analizarla
            if query.strip().startswith("{"):
                query_json = json.loads(query)
                
                # Verificar operaciones peligrosas
                if "script" in query:
                    logger.warning("Elasticsearch query contains script")
                    return False
                
                # Si pasa todas las validaciones
                return True
            else:
                return True  # Asumir seguro si no se reconoce el formato
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Error validating Elasticsearch query: {e}")
            return False  # Si hay errores en el formato, rechazar
    
    def _validate_influxdb_query(self, normalized_query: str) -> bool:
        """
        Validar consulta InfluxDB
        
        Args:
            normalized_query: Consulta normalizada
            
        Returns:
            True si la consulta es segura
        """
        # Verificar si es consulta de lectura
        if normalized_query.startswith("SELECT") or normalized_query.startswith("SHOW"):
            return True
        
        # Rechazar otras operaciones
        logger.warning(f"InfluxDB query not allowed: {normalized_query}")
        return False