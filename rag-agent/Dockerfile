# MCP 1.6.0 requiere Python 3.10+
FROM python:3.11-slim AS base

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
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
    
# Las dependencias git+https ya están incluidas en requirements.txt
# Se han quitado las siguientes líneas que causaban errores:
# pip install --no-cache-dir git+https://github.com/anthropics/mcp-python.git@main
# pip install --no-cache-dir git+https://github.com/anthropics/fastmcp.git@main

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

# Asegurar que starlette tenga la versión correcta
RUN pip install --no-cache-dir "starlette>=0.40.0,<0.47.0"

# Verificar instalación correcta de MCP y FastMCP
RUN python -c "import mcp, fastmcp; print(f'MCP y FastMCP importados correctamente. MCP version: {mcp.__version__ if hasattr(mcp, \"__version__\") else \"instalado\"}, FastMCP: {fastmcp.__version__ if hasattr(fastmcp, \"__version__\") else \"instalado\"}')"

# Exponer puerto
EXPOSE 8085

# Registrar hora de inicio para uptime
CMD export UPTIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) && \
    exec python main.py