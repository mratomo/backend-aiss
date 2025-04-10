# services/weaviate_service.py
import logging
import uuid
from typing import Dict, List, Optional, Any

import weaviate
from weaviate.exceptions import WeaviateBaseError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from fastapi import HTTPException

from config.settings import Settings
from services.vectordb_base import VectorDBBase

logger = logging.getLogger(__name__)

class WeaviateVectorDB(VectorDBBase):
    """Servicio para interactuar con la base de datos vectorial Weaviate"""

    def __init__(self, settings: Settings):
        """
        Inicializar servicio con la configuración
        
        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        self.weaviate_url = settings.weaviate_url
        self.api_key = settings.weaviate_api_key
        self.batch_size = 100  # Tamaño por defecto de batch
        self.timeout = 60      # Timeout por defecto
        self.client = self._init_client()
        
    def _init_client(self):
        """
        Inicializar cliente de Weaviate
        
        Returns:
            Cliente de Weaviate configurado
        """
        auth_config = None
        if self.api_key:
            auth_config = weaviate.auth.AuthApiKey(api_key=self.api_key)
            
        try:
            client = weaviate.Client(
                url=self.weaviate_url,
                auth_client_secret=auth_config,
                timeout_config=(self.timeout, self.timeout),
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
        """
        Verificar estado de Weaviate
        
        Returns:
            Dict con estado e información de Weaviate
        """
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

    async def ensure_collections_exist(self, collections: List[str]) -> None:
        """
        Asegurar que las colecciones/clases necesarias existen, crearlas si no
        
        Args:
            collections: Lista de nombres de colecciones a verificar/crear
        """
        try:
            if not self.client:
                self.client = self._init_client()
                if not self.client:
                    logger.error("No se pudo inicializar el cliente Weaviate")
                    return
            
            # Verificar qué clases existen
            schema = self.client.schema.get()
            existing_classes = [cls["class"] for cls in schema.get("classes", [])]
            
            # Crear clases que no existen
            for collection in collections:
                if collection not in existing_classes:
                    logger.info(f"Creando clase {collection} que no existe")
                    try:
                        await self._create_class(collection)
                    except Exception as create_err:
                        logger.error(f"Error al crear clase {collection}: {str(create_err)}")
                else:
                    logger.info(f"Clase {collection} ya existe")
                
        except Exception as e:
            logger.error(f"Error al verificar clases existentes: {str(e)}")
            logger.warning("No se pudieron verificar/crear clases, algunas funciones pueden no estar disponibles")

    async def _create_class(self, class_name: str) -> None:
        """
        Crear una clase en Weaviate
        
        Args:
            class_name: Nombre de la clase a crear
        """
        # Definir propiedades para la clase
        class_obj = {
            "class": class_name,
            "vectorizer": "none",  # Usamos 'none' porque proporcionamos nuestros propios vectores
            "vectorIndexConfig": {
                "distance": "cosine"
            },
            "properties": [
                {
                    "name": "entity_id",
                    "dataType": ["string"],
                    "description": "ID de la entidad asociada",
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
                
        except Exception as e:
            logger.error(f"Error al crear clase {class_name}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error al crear clase en Weaviate: {str(e)}")

    async def store_vector(self,
                          vector: List[float],
                          collection: str,
                          entity_id: str,
                          text: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Almacenar un vector en la base de datos vectorial
        
        Args:
            vector: Vector a almacenar
            collection: Nombre de la colección
            entity_id: ID de la entidad asociada
            text: Texto asociado al vector
            metadata: Metadatos adicionales
            
        Returns:
            ID del vector almacenado
        """
        # Generar ID único para el objeto
        object_id = str(uuid.uuid4())
        
        # Preparar propiedades del objeto
        properties = {
            "entity_id": entity_id
        }
        
        if text:
            properties["text"] = text
            
        if metadata:
            properties["metadata"] = metadata
        
        try:
            # Almacenar el objeto con su vector
            self.client.data_object.create(
                properties,
                collection,
                uuid=object_id,
                vector=vector
            )
            
            return object_id
            
        except Exception as e:
            logger.error(f"Error al almacenar vector en Weaviate: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error al almacenar vector en Weaviate: {str(e)}")

    async def delete_vector(self, vector_id: str, collection: str) -> bool:
        """
        Eliminar un vector de la base de datos vectorial
        
        Args:
            vector_id: ID del vector a eliminar
            collection: Nombre de la colección
            
        Returns:
            True si se eliminó correctamente
        """
        try:
            # Eliminar objeto por UUID
            self.client.data_object.delete(
                uuid=vector_id,
                class_name=collection
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error al eliminar vector de Weaviate: {str(e)}")
            
            # Si el objeto no existe, consideramos que ya está eliminado
            if "not found" in str(e).lower():
                return False
                
            raise HTTPException(status_code=500, detail=f"Error al eliminar vector de Weaviate: {str(e)}")

    async def search(self,
                    query_vector: List[float],
                    collection: str,
                    filters: Optional[Dict[str, Any]] = None,
                    limit: int = 10) -> List[Dict[str, Any]]:
        """
        Buscar vectores similares
        
        Args:
            query_vector: Vector de consulta
            collection: Nombre de la colección
            filters: Filtros adicionales
            limit: Número máximo de resultados
            
        Returns:
            Lista de resultados con scores
        """
        try:
            # Preparar consulta de búsqueda
            query = self.client.query.get(collection, ["entity_id", "text", "metadata", "_additional {id score}"])
            
            # Añadir filtros si se especifican
            if filters:
                filter_conditions = []
                
                for key, value in filters.items():
                    if key == "entity_id" and value:
                        filter_conditions.append({
                            "path": ["entity_id"],
                            "operator": "Equal",
                            "valueString": value
                        })
                
                # Combinar condiciones con operador AND si hay más de una
                if len(filter_conditions) > 1:
                    query = query.with_where({
                        "operator": "And",
                        "operands": filter_conditions
                    })
                elif filter_conditions:
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
            
            # Procesar resultados
            search_results = []
            
            # Verificar si hay resultados
            if (result and 
                "data" in result and 
                "Get" in result["data"] and 
                collection in result["data"]["Get"] and 
                result["data"]["Get"][collection]):
                
                for item in result["data"]["Get"][collection]:
                    # Extraer ID y puntuación
                    vector_id = item["_additional"]["id"]
                    score = item["_additional"]["score"]
                    
                    # Crear resultado
                    search_result = {
                        "vector_id": vector_id,
                        "entity_id": item.get("entity_id", ""),
                        "score": score,
                        "metadata": item.get("metadata", {})
                    }
                    
                    # Añadir texto si está disponible
                    if "text" in item:
                        search_result["text"] = item["text"]
                        
                    search_results.append(search_result)
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error al buscar vectores en Weaviate: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error al buscar vectores en Weaviate: {str(e)}")