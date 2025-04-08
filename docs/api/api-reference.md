# API Reference

Esta documentación proporciona información detallada sobre todos los endpoints disponibles en el API Gateway del backend AISS.

## Índice

- [Autenticación](#autenticación)
- [Usuarios](#usuarios)
- [Documentos](#documentos)
- [Áreas de Conocimiento](#áreas-de-conocimiento)
- [RAG (Retrieval Augmented Generation)](#rag-retrieval-augmented-generation)
- [LLM (Modelos de Lenguaje)](#llm-modelos-de-lenguaje)
- [Bases de Datos](#bases-de-datos)
  - [Conexiones](#conexiones)
  - [Agentes Verificadores de Consultas](#agentes-verificadores-de-consultas)
  - [Consultas](#consultas)
- [Terminal](#terminal)
- [Ollama](#ollama)

## Convenciones

Todas las respuestas siguen un formato consistente:

```json
{
  "status": "success", // o "error"
  "data": {},          // datos de respuesta (solo en caso de éxito)
  "error": "",         // mensaje de error (solo en caso de error)
  "meta": {}           // metadatos adicionales (paginación, etc.)
}
```

### Paginación

Los endpoints que devuelven listas soportan paginación con los siguientes parámetros:

- `page`: Número de página (1 por defecto)
- `limit`: Número de elementos por página (20 por defecto, máximo 100)

Respuesta con paginación:

```json
{
  "status": "success",
  "data": [...],
  "meta": {
    "pagination": {
      "total": 100,
      "page": 1,
      "limit": 20,
      "pages": 5
    }
  }
}
```

## Autenticación

El sistema utiliza autenticación basada en JWT con dos tipos de tokens:
- Access Token: Validez corta (30 minutos)
- Refresh Token: Validez larga (7 días)

Todos los endpoints (excepto login y refresh) requieren un Access Token válido en el header:

```
Authorization: Bearer <access_token>
```

### POST /api/v1/auth/login

Inicia sesión y obtiene tokens.

**Request:**
```json
{
  "username": "user@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 1800,
    "user": {
      "id": "user123",
      "username": "user@example.com",
      "name": "John Doe",
      "role": "admin"
    }
  }
}
```

### POST /api/v1/auth/refresh

Renueva el access token usando el refresh token.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 1800
  }
}
```

### POST /api/v1/auth/logout

Cierra la sesión actual.

**Request:** No requiere body

**Response:**
```json
{
  "status": "success",
  "data": {
    "message": "Logged out successfully"
  }
}
```

## Usuarios

### GET /api/v1/users

Obtiene una lista paginada de usuarios (solo para administradores).

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "user123",
      "username": "user@example.com",
      "name": "John Doe",
      "role": "admin",
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z"
    },
    // ...más usuarios
  ],
  "meta": {
    "pagination": {
      "total": 100,
      "page": 1,
      "limit": 20,
      "pages": 5
    }
  }
}
```

### GET /api/v1/users/{id}

Obtiene un usuario específico por ID.

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "user123",
    "username": "user@example.com",
    "name": "John Doe",
    "role": "admin",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z"
  }
}
```

### POST /api/v1/users

Crea un nuevo usuario (solo para administradores).

**Request:**
```json
{
  "username": "newuser@example.com",
  "password": "password123",
  "name": "Jane Doe",
  "role": "user"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "user456",
    "username": "newuser@example.com",
    "name": "Jane Doe",
    "role": "user",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z"
  }
}
```

### PUT /api/v1/users/{id}

Actualiza un usuario existente.

**Request:**
```json
{
  "name": "Jane Smith",
  "role": "admin"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "user456",
    "username": "newuser@example.com",
    "name": "Jane Smith",
    "role": "admin",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-02T00:00:00Z"
  }
}
```

### DELETE /api/v1/users/{id}

Elimina un usuario (solo para administradores).

**Response:**
```json
{
  "status": "success",
  "data": {
    "message": "User deleted successfully"
  }
}
```

## Documentos

### GET /api/v1/documents

Obtiene una lista paginada de documentos.

**Query Parameters:**
- `page`: Número de página
- `limit`: Elementos por página
- `area_id`: (opcional) Filtrar por área de conocimiento
- `query`: (opcional) Buscar por texto
- `sort`: (opcional) Campo de ordenación (default: "created_at")
- `order`: (opcional) Dirección de ordenación ("asc" o "desc", default: "desc")

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "doc123",
      "title": "Manual de usuario",
      "description": "Manual completo de usuario",
      "file_name": "manual.pdf",
      "file_type": "application/pdf",
      "file_size": 1048576,
      "area_id": "area123",
      "created_by": "user123",
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z",
      "embedding_status": "completed",
      "tags": ["manual", "usuario"]
    },
    // ...más documentos
  ],
  "meta": {
    "pagination": {
      "total": 50,
      "page": 1,
      "limit": 20,
      "pages": 3
    }
  }
}
```

### GET /api/v1/documents/{id}

Obtiene un documento específico por ID.

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "doc123",
    "title": "Manual de usuario",
    "description": "Manual completo de usuario",
    "file_name": "manual.pdf",
    "file_type": "application/pdf",
    "file_size": 1048576,
    "area_id": "area123",
    "created_by": "user123",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z",
    "embedding_status": "completed",
    "tags": ["manual", "usuario"],
    "chunks_count": 15,
    "total_tokens": 12500
  }
}
```

### POST /api/v1/documents

Crea un nuevo documento (multipart/form-data).

**Request Form Data:**
- `title`: Título del documento
- `description`: (opcional) Descripción
- `area_id`: ID del área de conocimiento
- `tags`: (opcional) Tags separados por comas
- `file`: Archivo a subir

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "doc789",
    "title": "Nuevo manual",
    "description": "Descripción del nuevo manual",
    "file_name": "nuevo_manual.pdf",
    "file_type": "application/pdf",
    "file_size": 2097152,
    "area_id": "area123",
    "created_by": "user123",
    "created_at": "2023-01-03T00:00:00Z",
    "updated_at": "2023-01-03T00:00:00Z",
    "embedding_status": "processing",
    "tags": ["manual", "nuevo"]
  }
}
```

### PUT /api/v1/documents/{id}

Actualiza un documento existente.

**Request:**
```json
{
  "title": "Manual actualizado",
  "description": "Descripción actualizada",
  "area_id": "area456",
  "tags": ["manual", "actualizado"]
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "doc123",
    "title": "Manual actualizado",
    "description": "Descripción actualizada",
    "file_name": "manual.pdf",
    "file_type": "application/pdf",
    "file_size": 1048576,
    "area_id": "area456",
    "created_by": "user123",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-03T00:00:00Z",
    "embedding_status": "completed",
    "tags": ["manual", "actualizado"]
  }
}
```

### DELETE /api/v1/documents/{id}

Elimina un documento.

**Response:**
```json
{
  "status": "success",
  "data": {
    "message": "Document deleted successfully"
  }
}
```

### GET /api/v1/documents/{id}/content

Obtiene el contenido de un documento o genera una URL presignada.

**Query Parameters:**
- `format`: (opcional) Formato de respuesta ("raw", "html", "text", "url" - default: "url")

**Response (format=url):**
```json
{
  "status": "success",
  "data": {
    "url": "https://minio.example.com/documents/signed-url-for-document...",
    "expires_in": 3600
  }
}
```

**Response (format=text):**
```json
{
  "status": "success",
  "data": {
    "content": "Contenido en texto plano del documento...",
    "chunks": [
      {
        "id": "chunk1",
        "content": "Primer fragmento del documento...",
        "page": 1
      },
      // ...más chunks
    ]
  }
}
```

### GET /api/v1/documents/search

Busca documentos usando búsqueda semántica.

**Query Parameters:**
- `query`: Consulta de búsqueda
- `area_id`: (opcional) Filtrar por área
- `limit`: (opcional) Número máximo de resultados (default: 10)
- `threshold`: (opcional) Umbral de similitud (0-1, default: 0.7)

**Response:**
```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "document_id": "doc123",
        "title": "Manual de usuario",
        "chunk_id": "chunk3",
        "content": "Fragmento relevante del documento...",
        "page": 2,
        "similarity": 0.92
      },
      // ...más resultados
    ]
  }
}
```

## Áreas de Conocimiento

### GET /api/v1/areas

Obtiene todas las áreas de conocimiento.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "area123",
      "name": "Documentación Técnica",
      "description": "Toda la documentación técnica del sistema",
      "parent_id": null,
      "created_by": "user123",
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z",
      "document_count": 15
    },
    // ...más áreas
  ]
}
```

### GET /api/v1/areas/{id}

Obtiene un área específica por ID.

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "area123",
    "name": "Documentación Técnica",
    "description": "Toda la documentación técnica del sistema",
    "parent_id": null,
    "created_by": "user123",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z",
    "document_count": 15,
    "children": [
      {
        "id": "area456",
        "name": "Manuales",
        "document_count": 8
      },
      // ...más áreas hijas
    ]
  }
}
```

### POST /api/v1/areas

Crea una nueva área de conocimiento.

**Request:**
```json
{
  "name": "Nueva Área",
  "description": "Descripción de la nueva área",
  "parent_id": "area123"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "area789",
    "name": "Nueva Área",
    "description": "Descripción de la nueva área",
    "parent_id": "area123",
    "created_by": "user123",
    "created_at": "2023-01-03T00:00:00Z",
    "updated_at": "2023-01-03T00:00:00Z",
    "document_count": 0
  }
}
```

### PUT /api/v1/areas/{id}

Actualiza un área existente.

**Request:**
```json
{
  "name": "Área Actualizada",
  "description": "Descripción actualizada"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "area123",
    "name": "Área Actualizada",
    "description": "Descripción actualizada",
    "parent_id": null,
    "created_by": "user123",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-03T00:00:00Z",
    "document_count": 15
  }
}
```

### DELETE /api/v1/areas/{id}

Elimina un área de conocimiento.

**Query Parameters:**
- `move_documents_to`: (opcional) ID de área a donde mover los documentos

**Response:**
```json
{
  "status": "success",
  "data": {
    "message": "Area deleted successfully"
  }
}
```

## RAG (Retrieval Augmented Generation)

### POST /api/v1/rag/query

Realiza una consulta RAG.

**Request:**
```json
{
  "query": "¿Cuáles son los principales componentes del sistema?",
  "area_id": "area123",
  "context_window": 3,
  "conversation_id": "conv123",
  "llm_provider": "openai",
  "llm_model": "gpt-4",
  "max_tokens": 1000,
  "temperature": 0.7
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "query_id": "query123",
    "answer": "Los principales componentes del sistema son...",
    "sources": [
      {
        "document_id": "doc123",
        "title": "Arquitectura del Sistema",
        "chunk_id": "chunk5",
        "content": "Contenido del fragmento relevante...",
        "page": 3,
        "similarity": 0.89
      },
      // ...más fuentes
    ],
    "conversation_id": "conv123",
    "processing_time_ms": 450,
    "token_usage": {
      "prompt": 350,
      "completion": 120,
      "total": 470
    }
  }
}
```

### GET /api/v1/rag/history

Obtiene el historial de consultas.

**Query Parameters:**
- `conversation_id`: (opcional) ID de conversación
- `page`: Número de página
- `limit`: Elementos por página

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "query_id": "query123",
      "conversation_id": "conv123",
      "query": "¿Cuáles son los principales componentes del sistema?",
      "answer": "Los principales componentes del sistema son...",
      "created_at": "2023-01-03T00:00:00Z",
      "user_id": "user123",
      "area_id": "area123",
      "token_usage": 470
    },
    // ...más consultas
  ],
  "meta": {
    "pagination": {
      "total": 50,
      "page": 1,
      "limit": 20,
      "pages": 3
    }
  }
}
```

### GET /api/v1/rag/conversations

Obtiene las conversaciones del usuario actual.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "conv123",
      "title": "Conversación sobre arquitectura",
      "created_at": "2023-01-03T00:00:00Z",
      "updated_at": "2023-01-03T00:10:00Z",
      "messages_count": 5,
      "area_id": "area123"
    },
    // ...más conversaciones
  ],
  "meta": {
    "pagination": {
      "total": 15,
      "page": 1,
      "limit": 20,
      "pages": 1
    }
  }
}
```

