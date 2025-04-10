# MCP 1.6.0 requiere Python 3.10+
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

# Copiar archivos de requisitos
COPY requirements.txt .

# Instalar dependencias en un entorno virtual
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Actualizar pip, instalar PyTorch con CUDA y otras dependencias
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch==2.1.0+cu121 --extra-index-url https://download.pytorch.org/whl/cu121 && \
    pip install --no-cache-dir -r requirements.txt && \
    # Verificar instalación de torch con CUDA
    python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}'); print(f'GPU count: {torch.cuda.device_count()}');"

FROM base

# Copiar el entorno virtual desde la etapa de construcción
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Configurar variables de entorno para mejor rendimiento
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONASYNCIODEBUG=0 \
    PYTHONOPTIMIZE=2

# Copiar código fuente
COPY . .

# Verificar la instalación
RUN python -c "import fastapi, uvicorn, pydantic, pydantic_settings; print(f'Import check successful: fastapi={fastapi.__version__}, uvicorn={uvicorn.__version__}, pydantic={pydantic.__version__}, pydantic_settings={pydantic_settings.__version__}')"

# Cambiar al usuario no privilegiado para mayor seguridad
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app /venv
USER appuser

# Exponer puerto
EXPOSE 8084

# Ejecutar la aplicación
CMD ["python", "main.py"]