#!/usr/bin/env python3
"""
Script para probar que Ollama está detectando y utilizando GPU correctamente.
Este script debe ejecutarse dentro del contenedor rag-agent o directamente desde el host
para verificar que el contenedor Ollama local está utilizando la GPU correctamente
para la validación de consultas de bases de datos.
"""

import os
import json
import asyncio
import argparse
import aiohttp
import time
import sys

async def test_ollama_api(api_url):
    """Prueba la conexión al API de Ollama y lista los modelos disponibles"""
    print(f"Probando conexión a Ollama en {api_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_url}/api/tags") as response:
                if response.status != 200:
                    print(f"❌ Error: No se pudo conectar a Ollama API (status: {response.status})")
                    return False, []
                
                data = await response.json()
                models = data.get('models', [])
                
                if models:
                    model_names = [m.get('name') for m in models]
                    print(f"✅ Conexión correcta con el API de Ollama")
                    print(f"📋 Modelos disponibles: {', '.join(model_names)}")
                    return True, models
                else:
                    print(f"⚠️ No hay modelos disponibles en el servidor Ollama")
                    return True, []
    except Exception as e:
        print(f"❌ Error conectando con Ollama API: {e}")
        return False, []

async def test_gpu_inference(api_url, model, use_gpu=True):
    """Prueba la inferencia del modelo con o sin opciones de GPU"""
    print(f"\n{'🚀 Probando inferencia con GPU' if use_gpu else '💻 Probando inferencia con CPU'}")
    print(f"Modelo: {model}")
    
    # Prompt para prueba
    prompt = "Explica brevemente cómo las GPU aceleran la inferencia de los modelos de lenguaje grandes (LLMs)"
    
    # Configuración básica
    options = {
        "temperature": 0.1,
        "num_predict": 300  # Limitar respuesta para prueba
    }
    
    # Añadir opciones de GPU si corresponde
    if use_gpu:
        gpu_options = {
            "num_gpu": 1,       # Usar 1 GPU
            "f16_kv": True,     # Usar FP16 para KV-cache (menor uso de memoria)
            "mirostat": 2,      # Estabilizador de muestreo
        }
        options.update(gpu_options)
        print("Opciones GPU activadas:", json.dumps(gpu_options, indent=2))
    
    # Payload para la petición
    payload = {
        "model": model,
        "prompt": prompt,
        "system": "Eres un experto en hardware para inteligencia artificial. Da respuestas concisas y técnicamente precisas.",
        "options": options,
        "stream": False
    }
    
    # Ejecutar la inferencia y medir tiempo
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{api_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ Error en la generación: status {response.status}")
                    print(f"Detalles: {error_text}")
                    
                    # Intentar con endpoint alternativo (chat)
                    print("Intentando con endpoint alternativo (/api/chat)...")
                    chat_payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "Eres un experto en hardware para inteligencia artificial."},
                            {"role": "user", "content": prompt}
                        ],
                        "options": options
                    }
                    
                    async with session.post(f"{api_url}/api/chat", json=chat_payload) as chat_response:
                        if chat_response.status != 200:
                            chat_error = await chat_response.text()
                            print(f"❌ Error con endpoint chat: {chat_response.status} - {chat_error}")
                            return None
                        
                        result = await chat_response.json()
                        response_text = result.get("message", {}).get("content", "")
                
                else:
                    result = await response.json()
                    response_text = result.get("response", "")
                
                end_time = time.time()
                elapsed = end_time - start_time
                
                # Mostrar resultados
                print(f"⏱️ Tiempo de generación: {elapsed:.2f} segundos")
                print(f"📊 Longitud de respuesta: {len(response_text)} caracteres")
                print(f"📊 Velocidad: {len(response_text) / elapsed:.2f} caracteres/segundo")
                
                # Mostrar fragmento de la respuesta
                preview_length = min(200, len(response_text))
                print(f"\n📝 Vista previa de respuesta:\n{response_text[:preview_length]}...\n")
                
                return {
                    "elapsed": elapsed,
                    "length": len(response_text),
                    "chars_per_second": len(response_text) / elapsed,
                    "text": response_text
                }
                
    except Exception as e:
        print(f"❌ Error durante la inferencia: {e}")
        return None

