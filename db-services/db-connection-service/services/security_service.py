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
        
        # Patrones mejorados para detectar inyecciones SQL comunes
        enhanced_patterns = [
            # Comentarios SQL -- pueden ser usados para eludir validaciones
            r'--.*$',
            # Comentarios tipo bloque /* ... */
            r'/\*.*?\*/',
            # Manipulación de comillas (indicador de posible inyección)
            r"'\s*OR\s*'.*?'?\s*=\s*'.*?'",
            r'"\s*OR\s*".*?"?\s*=\s*".*?"',
            # UNION SELECT comúnmente usado en inyecciones
            r'UNION\s+ALL\s+SELECT',
            r'UNION\s+SELECT',
            # Ejecución de comandos
            r';\s*EXEC\s+',
            r';\s*EXECUTE\s+',
            # Terminación y adición de comandos nuevos
            r';\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)',
            # Bypass de autenticación típico
            r"'\s*OR\s*[\"'0-9]+(=|<>|<|>)[\"'0-9]+",
            # Manipulación de tipo LIKE para eludir filtros
            r"LIKE\s+[\"']%.*?[\"']",
            # Intentos de obtener versión o información de sistema
            r'VERSION\s*\(\s*\)',
            r'DATABASE\s*\(\s*\)',
            # Consultas de fuerza bruta a información de schema
            r'FROM\s+information_schema\.',
            r'FROM\s+pg_catalog\.',
            r'FROM\s+sys\.',
            # Ataques de tiempo
            r'SLEEP\s*\(\s*\d+\s*\)',
            r'WAITFOR\s+DELAY',
            r'pg_sleep',
            # Procedimientos almacenados peligrosos
            r'xp_cmdshell',
            # Inyecciones NoSQL específicas
            r'\$where\s*:',
            r'\$regex\s*:',
            r'{\s*\$ne\s*:',
        ]
        
        # Combinar los patrones definidos en la configuración con los mejorados
        all_patterns = security_settings.injection_patterns + enhanced_patterns
        
        # Compilar patrones para búsqueda eficiente
        self.injection_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in all_patterns]
        
        # Registrar número de patrones para diagnóstico
        logger.info(f"Inicializado SecurityService con {len(self.injection_patterns)} patrones de detección")
    
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
        Validar consulta SQL de manera robusta
        
        Args:
            normalized_query: Consulta normalizada
            
        Returns:
            True si la consulta es segura
        """
        # Lista de operaciones permitidas
        allowed_operations = ["SELECT", "SHOW", "DESCRIBE", "EXPLAIN"]
        
        # Obtener primera palabra de la consulta (el comando principal)
        query_parts = normalized_query.strip().split()
        if not query_parts:
            logger.warning("Empty query")
            return False
            
        main_command = query_parts[0].upper()
        
        # Solo permitir comandos explícitamente permitidos
        if main_command not in allowed_operations:
            logger.warning(f"Command not allowed: {main_command}")
            return False
            
        # Verificar combinaciones peligrosas incluso en comandos permitidos
        dangerous_patterns = [
            # Comentarios que podrían usarse para truncar consultas
            r'--\s',        # SQL comment
            r'/\*.*\*/',    # Multi-line comment
            
            # Combinaciones de UNION que podrían usarse para inyecciones
            r'UNION\s+(?:ALL\s+)?SELECT',
            
            # Secuencias de escape que podrían romper la lógica de consulta
            r';\s*\w',      # Multiple statements
            
            # Modificaciones al esquema o datos
            r'INSERT\s+INTO',
            r'UPDATE\s+\w+\s+SET',
            r'DELETE\s+FROM',
            r'DROP\s+TABLE',
            r'ALTER\s+TABLE',
            r'CREATE\s+',
            r'TRUNCATE\s+',
            
            # Funciones del sistema que podrían revelar información sensible
            r'LOAD_FILE\(',
            r'SLEEP\(',
            r'BENCHMARK\(',
            r'SYSTEM\(',
            r'USER\(',
            r'DATABASE\(',
            r'VERSION\(',
            r'@@'           # Variables del sistema en MySQL/PostgreSQL
        ]
        
        # Compilar patrones para mejor rendimiento
        import re
        compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in dangerous_patterns]
        
        # Verificar cada patrón
        for pattern in compiled_patterns:
            if pattern.search(normalized_query):
                logger.warning(f"Query matches dangerous pattern: {pattern.pattern}")
                return False
                
        # Verificar patrones de inyección generales
        for pattern in self.injection_patterns:
            if pattern.search(normalized_query):
                logger.warning(f"Query matches injection pattern: {pattern.pattern}")
                return False
                
        # Validación de párametros (evitar inyecciones con comillas)
        quotes_count = normalized_query.count("'") + normalized_query.count('"')
        if quotes_count % 2 != 0:
            logger.warning("Query has unbalanced quotes")
            return False
            
        return True
    
    def _validate_mongodb_query(self, query: str) -> bool:
        """
        Validar consulta MongoDB con protección robusta
        
        Args:
            query: Consulta
            
        Returns:
            True si la consulta es segura
        """
        # Lista de operaciones permitidas en MongoDB
        allowed_operations = ["find", "findOne", "count", "distinct", "aggregate"]
        
        # Operadores prohibidos de MongoDB que pueden modificar datos o ejecutar JS
        prohibited_operators = [
            "$where",       # Permite ejecución de JavaScript
            "$expr",        # Permite expresiones complejas
            "$function",    # Función JavaScript personalizada
            "$accumulator", # Función personalizada en aggregation
            "$set",         # Modifica documentos
            "$unset",       # Elimina campos
            "$rename",      # Renombra campos
            "$out",         # Envía resultados a una colección
            "$merge",       # Fusiona resultados con una colección
            "$addFields",   # Añade campos
            "$replaceRoot", # Reemplaza documentos
            "$replaceWith", # Reemplaza documentos (alias de $replaceRoot)
            "$eval",        # Ejecuta JavaScript
            "$execute",     # Ejecuta comandos
            "mapReduce"     # Map-reduce (puede ejecutar JavaScript)
        ]
        
        # Validar formato JSON
        try:
            # Si la consulta está en formato JSON, intentar analizarla
            import json
            if query.strip().startswith("{"):
                query_json = json.loads(query)
                
                # Verificar operadores prohibidos recursivamente
                def check_prohibited(obj):
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if key in prohibited_operators:
                                logger.warning(f"MongoDB query contains prohibited operator: {key}")
                                return False
                            if isinstance(value, (dict, list)):
                                if not check_prohibited(value):
                                    return False
                    elif isinstance(obj, list):
                        for item in obj:
                            if isinstance(item, (dict, list)):
                                if not check_prohibited(item):
                                    return False
                    return True
                
                if not check_prohibited(query_json):
                    return False
                
                # Si pasa todas las validaciones
                return True
            elif query.strip().startswith("db."):
                # Validar sintaxis de tipo shell de MongoDB
                import re
                
                # Extraer la operación principal (ej: find, update, etc.)
                operation_match = re.search(r'db\.[^.]+\.(\w+)\(', query)
                if not operation_match:
                    logger.warning("Invalid MongoDB shell query format")
                    return False
                    
                operation = operation_match.group(1)
                
                # Verificar si la operación está permitida
                if operation not in allowed_operations:
                    logger.warning(f"MongoDB operation not allowed: {operation}")
                    return False
                
                # Verificar operadores prohibidos
                for op in prohibited_operators:
                    if op in query:
                        logger.warning(f"MongoDB query contains prohibited operator: {op}")
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