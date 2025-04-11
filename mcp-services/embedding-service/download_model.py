#!/usr/bin/env python
"""
Script para descargar modelos de Hugging Face durante la construcción de la imagen.
Descarga el modelo BAAI/bge-m3-large por defecto.
"""

import os
import time
import torch
from sentence_transformers import SentenceTransformer
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_model():
    """Descargar el modelo BAAI/bge-m3-large"""
    start_time = time.time()

    # Crear directorio para caché si no existe
    cache_dir = "./modelos"
    os.makedirs(cache_dir, exist_ok=True)

    # Nombre del modelo
    model_name = "BAAI/bge-m3-large"

    logger.info(f"Descargando modelo {model_name}...")

    # Cargar el modelo (esto descargará los archivos necesarios)
    model = SentenceTransformer(model_name, cache_folder=cache_dir, trust_remote_code=True)

    # Verificar que el modelo funciona correctamente
    test_text = "Este es un texto de prueba."
    logger.info(f"Verificando el modelo con texto: '{test_text}'")

    # Generar embedding
    embedding = model.encode(f"passage: {test_text}")

    # Verificar dimensiones
    dim = len(embedding)
    logger.info(f"Embedding generado correctamente. Dimensión: {dim}")

    # Tiempo de descarga
    elapsed_time = time.time() - start_time
    logger.info(f"Modelo descargado y verificado en {elapsed_time:.2f} segundos")

    # Mostrar archivos descargados
    model_dir = os.path.join(cache_dir, model_name.replace("/", "_"))
    if os.path.exists(model_dir):
        logger.info(f"Archivos del modelo en {model_dir}:")
        for root, dirs, files in os.walk(model_dir):
            level = root.replace(model_dir, '').count(os.sep)
            indent = ' ' * 4 * level
            logger.info(f"{indent}{os.path.basename(root)}/")
            for file in files:
                size_mb = os.path.getsize(os.path.join(root, file)) / (1024 * 1024)
                logger.info(f"{indent}    {file} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    download_model()