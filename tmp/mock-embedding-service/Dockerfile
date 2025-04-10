FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Copiar código
COPY app.py .

# Exponer puerto
EXPOSE 8084

# Iniciar aplicación
CMD ["python", "app.py"]