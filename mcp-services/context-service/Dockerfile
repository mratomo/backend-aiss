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
# Primero intentamos instalar desde PyPI, y si falla, desde GitHub
RUN pip install --no-cache-dir --upgrade pip && \
    # Primera estrategia: Instalar todo desde requirements.txt
    pip install --no-cache-dir -r requirements.txt && \
    echo "Verificando instalación de MCP..." && \
    if ! python -c "import mcp, fastmcp" &>/dev/null; then \
        echo "No se pudieron importar paquetes MCP, intentando instalación directa desde GitHub..." && \
        # Segunda estrategia: Instalar solo mcp y fastmcp directamente
        pip install --no-cache-dir mcp==1.6.0 fastmcp==0.4.1 || \
        # Tercera estrategia: Intentar desde GitHub con los repositorios correctos
        (echo "Instalando desde GitHub (modelcontextprotocol)..." && \
         pip install --no-cache-dir git+https://github.com/modelcontextprotocol/mcp-python.git@v1.6.0 && \
         pip install --no-cache-dir git+https://github.com/modelcontextprotocol/fastmcp.git@v0.4.1) || \
        # Cuarta estrategia: Intentar con los repositorios alternativos
        (echo "Intentando con repositorios alternativos..." && \
         pip install --no-cache-dir git+https://github.com/anthropics/mcp-python.git@v1.6.0 && \
         pip install --no-cache-dir git+https://github.com/anthropics/fastmcp.git@v0.4.1) && \
        echo "Instalación desde GitHub completada."; \
    else \
        echo "Paquetes MCP instalados correctamente desde PyPI."; \
    fi

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

# Verificar la instalación - CRÍTICO: todos los módulos deben estar disponibles
RUN python -c "import fastapi, uvicorn, pydantic, pydantic_settings; \
    print(f'Dependencias básicas: fastapi={fastapi.__version__}, uvicorn={uvicorn.__version__}, pydantic={pydantic.__version__}, pydantic_settings={pydantic_settings.__version__}'); \
    import mcp; \
    import fastmcp; \
    print(f'MCP libs: mcp y fastmcp importados correctamente'); \
    print(f'Versiones MCP: mcp={getattr(mcp, \"__version__\", \"desconocida\")}, fastmcp={getattr(fastmcp, \"__version__\", \"desconocida\")}')"

# Cambiar al usuario no privilegiado para mayor seguridad
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app /venv
USER appuser

# Exponer puerto
EXPOSE 8083

# Copiar y hacer ejecutable el script de inicio
RUN chmod +x start.sh

# Ejecutar la aplicación a través del script de inicio
CMD ["./start.sh"]