### POST /api/v1/rag/feedback

Envía feedback sobre una respuesta RAG.

**Request:**
```json
{
  "query_id": "query123",
  "rating": 4,
  "comment": "Respuesta precisa pero podría incluir más detalles",
  "feedback_type": "relevance"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "feedback_id": "feedback123",
    "query_id": "query123",
    "created_at": "2023-01-03T00:15:00Z"
  }
}
```

## LLM (Modelos de Lenguaje)

### GET /api/v1/llm/providers

Obtiene los proveedores LLM disponibles.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "openai",
      "name": "OpenAI",
      "description": "Proveedor OpenAI (GPT-3.5, GPT-4)",
      "models": [
        {
          "id": "gpt-3.5-turbo",
          "name": "GPT-3.5 Turbo",
          "max_tokens": 4096,
          "cost_per_1k_tokens": 0.002
        },
        {
          "id": "gpt-4",
          "name": "GPT-4",
          "max_tokens": 8192,
          "cost_per_1k_tokens": 0.06
        }
      ],
      "is_active": true
    },
    {
      "id": "anthropic",
      "name": "Anthropic",
      "description": "Proveedor Anthropic (Claude)",
      "models": [
        {
          "id": "claude-2",
          "name": "Claude 2",
          "max_tokens": 100000,
          "cost_per_1k_tokens": 0.01
        }
      ],
      "is_active": true
    },
    {
      "id": "ollama",
      "name": "Ollama",
      "description": "Modelos locales a través de Ollama",
      "models": [
        {
          "id": "llama2",
          "name": "Llama 2",
          "max_tokens": 4096,
          "cost_per_1k_tokens": 0
        }
      ],
      "is_active": true
    }
  ]
}
```

### GET /api/v1/llm/settings

Obtiene la configuración LLM del usuario actual.

**Response:**
```json
{
  "status": "success",
  "data": {
    "default_provider": "openai",
    "default_model": "gpt-4",
    "default_temperature": 0.7,
    "default_max_tokens": 1000,
    "api_keys": {
      "openai": "sk-***********",
      "anthropic": "sk-***********"
    }
  }
}
```

### PUT /api/v1/llm/settings

Actualiza la configuración LLM del usuario.

**Request:**
```json
{
  "default_provider": "anthropic",
  "default_model": "claude-2",
  "default_temperature": 0.5,
  "default_max_tokens": 2000,
  "api_keys": {
    "openai": "sk-new-key-here",
    "anthropic": "sk-new-key-here"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "default_provider": "anthropic",
    "default_model": "claude-2",
    "default_temperature": 0.5,
    "default_max_tokens": 2000,
    "api_keys": {
      "openai": "sk-***********",
      "anthropic": "sk-***********"
    }
  }
}
```

## Bases de Datos

### Conexiones

#### GET /api/v1/db-connections

Obtiene las conexiones a bases de datos configuradas.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "conn123",
      "name": "Base de datos principal",
      "description": "PostgreSQL principal",
      "db_type": "postgresql",
      "host": "db.example.com",
      "port": 5432,
      "database": "maindb",
      "username": "user",
      "created_by": "user123",
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z",
      "last_used": "2023-01-02T00:00:00Z",
      "status": "connected"
    },
    // ...más conexiones
  ]
}
```

