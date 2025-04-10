# Guía de Configuración de GPU para Ollama en AISS

Esta guía explica cómo configurar el soporte de GPU tanto para la validación local de consultas de base de datos como para los proveedores remotos de Ollama.

## Índice
1. [Configuración de GPU para Validación de Consultas DB](#configuración-de-gpu-para-validación-de-consultas-db)
2. [Configuración de GPU para Proveedores Ollama Remotos](#configuración-de-gpu-para-proveedores-ollama-remotos)
3. [Comprobación del Rendimiento de GPU](#comprobación-del-rendimiento-de-gpu)
4. [Resolución de Problemas](#resolución-de-problemas)

## Configuración de GPU para Validación de Consultas DB

El sistema AISS utiliza Ollama localmente para validar consultas SQL y otras operaciones de base de datos. Para acelerar este proceso, se puede utilizar la GPU del servidor siguiendo estos pasos:

1. Asegúrese de que los drivers NVIDIA y CUDA están instalados en el host.
2. Verifique que la configuración de Docker incluye el runtime NVIDIA.
3. Configure el contenedor Ollama en docker-compose.yml para usar GPU:

```yaml
ollama:
  image: ollama/ollama:0.1.27
  container_name: aiss-ollama
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
    - NVIDIA_DRIVER_CAPABILITIES=compute,utility
  volumes:
    - ${VOLUMES_PATH:-/home/prods/ssd/aissdata}/data/ollama:/root/.ollama
  expose:
    - "11434"
  restart: unless-stopped
  networks:
    - aiss-network
```

4. Habilite el uso de GPU en el servicio rag-agent:

```yaml
rag-agent:
  # ... configuración existente
  environment:
    # ... otras variables
    - OLLAMA_USE_GPU=true  # Habilitar uso de GPU para validación
```

5. Reinicie los servicios:
```bash
docker-compose down && docker-compose up -d
```

## Configuración de GPU para Proveedores Ollama Remotos

Para configurar un proveedor Ollama remoto con soporte GPU a través de la interfaz web:

1. Acceda a la sección "Administración" > "Proveedores LLM" en la interfaz web de AISS.
2. Seleccione "Añadir nuevo proveedor" o "Editar" un proveedor existente de tipo Ollama.
3. Complete los campos del formulario:
   - **Nombre**: Un nombre descriptivo (ej. "Ollama GPU Server")
   - **Tipo**: Seleccione "Ollama"
   - **Modelo**: El nombre del modelo disponible en su servidor Ollama
   - **API Endpoint**: URL del servidor Ollama (ej. "http://your-ollama-server.com:11434")
   - **Temperatura**: Valor entre 0.0 y 1.0
   - **Tokens máximos**: Límite de tokens para la generación

4. En la sección "Metadatos avanzados", añada la siguiente configuración JSON:
```json
{
  "use_gpu": true,
  "gpu_options": {
    "num_gpu": 1,
    "f16_kv": true,
    "mirostat": 2
  }
}
```

5. (Opcional) Puede ajustar los parámetros GPU según sus necesidades:
   - `num_gpu`: Número de GPUs a utilizar (generalmente 1)
   - `f16_kv`: Usar precisión media (FP16) para la caché KV, ahorra memoria
   - `mirostat`: Algoritmo de muestreo, valores entre 0 y 2 (2 es recomendado)

6. Guarde la configuración.

## Comprobación del Rendimiento de GPU

Para verificar que Ollama está utilizando la GPU correctamente:

1. Ejecute el script de prueba de GPU desde el directorio raíz del proyecto:
```bash
./test_db_gpu.sh
```

2. Este script realizará una comparación entre la ejecución con CPU y GPU, mostrando métricas de rendimiento.

3. Puede ver la actividad de la GPU durante la inferencia usando:
```bash
nvidia-smi -l 1
```

## Resolución de Problemas

Si encuentra problemas con la aceleración GPU:

1. **La GPU no muestra aceleración**: Verifique que los drivers NVIDIA están correctamente instalados y son compatibles con CUDA.

2. **Errores en el contenedor Ollama**: Revise los logs del contenedor:
```bash
docker logs aiss-ollama
```

3. **Conflictos de versiones CUDA**: Asegúrese de que la versión de CUDA en el host es compatible con Ollama.

4. **Memoria insuficiente**: Si ve errores de memoria, intente usar modelos más pequeños o ajuste la opción `f16_kv` a `true`.

5. **Rendimiento no óptimo**: Pruebe diferentes valores para las opciones de GPU, especialmente si tiene múltiples GPUs disponibles.

---

Para más información, consulte la [documentación oficial de Ollama](https://github.com/ollama/ollama/blob/main/docs/gpu.md) sobre configuración de GPU.