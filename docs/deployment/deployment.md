# Instrucciones de Despliegue

Este documento proporciona instrucciones detalladas para desplegar el Sistema de Gestión de Conocimiento con Model Context Protocol (MCP) utilizando Docker y Docker Compose.

## Requisitos Previos

### Hardware
- CPU: Mínimo 4 núcleos (recomendado 8+)
- RAM: Mínimo 16GB (recomendado 32GB+)
- Almacenamiento: Mínimo 50GB SSD
- GPU: Recomendada NVIDIA con CUDA compatible (para servicio de embeddings)

### Software
- Docker Engine 24.0.0+
- Docker Compose 2.20.0+
- NVIDIA Driver (si va a usar GPU)
- NVIDIA Container Toolkit (si va a usar GPU)

## Estructura del Proyecto

Asegúrese de tener la estructura de directorios del proyecto como se muestra a continuación:

```
mcp-knowledge-system/
├── api-gateway/
│   ├── Dockerfile
│   ├── go.mod
│   ├── go.sum
│   ├── main.go
│   └── ...
├── core-services/
│   ├── user-service/
│   │   ├── Dockerfile
│   │   └── ...
│   └── document-service/
│       ├── Dockerfile
│       └── ...
├── mcp-services/
│   ├── context-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── ...
│   └── embedding-service/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── ...
├── rag-agent/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ...
├── docker-compose.yml
└── .env
```

## Configuración

### Variables de Entorno

Cree un archivo `.env` en el directorio raíz con las siguientes variables (ajuste los valores según sus necesidades):

```
# Autenticación
AUTH_SECRET=your_auth_secret_key_here
ADMIN_INITIAL_PASSWORD=secure_admin_password

# MinIO
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Modelos de Embeddings
GENERAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L12-v2
PERSONAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L12-v2
USE_GPU=true

# Modelos LLM
OPENAI_DEFAULT_MODEL=gpt-4o
ANTHROPIC_DEFAULT_MODEL=claude-3-opus-20240229
OLLAMA_DEFAULT_MODEL=llama3
```

### Configuración GPU (Opcional)

Si va a utilizar GPU para el servicio de embeddings:

1. Asegúrese de tener instalado el driver NVIDIA y NVIDIA Container Toolkit:

```bash
# Verificar instalación del driver NVIDIA
nvidia-smi

# Instalar NVIDIA Container Toolkit (Ubuntu)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

2. Verifique que Docker puede acceder a la GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

## Pasos de Despliegue

### 1. Construir Imágenes

Navegue al directorio raíz del proyecto y construya todas las imágenes:

```bash
docker-compose build
```

Este proceso puede tardar varios minutos dependiendo de su conexión a Internet y el hardware disponible.

### 2. Iniciar los Servicios

Una vez construidas las imágenes, inicie los servicios:

```bash
docker-compose up -d
```

La opción `-d` ejecuta los contenedores en segundo plano.

### 3. Verificar el Despliegue

Verifique que todos los servicios estén ejecutándose correctamente:

```bash
docker-compose ps
```

También puede verificar los logs de cada servicio:

```bash
# Ver logs de todos los servicios
docker-compose logs

# Ver logs de un servicio específico
docker-compose logs api-gateway
```

### 4. Verificar Conectividad

Pruebe el punto de entrada del API Gateway:

```bash
curl http://localhost:8080/health
```

Debería recibir una respuesta como:

```json
{"status":"ok"}
```

### 5. Configuración Inicial

#### 5.1. Acceso al Administrador

El sistema crea automáticamente un usuario administrador al iniciar por primera vez con estas credenciales:

- **Username**: admin
- **Password**: El valor de `ADMIN_INITIAL_PASSWORD` en el archivo `.env` (o `admin123` si no se especificó)

#### 5.2. Configurar Proveedor LLM

Después de iniciar sesión como administrador, configure al menos un proveedor LLM:

```bash
# Ejemplo: Configurar OpenAI como proveedor
curl -X POST http://localhost:8080/llm/providers \
  -H "Authorization: Bearer <token_admin>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OpenAI GPT-4",
    "type": "openai",
    "api_key": "sk-your_openai_key",
    "model": "gpt-4o",
    "default": true,
    "temperature": 0.0,
    "max_tokens": 4096
  }'
```

## Mantenimiento

### Detener los Servicios

Para detener todos los servicios:

```bash
docker-compose down
```

### Respaldos

Es recomendable realizar respaldos periódicos de los volúmenes de datos:

```bash
# Crear directorio de respaldos
mkdir -p backups

# Respaldar MongoDB
docker run --rm -v mcp-knowledge-system_mongodb-data:/data -v $(pwd)/backups:/backup \
  ubuntu tar cvf /backup/mongodb.js-backup.tar /data

# Respaldar Qdrant
docker run --rm -v mcp-knowledge-system_qdrant-data:/data -v $(pwd)/backups:/backup \
  ubuntu tar cvf /backup/qdrant.yaml-backup.tar /data

# Respaldar MinIO
docker run --rm -v mcp-knowledge-system_minio-data:/data -v $(pwd)/backups:/backup \
  ubuntu tar cvf /backup/init.sh-backup.tar /data
```

### Actualización

Para actualizar el sistema:

1. Detenga los servicios:
```bash
docker-compose down
```

2. Actualice el código fuente

3. Reconstruya las imágenes:
```bash
docker-compose build
```

4. Inicie los servicios nuevamente:
```bash
docker-compose up -d
```

## Solución de Problemas

### Problemas de Conexión

Si los servicios no pueden comunicarse entre sí:

1. Verifique que todos los servicios estén en la misma red:
```bash
docker network inspect mcp-knowledge-system_mcp-network
```

2. Verifique que los nombres de host en la configuración coincidan con los nombres de los servicios en `docker-compose.yml`

### Problemas con GPU

Si el servicio de embeddings no puede acceder a la GPU:

1. Verifique que NVIDIA Container Toolkit esté instalado correctamente
2. Verifique que el servicio en `docker-compose.yml` tenga la configuración correcta para GPU
3. Pruebe ejecutar un contenedor CUDA simple:
```bash
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

### Logs de Servicios

Revise los logs para obtener más información sobre errores:

```bash
# Ver los últimos 100 líneas de log de un servicio específico
docker-compose logs --tail=100 embedding-service
```

## Monitoreo y Escalabilidad

### Monitoreo

Para un entorno de producción, se recomienda configurar herramientas de monitoreo:

- Prometheus para métricas
- Grafana para visualización
- ELK Stack para logs centralizados

### Escalabilidad

El sistema puede escalar horizontalmente:

1. Para servicios sin estado (como API Gateway), puede aumentar el número de réplicas:
```yaml
api-gateway:
  deploy:
    replicas: 3
```

2. Para servicios con estado, considere implementar soluciones de alta disponibilidad para las bases de datos (MongoDB, Qdrant)