#### GET /api/v1/db-connections/{id}

Obtiene detalles de una conexión a base de datos específica.

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "conn123",
    "name": "Base de datos principal",
    "description": "PostgreSQL principal",
    "db_type": "postgresql",
    "host": "db.example.com",
    "port": 5432,
    "database": "maindb",
    "username": "user",
    "created_by": "user123",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z",
    "last_used": "2023-01-02T00:00:00Z",
    "status": "connected"
  }
}
```

#### POST /api/v1/db-connections

Crea una nueva conexión a base de datos.

**Request:**
```json
{
  "name": "Base de datos secundaria",
  "description": "MySQL secundaria",
  "db_type": "mysql",
  "host": "mysql.example.com",
  "port": 3306,
  "database": "secondarydb",
  "username": "dbuser",
  "password": "dbpassword"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "conn456",
    "name": "Base de datos secundaria",
    "description": "MySQL secundaria",
    "db_type": "mysql",
    "host": "mysql.example.com",
    "port": 3306,
    "database": "secondarydb",
    "username": "dbuser",
    "created_by": "user123",
    "created_at": "2023-01-03T00:00:00Z",
    "updated_at": "2023-01-03T00:00:00Z",
    "status": "connected"
  }
}
```

#### PUT /api/v1/db-connections/{id}

Actualiza una conexión existente.

**Request:**
```json
{
  "name": "Base de datos actualizada",
  "description": "MySQL actualizada",
  "host": "new-mysql.example.com",
  "port": 3306,
  "username": "newuser",
  "password": "newpassword"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "conn456",
    "name": "Base de datos actualizada",
    "description": "MySQL actualizada",
    "db_type": "mysql",
    "host": "new-mysql.example.com",
    "port": 3306,
    "database": "secondarydb",
    "username": "newuser",
    "created_by": "user123",
    "created_at": "2023-01-03T00:00:00Z",
    "updated_at": "2023-01-04T00:00:00Z",
    "status": "connected"
  }
}
```

#### DELETE /api/v1/db-connections/{id}

Elimina una conexión.

**Response:**
```json
{
  "status": "success",
  "data": {
    "message": "Database connection deleted successfully"
  }
}
```

#### POST /api/v1/db-connections/{id}/test

Prueba una conexión a base de datos.

**Response:**
```json
{
  "status": "success",
  "data": {
    "status": "connected",
    "message": "Connection successful",
    "latency_ms": 25,
    "server_info": {
      "version": "MySQL 8.0.28",
      "timezone": "UTC"
    }
  }
}
```

#### GET /api/v1/db-connections/{id}/schema

Obtiene el esquema de una base de datos.

**Response:**
```json
{
  "status": "success",
  "data": {
    "tables": [
      {
        "name": "users",
        "columns": [
          {
            "name": "id",
            "type": "uuid",
            "is_primary": true,
            "is_nullable": false
          },
          {
            "name": "username",
            "type": "varchar(255)",
            "is_primary": false,
            "is_nullable": false
          },
          // ...más columnas
        ],
        "row_count": 1500
      },
      // ...más tablas
    ],
    "relationships": [
      {
        "table": "orders",
        "column": "user_id",
        "references_table": "users",
        "references_column": "id"
      },
      // ...más relaciones
    ]
  }
}
```

### Agentes Verificadores de Consultas

#### GET /api/v1/db-agents

Obtiene todos los agentes verificadores de consultas de base de datos.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "agent123",
      "name": "Verificador Principal",
      "description": "Agente para bases de datos principales",
      "type": "rag+db",
      "model_id": "gpt-4o",
      "allowed_operations": ["SELECT", "SHOW", "DESCRIBE"],
      "max_result_size": 1000,
      "query_timeout_secs": 30,
      "active": true,
      "default_system_prompt": "Eres un asistente especializado en verificar y generar consultas SQL seguras.",
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z",
      "created_by": "user123"
    },
    // ...más agentes
  ]
}
```

