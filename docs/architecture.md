# Arquitectura del Sistema

## Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Cliente (Frontend)                          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                             API Gateway                              │
│                                                                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │   Routing   │ │    Auth     │ │   CORS      │ │Rate Limiting│   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
└───────┬─────────────────┬────────────────┬───────────────┬──────────┘
        │                 │                │               │
        ▼                 ▼                ▼               ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐ ┌──────────────┐
│ User Service │  │   Document   │  │  Terminal    │ │ DB Services  │
│  (Core)      │  │   Service    │  │  Services    │ │              │
└───────┬──────┘  └───────┬──────┘  └───────┬──────┘ └───────┬──────┘
        │                 │                 │                │
        │                 │                 │                │
┌───────▼─────────────────▼─────────────────▼────────────────▼───────┐
│                      Datos y Almacenamiento                        │
│                                                                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │
│  │  MongoDB   │ │   Qdrant   │ │   MinIO    │ │  Ollama    │      │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘      │
└────────────────────────────────────────────────────────────────────┘
        │                 │                 │                │
        │                 │                 │                │
┌───────▼─────────────────▼─────────────────▼────────────────▼───────┐
│                      MCP Services & RAG Agent                      │
│                                                                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │
│  │  Context   │ │ Embedding  │ │ RAG Agent  │ │ External   │      │
│  │  Service   │ │  Service   │ │            │ │ LLM APIs   │      │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘      │
└────────────────────────────────────────────────────────────────────┘
```

## Descripción de los Componentes

### API Gateway
- **Tecnología**: Go
- **Función**: Punto de entrada único para todas las peticiones al sistema
- **Responsabilidades**: 
  - Enrutamiento de peticiones a los servicios apropiados
  - Autenticación y autorización mediante JWT
  - Gestión de CORS y limitación de tasas
  - Balanceo de carga y health checks de servicios
- **Endpoints públicos**: Proporciona todas las APIs RESTful que el frontend utiliza

### Core Services

#### User Service
- **Tecnología**: Go
- **Función**: Gestión completa de usuarios y autenticación
- **Responsabilidades**:
  - Registro, autenticación y autorización de usuarios
  - Gestión de perfiles de usuario
  - Gestión de roles y permisos
  - Seguridad y auditoría de accesos

#### Document Service
- **Tecnología**: Go
- **Función**: Gestión del ciclo de vida de documentos
- **Responsabilidades**:
  - Carga, actualización y eliminación de documentos
  - Indexación y clasificación
  - Extracción de texto y metadatos
  - Coordinación con Embedding Service para generación de embeddings
  - Almacenamiento de documentos en MinIO

### MCP Services

#### Context Service
- **Tecnología**: Python
- **Función**: Gestión de contextos y áreas de conocimiento
- **Responsabilidades**:
  - Creación y gestión de áreas de conocimiento
  - Organización de información contextual
  - Estructuración jerárquica de conocimiento
  - Coordinación con Embedding Service para búsqueda semántica

#### Embedding Service
- **Tecnología**: Python
- **Función**: Generación y gestión de embeddings vectoriales
- **Responsabilidades**:
  - Generación de embeddings de textos con modelos avanzados
  - Almacenamiento y recuperación de embeddings en Qdrant
  - Búsqueda semántica por similitud
  - Optimización de rendimiento con soporte GPU

### RAG Agent
- **Tecnología**: Python
- **Función**: Procesamiento de consultas con RAG
- **Responsabilidades**:
  - Integración con diferentes LLMs (OpenAI, Anthropic, Ollama)
  - Recuperación de información relevante basada en consultas
  - Generación de respuestas aumentadas
  - Gestión de conversaciones y control de contexto

### Terminal Services
- **Tecnología**: Go
- **Función**: Integración con terminal y shell
- **Responsabilidades**:
  - Gestión de sesiones SSH
  - Análisis de comandos
  - Sugerencias inteligentes
  - Integración con Context Service

### DB Services
- **Tecnología**: Go y Python
- **Función**: Integración con bases de datos externas
- **Responsabilidades**:
  - Conexión a diferentes tipos de bases de datos
  - Descubrimiento de esquemas
  - Traducción de consultas en lenguaje natural a SQL
  - Ejecución segura de consultas

### Almacenamiento
- **MongoDB**: Almacenamiento principal para usuarios, documentos, metadatos
- **Qdrant**: Base de datos vectorial para embeddings
- **MinIO**: Almacenamiento de objetos para documentos originales
- **Ollama**: Servicio opcional para LLMs locales

## Flujo de Datos Principales

### 1. Procesamiento de Documentos

```
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  Cliente  │───▶│ API       │───▶│ Document  │───▶│ MinIO     │
│           │    │ Gateway   │    │ Service   │    │           │
└───────────┘    └───────────┘    └───────────┘    └───────────┘
                                        │
                                        ▼
                                  ┌───────────┐    ┌───────────┐
                                  │ Embedding │───▶│ Qdrant    │
                                  │ Service   │    │           │
                                  └───────────┘    └───────────┘
                                        │
                                        ▼
                                  ┌───────────┐    ┌───────────┐
                                  │ Context   │───▶│ MongoDB   │
                                  │ Service   │    │           │
                                  └───────────┘    └───────────┘
```

### 2. Consulta RAG

```
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  Cliente  │───▶│ API       │───▶│ RAG       │───▶│ Context   │
│           │    │ Gateway   │    │ Agent     │    │ Service   │
└───────────┘    └───────────┘    └───────────┘    └───────────┘
                                        │                │
                                        │                ▼
                                        │          ┌───────────┐
                                        │          │ Embedding │
                                        │          │ Service   │
                                        │          └───────────┘
                                        │                │
                                        │                ▼
                                        │          ┌───────────┐
                                        │          │ Qdrant    │
                                        │          │           │
                                        │          └───────────┘
                                        ▼
                                  ┌───────────┐
                                  │ LLM API   │
                                  │ (Externa) │
                                  └───────────┘
```

### 3. Integración de Terminal

```
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  Cliente  │───▶│ API       │───▶│ Terminal  │───▶│ Session   │
│ Terminal  │    │ Gateway   │    │ Gateway   │    │ Service   │
└───────────┘    └───────────┘    └───────────┘    └───────────┘
                                        │                │
                                        ▼                │
                                  ┌───────────┐          │
                                  │ SSH       │          │
                                  │ Manager   │          │
                                  └───────────┘          │
                                        │                │
                                        ▼                ▼
                                  ┌───────────┐    ┌───────────┐
                                  │ Command   │◀───│ Context   │
                                  │ Analysis  │    │ Service   │
                                  └───────────┘    └───────────┘
```

## Comunicación entre Servicios

- **Interna**: APIs RESTful sobre HTTP con autenticación por tokens JWT
- **Externa**: APIs RESTful públicas protegidas por autenticación
- **Documentos y Objetos**: Acceso a través de firmados URLs presignadas
- **Sincronización**: Combinación de modelos síncronos (peticiones directas) y asíncronos para operaciones largas

## Escalabilidad

El sistema está diseñado para ser escalado horizontalmente:

- Cada servicio puede desplegarse en múltiples instancias
- Bases de datos configurables para replicación
- Servicios stateless donde sea posible
- API Gateway con capacidad de balanceo de carga
- Servicios de procesamiento pesado (como el Embedding Service) configurados para scale-out automático