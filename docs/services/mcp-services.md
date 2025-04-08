# MCP Services

## Visión General

Los Model Context Protocol (MCP) Services son componentes esenciales del backend que implementan el protocolo MCP para la gestión contextual de datos y la generación de embeddings. Estos servicios permiten la estructuración, recuperación y utilización inteligente de la información. Incluyen el Context Service, Embedding Service y servicios compatibles con múltiples proveedores de LLM como OpenAI, Anthropic, Google Gemini y Ollama a través de una interfaz común.

## Componentes Principales

El sistema MCP está compuesto por varios servicios principales: Context Service, Embedding Service, Ollama MCP Server y Attack Vulnerability Service. Estos servicios trabajan en conjunto para proporcionar capacidades avanzadas de procesamiento, recuperación contextual y análisis de seguridad.

```
┌───────────────────────────────────────────────────────────┐
│                     MCP Services                           │
│                                                           │
│  ┌─────────────────────┐       ┌─────────────────────┐    │
│  │                     │       │                     │    │
│  │   Context Service   │◀─────▶│  Embedding Service  │    │
│  │                     │       │                     │    │
│  └─────────────┬───────┘       └─────────┬───────────┘    │
│                │                         │                │
│                ▼                         ▼                │
│  ┌─────────────────────┐       ┌─────────────────────┐    │
│  │                     │       │                     │    │
│  │     MongoDB         │       │      Qdrant         │    │
│  │                     │       │                     │    │
│  └─────────────────────┘       └─────────────────────┘    │
│                │                                          │
│                ▼                                          │
│  ┌─────────────────────┐       ┌─────────────────────┐    │
│  │                     │       │                     │    │
│  │  Ollama MCP Server  │◀─────▶│      Ollama         │    │
│  │                     │       │                     │    │
│  └─────────────────────┘       └─────────────────────┘    │
│                                                           │
│  ┌─────────────────────┐       ┌─────────────────────┐    │
│  │                     │       │                     │    │
│  │  Attack Vulnera-    │◀─────▶│ Terminal Gateway    │    │
│  │  bility Service     │       │ Service             │    │
│  └─────────────────────┘       └─────────────────────┘    │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### Context Service

El Context Service es responsable de la gestión de contextos y áreas de conocimiento, permitiendo la organización jerárquica de la información y proporcionando capacidades para estructurar el conocimiento en dominios específicos.

#### Características Principales:

- **Gestión de áreas de conocimiento**: Creación, actualización y organización de áreas y subáreas
- **Gestión de contextos**: Almacenamiento y recuperación de información contextual
- **Estructuración jerárquica**: Relaciones padre-hijo entre áreas
- **Metadatos avanzados**: Asociación de metadatos a contextos para optimizar la recuperación
- **Indexación inteligente**: Preprocesamiento para mejorar la relevancia de las búsquedas
- **Asignación de LLM por área**: Capacidad de asignar un proveedor LLM específico a cada área de conocimiento
- **Compatibilidad multi-proveedor**: Soporte para OpenAI, Anthropic, Google Gemini y Ollama

#### Tecnologías Utilizadas:

- **Python 3.10+**: Lenguaje de programación principal
- **FastAPI**: Framework web de alto rendimiento
- **MongoDB**: Base de datos para almacenamiento de contextos y áreas
- **Pydantic**: Validación de datos y serialización
- **PyMongo**: Cliente MongoDB para Python

### Embedding Service

El Embedding Service es responsable de la generación, almacenamiento y búsqueda de embeddings vectoriales para textos, permitiendo búsquedas semánticas.

#### Características Principales:

- **Generación de embeddings**: Conversión de texto a vectores mediante modelos avanzados
- **Búsqueda semántica**: Recuperación de información basada en similitud conceptual
- **Procesamiento por lotes**: Optimización para grandes volúmenes de datos
- **Caché inteligente**: Reducción de procesamiento para textos recurrentes
- **Adaptabilidad multi-modelo**: Soporte para diferentes modelos de embeddings

#### Tecnologías Utilizadas:

- **Python 3.10+**: Lenguaje de programación principal
- **FastAPI**: Framework web de alto rendimiento
- **nomic-ai/nomic-embed-text-v1.5-fp16**: Modelo de embeddings principal
- **Transformers (Hugging Face)**: Librería para modelos de NLP
- **Qdrant**: Base de datos vectorial para almacenamiento y búsqueda
- **PyTorch**: Framework de aprendizaje automático
- **CUDA/ROCm**: Aceleración por GPU (opcional)

### Attack Vulnerability Service

El Attack Vulnerability Service es responsable de analizar vulnerabilidades en sistemas remotos basándose en el framework MITRE ATT&CK, proporcionando alertas de seguridad en tiempo real durante sesiones SSH.

#### Características Principales:

- **Análisis basado en MITRE ATT&CK**: Identificación de técnicas y tácticas aplicables a software detectado
- **Detección automática de software**: Identificación de sistemas operativos y aplicaciones instaladas
- **Clasificación de vulnerabilidades**: Categorización por nivel de severidad y impacto
- **Notificaciones en tiempo real**: Alertas inmediatas sobre vulnerabilidades críticas
- **Integración con terminal**: Funcionamiento transparente con las sesiones SSH existentes

#### Tecnologías Utilizadas:

- **Python 3.9+**: Lenguaje de programación principal
- **FastAPI**: Framework web de alto rendimiento
- **attackcti**: Cliente Python para MITRE ATT&CK
- **MongoDB**: Almacenamiento de información temporal de sesiones
- **packaging**: Para comparación y análisis de versiones de software

## Arquitectura y Flujo de Datos

### Diagrama de Flujo para Procesamiento de Documentos

```
┌─────────────┐     ┌────────────────┐     ┌────────────────┐
│ API Gateway │────▶│ Document       │────▶│ Context        │
│             │     │ Service        │     │ Service        │
└─────────────┘     └────────────────┘     └────────────────┘
                           │                       │
                           │                       │
                           │                       │
                           ▼                       ▼
                    ┌────────────────┐     ┌────────────────┐
                    │ MinIO          │     │ MongoDB        │
                    │ (docs storage) │     │ (metadata)     │
                    └────────────────┘     └────────────────┘
                                                   │
                                                   │
                                                   ▼
                                           ┌────────────────┐
                                           │ Embedding      │
                                           │ Service        │
                                           └────────────────┘
                                                   │
                                                   │
                                                   ▼
                                           ┌────────────────┐
                                           │ Qdrant         │
                                           │ (vector DB)    │
                                           └────────────────┘
