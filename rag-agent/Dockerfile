FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de requisitos
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Configurar variables de entorno para mejor rendimiento
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONASYNCIODEBUG=0 \
    PYTHONOPTIMIZE=2

# Copiar código fuente
COPY . .

# Exponer puerto
EXPOSE 8085

# Registrar hora de inicio para uptime
CMD export UPTIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) && \
    exec python main.py