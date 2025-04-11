FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS base

# Configurar variables de entorno
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# Instalar Python y dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    build-essential \
    git \
    curl \
    wget \
    procps \
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Crear enlace simbólico a python
RUN ln -sf /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

FROM base AS builder

# Configurar token de Hugging Face directamente en el Dockerfile
# NOTA: Esto no es una práctica recomendada para entornos de producción
ENV HF_TOKEN=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

# Copiar archivos de requisitos
COPY requirements.txt .

# Instalar dependencias en un entorno virtual
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Actualizar pip, instalar PyTorch con CUDA y otras dependencias
# IMPORTANTE: Usar versiones compatibles de libraries
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch==2.1.2+cu121 --extra-index-url https://download.pytorch.org/whl/cu121 && \
    pip install --no-cache-dir transformers==4.35.2 sentence-transformers==2.2.2 && \
    pip install --no-cache-dir -r requirements.txt && \
    # Verificar instalación de torch con CUDA
    python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}'); print(f'GPU count: {torch.cuda.device_count()}');"

# Establecer variables de entorno para la caché de modelos de Hugging Face/SentenceTransformers
ENV SENTENCE_TRANSFORMERS_HOME=/app/modelos \
    HF_HOME=/app/modelos \
    HF_HUB_CACHE=/app/modelos \
    TRANSFORMERS_CACHE=/app/modelos \
    HF_TOKEN=${HF_TOKEN}

# Crear directorio para caché de modelos
RUN mkdir -p /app/modelos

# Copiar el script de descarga de modelos actualizado para BGE-M3
COPY download_model.py /app/

# Descargar el modelo durante la fase de construcción
RUN cd /app && python download_model.py

FROM base

# Configurar token de Hugging Face en la imagen final
ENV HF_TOKEN=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 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONASYNCIODEBUG=0 \
    PYTHONOPTIMIZE=2 \
    # Variables para la caché de modelos
    SENTENCE_TRANSFORMERS_HOME=/app/modelos \
    HF_HOME=/app/modelos \
    HF_HUB_CACHE=/app/modelos \
    TRANSFORMERS_CACHE=/app/modelos \
    # Configuración del modelo por defecto
    DEFAULT_EMBEDDING_MODEL=BAAI/bge-m3-large

# Copiar el entorno virtual desde la etapa de construcción
COPY --from=builder /venv /venv
# Copiar modelos ya descargados
COPY --from=builder /app/modelos /app/modelos
ENV PATH="/venv/bin:$PATH"

# Copiar código fuente
COPY . .

# Verificar solo las dependencias básicas
RUN python -c "import fastapi, uvicorn, pydantic, pydantic_settings; print(f'Imports básicos correctos: fastapi={fastapi.__version__}, uvicorn={uvicorn.__version__}, pydantic={pydantic.__version__}, pydantic_settings={pydantic_settings.__version__}')"

# Cambiar al usuario no privilegiado para mayor seguridad
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app /venv && \
    # Asegurar que el usuario tenga acceso a la caché de modelos
    chmod -R 755 /app/modelos
USER appuser

# Exponer puerto
EXPOSE 8084

# Ejecutar la aplicación
CMD ["python", "main.py"]