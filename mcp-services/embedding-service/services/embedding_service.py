import logging
import uuid
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union

import torch
from transformers import AutoModel, AutoTokenizer
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from config.settings import Settings
from models.embedding import (
    EmbeddingRequest, EmbeddingResponse, EmbeddingBatchRequest,
    EmbeddingBatchResponse, EmbeddingType, EmbeddingDB, DocumentChunk
)
from services.vectordb_service import VectorDBService

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Servicio para generar y gestionar embeddings con modelos avanzados"""

    def __init__(self, database: AsyncIOMotorDatabase, vectordb_service: VectorDBService, settings: Settings):
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
        # Comprobar disponibilidad de GPU
        self.gpu_available = torch.cuda.is_available() and self.settings.models.use_gpu

        if self.gpu_available:
            device_count = torch.cuda.device_count()
            device_name = torch.cuda.get_device_name(0) if device_count > 0 else "Desconocida"
            memory_info = torch.cuda.get_device_properties(0).total_memory / (1024**3) if device_count > 0 else 0
            self.gpu_info = f"{device_count} dispositivo(s), {device_name} ({memory_info:.1f} GB)"
            self.device = "cuda:0"
            logger.info(f"Usando GPU: {self.gpu_info}")
        else:
            self.device = "cpu"
            logger.info("Usando CPU para generación de embeddings")

        # Asegurarse de que las colecciones existen en la base de datos vectorial
        await self.vectordb_service.ensure_collections_exist()

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
        """Cargar y optimizar modelo de embeddings"""
        try:
            # Verificar si es un modelo de Nomic
            if "nomic" in model_name.lower():
                try:
                    import nomic
                    from nomic import embed
                    
                    # Los modelos Nomic tienen una dimensión fija de 1024
                    vector_dim = 1024
                    
                    logger.info(f"Cargando modelo Nomic: {model_name}")
                    
                    # Nomic client es diferente a los modelos de HuggingFace
                    return {
                        "model_type": "nomic",
                        "model_name": model_name,
                        "vector_dim": vector_dim,
                        "tokenizer": None  # Nomic maneja su propio tokenizado
                    }
                except ImportError:
                    logger.error("Biblioteca Nomic no está instalada. Instálala con 'pip install nomic'")
                    raise
            else:
                # Cargar tokenizer de HuggingFace
                tokenizer = AutoTokenizer.from_pretrained(model_name)

                # Configurar opciones de carga
                load_options = {}

                # Activar cuantización 8-bit si está configurada
                if self.gpu_available and self.settings.models.use_8bit:
                    try:
                        import bitsandbytes as bnb
                        logger.info(f"Cargando modelo {model_name} con cuantización 8-bit")
                        load_options["load_in_8bit"] = True
                    except ImportError:
                        logger.warning("bitsandbytes no está instalado. Desactivando cuantización 8-bit.")

                # Usar asyncio para no bloquear el bucle de eventos durante la carga
                model = await asyncio.to_thread(
                    AutoModel.from_pretrained, model_name, **load_options
                )

                # Optimizar para inferencia
                model = model.eval()

                # Usar media precisión si está disponible
                if self.gpu_available and self.settings.models.use_fp16:
                    model = model.half()  # FP16 para aumentar el rendimiento

                # Mover el modelo a la GPU si está disponible
                model = model.to(self.device)

                # Obtener dimensión del vector (útil para Qdrant)
                # Para BGE, generalmente es 1024, para E5 podría ser 768
                # Lo obtenemos dinámicamente a partir de la configuración del modelo
                vector_dim = model.config.hidden_size

                logger.info(f"Modelo HuggingFace {model_name} cargado exitosamente. Dimensión del vector: {vector_dim}")

                return {
                    "model_type": "huggingface",
                    "model": model,
                    "tokenizer": tokenizer,
                    "vector_dim": vector_dim
                }
        except Exception as e:
            logger.error(f"Error cargando modelo {model_name}: {e}")
            raise

    def _update_vector_size(self):
        """Actualiza la configuración de tamaño de vector en Qdrant basado en los modelos cargados"""
        if EmbeddingType.GENERAL in self.models:
            vector_dim = self.models[EmbeddingType.GENERAL]["vector_dim"]
            self.settings.qdrant.vector_size = vector_dim
            self.vectordb_service.vector_size = vector_dim
            logger.info(f"Vector dimension actualizada a {vector_dim} para Qdrant")

    async def close(self):
        """Liberar recursos del servicio"""
        # Liberar modelos y GPU si es necesario
        for model_type in self.models:
            self.models[model_type].clear()

        self.models.clear()

        if self.gpu_available:
            # Limpiar caché de CUDA
            torch.cuda.empty_cache()
            logger.info("Recursos de GPU liberados")

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
        Genera embedding para un texto usando el modelo correspondiente (HuggingFace o Nomic)
        Con reintentos automáticos en caso de fallos transitorios.

        Args:
            text: Texto a convertir en embedding
            model_info: Información del modelo cargado

        Returns:
            Vector de embedding normalizado
        """
        model_type = model_info.get("model_type", "huggingface")
        
        # Generar embeddings con Nomic
        if model_type == "nomic":
            try:
                from nomic import embed
                
                # Generar embeddings con la API de Nomic
                def generate_nomic():
                    try:
                        embeddings = embed.text(
                            texts=[text],
                            model_name=model_info["model_name"]
                        )
                        # Convertir a tensor de PyTorch
                        return torch.tensor(embeddings[0])
                    except Exception as e:
                        logger.error(f"Error en generate_nomic: {e}")
                        raise
                
                # Ejecutar de forma asíncrona
                result = await asyncio.to_thread(generate_nomic)
                return result
                
            except Exception as e:
                logger.error(f"Error generando embedding con Nomic: {e}")
                raise
        
        # Generar embeddings con modelos HuggingFace (BGE/E5)
        else:
            max_length = self.settings.models.max_length
            model = model_info["model"]
            tokenizer = model_info["tokenizer"]

            # Tokenizar texto con manejo de errores
            try:
                inputs = tokenizer(
                    text,
                    max_length=max_length,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt"
                )
            except Exception as e:
                logger.error(f"Error al tokenizar texto: {e}")
                # Crear un texto más pequeño y simple si la tokenización falla
                fallback_text = text[:500] if len(text) > 500 else text
                inputs = tokenizer(
                    fallback_text,
                    max_length=max_length // 2,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt"
                )

            # Mover a GPU si está disponible
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Ejecutar en un thread separado para no bloquear el event loop
            def generate_huggingface():
                try:
                    with torch.no_grad():
                        outputs = model(**inputs)
                        # Para modelos BGE/E5, usamos el token [CLS] (primer token)
                        embeddings = outputs.last_hidden_state[:, 0]
                        # Normalizar para similaridad de coseno
                        normalized = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                        return normalized[0].cpu()  # Mover de vuelta a CPU para el resultado
                except Exception as e:
                    logger.error(f"Error en generate_huggingface: {e}")
                    raise

            # Ejecutar de forma asíncrona
            result = await asyncio.to_thread(generate_huggingface)
            return result

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

        # Obtener modelo para el tipo de embedding
        model_info = self._get_model(embedding_type)
        model_type = model_info.get("model_type", "huggingface")
        
        vectors = []
        
        # Manejar diferentes tipos de modelos
        if model_type == "nomic":
            # Procesamiento por lotes con Nomic
            try:
                from nomic import embed
                
                # Nomic maneja eficientemente los batches internamente
                def generate_nomic_batch():
                    embeddings = embed.text(
                        texts=texts,
                        model_name=model_info["model_name"]
                    )
                    # Convertir a tensores de PyTorch
                    return [torch.tensor(emb) for emb in embeddings]
                
                # Ejecutar de forma asíncrona
                vectors = await asyncio.to_thread(generate_nomic_batch)
                
            except Exception as e:
                logger.error(f"Error generando embeddings batch con Nomic: {e}")
                raise
        else:
            # Procesar en batches con modelos HuggingFace para optimizar GPU
            model = model_info["model"]
            tokenizer = model_info["tokenizer"]
            batch_size = min(len(texts), self.settings.models.batch_size)
            
            # Procesar por lotes para aprovechar el hardware
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i+batch_size]

                # Tokenizar en batch
                inputs = tokenizer(
                    batch_texts,
                    max_length=self.settings.models.max_length,
                    padding=True,
                    truncation=True,
                    return_tensors="pt"
                )

                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                # Generar embeddings (usando asyncio para no bloquear)
                def generate_batch():
                    with torch.no_grad():
                        outputs = model(**inputs)
                        # Para modelos BGE/E5, usamos el token [CLS] (primer token)
                        embeddings = outputs.last_hidden_state[:, 0]
                        # Normalizar para similaridad de coseno
                        normalized = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                        return normalized.cpu()  # Mover de vuelta a CPU

                batch_vectors = await asyncio.to_thread(generate_batch)
                vectors.extend(batch_vectors.unbind())

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
        """Buscar textos similares a la consulta"""
        # Obtener modelo para el tipo de embedding
        model_info = self._get_model(embedding_type)

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

    async def list_contexts(self) -> List[Dict[str, Any]]:
        """Listar contextos MCP disponibles"""
        # Conexión con el servicio de contexto MCP
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.settings.mcp_service_url}/contexts") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Error al listar contextos: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error conectando con el servicio de contexto: {e}")
            return []

    async def activate_context(self, context_id: str) -> Dict[str, Any]:
        """Activar un contexto MCP"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.settings.mcp_service_url}/contexts/{context_id}/activate") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Error al activar contexto: {response.status} - {error_text}")
                        raise HTTPException(status_code=response.status, detail=f"Error activando contexto: {error_text}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error conectando con el servicio de contexto: {e}")
            raise HTTPException(status_code=500, detail=f"Error conectando con el servicio de contexto: {str(e)}")

    async def deactivate_context(self, context_id: str) -> Dict[str, Any]:
        """Desactivar un contexto MCP"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.settings.mcp_service_url}/contexts/{context_id}/deactivate") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Error al desactivar contexto: {response.status} - {error_text}")
                        raise HTTPException(status_code=response.status, detail=f"Error desactivando contexto: {error_text}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error conectando con el servicio de contexto: {e}")
            raise HTTPException(status_code=500, detail=f"Error conectando con el servicio de contexto: {str(e)}")