#### GET /api/v1/db-agents/{id}

Obtiene un agente verificador específico por ID.

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "agent123",
    "name": "Verificador Principal",
    "description": "Agente para bases de datos principales",
    "type": "rag+db",
    "model_id": "gpt-4o",
    "allowed_operations": ["SELECT", "SHOW", "DESCRIBE"],
    "max_result_size": 1000,
    "query_timeout_secs": 30,
    "active": true,
    "default_system_prompt": "Eres un asistente especializado en verificar y generar consultas SQL seguras.",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z",
    "created_by": "user123",
    "connections_count": 3
  }
}
```

#### POST /api/v1/db-agents

Crea un nuevo agente verificador (solo administradores).

**Request:**
```json
{
  "name": "Nuevo Verificador",
  "description": "Verificador para bases de datos de test",
  "type": "db-only",
  "model_id": "claude-3-haiku-20240307",
  "allowed_operations": ["SELECT"],
  "max_result_size": 500,
  "query_timeout_secs": 15,
  "default_system_prompt": "Eres un asistente especializado en verificar consultas a bases de datos de test."
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "agent456",
    "name": "Nuevo Verificador",
    "description": "Verificador para bases de datos de test",
    "type": "db-only",
    "model_id": "claude-3-haiku-20240307",
    "allowed_operations": ["SELECT"],
    "max_result_size": 500,
    "query_timeout_secs": 15,
    "active": true,
    "default_system_prompt": "Eres un asistente especializado en verificar consultas a bases de datos de test.",
    "created_at": "2023-01-03T00:00:00Z",
    "updated_at": "2023-01-03T00:00:00Z",
    "created_by": "user123",
    "connections_count": 0
  }
}
```

#### PUT /api/v1/db-agents/{id}

Actualiza un agente verificador existente (solo administradores).

**Request:**
```json
{
  "name": "Verificador Actualizado",
  "model_id": "llama3",
  "allowed_operations": ["SELECT", "DESCRIBE"],
  "active": true,
  "default_system_prompt": "Eres un asistente experto en seguridad de bases de datos que verifica y genera consultas SQL seguras."
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "agent123",
    "name": "Verificador Actualizado",
    "description": "Agente para bases de datos principales",
    "type": "rag+db",
    "model_id": "llama3",
    "allowed_operations": ["SELECT", "DESCRIBE"],
    "max_result_size": 1000,
    "query_timeout_secs": 30,
    "active": true,
    "default_system_prompt": "Eres un asistente experto en seguridad de bases de datos que verifica y genera consultas SQL seguras.",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-03T00:00:00Z",
    "created_by": "user123",
    "connections_count": 3
  }
}
```

#### DELETE /api/v1/db-agents/{id}

Elimina un agente verificador (solo administradores).

**Response:**
```json
{
  "status": "success",
  "data": {
    "message": "Database agent deleted successfully"
  }
}
```

#### GET /api/v1/db-agents/{id}/prompts

Obtiene los prompts configurados para un agente verificador.

**Response:**
```json
{
  "status": "success",
  "data": {
    "system_prompt": "Eres un asistente especializado en consultas a bases de datos. Tu tarea es analizar consultas en lenguaje natural y convertirlas en consultas estructuradas SQL/NoSQL según corresponda.",
    "query_evaluation_prompt": "Evalúa si esta consulta requiere acceso a base de datos o puede resolverse con RAG convencional.\n\nEjemplos que requieren BD:\n- \"Consulta el estado actual de la máquina SRV-2023-089\"\n- \"Muéstrame las últimas alertas de seguridad\"\n\nEjemplos que NO requieren BD:\n- \"Explícame el procedimiento de mantenimiento\"\n- \"Resume la política de seguridad\"\n\nConsulta: \"{query}\"\n\nResponde solo con 'DB' o 'RAG' seguido de un breve razonamiento.",
    "query_generation_prompt": "Convierte la siguiente consulta en lenguaje natural a una consulta estructurada para {db_type}.\n\nInformación del esquema:\n{schema_info}\n\nConsulta en lenguaje natural: \"{query}\"\n\nGenera solo la consulta SQL/NoSQL sin explicaciones adicionales.",
    "result_formatting_prompt": "Formatea los resultados de la consulta de manera clara y concisa para el usuario.\n\nConsulta original: \"{query}\"\n\nResultados de la consulta:\n{results}\n\nPor favor, formatea estos resultados de manera clara y concisa, incluyendo tablas si es apropiado.",
    "example_db_queries": "1. Consulta original: \"Muéstrame los 5 productos más vendidos del mes pasado\"\n   SQL: SELECT p.product_name, SUM(oi.quantity) as total_sold FROM products p JOIN order_items oi ON p.id = oi.product_id JOIN orders o ON oi.order_id = o.id WHERE o.order_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH) GROUP BY p.id ORDER BY total_sold DESC LIMIT 5;\n\n2. Consulta original: \"¿Cuántos usuarios nuevos se registraron esta semana?\"\n   SQL: SELECT COUNT(*) as new_users FROM users WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 1 WEEK);"
  }
}
```

#### PUT /api/v1/db-agents/{id}/prompts

Actualiza los prompts de un agente verificador (solo administradores).

**Request:**
```json
{
  "system_prompt": "Eres un verificador experto en bases de datos que analiza y genera consultas seguras en lenguaje SQL.",
  "query_evaluation_prompt": "Determina si esta consulta necesita acceso a una base de datos real o puede responderse con conocimiento general.\n\nConsulta: \"{query}\"\n\nResponde con 'DB' o 'RAG' según corresponda, y explica brevemente tu razonamiento.",
  "query_generation_prompt": "Convierte esta consulta en lenguaje natural a SQL optimizado y seguro para {db_type}.\n\nEsquema disponible:\n{schema_info}\n\nConsulta: \"{query}\"\n\nGenera solo la consulta SQL sin comentarios adicionales.",
  "result_formatting_prompt": "Presenta estos resultados de base de datos de forma clara y útil para el usuario.\n\nConsulta original: \"{query}\"\n\nDatos obtenidos:\n{results}",
  "example_db_queries": "Ejemplo 1: \"Encuentra usuarios inactivos por más de 90 días\"\nSELECT * FROM users WHERE last_login < NOW() - INTERVAL 90 DAY;"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "system_prompt": "Eres un verificador experto en bases de datos que analiza y genera consultas seguras en lenguaje SQL.",
    "query_evaluation_prompt": "Determina si esta consulta necesita acceso a una base de datos real o puede responderse con conocimiento general.\n\nConsulta: \"{query}\"\n\nResponde con 'DB' o 'RAG' según corresponda, y explica brevemente tu razonamiento.",
    "query_generation_prompt": "Convierte esta consulta en lenguaje natural a SQL optimizado y seguro para {db_type}.\n\nEsquema disponible:\n{schema_info}\n\nConsulta: \"{query}\"\n\nGenera solo la consulta SQL sin comentarios adicionales.",
    "result_formatting_prompt": "Presenta estos resultados de base de datos de forma clara y útil para el usuario.\n\nConsulta original: \"{query}\"\n\nDatos obtenidos:\n{results}",
    "example_db_queries": "Ejemplo 1: \"Encuentra usuarios inactivos por más de 90 días\"\nSELECT * FROM users WHERE last_login < NOW() - INTERVAL 90 DAY;"
  }
}
```

#### GET /api/v1/db-agents/{id}/connections

Obtiene las conexiones asignadas a un agente verificador.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "assign123",
      "agent_id": "agent123",
      "connection": {
        "id": "conn123",
        "name": "Base de datos principal",
        "db_type": "postgresql",
        "host": "db.example.com",
        "database": "maindb"
      },
      "permissions": ["read"],
      "assigned_at": "2023-01-01T00:00:00Z",
      "assigned_by": "user123"
    },
    // ...más asignaciones
  ]
}
```

