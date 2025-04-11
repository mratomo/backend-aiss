#!/usr/bin/env python
"""
Script para descargar modelos de Hugging Face durante la construcción de la imagen.
Descarga el modelo BAAI/bge-m3-large por defecto con soporte para autenticación.
"""

import os
import time
import torch
import logging
from pathlib import Path
from typing import Optional, Dict

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_huggingface_auth():
    """Configurar autenticación para Hugging Face Hub"""
    token = os.environ.get("HF_TOKEN")
    if token:
        try:
            # Importar huggingface_hub para autenticación
            import huggingface_hub
            huggingface_hub.login(token=token, add_to_git_credential=False)
            logger.info("✅ Autenticación de Hugging Face configurada correctamente")
            return True
        except Exception as e:
            logger.error(f"❌ Error al configurar autenticación de Hugging Face: {e}")
            return False
    else:
        logger.warning("⚠️ No se ha encontrado HF_TOKEN. Los modelos gated no serán accesibles.")
        return False

def check_model_compatibility(model_name: str) -> Dict:
    """
    Verificar versiones instaladas y compatibilidad para un modelo específico

    Args:
        model_name: Nombre del modelo a verificar

    Returns:
        Dict con información de compatibilidad
    """
    import pkg_resources

    # Versiones instaladas
    try:
        torch_version = pkg_resources.get_distribution("torch").version
        transformers_version = pkg_resources.get_distribution("transformers").version
        sentence_transformers_version = pkg_resources.get_distribution("sentence_transformers").version
    except pkg_resources.DistributionNotFound as e:
        logger.error(f"❌ Dependencia no encontrada: {e}")
        return {"compatible": False, "error": f"Dependencia no instalada: {e}"}

    # Verificar compatibilidad para BGE-M3
    if "bge-m3" in model_name.lower():
        # Compatibilidad conocida para BGE-M3
        if torch_version.startswith("2.5"):
            logger.warning("⚠️ PyTorch 2.5.x es muy reciente y podría tener problemas de compatibilidad")

        # Verificar transformers y sentence-transformers
        st_major, st_minor = map(int, sentence_transformers_version.split('.')[:2])
        tf_major, tf_minor = map(int, transformers_version.split('.')[:2])

        # Para BGE-M3, recomendamos estas versiones
        required = {
            "transformers": ">=4.30.0,<4.36.0",
            "sentence-transformers": ">=2.2.0,<2.3.0",
            "torch": ">=2.0.0,<2.2.0"
        }

        # Verificar mínimos
        if tf_major < 4 or (tf_major == 4 and tf_minor < 30):
            return {
                "compatible": False,
                "error": f"Transformers {transformers_version} es demasiado antiguo para BGE-M3"
            }

        if tf_major > 4 or (tf_major == 4 and tf_minor > 35):
            logger.warning(f"⚠️ Transformers {transformers_version} podría ser demasiado reciente para BGE-M3")

        if st_major < 2 or (st_major == 2 and st_minor < 2):
            return {
                "compatible": False,
                "error": f"SentenceTransformers {sentence_transformers_version} es demasiado antiguo para BGE-M3"
            }

        # Devolver resultado
        return {
            "compatible": True,
            "torch": torch_version,
            "transformers": transformers_version,
            "sentence_transformers": sentence_transformers_version,
            "recommendation": required
        }

    # Para otros modelos, requisitos más generales
    return {"compatible": True, "torch": torch_version, "transformers": transformers_version,
            "sentence_transformers": sentence_transformers_version}

def download_bge_model(model_name: str, cache_dir: str, device: str = "cpu") -> bool:
    """
    Descargar específicamente modelos BGE con manejo especial

    Args:
        model_name: Nombre del modelo BGE
        cache_dir: Directorio para caché
        device: Dispositivo para cargar el modelo

    Returns:
        True si se descargó correctamente, False en caso contrario
    """
    try:
        from sentence_transformers import SentenceTransformer
        import huggingface_hub

        logger.info(f"Descargando modelo {model_name}...")
        start_time = time.time()

        # Para BGE-M3, verificar que el token está configurado
        if "bge-m3" in model_name.lower():
            token = os.environ.get("HF_TOKEN")
            if not token:
                logger.error("❌ BGE-M3 requiere autenticación con HF_TOKEN")
                return False

            # Verificar aceptación de modelo
            try:
                huggingface_hub.model_info(model_name)
                logger.info(f"✅ Acceso confirmado al modelo {model_name}")
            except Exception as e:
                logger.error(f"❌ No se puede acceder al modelo {model_name}: {e}")
                logger.error("Asegúrate de aceptar los términos del modelo en huggingface.co")
                return False

        # Cargar el modelo (esto descargará los archivos necesarios)
        model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            trust_remote_code=True,
            device=device
        )

        # Verificar que el modelo funciona correctamente
        test_text = "Este es un texto de prueba."
        logger.info(f"Verificando el modelo con texto: '{test_text}'")

        # Para BGE-M3, usar el prefijo correcto
        if "bge-m3" in model_name.lower():
            test_text = f"passage: {test_text}"

        # Generar embedding
        embedding = model.encode(test_text)

        # Verificar dimensiones
        dim = len(embedding)
        elapsed_time = time.time() - start_time
        logger.info(f"✅ Modelo {model_name} descargado y verificado en {elapsed_time:.2f} segundos")
        logger.info(f"   Dimensión del embedding: {dim}")

        # Guardar información del modelo
        model_info = {
            "name": model_name,
            "dimension": dim,
            "device": device,
            "download_time": elapsed_time
        }

        # Guardar esta información en un archivo
        info_file = os.path.join(cache_dir, "model_info.txt")
        with open(info_file, "w") as f:
            for key, value in model_info.items():
                f.write(f"{key}: {value}\n")

        return True

    except Exception as e:
        logger.error(f"❌ Error descargando modelo {model_name}: {e}")
        return False

def try_fallback_models(cache_dir: str, device: str = "cpu") -> bool:
    """
    Intentar modelos de respaldo si el principal falla

    Args:
        cache_dir: Directorio para caché
        device: Dispositivo para cargar el modelo

    Returns:
        True si algún modelo se descargó correctamente, False si todos fallaron
    """
    fallback_models = [
        "BAAI/bge-large-en-v1.5",  # Buen modelo no gated
        "BAAI/bge-base-en-v1.5",   # Versión más pequeña
        "intfloat/e5-large-v2",    # Buen rendimiento general
        "all-MiniLM-L6-v2"         # Muy ligero, siempre debería funcionar
    ]

    for model_name in fallback_models:
        logger.info(f"Intentando modelo alternativo: {model_name}")
        success = download_bge_model(model_name, cache_dir, device)
        if success:
            logger.info(f"✅ Modelo alternativo {model_name} descargado correctamente")
            return True

    logger.error("❌ Todos los modelos alternativos fallaron")
    return False