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

## Configuración de Red Docker

El sistema utiliza una arquitectura de red Docker segura donde el backend está aislado de la red externa, con un proxy inverso en el frontend para la comunicación.

### Estructura de Red

```
   Internet/Red Externa
          |
          ↓
  +---------------+
  |   Frontend    | ← Los usuarios se conectan aquí (puerto 80/443)
  | (Nginx/Proxy) |
  +-------+-------+
          |
          ↓
  +---------------+
  |  API Gateway  | ← No expuesto externamente, solo accesible desde la red Docker
  +-------+-------+
          |
          ↓
+------------------+
| Servicios Internos | ← Solo accesibles dentro de la red Docker
+------------------+
```

### Nombres de Servicio Docker

Los servicios están disponibles en la red Docker interna con estos nombres de host:

| Servicio                        | Nombre de Host Docker      | Puerto Interno |
|---------------------------------|----------------------------|----------------|
| API Gateway                     | api-gateway                | 8080           |
| Servicio de Usuarios            | user-service               | 8081           |
| Servicio de Documentos          | document-service           | 8082           |
| Servicio de Contexto MCP        | context-service            | 8083           |
| Servicio de Embedding           | embedding-service          | 8084           |
| Servicio RAG                    | rag-agent                  | 8085           |
| Gateway de Terminal             | terminal-gateway-service   | 8086           |
| Servicio de Sesión Terminal     | terminal-session-service   | 8087           |
| Servicio de Sugerencias         | terminal-suggestion-service| 8088           |
| Servicio de Conexión a BD       | db-connection-service      | 8089           |
| Servicio de Descubrimiento      | schema-discovery-service   | 8090           |
| Servicio de Contexto Terminal   | terminal-context-aggregator| 8091           |

### Comunicación Frontend-Backend

El frontend debe configurarse para utilizar un proxy inverso (Nginx) que redirija todas las solicitudes de API a la API Gateway dentro de la red Docker. Ejemplo de configuración:

```nginx
# Dentro del archivo nginx.conf del frontend
location /api/ {
    proxy_pass http://api-gateway:8080/api/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache_bypass $http_upgrade;
}

# Para conexiones WebSocket a terminal
location /ws/ {
    proxy_pass http://terminal-gateway-service:8086/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

Para más detalles sobre la configuración del proxy, consulte [Configuración Docker con Proxy Inverso](deployment/docker-proxy-config.md).

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
- **Tecnología**: Go/Python
- **Función**: Integración con terminal y shell
- **Responsabilidades**:
  - Gestión de sesiones SSH
  - Análisis de comandos
  - Sugerencias inteligentes
  - Integración con Context Service

### DB Services
- **Tecnología**: Python
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

### 4. Integración con Base de Datos Externa

```
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  Cliente  │───▶│ API       │───▶│ DB        │───▶│ DB Conn   │
│           │    │ Gateway   │    │ Agent     │    │ Service   │
└───────────┘    └───────────┘    └───────────┘    └───────────┘
                                        │                │
                                        │                ▼
                                        │          ┌───────────┐
                                        │          │ Base de   │
                                        │          │ Datos     │
                                        │          └───────────┘
                                        │                │
                                        │                ▼
                                        │          ┌───────────┐
                                        │          │ Schema    │
                                        │          │ Discovery │
                                        │          └───────────┘
                                        ▼
                                  ┌───────────┐
                                  │ RAG Agent │
                                  │ (LLM)     │
                                  └───────────┘
```

## Comunicación entre Servicios

- **Interna**: APIs RESTful sobre HTTP con autenticación por tokens JWT
- **Externa**: APIs RESTful públicas protegidas por autenticación
- **Documentos y Objetos**: Acceso a través de firmados URLs presignadas
- **Sincronización**: Combinación de modelos síncronos (peticiones directas) y asíncronos para operaciones largas

## Seguridad

Los aspectos de seguridad principales incluyen:

1. **Autenticación**: JWT con validación completa (emisor, audiencia, ID único)
2. **Autorización**: Control de acceso basado en roles (RBAC)
3. **Encriptación en tránsito**: HTTPS y WSS para conexiones externas
4. **Encriptación de datos sensibles**: Para credenciales de base de datos y tokens
5. **Aislamiento de red Docker**: API Gateway y servicios no expuestos externamente
6. **Protección contra inyección SQL**: Validación avanzada de consultas
7. **Validación de API keys**: Para proveedores LLM externos
8. **Limitación de tasa**: Para prevenir uso excesivo de APIs externas

## Escalabilidad

El sistema está diseñado para ser escalado horizontalmente:

- Cada servicio puede desplegarse en múltiples instancias
- Bases de datos configurables para replicación
- Servicios stateless donde sea posible
- API Gateway con capacidad de balanceo de carga
- Servicios de procesamiento pesado (como el Embedding Service) configurados para scale-out automático

## Referencia a Documentación Detallada

Para información más detallada sobre componentes específicos, consulte:

- [Servicios Core](services/core-services.md)
- [Servicios de Terminal](services/terminal-services.md)
- [Servicios de MCP](services/mcp-services.md)
- [Servicios de BD](services/db-services.md)
- [Agente RAG](services/rag-agent.md)
- [Integración de Bases de Datos](integration/db-integration.md)
- [Integración de Terminal](integration/terminal-integration.md)
- [Seguridad](security/security.md)
- [Despliegue](deployment/deployment.md)