#### POST /api/v1/db-agents/{id}/connections

Asigna una conexión a un agente verificador (solo administradores).

**Request:**
```json
{
  "connection_id": "conn456",
  "permissions": ["read", "write"]
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "assign789",
    "agent_id": "agent123",
    "connection": {
      "id": "conn456",
      "name": "Base de datos secundaria",
      "db_type": "mysql",
      "host": "mysql.example.com",
      "database": "secondarydb"
    },
    "permissions": ["read", "write"],
    "assigned_at": "2023-01-03T00:00:00Z",
    "assigned_by": "user123"
  }
}
```

#### DELETE /api/v1/db-agents/{id}/connections/{connectionId}

Elimina una asignación de conexión a un agente (solo administradores).

**Response:**
```json
{
  "status": "success",
  "data": {
    "message": "Connection assignment removed successfully"
  }
}
```

### Consultas

#### POST /api/v1/db-queries

Ejecuta una consulta a través de un agente verificador.

**Request:**
```json
{
  "agent_id": "agent123",
  "query": "Obtener los 10 clientes con más compras en el último mes",
  "connections": ["conn123", "conn456"],
  "options": {
    "max_results": 500,
    "timeout": 60
  }
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "query123",
    "query_type": "db",
    "answer": "Aquí están los 10 clientes que realizaron más compras el mes pasado:\n\n| Cliente | Compras | Total |\n|---------|---------|-------|\n| John Smith | 15 | $1,245.65 |\n| Jane Doe | 12 | $987.40 |\n...",
    "generated_queries": [
      {
        "connection_id": "conn123",
        "query_text": "SELECT c.customer_name, COUNT(o.id) as total_orders, SUM(o.total) as total_amount FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.order_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH) GROUP BY c.id ORDER BY total_orders DESC LIMIT 10"
      }
    ],
    "execution_time_ms": 250,
    "has_error": false,
    "timestamp": "2023-01-03T00:00:00Z"
  }
}
```