```

### Diagrama de Flujo para Consultas RAG

```
┌─────────────┐     ┌────────────────┐
│ API Gateway │────▶│ RAG Agent      │
│             │     │                │
└─────────────┘     └────────┬───────┘
                             │
                             ▼
              ┌───────────────────────────┐
              │                           │
              ▼                           ▼
     ┌────────────────┐         ┌────────────────┐
     │ Embedding      │         │ Context        │
     │ Service        │         │ Service        │
     └────────┬───────┘         └────────┬───────┘
              │                          │
              ▼                          ▼
     ┌────────────────┐         ┌────────────────┐
     │ Qdrant         │         │ MongoDB        │
     │ (vector DB)    │         │ (metadata)     │
     └────────────────┘         └────────────────┘
              │                          │
              └──────────────┬───────────┘
                             │
                             ▼
              ┌───────────────────────────┐
              │                           │
              ▼                           ▼
     ┌────────────────┐         ┌────────────────┐
     │ External LLM   │         │ Ollama MCP     │
     │ Provider       │         │ Server         │
     └────────────────┘         └────────┬───────┘
                                         │
                                         ▼
                                ┌────────────────┐
                                │ Ollama         │
                                │ (Local LLM)    │
                                └────────────────┘
```

### Diagrama de Flujo para Análisis de Vulnerabilidades

```
┌─────────────┐     ┌────────────────┐     ┌────────────────┐
│ Usuario     │────▶│ Terminal       │────▶│ SSH            │
│             │     │ Gateway        │     │ Connection     │
└─────────────┘     └────────┬───────┘     └────────┬───────┘
                             │                      │
                             │                      │
                             │     ┌───────────────▶│
                             │     │                │
                             ▼     │                ▼
                    ┌────────────────┐      ┌────────────────┐
                    │ detectOSInfo   │      │ Remote System  │
                    │ detectSoftware │      │ (OS + Apps)    │
                    └────────┬───────┘      └────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ Attack         │
                    │ Vulnerability  │
                    │ Service        │
                    └────────┬───────┘
                             │
                             │
              ┌──────────────┴───────────┐
              │                          │
              ▼                          ▼
     ┌────────────────┐         ┌────────────────┐
     │ MITRE ATT&CK   │         │ Local Cache    │
     │ Data           │         │                │
     └────────────────┘         └────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ Vulnerability   │
                    │ Notifications   │
                    │ to User        │
                    └────────────────┘
