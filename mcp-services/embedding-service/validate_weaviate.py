#!/usr/bin/env python3
"""
Script para validar la configuración y funcionamiento de Weaviate
Este script verifica que Weaviate esté correctamente configurado y
que las clases necesarias existan para el sistema AISS.
"""

import requests
import json
import sys
import os
import time

# Configuración
WEAVIATE_URL = os.environ.get("WEAVIATE_URL", "http://localhost:6333")
RETRIES = 5
WAIT_TIME = 2

def check_weaviate_status():
    """Verificar que Weaviate esté en funcionamiento"""
    print(f"Verificando estado de Weaviate en {WEAVIATE_URL}...")
    
    for i in range(RETRIES):
        try:
            response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready", timeout=5)
            if response.status_code == 200:
                print("✅ Weaviate está en funcionamiento")
                return True
            else:
                print(f"⚠️ Weaviate respondió con código {response.status_code}, reintentando ({i+1}/{RETRIES})...")
        except Exception as e:
            print(f"⚠️ Error al conectar con Weaviate: {e}, reintentando ({i+1}/{RETRIES})...")
        
        time.sleep(WAIT_TIME)
    
    print("❌ No se pudo conectar con Weaviate después de varios intentos")
    return False

def get_schema():
    """Obtener el esquema actual de Weaviate"""
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/schema", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error al obtener el esquema: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error al obtener el esquema: {e}")
        return None

def check_classes(schema):
    """Verificar que las clases necesarias existan"""
    if not schema or "classes" not in schema:
        print("❌ No se encontraron clases en el esquema")
        return False
    
    classes = schema["classes"]
    class_names = [c["class"] for c in classes]
    
    required_classes = ["GeneralKnowledge", "PersonalKnowledge"]
    missing_classes = [c for c in required_classes if c not in class_names]
    
    if missing_classes:
        print(f"❌ Faltan las siguientes clases: {', '.join(missing_classes)}")
        return False
    
    print("✅ Todas las clases requeridas están presentes")
    return True

def check_properties(schema):
    """Verificar que las propiedades necesarias existan en cada clase"""
    if not schema or "classes" not in schema:
        return False
    
    required_properties = ["doc_id", "owner_id", "area_id", "text", "metadata"]
    valid = True
    
    for cls in schema["classes"]:
        if cls["class"] in ["GeneralKnowledge", "PersonalKnowledge"]:
            property_names = [p["name"] for p in cls.get("properties", [])]
            missing_properties = [p for p in required_properties if p not in property_names]
            
            if missing_properties:
                print(f"❌ En la clase {cls['class']} faltan las propiedades: {', '.join(missing_properties)}")
                valid = False
            else:
                print(f"✅ Clase {cls['class']}: todas las propiedades están presentes")
    
    return valid

def check_vectorizer_config(schema):
    """Verificar la configuración del vectorizador"""
    if not schema or "classes" not in schema:
        return False
    
    valid = True
    
    for cls in schema["classes"]:
        if cls["class"] in ["GeneralKnowledge", "PersonalKnowledge"]:
            vectorizer = cls.get("vectorizer")
            if vectorizer != "none":
                print(f"⚠️ La clase {cls['class']} usa vectorizador '{vectorizer}' en lugar de 'none'")
                valid = False
            else:
                print(f"✅ Clase {cls['class']}: configuración de vectorizador correcta")
            
            vector_config = cls.get("vectorIndexConfig", {})
            distance = vector_config.get("distance")
            if distance != "cosine":
                print(f"⚠️ La clase {cls['class']} usa distancia '{distance}' en lugar de 'cosine'")
                valid = False
            else:
                print(f"✅ Clase {cls['class']}: configuración de distancia correcta")
    
    return valid

def main():
    """Función principal"""
    print("\n=== VALIDACIÓN DE WEAVIATE PARA SISTEMA AISS ===\n")
    
    if not check_weaviate_status():
        print("\n❌ No se pudo conectar con Weaviate. Verificación fallida.")
        sys.exit(1)
    
    schema = get_schema()
    if not schema:
        print("\n❌ No se pudo obtener el esquema de Weaviate. Verificación fallida.")
        sys.exit(1)
    
    print("\n--- Verificación de clases ---")
    classes_ok = check_classes(schema)
    
    print("\n--- Verificación de propiedades ---")
    properties_ok = check_properties(schema)
    
    print("\n--- Verificación de configuración de vectores ---")
    vectorizer_ok = check_vectorizer_config(schema)
    
    print("\n=== RESUMEN DE VALIDACIÓN ===")
    if classes_ok and properties_ok and vectorizer_ok:
        print("✅ Weaviate está correctamente configurado para el sistema AISS")
        sys.exit(0)
    else:
        print("⚠️ Se encontraron problemas en la configuración de Weaviate")
        sys.exit(1)

if __name__ == "__main__":
    main()