#### GET /api/v1/db-queries/history

Obtiene el historial de consultas del usuario actual.

**Query Parameters:**
- `limit`: (opcional) Número máximo de resultados (default: 20)
- `offset`: (opcional) Índice de inicio para paginación (default: 0)

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "query123",
      "query": "Obtener los 10 clientes con más compras en el último mes",
      "query_type": "db",
      "status": "completed",
      "execution_time_ms": 250,
      "created_at": "2023-01-03T00:00:00Z",
      "completed_at": "2023-01-03T00:00:05Z"
    },
    // ...más consultas
  ],
  "meta": {
    "total": 45,
    "limit": 20,
    "offset": 0
  }
}
```

#### GET /api/v1/db-queries/history/{id}

Obtiene el detalle de una consulta específica.

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "query123",
    "original_query": "Obtener los 10 clientes con más compras en el último mes",
    "query_type": "db",
    "status": "completed",
    "result": "Aquí están los 10 clientes que realizaron más compras el mes pasado:\n\n| Cliente | Compras | Total |\n|---------|---------|-------|\n| John Smith | 15 | $1,245.65 |\n| Jane Doe | 12 | $987.40 |\n...",
    "generated_queries": [
      {
        "connection_id": "conn123",
        "connection_name": "Base de datos principal",
        "query_text": "SELECT c.customer_name, COUNT(o.id) as total_orders, SUM(o.total) as total_amount FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.order_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH) GROUP BY c.id ORDER BY total_orders DESC LIMIT 10"
      }
    ],
    "execution_time_ms": 250,
    "has_error": false,
    "error_message": null,
    "created_at": "2023-01-03T00:00:00Z",
    "completed_at": "2023-01-03T00:00:05Z",
    "agent": {
      "id": "agent123",
      "name": "Verificador Principal"
    }
  }
}
```

