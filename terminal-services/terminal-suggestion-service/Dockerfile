# Python 3.10+ requerido para compatibilidad con Pydantic v2
FROM python:3.11-slim AS base

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder

# Copiar archivos de requisitos
COPY requirements.txt .

# Instalar dependencias en un entorno virtual
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Actualizar pip e instalar dependencias
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

FROM base

# Copiar el entorno virtual desde la etapa de construcción
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Configurar variables de entorno para mejor rendimiento
ENV HOST=0.0.0.0 \
    PORT=8094 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copiar código fuente
COPY . .

# Verificar la instalación
RUN python -c "import fastapi, uvicorn, pydantic, pydantic_settings, httpx, PyJWT; print(f'fastapi={fastapi.__version__}, uvicorn={uvicorn.__version__}, pydantic={pydantic.__version__}, pydantic_settings={pydantic_settings.__version__}, httpx={httpx.__version__}, PyJWT={PyJWT.__version__}')"

# Cambiar al usuario no privilegiado para mayor seguridad
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app /venv
USER appuser

# Exponer puerto
EXPOSE 8094

# Ejecutar la aplicación
CMD ["python", "main.py"]