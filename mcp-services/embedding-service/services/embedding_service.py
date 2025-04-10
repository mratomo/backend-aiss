import logging
import uuid
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union

import torch
# Importar sentence_transformers directamente en lugar de transformers
from sentence_transformers import SentenceTransformer
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from config.settings import Settings
from models.embedding import (
    EmbeddingRequest, EmbeddingResponse, EmbeddingBatchRequest,
    EmbeddingBatchResponse, EmbeddingType, EmbeddingDB, DocumentChunk
)
from services.vectordb_base import VectorDBBase

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Servicio para generar y gestionar embeddings con modelos avanzados"""

    def __init__(self, database: AsyncIOMotorDatabase, vectordb_service: VectorDBBase, settings: Settings):
        """Inicializar servicio con la base de datos, servicio vectorial y configuración"""
        self.db = database
        self.collection = database.embeddings
        self.vectordb_service = vectordb_service
        self.settings = settings

        # Modelos para embeddings
        self.models: Dict[EmbeddingType, Dict[str, Any]] = {}
        self.gpu_available = False
        self.gpu_info = "No GPU detected"
        self.device = None

        # Verificar dependencias opcionales al inicio
        self.pdf_support = False
        self.docx_support = False
        try:
            import PyPDF2
            self.pdf_support = True
        except ImportError:
            logger.warning("PyPDF2 no está instalado. El procesamiento de PDFs será limitado.")

        try:
            import docx
            self.docx_support = True
        except ImportError:
            logger.warning("python-docx no está instalado. El procesamiento de documentos Word será limitado.")

    async def initialize_models(self):
        """Inicializar modelos de embeddings optimizados para GPU"""
        try:
            # Comprobar disponibilidad de GPU
            use_gpu = self.settings.models.use_gpu
            gpu_detected = torch.cuda.is_available()
            fallback_to_cpu = self.settings.models.fallback_to_cpu
            
            # Primera verificación: ¿Se quiere usar GPU y está disponible?
            self.gpu_available = gpu_detected and use_gpu
            
            if use_gpu and not gpu_detected:
                if fallback_to_cpu:
                    logger.warning("GPU solicitada pero no detectada. Fallback a CPU activado.")
                    self.device = "cpu"
                    self.gpu_info = "GPU no disponible, usando CPU"
                    self.gpu_available = False
                else:
                    error_msg = "GPU solicitada pero no detectada y fallback a CPU desactivado"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
            elif self.gpu_available:
                try:
                    # Intentar inicializar y obtener información detallada de GPU
                    device_count = torch.cuda.device_count()
                    device_name = torch.cuda.get_device_name(0) if device_count > 0 else "Desconocida"
                    memory_info = torch.cuda.get_device_properties(0).total_memory / (1024**3) if device_count > 0 else 0
                    self.gpu_info = f"{device_count} dispositivo(s), {device_name} ({memory_info:.1f} GB)"
                    self.device = "cuda:0"
                    
                    # Información detallada sobre la GPU
                    logger.info(f"Usando GPU: {self.gpu_info}")
                    logger.info(f"CUDA version: {torch.version.cuda}")
                    logger.info(f"PyTorch CUDA configurado: {torch.cuda.is_available()}")
                    
                    # Intento de reservar una pequeña cantidad de memoria para verificar que la GPU funciona
                    try:
                        test_tensor = torch.zeros((10, 10), device=self.device)
                        del test_tensor  # Liberar inmediatamente
                        logger.info("GPU verificada correctamente")
                    except Exception as e:
                        # Error al reservar memoria de GPU
                        logger.error(f"Error al probar GPU: {e}")
                        if fallback_to_cpu:
                            logger.warning("Fallback a CPU debido a error en prueba de GPU")
                            self.device = "cpu"
                            self.gpu_info = f"Error en GPU: {str(e)}, usando CPU"
                            self.gpu_available = False
                        else:
                            raise ValueError(f"Error al inicializar GPU: {e}")
                    
                    # Verificar que estamos usando tecnología adecuada para RTX 4090
                    if self.gpu_available:
                        logger.info("SentenceTransformer está configurado para aprovechar la GPU detectada")
                        logger.info("Batch size optimizado para RTX 4090: " + str(self.settings.models.batch_size))
                        if self.settings.models.use_fp16:
                            logger.info("FP16 (media precisión) activado para mejor rendimiento en RTX 4090")
                        logger.info("Modelo Nomic utilizará GPU a través de SentenceTransformer")
                except Exception as e:
                    # Error general al configurar GPU
                    logger.error(f"Error configurando GPU: {e}")
                    if fallback_to_cpu:
                        logger.warning("Fallback a CPU debido a error en configuración de GPU")
                        self.device = "cpu"
                        self.gpu_info = f"Error: {str(e)}, usando CPU"
                        self.gpu_available = False
                    else:
                        raise ValueError(f"Error crítico al configurar GPU y fallback a CPU desactivado: {e}")
            else:
                # Usar CPU por elección (use_gpu = False)
                self.device = "cpu"
                self.gpu_info = "CPU seleccionada por configuración"
                logger.info("Usando CPU para generación de embeddings por configuración")
            
            # Si llegamos aquí sin GPU disponible y sin errores, es porque estamos usando CPU
            if not self.gpu_available:
                logger.info("Usando CPU para generación de embeddings")
            
            # Asegurarse de que las colecciones existen en la base de datos vectorial
            await self.vectordb_service.ensure_collections_exist()
            
        except Exception as e:
            logger.error(f"Error crítico inicializando hardware para modelos: {e}")
            if fallback_to_cpu:
                logger.warning("Fallback a CPU debido a error crítico")
                self.device = "cpu"
                self.gpu_info = f"Error crítico: {str(e)}, usando CPU"
                self.gpu_available = False
                # Intentar continuar
            else:
                raise ValueError(f"Error crítico inicializando hardware para modelos y fallback a CPU desactivado: {e}")

        # Cargar modelo para embeddings generales
        logger.info(f"Cargando modelo de embedding general: {self.settings.models.general_model}")
        general_model = await self._load_model(self.settings.models.general_model)
        self.models[EmbeddingType.GENERAL] = general_model

        # Cargar modelo para embeddings personales (si es diferente)
        if self.settings.models.personal_model != self.settings.models.general_model:
            logger.info(f"Cargando modelo de embedding personal: {self.settings.models.personal_model}")
            personal_model = await self._load_model(self.settings.models.personal_model)
            self.models[EmbeddingType.PERSONAL] = personal_model
        else:
            # Usar el mismo modelo para ambos tipos
            logger.info("Usando el mismo modelo para embeddings personales")
            self.models[EmbeddingType.PERSONAL] = general_model

        # Actualizar tamaño del vector en configuración de Qdrant si es necesario
        self._update_vector_size()

    async def _load_model(self, model_name: str) -> Dict[str, Any]:
        """
        Cargar y optimizar modelo de embeddings (SOLO NOMIC v1.5).
        Devuelve un diccionario con la instancia del modelo y metadatos.
        """
        # Como solo usamos Nomic, model_name siempre debería ser "nomic-ai/nomic-embed-text-v1.5"
        if "nomic-ai/nomic-embed-text-v1.5" not in model_name:
            # Forzar al modelo correcto si por alguna razón se intenta cargar otro
            logger.warning(f"Intentando cargar un modelo no soportado: {model_name}. Usando Nomic v1.5.")
            model_name = "nomic-ai/nomic-embed-text-v1.5"
            
        try:
            # Verificar versión de sentence_transformers 
            try:
                import importlib.metadata
                st_version = importlib.metadata.version("sentence_transformers")
                logger.info(f"SentenceTransformer versión detectada: {st_version}")
            except ImportError:
                logger.error("Biblioteca sentence_transformers no está instalada correctamente.")
                raise
            
            # Crear directorio para caché si no existe
            import os
            cache_dir = "./modelos"
            os.makedirs(cache_dir, exist_ok=True)
            
            # Cargar el modelo una sola vez - esta función es crucial para la eficiencia
            logger.info(f"Cargando modelo {model_name} usando SentenceTransformer...")
            
            # Ejecutar en un thread separado para no bloquear
            def load_actual_model():
                try:
                    # Determinar dispositivo (ya debería estar en self.device)
                    device = self.device
                    
                    # Si fallback_to_cpu=False y solo hay CPU disponible, es un error crítico
                    if device == "cpu" and not self.settings.models.fallback_to_cpu:
                        raise RuntimeError("GPU requerida pero solo CPU disponible y fallback desactivado.")
                    
                    # Verificar disponibilidad de GPU y mostrar información
                    if self.gpu_available:
                        # Verificar memoria disponible - útil para RTX 4090 con 24GB
                        mem_info = torch.cuda.get_device_properties(0)
                        total_mem_gb = mem_info.total_memory / (1024 * 1024 * 1024)
                        logger.info(f"GPU detectada: {mem_info.name} con {total_mem_gb:.1f} GB de memoria")
                    else:
                        if not self.settings.models.fallback_to_cpu:
                            raise RuntimeError("No se detectó GPU y fallback a CPU está desactivado.")
                        logger.warning("Usando CPU (GPU no disponible o desactivada).")
                    
                    # Cargar modelo usando SentenceTransformer - ESTA INSTANCIA SE REUTILIZARÁ
                    logger.info(f"Cargando y manteniendo en memoria modelo {model_name} en {device}...")
                    sentence_model = SentenceTransformer(
                        model_name, 
                        cache_folder=cache_dir,
                        device=device,
                        trust_remote_code=True  # Necesario para modelos Nomic
                    )
                    
                    # Verificar modelo con una entrada simple
                    test_text = "search_document: Prueba de modelo"
                    logger.info(f"Verificando el modelo con texto de prueba: '{test_text}'")
                    
                    # Generar embedding de prueba
                    embedding = sentence_model.encode(
                        test_text, 
                        convert_to_tensor=True,
                        show_progress_bar=False
                    )
                    
                    # Obtener dimensión del embedding
                    embedding_dim = embedding.size(-1)
                    logger.info(f"Dimensión de embedding detectada: {embedding_dim}")
                    logger.info(f"Modelo verificado exitosamente en {device}")
                    
                    # Importante: NO eliminamos el modelo, lo devolvemos para reutilizarlo
                    # Solo liberamos el embedding de prueba
                    del embedding
                    
                    # Devolvemos la instancia del modelo y la dimensión del vector
                    return {
                        "model_instance": sentence_model,
                        "vector_dim": embedding_dim
                    }
                except Exception as e:
                    logger.error(f"Error cargando modelo: {e}", exc_info=True)
                    raise
            
            # Cargar el modelo de forma asíncrona
            model_data = await asyncio.to_thread(load_actual_model)
            
            # Obtener la instancia del modelo y la dimensión del vector
            sentence_model = model_data["model_instance"]
            vector_dim = model_data["vector_dim"]
            
            logger.info(f"Modelo Nomic cargado exitosamente con SentenceTransformer: {model_name}")
            
            if self.gpu_available:
                logger.info(f"Nomic utilizará GPU en dispositivo: {self.device}")
            
            # Obtener versión de transformers
            try:
                import transformers
                transformers_version = getattr(transformers, "__version__", "desconocida")
            except ImportError:
                transformers_version = "no disponible"
            
            # Devolver diccionario con la instancia del modelo y metadatos
            return {
                "model_type": "nomic",
                "model_name": model_name,
                "model_instance": sentence_model,  # IMPORTANTE: Ahora devolvemos la instancia real del modelo
                "vector_dim": vector_dim,
                "version": transformers_version,
                "cache_dir": cache_dir
            }
        except Exception as e:
            logger.error(f"Error cargando modelo Nomic con SentenceTransformer: {e}", exc_info=True)
            raise

    def _update_vector_size(self):
        """Registra información sobre la dimensión del vector para el modelo de embedding y la base de datos vectorial"""
        if EmbeddingType.GENERAL in self.models:
            vector_dim = self.models[EmbeddingType.GENERAL]["vector_dim"]
            model_type = self.models[EmbeddingType.GENERAL].get("model_type", "desconocido")
            model_name = self.models[EmbeddingType.GENERAL].get("model_name", "desconocido")
            
            # Verificar si las dimensiones son válidas
            if vector_dim is None or vector_dim <= 0:
                logger.warning(f"Dimensión de vector inválida: {vector_dim} para modelo {model_name}")
                vector_dim = 1024  # Valor predeterminado para Nomic
            
            # Esta información es útil para diagnóstico y verificación de compatibilidad
            logger.info(f"Vector dimension detectada: {vector_dim} (modelo {model_type}: {model_name})")
            logger.info(f"Base de datos vectorial: {self.settings.vector_db} configurada para manejar vectores de {vector_dim} dimensiones")

    async def close(self):
        """Liberar recursos del servicio - limpieza adecuada de modelos cargados"""
        # Liberar modelos y GPU si es necesario
        for model_type in self.models:
            model_info = self.models[model_type]
            
            # Liberar la instancia del modelo explícitamente
            if "model_instance" in model_info:
                logger.info(f"Liberando instancia del modelo para {model_type}")
                model_instance = model_info["model_instance"]
                model_info["model_instance"] = None
                del model_instance
            
            # Limpiar el resto de la información
            model_info.clear()

        # Limpiar diccionario de modelos
        self.models.clear()

        if self.gpu_available:
            # Limpiar caché de CUDA
            torch.cuda.empty_cache()
            logger.info("Instancias de modelos y recursos de GPU liberados correctamente")

    def _get_model(self, embedding_type: EmbeddingType) -> Dict[str, Any]:
        """Obtener modelo para el tipo de embedding especificado"""
        model_info = self.models.get(embedding_type)
        if not model_info:
            logger.error(f"Modelo no inicializado para el tipo de embedding: {embedding_type}")
            raise HTTPException(status_code=500, detail=f"Modelo no inicializado para el tipo de embedding: {embedding_type}")
        return model_info

    async def create_embedding(self,
                               text: str,
                               embedding_type: EmbeddingType,
                               doc_id: str,
                               owner_id: str,
                               area_id: Optional[str] = None,
                               metadata: Optional[Dict[str, Any]] = None) -> EmbeddingResponse:
        """Generar y almacenar un embedding para un texto"""
        # Obtener modelo para el tipo de embedding
        model_info = self._get_model(embedding_type)

        # Generar embedding de forma asíncrona para no bloquear el bucle de eventos
        vector = await self._generate_embedding(text, model_info)
        vector_list = vector.tolist()

        # Preparar metadatos
        meta = metadata.copy() if metadata else {}
        if "doc_id" not in meta:
            meta["doc_id"] = doc_id
        if "owner_id" not in meta:
            meta["owner_id"] = owner_id
        if area_id and "area_id" not in meta:
            meta["area_id"] = area_id

        # Almacenar vector en la base de datos vectorial
        vector_id = await self.vectordb_service.store_vector(
            vector=vector_list,
            embedding_type=embedding_type,
            doc_id=doc_id,
            owner_id=owner_id,
            text=text[:1000],  # Guardar un fragmento del texto
            area_id=area_id,
            metadata=meta
        )

        # Generar ID único para el embedding
        embedding_id = str(uuid.uuid4())

        # Preparar documento para MongoDB
        embedding_db = {
            "embedding_id": embedding_id,
            "doc_id": doc_id,
            "embedding_type": embedding_type,
            "owner_id": owner_id,
            "area_id": area_id,
            "vector_id": vector_id,
            "collection_name": self.vectordb_service._get_collection_for_type(embedding_type),
            "text_snippet": text[:500],  # Guardar un fragmento como referencia
            "created_at": datetime.utcnow(),
            "metadata": meta
        }

        # Almacenar referencia en MongoDB
        await self.collection.insert_one(embedding_db)

        # Crear respuesta
        return EmbeddingResponse(
            embedding_id=embedding_id,
            doc_id=doc_id,
            embedding_type=embedding_type,
            owner_id=owner_id,
            area_id=area_id,
            created_at=embedding_db["created_at"],
            status="success",
            metadata=meta
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((RuntimeError, ConnectionError, TimeoutError)),
        retry_error_callback=lambda retry_state: logger.error(f"Failed embedding generation after {retry_state.attempt_number} attempts")
    )
    async def _generate_embedding(self,
                                  text: str,
                                  model_info: Dict[str, Any]) -> torch.Tensor:
        """
        Genera embedding para un texto usando el modelo Nomic v1.5 con SentenceTransformer.
        Usa la instancia precargada del modelo para mayor eficiencia.
        Con reintentos automáticos en caso de fallos transitorios.

        Args:
            text: Texto a convertir en embedding
            model_info: Información del modelo cargado, incluye la instancia SentenceTransformer

        Returns:
            Vector de embedding normalizado
        """
        try:
            # Verificar disponibilidad de GPU si es obligatoria
            if self.device == "cpu" and not self.settings.models.fallback_to_cpu:
                raise RuntimeError("GPU requerida para generar embeddings pero solo CPU disponible.")
            
            # Importante: Obtener la instancia del modelo ya cargada
            sentence_model = model_info.get("model_instance")
            if sentence_model is None:
                raise ValueError("Instancia de modelo no disponible - inicialización incorrecta")
            
            # Generar embeddings usando la instancia precargada del modelo
            def generate_nomic_embedding(model, input_text):
                try:
                    # Añadir prefijo de instrucción según recomendación de Nomic si no existe ya
                    # 'search_document:' para textos que serán almacenados
                    # 'search_query:' para consultas de búsqueda
                    if input_text.startswith("search_query:") or input_text.startswith("search_document:"):
                        prefixed_text = input_text  # Ya tiene el prefijo correcto
                    else:
                        prefixed_text = f"search_document: {input_text}"  # Por defecto usar search_document
                    
                    # Generar embedding usando el modelo precargado (más eficiente)
                    embedding = model.encode(
                        prefixed_text, 
                        convert_to_tensor=True,
                        show_progress_bar=False
                    )
                    
                    # Normalizar para consistencia (aunque SentenceTransformer ya lo hace)
                    normalized = torch.nn.functional.normalize(embedding, p=2, dim=0)
                    
                    # Mover a CPU para procesamiento posterior
                    normalized = normalized.cpu()
                    
                    # NO destruimos el modelo, solo la representación intermedia
                    del embedding
                    
                    return normalized
                except Exception as e:
                    logger.error(f"Error en generate_nomic_embedding: {e}", exc_info=True)
                    raise
            
            # Ejecutar de forma asíncrona - pasamos la instancia del modelo
            result = await asyncio.to_thread(generate_nomic_embedding, sentence_model, text)
            return result
        except Exception as e:
            logger.error(f"Error generando embedding con Nomic/SentenceTransformer: {e}", exc_info=True)
            raise

    async def create_embeddings_batch(self,
                                      texts: List[str],
                                      embedding_type: EmbeddingType,
                                      doc_ids: List[str],
                                      owner_id: str,
                                      area_id: Optional[str] = None,
                                      metadata: Optional[Dict[str, Any]] = None) -> List[EmbeddingResponse]:
        """Generar y almacenar embeddings para múltiples textos en batch (optimizado para RTX 4090)"""
        # Verificar que las listas tienen el mismo tamaño
        if len(texts) != len(doc_ids):
            logger.error("Las listas de textos y doc_ids tienen diferente tamaño")
            raise HTTPException(status_code=400, detail="Las listas de textos y doc_ids deben tener el mismo tamaño")

        # Limitar número de textos por batch
        if len(texts) > self.settings.max_texts_per_batch:
            logger.error(f"Número máximo de textos por batch excedido: {len(texts)} > {self.settings.max_texts_per_batch}")
            raise HTTPException(status_code=400, detail=f"Número máximo de textos por batch excedido: {len(texts)} > {self.settings.max_texts_per_batch}")

        # Obtener modelo para el tipo de embedding
        model_info = self._get_model(embedding_type)
        
        # Verificar disponibilidad de GPU si es obligatoria
        if self.device == "cpu" and not self.settings.models.fallback_to_cpu:
            raise RuntimeError("GPU requerida para generar embeddings batch pero solo CPU disponible.")
        
        # Importante: Obtener la instancia del modelo ya cargada
        sentence_model = model_info.get("model_instance")
        if sentence_model is None:
            raise ValueError("Instancia de modelo no disponible - inicialización incorrecta")
        
        # Procesamiento por lotes con la instancia de SentenceTransformer ya cargada
        try:
            # Función para generar embeddings en batch con el modelo precargado
            def generate_nomic_batch(model, input_texts):
                try:
                    # Añadir prefijo de instrucción a todos los textos que no lo tengan ya
                    prefixed_texts = []
                    for t in input_texts:
                        if t.startswith("search_query:") or t.startswith("search_document:"):
                            prefixed_texts.append(t)  # Ya tiene el prefijo correcto
                        else:
                            prefixed_texts.append(f"search_document: {t}")  # Por defecto
                    
                    # Usar el batch_size configurado - optimizado para RTX 4090 (128)
                    batch_size = self.settings.models.batch_size
                    
                    logger.info(f"Procesando embeddings batch con modelo precargado (total: {len(input_texts)} textos)")
                    logger.info(f"Usando batch_size={batch_size} optimizado para RTX 4090")
                    
                    # Generar embeddings en batch con el modelo precargado - mucho más eficiente
                    embeddings = model.encode(
                        prefixed_texts,
                        batch_size=batch_size,
                        convert_to_tensor=True,
                        show_progress_bar=True  # Mostrar progreso en batches grandes
                    )
                    
                    # Normalizar y convertir a CPU
                    all_embeddings = [torch.nn.functional.normalize(emb, p=2, dim=0).cpu() for emb in embeddings]
                    
                    # Liberar memoria de tensores temporales (pero NO el modelo)
                    del embeddings
                    
                    logger.info(f"Generados {len(all_embeddings)} vectores. Dimensión: {all_embeddings[0].shape if all_embeddings else 'N/A'}")
                    
                    return all_embeddings
                except Exception as e:
                    logger.error(f"Error en generate_nomic_batch: {e}", exc_info=True)
                    raise
            
            # Ejecutar de forma asíncrona - pasamos el modelo precargado
            vectors = await asyncio.to_thread(generate_nomic_batch, sentence_model, texts)
            
        except Exception as e:
            logger.error(f"Error generando embeddings batch con Nomic/SentenceTransformer: {e}", exc_info=True)
            raise

        # Convertir a listas de Python
        vector_lists = [vector.tolist() for vector in vectors]

        # Preparar metadatos base
        meta = metadata.copy() if metadata else {}
        if "owner_id" not in meta:
            meta["owner_id"] = owner_id
        if area_id and "area_id" not in meta:
            meta["area_id"] = area_id

        # Almacenar vectores en batch
        vector_ids = await self.vectordb_service.store_vectors_batch(
            vectors=vector_lists,
            embedding_type=embedding_type,
            doc_ids=doc_ids,
            owner_id=owner_id,
            texts=[text[:1000] for text in texts],  # Guardar fragmentos
            area_id=area_id,
            metadata=meta
        )

        # Preparar documentos para MongoDB y respuestas
        responses: List[EmbeddingResponse] = []
        collection_name = self.vectordb_service._get_collection_for_type(embedding_type)

        for i, (text, doc_id, vector_id) in enumerate(zip(texts, doc_ids, vector_ids)):
            # Generar ID único para cada embedding
            embedding_id = str(uuid.uuid4())

            # Clonar metadatos y añadir doc_id específico
            item_meta = meta.copy()
            item_meta["doc_id"] = doc_id

            # Preparar documento para MongoDB
            embedding_db = {
                "embedding_id": embedding_id,
                "doc_id": doc_id,
                "embedding_type": embedding_type,
                "owner_id": owner_id,
                "area_id": area_id,
                "vector_id": vector_id,
                "collection_name": collection_name,
                "text_snippet": text[:500],  # Guardar un fragmento
                "created_at": datetime.utcnow(),
                "metadata": item_meta
            }

            # Almacenar referencia en MongoDB
            await self.collection.insert_one(embedding_db)

            # Crear respuesta
            response = EmbeddingResponse(
                embedding_id=embedding_id,
                doc_id=doc_id,
                embedding_type=embedding_type,
                owner_id=owner_id,
                area_id=area_id,
                created_at=embedding_db["created_at"],
                status="success",
                metadata=item_meta
            )
            responses.append(response)

        return responses

    async def create_document_embedding(self,
                                        document: bytes,
                                        filename: str,
                                        content_type: str,
                                        embedding_type: EmbeddingType,
                                        doc_id: str,
                                        owner_id: str,
                                        area_id: Optional[str] = None,
                                        metadata: Optional[Dict[str, Any]] = None) -> EmbeddingResponse:
        """Generar y almacenar embedding para un documento"""
        # Verificar tamaño máximo
        max_size = self.settings.max_document_size_mb * 1024 * 1024
        if len(document) > max_size:
            logger.error(f"Tamaño de documento excedido: {len(document)} bytes > {max_size} bytes")
            raise HTTPException(status_code=413, detail=f"Tamaño de documento excedido: {len(document)} bytes > {max_size} bytes")

        # Extraer texto del documento según su tipo
        text = await self._extract_text_from_document(document, filename, content_type)
        if not text:
            logger.error(f"No se pudo extraer texto del documento: {filename}")
            raise HTTPException(status_code=422, detail=f"No se pudo extraer texto del documento: {filename}")

        # Preparar metadatos
        meta = metadata.copy() if metadata else {}
        meta.update({
            "filename": filename,
            "content_type": content_type,
            "file_size": len(document)
        })

        # Si el texto es muy largo, dividirlo en chunks optimizados para BGE/E5
        if len(text) > self.settings.chunk_size:
            chunks = self._chunk_text(text, self.settings.chunk_size, self.settings.chunk_overlap)

            # Crear embeddings para cada chunk
            embedding_responses: List[EmbeddingResponse] = []
            for i, chunk in enumerate(chunks):
                # Añadir información de chunk a los metadatos
                chunk_meta = meta.copy()
                chunk_meta.update({
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                })

                # Crear embedding para el chunk
                response = await self.create_embedding(
                    text=chunk,
                    embedding_type=embedding_type,
                    doc_id=doc_id,
                    owner_id=owner_id,
                    area_id=area_id,
                    metadata=chunk_meta
                )
                embedding_responses.append(response)

            # Devolver el primer embedding como principal
            if embedding_responses:
                main_response = embedding_responses[0]
                main_response.metadata["total_chunks"] = len(chunks)
                main_response.metadata["has_chunks"] = True
                return main_response

            # Si por alguna razón no se generaron embeddings
            raise HTTPException(status_code=500, detail="Error al generar embeddings para los chunks del documento")
        else:
            # Crear un solo embedding para todo el documento
            return await self.create_embedding(
                text=text,
                embedding_type=embedding_type,
                doc_id=doc_id,
                owner_id=owner_id,
                area_id=area_id,
                metadata=meta
            )

    async def _extract_text_from_document(self, document: bytes, filename: str, content_type: str) -> str:
        """Extraer texto de un documento según su tipo"""
        # Detectar tipo de archivo por extensión y content_type
        ext = os.path.splitext(filename)[1].lower()

        if content_type == "text/plain" or ext in [".txt", ".text"]:
            # Texto plano
            try:
                return document.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    return document.decode("latin-1")
                except Exception as e:
                    logger.error(f"Error decodificando texto: {e}")
                    raise HTTPException(status_code=422, detail=f"Error decodificando texto: {e}")

        elif content_type == "application/pdf" or ext == ".pdf":
            # Usar la bandera de soporte PDF para decidir el comportamiento
            if not self.pdf_support:
                logger.warning(f"Procesamiento de PDF no disponible para: {filename}")
                return f"[Contenido de PDF no soportado: {filename}]"
            try:
                import PyPDF2
                from io import BytesIO

                def read_pdf(doc_bytes: bytes) -> str:
                    reader = PyPDF2.PdfReader(BytesIO(doc_bytes))
                    text_content = ""
                    for page in reader.pages:
                        # page.extract_text() puede devolver None si no se pudo extraer contenido
                        text_page = page.extract_text() or ""
                        text_content += text_page + "\n"
                    return text_content

                text = await asyncio.to_thread(read_pdf, document)
                return text
            except Exception as e:
                logger.error(f"Error extrayendo texto de PDF: {e}")
                return f"[Error en contenido de PDF: {filename}]"

        elif content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"] or ext in [".doc", ".docx"]:
            # Usar la bandera de soporte DOCX para decidir el comportamiento
            if not self.docx_support:
                logger.warning(f"Procesamiento de documentos Word no disponible para: {filename}")
                return f"[Contenido de Word no soportado: {filename}]"
            try:
                import docx
                from io import BytesIO

                def read_docx(doc_bytes: bytes) -> str:
                    doc = docx.Document(BytesIO(doc_bytes))
                    text_content = ""
                    for para in doc.paragraphs:
                        text_content += para.text + "\n"
                    return text_content

                text = await asyncio.to_thread(read_docx, document)
                return text
            except Exception as e:
                logger.error(f"Error extrayendo texto de Word: {e}")
                return f"[Error en contenido de Word: {filename}]"

        else:
            # Para otros tipos, devolver un mensaje de error
            logger.warning(f"Tipo de documento no soportado: {content_type}, {ext}")
            return f"[Documento no soportado: {filename}, {content_type}]"

    def _chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """
        Dividir texto en chunks con superposición optimizada para modelos BGE/E5

        Args:
            text: Texto a dividir
            chunk_size: Tamaño máximo de cada chunk en caracteres
            chunk_overlap: Número de caracteres de superposición entre chunks

        Returns:
            Lista de chunks de texto
        """
        chunks: List[str] = []
        start = 0

        # Ajustar para tamaño óptimo de BGE/E5
        max_chars = min(chunk_size, 2048)  # Aproximadamente 512 tokens para modelos BGE/E5

        while start < len(text):
            # Calcular el final del chunk
            end = min(start + max_chars, len(text))

            # Ajustar final para no cortar en medio de una palabra
            if end < len(text):
                # Buscar el próximo espacio después del final
                next_space = text.find(" ", end)
                if next_space != -1 and next_space - end < 20:  # No buscar demasiado lejos
                    end = next_space
                else:
                    # Buscar el último espacio antes del final
                    last_space = text.rfind(" ", start, end)
                    if last_space != -1 and end - last_space < chunk_size / 4:  # No perder demasiado texto
                        end = last_space

            # Extraer el chunk
            chunk = text[start:end].strip()

            # Añadir a la lista si no está vacío
            if chunk:
                chunks.append(chunk)

            # Calcular el próximo punto de inicio con superposición
            start = end - chunk_overlap

            # Asegurarse de que avancemos al menos un carácter
            if start >= end:
                start = end + 1

        return chunks

    async def get_embedding(self, embedding_id: str) -> Optional[Dict[str, Any]]:
        """Obtener información de un embedding por su ID"""
        # Buscar en la base de datos
        embedding_doc = await self.collection.find_one({"embedding_id": embedding_id})
        if not embedding_doc:
            return None

        # Convertir ObjectId a string si es necesario
        if "_id" in embedding_doc:
            embedding_doc["_id"] = str(embedding_doc["_id"])

        return embedding_doc

    async def delete_embedding(self, embedding_id: str) -> bool:
        """Eliminar un embedding y su vector asociado"""
        # Buscar en la base de datos
        embedding_doc = await self.collection.find_one({"embedding_id": embedding_id})
        if not embedding_doc:
            return False

        # Eliminar vector de la base de datos vectorial
        embedding_type = embedding_doc.get("embedding_type")
        vector_id = embedding_doc.get("vector_id")

        if embedding_type and vector_id:
            try:
                await self.vectordb_service.delete_vector(vector_id, embedding_type)
            except Exception as e:
                logger.error(f"Error eliminando vector {vector_id}: {e}")

        # Eliminar referencia de MongoDB
        result = await self.collection.delete_one({"embedding_id": embedding_id})
        return result.deleted_count > 0

    async def search(self,
                     query: str,
                     embedding_type: EmbeddingType,
                     owner_id: Optional[str] = None,
                     area_id: Optional[str] = None,
                     limit: int = 10) -> List[Dict[str, Any]]:
        """Buscar textos similares a la consulta usando Nomic v1.5"""
        # Obtener modelo para el tipo de embedding
        model_info = self._get_model(embedding_type)

        # Agregar prefijo especial search_query para consultas (recomendado por Nomic)
        # Esto optimiza el embedding para búsqueda
        if not query.startswith("search_query:"):
            query = f"search_query: {query}"
            logger.info(f"Prefijo de búsqueda añadido a la consulta: '{query}'")

        # Generar embedding para la consulta
        query_vector = await self._generate_embedding(query, model_info)
        query_vector_list = query_vector.tolist()

        # Realizar búsqueda en la base de datos vectorial
        results = await self.vectordb_service.search(
            query_vector=query_vector_list,
            embedding_type=embedding_type,
            owner_id=owner_id,
            area_id=area_id,
            limit=limit
        )

        # Log para debug
        if results:
            logger.info(f"Búsqueda con Nomic v1.5 encontró {len(results)} resultados. " +
                       f"Mejor score: {results[0].score:.4f}")
        else:
            logger.info("La búsqueda no encontró resultados.")

        # Convertir a formato de respuesta simple
        return [
            {
                "doc_id": result.doc_id,
                "score": result.score,
                "text": result.text,
                "metadata": result.metadata
            }
            for result in results
        ]

    async def check_context_service_health(self) -> Tuple[bool, dict]:
        """Verificar la disponibilidad del servicio de contexto MCP"""
        url = f"{self.settings.mcp_service_url}/health"
        try:
            if self.settings.use_httpx:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        logger.info("Context service health check successful")
                        return True, data
                    else:
                        logger.error(f"Context service health check failed with status {response.status_code}")
                        return False, {"status": "error", "code": response.status_code, "message": "MCP service health check failed"}
            else:
                import aiohttp
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10.0)) as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info("Context service health check successful")
                            return True, data
                        else:
                            logger.error(f"Context service health check failed with status {response.status}")
                            return False, {"status": "error", "code": response.status, "message": "MCP service health check failed"}
        except Exception as e:
            logger.error(f"Critical error: Context service not available: {e}")
            return False, {"status": "error", "error": str(e), "message": "MCP service unavailable"}

    async def list_contexts(self) -> List[Dict[str, Any]]:
        """Listar contextos MCP disponibles"""
        # Verificar la disponibilidad del servicio de contexto
        service_available, error_info = await self.check_context_service_health()
        
        if not service_available:
            error_message = error_info.get("message", "Unknown error")
            logger.error(f"Critical dependency error: Context service not available - {error_message}")
            raise HTTPException(
                status_code=503, 
                detail={
                    "error": "MCP Context Service unavailable",
                    "details": error_info,
                    "message": "The MCP Context Service is required for proper operation of the embedding service"
                }
            )
        
        # Conexión con el servicio de contexto MCP
        try:
            if self.settings.use_httpx:
                import httpx
                async with httpx.AsyncClient(timeout=self.settings.mcp_service_timeout) as client:
                    response = await client.get(f"{self.settings.mcp_service_url}/contexts")
                    if response.status_code == 200:
                        return response.json()
                    else:
                        logger.error(f"Error al listar contextos: {response.status_code}")
                        raise HTTPException(
                            status_code=response.status_code, 
                            detail=f"Error listing contexts from MCP service: {response.text}"
                        )
            else:
                import aiohttp
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.settings.mcp_service_timeout)) as session:
                    async with session.get(f"{self.settings.mcp_service_url}/contexts") as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            logger.error(f"Error al listar contextos: {response.status} - {error_text}")
                            raise HTTPException(
                                status_code=response.status, 
                                detail=f"Error listing contexts from MCP service: {error_text}"
                            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error conectando con el servicio de contexto: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error connecting to MCP Context Service: {str(e)}"
            )

    async def activate_context(self, context_id: str) -> Dict[str, Any]:
        """Activar un contexto MCP"""
        # Verificar la disponibilidad del servicio de contexto
        service_available, error_info = await self.check_context_service_health()
        
        if not service_available:
            error_message = error_info.get("message", "Unknown error")
            logger.error(f"Critical dependency error: Context service not available - {error_message}")
            raise HTTPException(
                status_code=503, 
                detail={
                    "error": "MCP Context Service unavailable",
                    "details": error_info,
                    "message": f"Unable to activate context {context_id}: MCP service is required for this operation"
                }
            )
        
        try:
            if self.settings.use_httpx:
                import httpx
                async with httpx.AsyncClient(timeout=self.settings.mcp_service_timeout) as client:
                    response = await client.post(f"{self.settings.mcp_service_url}/contexts/{context_id}/activate")
                    if response.status_code == 200:
                        return response.json()
                    else:
                        error_text = response.text
                        logger.error(f"Error al activar contexto: {response.status_code} - {error_text}")
                        raise HTTPException(
                            status_code=response.status_code, 
                            detail=f"Error activating context {context_id}: {error_text}"
                        )
            else:
                import aiohttp
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.settings.mcp_service_timeout)) as session:
                    async with session.post(f"{self.settings.mcp_service_url}/contexts/{context_id}/activate") as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            logger.error(f"Error al activar contexto: {response.status} - {error_text}")
                            raise HTTPException(
                                status_code=response.status, 
                                detail=f"Error activating context {context_id}: {error_text}"
                            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error connecting to context service when activating context {context_id}: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error activating context {context_id}: Unable to connect to MCP Context Service: {str(e)}"
            )

    async def deactivate_context(self, context_id: str) -> Dict[str, Any]:
        """Desactivar un contexto MCP"""
        # Verificar la disponibilidad del servicio de contexto
        service_available, error_info = await self.check_context_service_health()
        
        if not service_available:
            error_message = error_info.get("message", "Unknown error")
            logger.error(f"Critical dependency error: Context service not available - {error_message}")
            raise HTTPException(
                status_code=503, 
                detail={
                    "error": "MCP Context Service unavailable",
                    "details": error_info,
                    "message": f"Unable to deactivate context {context_id}: MCP service is required for this operation"
                }
            )
        
        try:
            if self.settings.use_httpx:
                import httpx
                async with httpx.AsyncClient(timeout=self.settings.mcp_service_timeout) as client:
                    response = await client.post(f"{self.settings.mcp_service_url}/contexts/{context_id}/deactivate")
                    if response.status_code == 200:
                        return response.json()
                    else:
                        error_text = response.text
                        logger.error(f"Error al desactivar contexto: {response.status_code} - {error_text}")
                        raise HTTPException(
                            status_code=response.status_code, 
                            detail=f"Error deactivating context {context_id}: {error_text}"
                        )
            else:
                import aiohttp
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.settings.mcp_service_timeout)) as session:
                    async with session.post(f"{self.settings.mcp_service_url}/contexts/{context_id}/deactivate") as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            logger.error(f"Error al desactivar contexto: {response.status} - {error_text}")
                            raise HTTPException(
                                status_code=response.status, 
                                detail=f"Error deactivating context {context_id}: {error_text}"
                            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error connecting to context service when deactivating context {context_id}: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error deactivating context {context_id}: Unable to connect to MCP Context Service: {str(e)}"
            )