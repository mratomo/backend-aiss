import logging
import uuid
from typing import Dict, List, Optional, Any

try:
    import structlog
    logger = structlog.get_logger("weaviate_service")
    structlog_available = True
except ImportError:
    logger = logging.getLogger("weaviate_service")
    structlog_available = False

import weaviate
from weaviate.exceptions import WeaviateBaseError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from fastapi import HTTPException

# Importar prometheus si está disponible
try:
    from prometheus_client import Counter
    prometheus_available = True
    
    # Importar el registro personalizado desde main.py
    try:
        from main import custom_registry
        # Definir métricas específicas para Weaviate usando el registro personalizado
        WEAVIATE_OPERATIONS = Counter(
            'weaviate_operations_total', 
            'Operaciones realizadas en Weaviate', 
            ['operation', 'status'],
            registry=custom_registry
        )
    except ImportError:
        # Fallback a registro global si no se puede importar
        prometheus_available = False
except ImportError:
    prometheus_available = False

from config.settings import Settings
from models.embedding import EmbeddingType, SearchResult
from services.vectordb_base import VectorDBBase

class WeaviateVectorDB(VectorDBBase):
    """Servicio para interactuar con la base de datos vectorial Weaviate"""

    def __init__(self, settings: Settings):
        """Inicializar servicio con la configuración"""
        self.settings = settings
        self.weaviate_url = settings.weaviate.url
        self.api_key = settings.weaviate.api_key
        self.class_general = settings.weaviate.class_general
        self.class_personal = settings.weaviate.class_personal
        self.batch_size = settings.weaviate.batch_size
        self.timeout = settings.weaviate.timeout
        self.client = self._init_client()
        
    def _init_client(self):
        """Inicializar cliente de Weaviate"""
        auth_config = None
        if self.api_key:
            auth_config = weaviate.auth.AuthApiKey(api_key=self.api_key)
            
        try:
            client = weaviate.Client(
                url=self.weaviate_url,
                auth_client_secret=auth_config,
                timeout_config=(self.timeout, self.timeout),  # (connect_timeout, read_timeout)
                additional_headers={"X-OpenAI-Api-Key": self.api_key} if self.api_key else None
            )
            return client
        except Exception as e:
            logger.error(f"Error inicializando cliente Weaviate: {str(e)}")
            # No lanzamos excepción para permitir que la aplicación siga funcionando
            # aún si Weaviate no está disponible inicialmente
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def get_status(self) -> Dict:
        """Verificar estado de Weaviate"""
        try:
            if not self.client:
                self.client = self._init_client()
                if not self.client:
                    return {"status": "error", "message": "No se pudo inicializar el cliente Weaviate"}
            
            # Verificar si el servidor está vivo
            is_ready = self.client.is_ready()
            if not is_ready:
                return {"status": "error", "message": "Weaviate no está listo"}
                
            # Obtener información detallada
            meta = self.client.get_meta()
            version = meta.get("version", "unknown")
            
            return {
                "status": "ok",
                "result": {
                    "message": "Connected to Weaviate successfully",
                    "version": version
                }
            }
        except Exception as e:
            logger.error(f"Error verificando estado de Weaviate: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def ensure_collections_exist(self) -> None:
        """Asegurar que las clases necesarias existen, crearlas si no"""
        try:
            if not self.client:
                self.client = self._init_client()
                if not self.client:
                    logger.error("No se pudo inicializar el cliente Weaviate")
                    return
            
            # Verificar si la clase general existe
            schema = self.client.schema.get()
            existing_classes = [cls["class"] for cls in schema.get("classes", [])]
            
            # Crear clase para conocimiento general si no existe
            if self.class_general not in existing_classes:
                logger.info(f"Creando clase {self.class_general} que no existe")
                try:
                    await self._create_class(self.class_general)
                except Exception as create_err:
                    logger.error(f"Error al crear clase {self.class_general}: {str(create_err)}")
            else:
                logger.info(f"Clase {self.class_general} ya existe")
            
            # Crear clase para conocimiento personal si no existe
            if self.class_personal not in existing_classes:
                logger.info(f"Creando clase {self.class_personal} que no existe")
                try:
                    await self._create_class(self.class_personal)
                except Exception as create_err:
                    logger.error(f"Error al crear clase {self.class_personal}: {str(create_err)}")
            else:
                logger.info(f"Clase {self.class_personal} ya existe")
                
        except Exception as e:
            logger.error(f"Error al verificar clases existentes: {str(e)}")
            logger.warning("No se pudieron verificar/crear clases, algunas funciones pueden no estar disponibles")

    async def _create_class(self, class_name: str) -> None:
        """Crear una clase en Weaviate"""
        
        # Definir propiedades para la clase
        class_obj = {
            "class": class_name,
            "vectorizer": "none",  # Usamos 'none' porque proporcionamos nuestros propios vectores
            "vectorIndexConfig": {
                "distance": "cosine"
            },
            "properties": [
                {
                    "name": "doc_id",
                    "dataType": ["string"],
                    "description": "ID del documento",
                    "indexFilterable": True,
                    "indexSearchable": True
                },
                {
                    "name": "owner_id",
                    "dataType": ["string"],
                    "description": "ID del propietario",
                    "indexFilterable": True,
                    "indexSearchable": True
                },
                {
                    "name": "area_id",
                    "dataType": ["string"],
                    "description": "ID del área",
                    "indexFilterable": True,
                    "indexSearchable": True
                },
                {
                    "name": "text",
                    "dataType": ["text"],
                    "description": "Texto del embedding",
                    "indexFilterable": True,
                    "indexSearchable": True,
                    "tokenization": "field"
                },
                {
                    "name": "metadata",
                    "dataType": ["object"],
                    "description": "Metadatos adicionales",
                    "indexFilterable": False,
                    "indexSearchable": False
                }
            ]
        }
        
        # Crear la clase en Weaviate
        try:
            self.client.schema.create_class(class_obj)
            logger.info(f"Clase {class_name} creada exitosamente")
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="create_class", status="success").inc()
                
        except Exception as e:
            logger.error(f"Error al crear clase {class_name}: {str(e)}")
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="create_class", status="error").inc()
                
            raise HTTPException(status_code=500, detail=f"Error al crear clase en Weaviate: {str(e)}")

    def _get_class_for_type(self, embedding_type: EmbeddingType) -> str:
        """Obtener el nombre de la clase correspondiente al tipo de embedding"""
        if embedding_type == EmbeddingType.GENERAL:
            return self.class_general
        elif embedding_type == EmbeddingType.PERSONAL:
            return self.class_personal
        else:
            logger.error(f"Tipo de embedding no soportado: {embedding_type}")
            raise HTTPException(status_code=400, detail=f"Tipo de embedding no soportado: {embedding_type}")

    async def store_vector(self,
                           vector: List[float],
                           embedding_type: EmbeddingType,
                           doc_id: str,
                           owner_id: str,
                           text: Optional[str] = None,
                           area_id: Optional[str] = None,
                           metadata: Optional[Dict[str, Any]] = None) -> str:
        """Almacenar un vector en la base de datos vectorial"""
        class_name = self._get_class_for_type(embedding_type)
        
        # Generar ID único para el objeto
        object_id = str(uuid.uuid4())
        
        # Preparar propiedades del objeto
        properties = {
            "doc_id": doc_id,
            "owner_id": owner_id
        }
        
        if area_id:
            properties["area_id"] = area_id
            
        if text:
            properties["text"] = text
            
        if metadata:
            properties["metadata"] = metadata
        
        try:
            # Almacenar el objeto con su vector
            self.client.data_object.create(
                properties,
                class_name,
                uuid=object_id,
                vector=vector
            )
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="store_vector", status="success").inc()
                
            return object_id
            
        except Exception as e:
            logger.error(f"Error al almacenar vector en Weaviate: {str(e)}")
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="store_vector", status="error").inc()
                
            raise HTTPException(status_code=500, detail=f"Error al almacenar vector en Weaviate: {str(e)}")

    async def store_vectors_batch(self,
                                  vectors: List[List[float]],
                                  embedding_type: EmbeddingType,
                                  doc_ids: List[str],
                                  owner_id: str,
                                  texts: Optional[List[str]] = None,
                                  area_id: Optional[str] = None,
                                  metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """Almacenar múltiples vectores en batch"""
        class_name = self._get_class_for_type(embedding_type)
        
        # Verificar que las listas tienen el mismo tamaño
        if len(vectors) != len(doc_ids):
            logger.error("Las listas de vectores y doc_ids tienen diferente tamaño")
            raise HTTPException(status_code=400, detail="Las listas de vectores y doc_ids deben tener el mismo tamaño")
        if texts and len(texts) != len(vectors):
            logger.error("La lista de textos no coincide con la lista de vectores")
            raise HTTPException(status_code=400, detail="La lista de textos debe tener el mismo tamaño que la lista de vectores")
        
        # Lista para guardar los IDs generados
        object_ids: List[str] = []
        
        try:
            # Configurar cliente de batch
            client = self.client.batch.configure(
                batch_size=self.batch_size,
                timeout_retries=3,
                callback=self._batch_callback
            )
            
            # Iniciar el batch
            with client:
                for i, vector in enumerate(vectors):
                    # Generar ID único para el objeto
                    object_id = str(uuid.uuid4())
                    object_ids.append(object_id)
                    
                    # Preparar propiedades del objeto
                    properties = {
                        "doc_id": doc_ids[i],
                        "owner_id": owner_id
                    }
                    
                    if area_id:
                        properties["area_id"] = area_id
                        
                    if texts:
                        properties["text"] = texts[i]
                        
                    if metadata:
                        properties["metadata"] = metadata
                    
                    # Añadir objeto al batch
                    client.add_data_object(
                        properties,
                        class_name,
                        uuid=object_id,
                        vector=vector
                    )
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="store_vectors_batch", status="success").inc()
                
            return object_ids
            
        except Exception as e:
            logger.error(f"Error al almacenar vectores en batch en Weaviate: {str(e)}")
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="store_vectors_batch", status="error").inc()
                
            raise HTTPException(status_code=500, detail=f"Error al almacenar vectores en batch en Weaviate: {str(e)}")

    def _batch_callback(self, results: Optional[List[Dict[str, Any]]]) -> None:
        """Callback para el procesamiento batch de Weaviate"""
        # Esta función se llama después de cada batch para procesar los resultados
        if results is not None:
            for result in results:
                if "errors" in result and result["errors"]:
                    logger.error(f"Error en batch de Weaviate: {result['errors']}")

    async def delete_vector(self, vector_id: str, embedding_type: EmbeddingType) -> bool:
        """Eliminar un vector de la base de datos vectorial"""
        class_name = self._get_class_for_type(embedding_type)
        
        try:
            # Eliminar objeto por UUID
            self.client.data_object.delete(
                uuid=vector_id,
                class_name=class_name
            )
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="delete_vector", status="success").inc()
                
            return True
            
        except Exception as e:
            logger.error(f"Error al eliminar vector de Weaviate: {str(e)}")
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="delete_vector", status="error").inc()
                
            # Si el objeto no existe, consideramos que ya está eliminado
            if "not found" in str(e).lower():
                return False
                
            raise HTTPException(status_code=500, detail=f"Error al eliminar vector de Weaviate: {str(e)}")

    async def search(self,
                     query_vector: List[float],
                     embedding_type: EmbeddingType,
                     owner_id: Optional[str] = None,
                     area_id: Optional[str] = None,
                     limit: int = 10) -> List[SearchResult]:
        """Buscar vectores similares"""
        class_name = self._get_class_for_type(embedding_type)
        
        try:
            # Preparar consulta de búsqueda
            query = self.client.query.get(class_name, ["doc_id", "text", "owner_id", "area_id", "metadata", "_additional {id score}"])
            
            # Añadir filtros si se especifican
            if owner_id or area_id:
                filter_conditions = []
                
                if owner_id:
                    filter_conditions.append({
                        "path": ["owner_id"],
                        "operator": "Equal",
                        "valueString": owner_id
                    })
                    
                if area_id:
                    filter_conditions.append({
                        "path": ["area_id"],
                        "operator": "Equal",
                        "valueString": area_id
                    })
                
                # Combinar condiciones con operador AND
                if len(filter_conditions) > 1:
                    query = query.with_where({
                        "operator": "And",
                        "operands": filter_conditions
                    })
                else:
                    query = query.with_where(filter_conditions[0])
            
            # Añadir vector para búsqueda por similitud
            query = query.with_near_vector({
                "vector": query_vector,
                "certainty": 0.7  # Threshold, equivalente a score > 0.7
            })
            
            # Limitar número de resultados
            query = query.with_limit(limit)
            
            # Ejecutar la consulta
            result = query.do()
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="search", status="success").inc()
            
            # Procesar resultados
            search_results: List[SearchResult] = []
            
            # Verificar si hay resultados
            if (result and 
                "data" in result and 
                "Get" in result["data"] and 
                class_name in result["data"]["Get"] and 
                result["data"]["Get"][class_name]):
                
                for item in result["data"]["Get"][class_name]:
                    # Extraer ID y puntuación
                    id = item["_additional"]["id"]
                    score = item["_additional"]["score"]
                    
                    # Crear resultado
                    search_result = SearchResult(
                        embedding_id=id,
                        doc_id=item["doc_id"],
                        score=score,
                        metadata=item.get("metadata", {})
                    )
                    
                    # Añadir texto si está disponible
                    if "text" in item:
                        search_result.text = item["text"]
                        
                    search_results.append(search_result)
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error al buscar vectores en Weaviate: {str(e)}")
            
            if prometheus_available:
                WEAVIATE_OPERATIONS.labels(operation="search", status="error").inc()
                
            raise HTTPException(status_code=500, detail=f"Error al buscar vectores en Weaviate: {str(e)}")