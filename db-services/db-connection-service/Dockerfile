FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias para clientes de base de datos
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    libpq-dev \
    unixodbc-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de requisitos
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

# Exponer puerto
EXPOSE 8086

# Comando para iniciar la aplicación
CMD ["python", "main.py"]