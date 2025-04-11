import logging
import uuid
import os
import asyncio
import gc
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union

import torch
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

        # Variables para el modelo actual (único activo)
        self.current_model_name: Optional[str] = None
        self.current_model_instance: Optional[SentenceTransformer] = None
        self.current_model_dim: Optional[int] = None
        self.model_change_lock = asyncio.Lock()  # Lock para proteger cambios de modelo

        # Estado de GPU
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
        """Inicializar modelo de embedding por defecto"""
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

            # Cargar el modelo por defecto
            default_model = self.settings.models.default_model_name
            logger.info(f"Cargando modelo de embedding por defecto: {default_model}")
            await self._load_and_set_model(default_model)

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

    async def _load_and_set_model(self, model_name: str) -> bool:
        """
        Cargar y configurar un modelo específico como el modelo activo

        Args:
            model_name: Nombre del modelo a cargar desde HuggingFace

        Returns:
            True si se cargó correctamente, False en caso contrario
        """
        try:
            # Crear directorio para caché si no existe
            cache_dir = "./modelos"
            os.makedirs(cache_dir, exist_ok=True)

            logger.info(f"Cargando modelo {model_name}...")

            # Ejecutar en un thread separado para no bloquear
            def load_actual_model():
                try:
                    # Usar el dispositivo configurado
                    device = self.device

                    # Verificación final de disponibilidad de GPU
                    if device == "cpu" and not self.settings.models.fallback_to_cpu and self.settings.models.use_gpu:
                        raise RuntimeError("GPU requerida pero solo CPU disponible y fallback desactivado.")

                    # Cargar modelo usando SentenceTransformer
                    logger.info(f"Cargando modelo {model_name} en {device}...")
                    sentence_model = SentenceTransformer(
                        model_name,
                        cache_folder=cache_dir,
                        device=device,
                        trust_remote_code=True
                    )

                    # Verificar modelo con una entrada simple
                    test_text = "Prueba de modelo"
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

                    # Liberar embedding de prueba
                    del embedding

                    # Devolver la instancia y dimensión
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

            # Establecer como modelo actual
            self.current_model_name = model_name
            self.current_model_instance = sentence_model
            self.current_model_dim = vector_dim

            logger.info(f"Modelo {model_name} cargado y establecido como modelo activo")
            logger.info(f"Dimensión de vector: {vector_dim}")

            return True

        except Exception as e:
            logger.error(f"Error cargando modelo {model_name}: {e}", exc_info=True)
            return False

    async def _unload_current_model(self) -> None:
        """Descargar el modelo actual para liberar memoria"""
        if self.current_model_instance is None:
            logger.info("No hay modelo activo para descargar")
            return

        try:
            logger.info(f"Descargando modelo actual: {self.current_model_name}")

            # Guardar nombre para el log
            model_name = self.current_model_name

            # Eliminar referencias
            model_instance = self.current_model_instance
            self.current_model_instance = None
            self.current_model_name = None
            self.current_model_dim = None

            # Forzar eliminación del modelo
            del model_instance

            # Forzar recolección de basura
            gc.collect()

            # Liberar caché de CUDA si hay GPU
            if self.gpu_available and torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("Memoria GPU liberada")

            logger.info(f"Modelo {model_name} descargado correctamente")

        except Exception as e:
            logger.error(f"Error descargando modelo: {e}")
            # No re-lanzar excepción para permitir la carga del nuevo modelo

    async def change_active_model(self, new_model_name: str) -> bool:
        """
        Cambiar el modelo activo por uno nuevo

        Args:
            new_model_name: Nombre del nuevo modelo a cargar

        Returns:
            True si se cambió correctamente, False en caso contrario
        """
        # Adquirir lock para proteger el proceso de cambio
        async with self.model_change_lock:
            # Si es el mismo modelo, no hacer nada
            if new_model_name == self.current_model_name:
                logger.info(f"El modelo {new_model_name} ya está activo")
                return True

            # Descargar modelo actual
            await self._unload_current_model()

            # Cargar nuevo modelo
            success = await self._load_and_set_model(new_model_name)

            if success:
                logger.info(f"Cambio de modelo exitoso: {new_model_name}")
                # Aquí podríamos emitir un evento o actualizar métricas sobre el cambio
            else:
                logger.error(f"Error al cambiar al modelo {new_model_name}")
                # Intentar volver al modelo por defecto si fallamos
                default_model = self.settings.models.default_model_name
                if default_model != new_model_name:
                    logger.info(f"Intentando volver al modelo por defecto: {default_model}")
                    await self._load_and_set_model(default_model)

            return success

    async def close(self):
        """Liberar recursos del servicio"""
        # Eliminar modelo activo
        await self._unload_current_model()

    def _get_model_instance(self) -> Optional[SentenceTransformer]:
        """Obtener la instancia del modelo activo"""
        if self.current_model_instance is None:
            logger.error("No hay un modelo de embedding activo")
            raise HTTPException(status_code=500, detail="No hay un modelo de embedding activo inicializado")
        return self.current_model_instance

    async def create_embedding(self,
                               text: str,
                               embedding_type: EmbeddingType,
                               doc_id: str,
                               owner_id: str,
                               area_id: Optional[str] = None,
                               metadata: Optional[Dict[str, Any]] = None) -> EmbeddingResponse:
        """Generar y almacenar un embedding para un texto"""
        # Verificar que hay un modelo activo
        model_instance = self._get_model_instance()

        # Generar embedding de forma asíncrona
        vector = await self._generate_embedding(text, model_instance)
        vector_list = vector.tolist()

        # Preparar metadatos
        meta = metadata.copy() if metadata else {}
        if "doc_id" not in meta:
            meta["doc_id"] = doc_id
        if "owner_id" not in meta:
            meta["owner_id"] = owner_id
        if area_id and "area_id" not in meta:
            meta["area_id"] = area_id

        # Añadir información del modelo
        meta["model_name"] = self.current_model_name
        meta["vector_dim"] = self.current_model_dim

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
            "metadata": meta,
            "model_name": self.current_model_name  # Guardar qué modelo generó este embedding
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
                                  model_instance: SentenceTransformer) -> torch.Tensor:
        """
        Genera embedding para un texto usando el modelo activo
        Con reintentos automáticos en caso de fallos transitorios.

        Args:
            text: Texto a convertir en embedding
            model_instance: Instancia del modelo SentenceTransformer

        Returns:
            Vector de embedding normalizado
        """
        try:
            # Verificar que tenemos un modelo válido
            if model_instance is None:
                raise ValueError("Instancia de modelo no disponible - inicialización incorrecta")

            # Generar embeddings usando la instancia precargada del modelo
            def generate_embedding(model, input_text):
                try:
                    # Determinar si debemos usar un prefijo para BGE-M3
                    use_prefix = "bge-m3" in self.current_model_name.lower()

                    if use_prefix:
                        # Para BGE-M3, añadir prefijo si no existe ya
                        if input_text.startswith("passage:") or input_text.startswith("query:"):
                            prefixed_text = input_text  # Ya tiene el prefijo correcto
                        else:
                            prefixed_text = f"passage: {input_text}"  # Por defecto usar passage
                    else:
                        # Para otros modelos, no usar prefijo
                        prefixed_text = input_text

                    # Generar embedding
                    embedding = model.encode(
                        prefixed_text,
                        convert_to_tensor=True,
                        show_progress_bar=False
                    )

                    # Normalizar para consistencia
                    normalized = torch.nn.functional.normalize(embedding, p=2, dim=0)

                    # Mover a CPU para procesamiento posterior
                    normalized = normalized.cpu()

                    return normalized
                except Exception as e:
                    logger.error(f"Error generando embedding: {e}", exc_info=True)
                    raise

            # Ejecutar de forma asíncrona
            result = await asyncio.to_thread(generate_embedding, model_instance, text)
            return result
        except Exception as e:
            logger.error(f"Error generando embedding: {e}", exc_info=True)
            raise

    async def create_embeddings_batch(self,
                                      texts: List[str],
                                      embedding_type: EmbeddingType,
                                      doc_ids: List[str],
                                      owner_id: str,
                                      area_id: Optional[str] = None,
                                      metadata: Optional[Dict[str, Any]] = None) -> List[EmbeddingResponse]:
        """Generar y almacenar embeddings para múltiples textos en batch"""
        # Verificar que las listas tienen el mismo tamaño
        if len(texts) != len(doc_ids):
            logger.error("Las listas de textos y doc_ids tienen diferente tamaño")
            raise HTTPException(status_code=400, detail="Las listas de textos y doc_ids deben tener el mismo tamaño")

        # Limitar número de textos por batch
        if len(texts) > self.settings.max_texts_per_batch:
            logger.error(f"Número máximo de textos por batch excedido: {len(texts)} > {self.settings.max_texts_per_batch}")
            raise HTTPException(status_code=400, detail=f"Número máximo de textos por batch excedido: {len(texts)} > {self.settings.max_texts_per_batch}")

        # Verificar que hay un modelo activo
        model_instance = self._get_model_instance()

        # Procesamiento por lotes
        try:
            # Función para generar embeddings en batch
            def generate_batch(model, input_texts):
                try:
                    # Determinar si debemos usar un prefijo para BGE-M3
                    use_prefix = "bge-m3" in self.current_model_name.lower()

                    # Preparar textos con prefijos si es necesario
                    prefixed_texts = []
                    for t in input_texts:
                        if use_prefix:
                            if t.startswith("passage:") or t.startswith("query:"):
                                prefixed_texts.append(t)  # Ya tiene el prefijo correcto
                            else:
                                prefixed_texts.append(f"passage: {t}")  # Por defecto
                        else:
                            prefixed_texts.append(t)  # Sin prefijo

                    # Usar el batch_size configurado
                    batch_size = self.settings.models.batch_size

                    logger.info(f"Procesando embeddings batch con modelo {self.current_model_name} (total: {len(input_texts)} textos)")
                    logger.info(f"Usando batch_size={batch_size}")

                    # Generar embeddings en batch
                    embeddings = model.encode(
                        prefixed_texts,
                        batch_size=batch_size,
                        convert_to_tensor=True,
                        show_progress_bar=True  # Mostrar progreso en batches grandes
                    )

                    # Normalizar y convertir a CPU
                    all_embeddings = [torch.nn.functional.normalize(emb, p=2, dim=0).cpu() for emb in embeddings]

                    # Liberar memoria de tensores temporales
                    del embeddings

                    logger.info(f"Generados {len(all_embeddings)} vectores. Dimensión: {all_embeddings[0].shape if all_embeddings else 'N/A'}")

                    return all_embeddings
                except Exception as e:
                    logger.error(f"Error generando batch de embeddings: {e}", exc_info=True)
                    raise

            # Ejecutar de forma asíncrona
            vectors = await asyncio.to_thread(generate_batch, model_instance, texts)

        except Exception as e:
            logger.error(f"Error generando embeddings batch: {e}", exc_info=True)
            raise

        # Convertir a listas de Python
        vector_lists = [vector.tolist() for vector in vectors]

        # Preparar metadatos base
        meta = metadata.copy() if metadata else {}
        if "owner_id" not in meta:
            meta["owner_id"] = owner_id
        if area_id and "area_id" not in meta:
            meta["area_id"] = area_id

        # Añadir información del modelo
        meta["model_name"] = self.current_model_name
        meta["vector_dim"] = self.current_model_dim

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
                "metadata": item_meta,
                "model_name": self.current_model_name  # Guardar qué modelo generó este embedding
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

        # Si el texto es muy largo, dividirlo en chunks
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
        Dividir texto en chunks con superposición optimizada

        Args:
            text: Texto a dividir
            chunk_size: Tamaño máximo de cada chunk en caracteres
            chunk_overlap: Número de caracteres de superposición entre chunks

        Returns:
            Lista de chunks de texto
        """
        chunks: List[str] = []
        start = 0

        # Ajustar para tamaño óptimo
        max_chars = min(chunk_size, 2048)  # Limitar a 2048 por defecto

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
        """Buscar textos similares a la consulta"""
        # Verificar que hay un modelo activo
        model_instance = self._get_model_instance()

        # Para BGE-M3, añadir prefijo para consultas
        if "bge-m3" in self.current_model_name.lower():
            if not query.startswith("query:"):
                query = f"query: {query}"
                logger.info(f"Prefijo de búsqueda añadido para BGE-M3: '{query}'")

        # Generar embedding para la consulta
        query_vector = await self._generate_embedding(query, model_instance)
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
            logger.info(f"Búsqueda con {self.current_model_name} encontró {len(results)} resultados. " +
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