```

## APIs y Endpoints

### Context Service API

#### Áreas de Conocimiento

- **GET /api/v1/areas**: Listar todas las áreas
- **GET /api/v1/areas/{id}**: Obtener área específica
- **POST /api/v1/areas**: Crear nueva área
- **PUT /api/v1/areas/{id}**: Actualizar área existente
- **DELETE /api/v1/areas/{id}**: Eliminar área
- **PUT /api/v1/areas/{id}/primary-llm**: Asignar un LLM principal a un área
- **GET /api/v1/areas/{id}/primary-llm**: Obtener el LLM principal de un área
- **PUT /api/v1/areas/{id}/system-prompt**: Actualizar el prompt de sistema de un área
- **GET /api/v1/areas/{id}/system-prompt**: Obtener el prompt de sistema de un área

#### Contextos

- **GET /api/v1/contexts**: Listar contextos
- **GET /api/v1/contexts/{id}**: Obtener contexto específico
- **POST /api/v1/contexts**: Crear nuevo contexto
- **PUT /api/v1/contexts/{id}**: Actualizar contexto existente
- **DELETE /api/v1/contexts/{id}**: Eliminar contexto

#### Búsqueda de Contexto

- **POST /api/v1/contexts/search**: Buscar contextos

### Embedding Service API

#### Generación de Embeddings

- **POST /api/v1/embeddings**: Generar embeddings para texto
- **POST /api/v1/embeddings/batch**: Generar embeddings por lotes

#### Búsqueda Semántica

- **POST /api/v1/search**: Búsqueda semántica por similitud
- **POST /api/v1/search/hybrid**: Búsqueda híbrida (keyword + semántica)

#### Gestión de Colecciones

- **GET /api/v1/collections**: Listar colecciones
- **GET /api/v1/collections/{name}**: Obtener información de colección
- **POST /api/v1/collections**: Crear nueva colección
- **DELETE /api/v1/collections/{name}**: Eliminar colección

## Modelos de Datos

### Context Service

#### Área de Conocimiento

```json
{
  "id": "area123",
  "name": "Documentación Técnica",
  "description": "Documentación técnica del sistema",
  "parent_id": null,
  "metadata": {
    "icon": "document",
    "color": "blue"
  },
  "primary_llm_provider_id": "llm_provider_openai_123",
  "mcp_context_id": "ctx_123456789",
  "created_by": "user123",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-02T00:00:00Z"
}
```

#### Contexto

```json
{
  "id": "ctx123",
  "area_id": "area123",
  "type": "document_chunk",
  "content": "El sistema implementa una arquitectura de microservicios...",
  "metadata": {
    "document_id": "doc456",
    "chunk_id": 3,
    "page": 2,
    "source": "manual_tecnico.pdf"
  },
  "embedding_id": "emb789",
  "created_at": "2023-01-02T00:00:00Z",
  "updated_at": "2023-01-02T00:00:00Z"
}
```

### Embedding Service

#### Embedding

```json
{
  "id": "emb789",
  "content_id": "ctx123",
  "model": "nomic-ai/nomic-embed-text-v1.5-fp16",
  "vector": [0.123, 0.456, ...],
  "dimensions": 1024,
  "content_hash": "a1b2c3d4...",
  "metadata": {
    "document_id": "doc456",
    "area_id": "area123",
    "chunk_id": 3
  },
  "created_at": "2023-01-02T00:00:00Z"
}
```

#### Colección

```json
{
  "name": "general_knowledge",
  "vector_size": 1024,
  "model": "nomic-ai/nomic-embed-text-v1.5-fp16",
  "distance": "cosine",
  "count": 12345,
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-03T00:00:00Z"
}
```

## Configuración

### Context Service

El Context Service se configura mediante variables de entorno o archivo `.env`:

```
# Configuración del servidor
PORT=8083
ENVIRONMENT=production
LOG_LEVEL=info

# Configuración de MongoDB
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=mcp_context_service

# Configuración del Embedding Service
EMBEDDING_SERVICE_URL=http://embedding-service:8084

# Configuración de cache
CACHE_ENABLED=true
CACHE_TTL_SECONDS=3600
```

### Embedding Service

El Embedding Service se configura mediante variables de entorno o archivo `.env`:

```
# Configuración del servidor
PORT=8084
ENVIRONMENT=production
LOG_LEVEL=info

# Configuración de MongoDB
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=mcp_embedding_service

# Configuración de Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

# Configuración de modelos
GENERAL_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5-fp16
PERSONAL_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5-fp16
USE_GPU=true
USE_FP16=true
USE_8BIT=false
MAX_LENGTH=512

