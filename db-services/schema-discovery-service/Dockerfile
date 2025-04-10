# Python 3.10+ requerido para compatibilidad con Pydantic v2
FROM python:3.11-slim AS base

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    python3-dev \
    libpq-dev \
    unixodbc-dev \
    git \
    procps \
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
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONASYNCIODEBUG=0 \
    PYTHONOPTIMIZE=2

# Copiar código fuente
COPY . .

# Verificar solo las dependencias básicas
RUN python -c "import fastapi, uvicorn, pydantic, pydantic_settings; print(f'Imports básicos correctos: fastapi={fastapi.__version__}, uvicorn={uvicorn.__version__}')"

# Cambiar al usuario no privilegiado para mayor seguridad
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app /venv
USER appuser

# Exponer puerto
EXPOSE 8087

# Ejecutar la aplicación
CMD ["python", "main.py"]