## Terminal

### GET /api/v1/terminal/sessions

Obtiene las sesiones de terminal del usuario.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "session123",
      "user_id": "user123",
      "status": "connected",
      "target_info": {
        "hostname": "server1.example.com",
        "ip_address": "192.168.1.100",
        "os_type": "Linux",
        "os_version": "Ubuntu 20.04"
      },
      "created_at": "2023-01-03T00:00:00Z",
      "last_activity": "2023-01-03T00:10:00Z",
      "command_count": 15
    },
    // ...más sesiones
  ]
}
```

### POST /api/v1/terminal/sessions

Crea una nueva sesión de terminal.

**Request:**
```json
{
  "target_host": "server1.example.com",
  "port": 22,
  "username": "ubuntu",
  "auth_method": "key", // o "password"
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----",
  "passphrase": "", // opcional
  "options": {
    "terminal_type": "xterm-256color",
    "window_size": {
      "cols": 80,
      "rows": 24
    }
  }
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "session_id": "session456",
    "status": "connecting",
    "connection_url": "wss://api.example.com/ws/terminal/session456"
  }
}
```

### GET /api/v1/terminal/sessions/{id}/commands

Obtiene el historial de comandos de una sesión.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "cmd123",
      "session_id": "session123",
      "command": "ls -la",
      "exit_code": 0,
      "duration_ms": 50,
      "working_directory": "/home/ubuntu",
      "timestamp": "2023-01-03T00:05:00Z",
      "has_error": false
    },
    // ...más comandos
  ]
}
```