# Configuración de procesamiento
BATCH_SIZE=32
SIMILARITY_THRESHOLD=0.65
```

## Rendimiento y Escalabilidad

### Optimizaciones Implementadas

1. **Procesamiento por lotes**: Mejora el throughput al procesar múltiples textos juntos
2. **Cache de embeddings**: Reutilización de embeddings para textos idénticos
3. **Optimizaciones GPU**: Utilización de FP16 y paralelización para acelerar generación
4. **Descomposición de textos**: División inteligente para documentos largos
5. **Indexación vectorial**: Estructura de datos optimizada para búsqueda KNN

### Métricas de Rendimiento

| Operación | Tiempo Promedio | Throughput |
|-----------|-----------------|------------|
| Generación de embedding (1 texto) | 50-100ms | 10-20/s |
| Generación por lotes (32 textos) | 800-1200ms | 25-40/s |
| Búsqueda semántica | 30-50ms | 20-30/s |
| Creación de área | 20-30ms | 30-50/s |
| Búsqueda de contexto | 40-70ms | 15-25/s |

### Recomendaciones de Escalado

- **Vertical**: Incrementar memoria RAM y GPUs para el Embedding Service
- **Horizontal**: Añadir réplicas adicionales del Context Service
- **Databases**: Configurar replicación para MongoDB y Qdrant
- **Caching**: Implementar Redis para cache distribuida
- **Particionado**: Dividir colecciones de vectores por área o tipo de contenido

## Monitoreo y Diagnóstico

### Métricas de Salud

- **GET /health**: Estado del servicio y sus dependencias
- **GET /metrics**: Métricas en formato Prometheus

## Asignación de Proveedores LLM por Área

El sistema permite asignar un proveedor LLM específico a cada área de conocimiento, lo que permite especializar los modelos según el dominio o las necesidades específicas del conocimiento.

### Beneficios

- **Especialización por dominio**: Usar modelos específicos optimizados para cada tipo de conocimiento
- **Optimización de recursos**: Asignar modelos más grandes o potentes solo a las áreas que lo requieren
- **Balanceo de carga**: Distribuir las consultas entre diferentes proveedores según las áreas
- **Fallback automático**: Si el proveedor específico no está disponible, se usa el proveedor predeterminado

### Flujo de asignación

1. El administrador del sistema crea un proveedor LLM en la base de datos (OpenAI, Anthropic, Google, Ollama)
2. Al crear o editar un área de conocimiento, se asigna un proveedor LLM específico usando la API
3. Cuando se realizan consultas a esa área específica, el sistema automáticamente usa el proveedor asignado

### Ejemplo de uso

```json
// Asignar un proveedor LLM específico al área "Documentación Técnica"
PUT /api/v1/areas/area123/primary-llm
{
  "llm_provider_id": "provider_anthropic_456"
}

// Consultar el proveedor LLM asignado
GET /api/v1/areas/area123/primary-llm
{
  "area_id": "area123",
  "primary_llm_provider_id": "provider_anthropic_456"
}

// Al realizar consultas al RAG Agent, se especifica el área
POST /api/v1/llm
{
  "prompt": "¿Cómo funciona la arquitectura MCP?",
  "area_id": "area123"  // Con esto, el sistema usa automáticamente el proveedor Anthropic
}
```

### Logs y Trazas

Los servicios utilizan un formato de log estructurado:

```
{
  "timestamp": "2023-05-10T14:30:00Z",
  "level": "INFO",
  "service": "embedding-service",
  "message": "Generated embeddings batch",
  "details": {
    "batch_size": 32,
    "processing_time_ms": 952,
    "model": "BAAI/bge-large-en-v1.5"
  },
  "request_id": "req-123456"
}
```

### Alertas Configuradas

1. **Alto tiempo de respuesta**: >500ms para operaciones críticas
2. **Error rate**: >1% de requests con error
3. **Utilización de memoria**: >90% de memoria disponible
4. **Utilización de GPU**: >95% por más de 5 minutos
5. **Queue depth**: >100 operaciones pendientes

## Guía de Solución de Problemas

### Problemas Comunes y Soluciones

| Problema | Posibles Causas | Soluciones |
|----------|-----------------|------------|
| Alto tiempo de respuesta | GPU saturada, tráfico excesivo | Incrementar réplicas, ajustar batch size |
| Errores en generación de embeddings | Modelo no disponible, CUDA OOM | Verificar GPU, reducir max_length |
| Inconsistencia en resultados de búsqueda | Índice desactualizado, umbral incorrecto | Reconstruir índice, ajustar similarity_threshold |
| Conexión fallida a Qdrant | Red, credenciales | Verificar conectividad, API key |
| MongoDB timeout | Consultas pesadas, índices faltantes | Optimizar queries, añadir índices |

### Comandos de Diagnóstico

```bash
# Verificar estado del servicio
curl http://embedding-service:8084/health

# Verificar métricas
curl http://embedding-service:8084/metrics

# Testear generación de embeddings
curl -X POST http://embedding-service:8084/api/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"text": "Texto de prueba", "model": "nomic-ai/nomic-embed-text-v1.5-fp16"}'

# Verificar índices de Qdrant
curl http://qdrant:6333/collections/general_knowledge
```

## Referencias

- [Documentación de FastAPI](https://fastapi.tiangolo.com/)
- [MongoDB Documentation](https://docs.mongodb.com/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Hugging Face Transformers](https://huggingface.co/docs/transformers/)
- [nomic-ai/nomic-embed-text-v1.5-fp16](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-fp16)