async def run_comparison(api_url, model):
    """Ejecuta una comparación entre CPU y GPU para el mismo prompt y modelo"""
    print("\n" + "="*60)
    print("COMPARACIÓN DE RENDIMIENTO CPU vs GPU")
    print("="*60)
    
    # Verificar que la API está respondiendo
    api_ok, models = await test_ollama_api(api_url)
    if not api_ok:
        print("❌ No se puede conectar con Ollama API. Abortando prueba.")
        return False
    
    # Verificar que el modelo existe
    model_names = [m.get('name') for m in models]
    if model not in model_names and models:
        print(f"⚠️ El modelo {model} no está disponible.")
        model = model_names[0]  # Usar el primer modelo disponible
        print(f"Usando modelo alternativo: {model}")
    
    # Prueba sin opciones GPU (CPU)
    cpu_result = await test_gpu_inference(api_url, model, use_gpu=False)
    if not cpu_result:
        print("❌ La prueba CPU falló. No se puede continuar con la comparación.")
        return False
    
    # Pequeña pausa para asegurar recursos liberados
    await asyncio.sleep(2)
    
    # Prueba con opciones GPU
    gpu_result = await test_gpu_inference(api_url, model, use_gpu=True)
    if not gpu_result:
        print("❌ La prueba GPU falló. Verificar configuración de GPU para Ollama.")
        return False
    
    # Comparar resultados
    print("\n" + "="*60)
    print("RESULTADOS COMPARATIVOS")
    print("="*60)
    
    speedup = gpu_result["chars_per_second"] / cpu_result["chars_per_second"]
    time_ratio = cpu_result["elapsed"] / gpu_result["elapsed"]
    
    print(f"CPU: {cpu_result['elapsed']:.2f}s ({cpu_result['chars_per_second']:.2f} chars/s)")
    print(f"GPU: {gpu_result['elapsed']:.2f}s ({gpu_result['chars_per_second']:.2f} chars/s)")
    print(f"Aceleración con GPU: {speedup:.2f}x")
    print(f"Reducción de tiempo: {(1 - gpu_result['elapsed'] / cpu_result['elapsed']) * 100:.1f}%")
    
    if speedup >= 1.5:
        print("\n✅ La GPU está proporcionando una aceleración significativa!")
        print(f"   {speedup:.1f}x más rápido con GPU")
        return True
    elif speedup >= 1.1:
        print("\n✅ La GPU proporciona algo de aceleración, pero podría optimizarse más.")
        print(f"   {speedup:.1f}x más rápido con GPU")
        return True
    else:
        print("\n⚠️ La GPU no muestra aceleración significativa. Verificar configuración.")
        return False

async def test_ollama_gpu(api_url="http://ollama:11434", model="llama3:7b-instruct", run_comparison=False):
    """Prueba la detección y uso de GPU por Ollama"""
    
    # Verificar conexión y modelos disponibles
    api_ok, models = await test_ollama_api(api_url)
    if not api_ok:
        return False
    
    # Verificar si el modelo solicitado existe
    model_names = [m.get('name') for m in models]
    if model not in model_names and models:
        print(f"⚠️ El modelo '{model}' no está disponible.")
        if models:
            model = model_names[0]  # Usar el primer modelo disponible
            print(f"Usando modelo alternativo: {model}")
        else:
            print("❌ No hay modelos disponibles para probar.")
            return False
    
    if run_comparison:
        # Ejecutar prueba comparativa
        return await run_comparison(api_url, model)
    else:
        # Ejecutar solo prueba con GPU
        result = await test_gpu_inference(api_url, model, use_gpu=True)
        return result is not None

async def main():
    parser = argparse.ArgumentParser(description="Prueba de GPU para Ollama")
    parser.add_argument("--url", default=os.environ.get("OLLAMA_API_BASE", "http://ollama:11434"), 
                        help="URL de la API de Ollama")
    parser.add_argument("--model", default="llama3", help="Modelo a probar")
    parser.add_argument("--host", action="store_true", help="Si se ejecuta desde el host, usar localhost")
    parser.add_argument("--compare", action="store_true", help="Realizar comparación CPU vs GPU")
    args = parser.parse_args()
    
    # Si se ejecuta desde el host, utilizar localhost en lugar del nombre del contenedor
    if args.host and args.url == "http://ollama:11434":
        api_url = "http://localhost:11434"
        print(f"Ejecutando desde el host, usando {api_url}")
    else:
        api_url = args.url
    
    # Imprimir información inicial
    print("\n" + "="*60)
    print("PRUEBA DE FUNCIONALIDAD GPU PARA OLLAMA")
    print("="*60)
    print(f"URL API: {api_url}")
    print(f"Modelo: {args.model}")
    
    # Realizar prueba
    if args.compare:
        success = await run_comparison(api_url, args.model)
    else:
        success = await test_ollama_gpu(api_url=api_url, model=args.model)
    
    if success:
        print("\n✅ PRUEBA EXITOSA: Ollama está funcionando correctamente con GPU")
        sys.exit(0)
    else:
        print("\n❌ PRUEBA FALLIDA: Hay problemas con la configuración de Ollama o GPU")
        sys.exit(1)
        
if __name__ == "__main__":
    asyncio.run(main())