### GET /api/v1/terminal/suggestions

Obtiene sugerencias para comandos.

**Query Parameters:**
- `session_id`: ID de la sesión de terminal
- `context`: (opcional) Contexto actual (último comando, directorio, etc.)

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "sug123",
      "command": "docker ps -a",
      "description": "Listar todos los contenedores Docker",
      "risk_level": "low",
      "requires_approval": false
    },
    // ...más sugerencias
  ]
}
```

### POST /api/v1/terminal/feedback

Envía feedback sobre sugerencias de comandos.

**Request:**
```json
{
  "suggestion_id": "sug123",
  "was_used": true,
  "rating": 5,
  "comment": "Excelente sugerencia, resolvió mi problema"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "message": "Feedback received successfully"
  }
}
```

## Ollama

### GET /api/v1/ollama/models

Obtiene los modelos disponibles en el servicio Ollama.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "name": "llama2",
      "size": 3800000000,
      "modified_at": "2023-01-01T00:00:00Z",
      "quantization_level": "Q4_0",
      "parameter_size": "7B",
      "is_running": true
    },
    // ...más modelos
  ]
}
```

### POST /api/v1/ollama/models/pull

Descarga un modelo a Ollama.

**Request:**
```json
{
  "model": "llama2:13b"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "task_id": "task123",
    "message": "Model download started",
    "model": "llama2:13b"
  }
}
```

### GET /api/v1/ollama/settings

Obtiene la configuración de Ollama.

**Response:**
```json
{
  "status": "success",
  "data": {
    "host": "http://ollama:11434",
    "concurrency": 1,
    "context_size": 4096,
    "num_gpu": 1,
    "num_thread": 4
  }
}
```

### PUT /api/v1/ollama/settings

Actualiza la configuración de Ollama.

**Request:**
```json
{
  "concurrency": 2,
  "num_thread": 8
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "host": "http://ollama:11434",
    "concurrency": 2,
    "context_size": 4096,
    "num_gpu": 1,
    "num_thread": 8
  }
}
```