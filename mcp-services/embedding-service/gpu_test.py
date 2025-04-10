#!/usr/bin/env python
"""
Script para verificar que PyTorch con CUDA está correctamente configurado
y que el modelo Nomic AI puede utilizar la GPU para generar embeddings.
"""

import os
import torch
import time
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_gpu():
    """Verificar que PyTorch detecta la GPU correctamente"""
    logger.info("Verificando configuración de GPU para PyTorch:")
    
    # Información básica de PyTorch
    logger.info(f"PyTorch version: {torch.__version__}")
    
    # Verificar si CUDA está disponible
    cuda_available = torch.cuda.is_available()
    logger.info(f"CUDA disponible: {cuda_available}")
    
    if cuda_available:
        # Información detallada de CUDA
        logger.info(f"CUDA version: {torch.version.cuda}")
        device_count = torch.cuda.device_count()
        logger.info(f"Dispositivos CUDA detectados: {device_count}")
        
        for i in range(device_count):
            device_properties = torch.cuda.get_device_properties(i)
            logger.info(f"Dispositivo {i}: {device_properties.name}")
            logger.info(f"  - Memoria total: {device_properties.total_memory / (1024**3):.2f} GB")
            logger.info(f"  - Compute capability: {device_properties.major}.{device_properties.minor}")
    else:
        logger.warning("No se detectó ninguna GPU con soporte CUDA.")
        logger.info("Comprueba que:")
        logger.info("  1. Los drivers NVIDIA están instalados")
        logger.info("  2. PyTorch se instaló con soporte CUDA")
        logger.info("  3. NVIDIA Container Toolkit está configurado correctamente")
        return False
    
    return cuda_available

def test_nomic_embedding():
    """Verificar que el modelo Nomic AI puede utilizar la GPU"""
    try:
        import nomic
        from nomic import embed
        
        logger.info(f"Nomic version: {nomic.__version__}")
        logger.info("Probando generación de embeddings con Nomic...")
        
        # Texto de prueba
        test_text = "Este es un texto de prueba para verificar la generación de embeddings con GPU."
        
        # Configuración actual de CUDA
        cuda_state = torch.cuda.is_available()
        logger.info(f"Estado de CUDA antes de la prueba: {cuda_state}")
        
        # Medir tiempo de ejecución
        start_time = time.time()
        
        # Generar embedding con Nomic
        embeddings = embed.text(
            texts=[test_text],
            model_name="nomic-ai/nomic-embed-text-v1.5-fp16"
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info(f"Embedding generado en {duration:.4f} segundos")
        logger.info(f"Dimensión del embedding: {len(embeddings[0])}")
        
        # Verificar uso de GPU después de la generación del embedding
        if torch.cuda.is_available():
            # Verificar uso de memoria de la GPU
            current_memory = torch.cuda.memory_allocated() / (1024**3)
            max_memory = torch.cuda.max_memory_allocated() / (1024**3)
            logger.info(f"Memoria GPU actualmente en uso: {current_memory:.2f} GB")
            logger.info(f"Memoria GPU máxima usada: {max_memory:.2f} GB")
        
        return True
    except ImportError as e:
        logger.error(f"Error importando librería Nomic: {e}")
        logger.info("Asegúrate de que 'nomic' está instalado con: pip install nomic")
        return False
    except Exception as e:
        logger.error(f"Error durante la prueba de embeddings: {e}")
        return False

def test_tensor_operations():
    """Realizar operaciones de tensor para verificar que CUDA funciona correctamente"""
    try:
        logger.info("Realizando operaciones de tensor en GPU...")
        
        if not torch.cuda.is_available():
            logger.warning("CUDA no disponible para operaciones de tensor")
            return False
        
        # Crear tensores grandes para forzar el uso de la GPU
        device = torch.device("cuda")
        
        # Crear tensores y medir tiempo
        start_time = time.time()
        
        # Operación intensiva: multiplicación de matrices
        size = 5000
        a = torch.randn(size, size, device=device)
        b = torch.randn(size, size, device=device)
        
        # Forzar sincronización para medir correctamente
        torch.cuda.synchronize()
        prep_time = time.time()
        logger.info(f"Tensores preparados en {prep_time - start_time:.4f} segundos")
        
        # Realizar multiplicación de matrices
        c = torch.matmul(a, b)
        
        # Forzar sincronización para medir correctamente
        torch.cuda.synchronize()
        end_time = time.time()
        
        logger.info(f"Multiplicación de matrices {size}x{size} completada en {end_time - prep_time:.4f} segundos")
        
        # Verificar uso de memoria
        current_memory = torch.cuda.memory_allocated() / (1024**3)
        max_memory = torch.cuda.max_memory_allocated() / (1024**3)
        logger.info(f"Memoria GPU actualmente en uso: {current_memory:.2f} GB")
        logger.info(f"Memoria GPU máxima usada: {max_memory:.2f} GB")
        
        return True
    except Exception as e:
        logger.error(f"Error durante operaciones de tensor: {e}")
        return False

if __name__ == "__main__":
    logger.info("===== Iniciando pruebas de GPU para servicio de embeddings =====")
    
    # Mostrar variables de entorno relacionadas con GPU
    logger.info("Variables de entorno relacionadas con GPU:")
    for var in ["CUDA_VISIBLE_DEVICES", "USE_GPU", "USE_8BIT", "USE_FP16"]:
        logger.info(f"{var}: {os.environ.get(var, 'no establecida')}")
    
    # Ejecutar pruebas
    gpu_check = check_gpu()
    if not gpu_check:
        logger.error("La verificación de GPU falló. El sistema no podrá utilizar aceleración GPU.")
    
    tensor_test = test_tensor_operations() if gpu_check else False
    nomic_test = test_nomic_embedding()
    
    # Resumen de resultados
    logger.info("\n===== Resumen de pruebas =====")
    logger.info(f"Detección de GPU: {'✅ EXITOSA' if gpu_check else '❌ FALLIDA'}")
    logger.info(f"Operaciones de tensor en GPU: {'✅ EXITOSAS' if tensor_test else '❌ FALLIDAS'}")
    logger.info(f"Embeddings con Nomic AI: {'✅ EXITOSOS' if nomic_test else '❌ FALLIDOS'}")
    
    # Resultado global
    if gpu_check and (tensor_test or nomic_test):
        logger.info("✅ PRUEBA EXITOSA: La GPU está configurada correctamente y puede ser utilizada")
        exit(0)
    else:
        logger.error("❌ PRUEBA FALLIDA: Hay problemas con la configuración de GPU")
        exit(1)