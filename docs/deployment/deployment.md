# Guía de Despliegue

## Requisitos del Sistema

### Hardware Recomendado
- **CPU**: 4+ núcleos (8+ para entornos de producción)
- **RAM**: 8GB mínimo (16GB+ recomendado, especialmente si se utilizan modelos locales)
- **Almacenamiento**: 20GB mínimo (depende del volumen de documentos)
- **GPU**: Opcional pero recomendado para el servicio de embeddings

### Software Requerido
- **Docker**: v20.10.0+
- **Docker Compose**: v2.0.0+
- **Git**: Para clonar el repositorio

## Preparación del Entorno

### 1. Clonar el Repositorio

```bash
git clone https://github.com/yourusername/backend-aiss.git
cd backend-aiss
```

### 2. Configuración de Variables de Entorno

Crear un archivo `.env` en la raíz del proyecto basado en `.env.example`:

```bash
cp .env.example .env
```

Editar el archivo `.env` con los valores apropiados:

```
# Configuración General
ENVIRONMENT=production
LOG_LEVEL=info

# Configuración API Gateway
API_GATEWAY_PORT=8080
JWT_SECRET=your-secure-jwt-secret
JWT_EXPIRATION=30m
REFRESH_TOKEN_EXPIRATION=7d

# Configuración MongoDB
MONGODB_URI=mongodb://mongo:27017
MONGODB_DATABASE=aiss_backend
MONGODB_USER=admin
MONGODB_PASSWORD=secure-password

# Configuración Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

# Configuración Embedding Service
GENERAL_EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
PERSONAL_EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
USE_GPU=true
USE_FP16=true

# Configuración MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET=documents

# Configuración de LLM (opcional)
DEFAULT_LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

# Configuración de Ollama (opcional)
OLLAMA_HOST=http://ollama:11434

# Configuración CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.yourcompany.com
```

## Despliegue del Sistema

### Construcción y Arranque de Servicios

```bash
# Construcción de imágenes
docker-compose build

# Arranque de todos los servicios
docker-compose up -d
```

### Verificación del Despliegue

```bash
# Verificar que todos los contenedores están en ejecución
docker-compose ps

# Verificar logs
docker-compose logs -f
```

### Inicialización de Bases de Datos

Las colecciones de MongoDB y Qdrant se inicializan automáticamente. Si necesitas ejecutar scripts de inicialización manualmente:

```bash
# Inicializar MongoDB
docker-compose exec mongodb mongosh --file /docker-entrypoint-initdb.d/mongodb.js

# Inicializar Qdrant
docker-compose exec qdrant curl -X POST http://localhost:6333/collections -H "Content-Type: application/json" -d @/docker-entrypoint-initdb.d/qdrant-collections.json
```

## Estructura de Despliegue

### Diagrama de Contenedores

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose Network                  │
│                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │  API    │  │  User   │  │Document │  │Terminal │         │
│  │ Gateway │  │ Service │  │ Service │  │ Gateway │         │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘         │
│       │            │            │            │              │
│  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐         │
│  │ Context │  │Embedding│  │  RAG    │  │Terminal │         │
│  │ Service │  │ Service │  │  Agent  │  │ Session │         │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘         │
│       │            │            │            │              │
│  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐         │
│  │ MongoDB │  │ Qdrant  │  │ MinIO   │  │ Ollama  │         │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### Puertos Expuestos

- **8080**: API Gateway
- **8081**: User Service (interno)
- **8082**: Document Service (interno)
- **8083**: Context Service (interno)
- **8084**: Embedding Service (interno)
- **8085**: RAG Agent (interno)
- **8086**: Terminal Gateway (interno)
- **8087**: Terminal Session Service (interno)
- **9000**: MinIO API (interno)
- **9001**: MinIO Console (opcional, expuesto para administración)
- **6333**: Qdrant API (interno)
- **6334**: Qdrant UI (opcional, expuesto para administración)
- **27017**: MongoDB (interno)
- **11434**: Ollama API (interno)

## Configuración de Alta Disponibilidad (Entorno de Producción)

Para entornos de producción con alta disponibilidad:

### Escalado de Servicios

```bash
# Escalar servicios críticos
docker-compose up -d --scale api-gateway=2 --scale document-service=2 --scale embedding-service=2
```

### Configuración con Docker Swarm

Para entornos más grandes, utiliza Docker Swarm:

```bash
# Inicializar Swarm
docker swarm init

# Desplegar el stack
docker stack deploy -c docker-compose.prod.yml aiss-backend
```

### Balanceo de Carga

Añadir un balanceador de carga (como Nginx o Traefik) delante del API Gateway:

```nginx
# Ejemplo de configuración de Nginx
upstream api_gateway {
    server api-gateway-1:8080;
    server api-gateway-2:8080;
}

server {
    listen 80;
    server_name api.yourcompany.com;

    location / {
        proxy_pass http://api_gateway;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Monitoreo y Mantenimiento

### Monitoreo de Servicios

Configurar Prometheus y Grafana para monitoreo:

```bash
# Iniciar stack de monitoreo
docker-compose -f docker-compose.monitoring.yml up -d
```

### Backup y Recuperación

```bash
# Backup de MongoDB
docker-compose exec mongodb mongodump --out /backup/$(date +%Y-%m-%d)

# Backup de Qdrant
docker-compose exec qdrant curl -X GET http://localhost:6333/collections/general_knowledge/snapshot?snapshot=/backup/qdrant_$(date +%Y-%m-%d).snapshot
```

### Actualización del Sistema

```bash
# Obtener últimos cambios
git pull

# Reconstruir y actualizar servicios
docker-compose down
docker-compose build
docker-compose up -d
```

## Solución de Problemas

### Problema: Servicios que no inician

Verificar logs del servicio específico:
```bash
docker-compose logs <service-name>
```

### Problema: Errores de conexión entre servicios

Verificar configuración de red y variables de entorno:
```bash
docker-compose config
docker network inspect backend-aiss_default
```

### Problema: Alto uso de memoria

Ajustar límites de memoria en docker-compose.yml:
```yaml
services:
  embedding-service:
    deploy:
      resources:
        limits:
          memory: 4G
```

### Problema: Errores en la generación de embeddings

Verificar configuración del servicio de embeddings:
```bash
docker-compose logs embedding-service
```

## Consideraciones de Seguridad

1. **Cambiar todas las contraseñas por defecto** en el archivo `.env`
2. **Configurar HTTPS** para el API Gateway
3. **Restringir CORS** a dominios específicos
4. **Rotar regularmente** las claves JWT
5. **Configurar autenticación** para MongoDB, Qdrant y MinIO
6. **Limitar acceso a la red Docker** desde el exterior
7. **Utilizar secretos de Docker** para información sensible

## Más Información

Para más detalles sobre configuraciones específicas y avanzadas, consultar:

- [Configuración Avanzada de Servicios](../advanced/services-config.md)
- [Integración con Servicios Externos](../integration/external-services.md)
- [Guía de Actualización](../maintenance/upgrade-guide.md)