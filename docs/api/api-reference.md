# Documentación de API - Sistema de Gestión de Conocimiento con MCP

## Índice

1. [Introducción](#introducción)
2. [Autenticación](#autenticación)
3. [API Gateway](#api-gateway)
4. [Servicio de Usuarios](#servicio-de-usuarios)
5. [Servicio de Documentos](#servicio-de-documentos)
6. [Servicio de Contexto](#servicio-de-contexto)
7. [Servicio de Embeddings](#servicio-de-embeddings)
8. [Agente RAG](#agente-rag)

## Introducción

Este documento describe las APIs RESTful disponibles en el sistema de gestión de conocimiento con Model Context Protocol (MCP). El sistema consta de varios servicios interconectados, cada uno responsable de diferentes funcionalidades.

Todos los endpoints están disponibles a través del API Gateway, que actúa como punto de entrada único al sistema.

## Autenticación

La autenticación se realiza mediante tokens JWT. Para acceder a endpoints protegidos, se debe incluir el token en el encabezado `Authorization` de las solicitudes:

```
Authorization: Bearer <token>
```

Para obtener un token, se debe utilizar el endpoint de login.

## API Gateway

El API Gateway expone los siguientes endpoints principales:

### Endpoints públicos

- **GET /health** - Verificar salud del sistema
- **POST /auth/register** - Registrar un nuevo usuario
- **POST /auth/login** - Iniciar sesión y obtener token
- **POST /auth/refresh** - Refrescar token de autenticación

### Endpoints protegidos

Todos los endpoints a continuación requieren autenticación.

## Servicio de Usuarios

### Endpoints de Usuario

- **GET /users/me** - Obtener información del usuario actual
- **PUT /users/me** - Actualizar información del usuario actual
- **PUT /users/password** - Cambiar contraseña

### Endpoints de Administración (requieren rol de administrador)

- **GET /users** - Listar todos los usuarios
- **GET /users/:id** - Obtener un usuario específico
- **PUT /users/:id/permissions** - Actualizar permisos de un usuario

## Servicio de Documentos

### Documentos Personales

- **GET /documents/personal** - Listar documentos personales
- **POST /documents/personal** - Subir nuevo documento personal
- **GET /documents/personal/:id** - Obtener información de documento personal
- **GET /documents/personal/:id/content** - Descargar contenido de documento personal
- **DELETE /documents/personal/:id** - Eliminar documento personal

### Documentos Compartidos

- **GET /documents/shared** - Listar documentos compartidos
- **GET /documents/shared/:id** - Obtener información de documento compartido
- **GET /documents/shared/:id/content** - Descargar contenido de documento compartido

### Administración de Documentos (requieren rol de administrador)

- **POST /documents/shared** - Subir nuevo documento compartido
- **PUT /documents/shared/:id** - Actualizar información de documento compartido
- **DELETE /documents/shared/:id** - Eliminar documento compartido

### Búsqueda

- **GET /documents/search** - Buscar documentos

## Servicio de Contexto

### Áreas de Conocimiento

- **GET /knowledge/areas** - Listar áreas de conocimiento
- **GET /knowledge/areas/:id** - Obtener información de un área específica

### Administración de Áreas (requieren rol de administrador)

- **POST /knowledge/admin/areas** - Crear nueva área de conocimiento
- **PUT /knowledge/admin/areas/:id** - Actualizar área de conocimiento
- **DELETE /knowledge/admin/areas/:id** - Eliminar área de conocimiento

## Servicio de Embeddings

Los siguientes endpoints son internos y no están expuestos directamente a través del API Gateway.

### Embeddings

- **POST /embeddings** - Generar embedding para un texto
- **POST /embeddings/batch** - Generar embeddings para múltiples textos
- **POST /embeddings/document** - Generar embedding para un documento
- **GET /embeddings/:id** - Obtener información de un embedding
- **DELETE /embeddings/:id** - Eliminar un embedding

### Búsqueda Semántica

- **GET /search** - Buscar textos similares a una consulta

### Contextos MCP

- **GET /contexts** - Listar contextos MCP
- **POST /contexts/:id/activate** - Activar un contexto MCP
- **POST /contexts/:id/deactivate** - Desactivar un contexto MCP

## Agente RAG

### Consultas

- **POST /queries** - Realizar consulta RAG general
- **POST /queries/area/:areaId** - Realizar consulta RAG en área específica
- **POST /queries/personal** - Realizar consulta RAG en conocimiento personal
- **GET /queries/history** - Obtener historial de consultas

### Proveedores LLM (requieren rol de administrador)

- **GET /llm/providers** - Listar proveedores LLM configurados
- **POST /llm/providers** - Añadir nuevo proveedor LLM
- **PUT /llm/providers/:id** - Actualizar proveedor LLM
- **DELETE /llm/providers/:id** - Eliminar proveedor LLM
- **POST /llm/providers/:id/test** - Probar proveedor LLM

## Detalles de los Endpoints

### Autenticación

#### Registrar Usuario

```
POST /auth/register
```

Payload:
```json
{
  "username": "usuario",
  "email": "usuario@ejemplo.com",
  "password": "contraseña123"
}
```

Respuesta:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 86400,
  "token_type": "Bearer"
}
```

#### Iniciar Sesión

```
POST /auth/login
```

Payload:
```json
{
  "username": "usuario",
  "password": "contraseña123"
}
```

Respuesta:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 86400,
  "token_type": "Bearer"
}
```

### Consultas RAG

#### Realizar Consulta General

```
POST /queries
```

Payload:
```json
{
  "query": "¿Cuáles son las principales aplicaciones de la inteligencia artificial?",
  "user_id": "user123",
  "include_personal": true,
  "area_ids": ["area1", "area2"],
  "llm_provider_id": "provider1",
  "max_sources": 5
}
```

Respuesta:
```json
{
  "query": "¿Cuáles son las principales aplicaciones de la inteligencia artificial?",
  "answer": "Las principales aplicaciones de la inteligencia artificial incluyen...",
  "sources": [
    {
      "id": "doc1",
      "title": "Introducción a la IA",
      "url": "http://ejemplo.com/documentos/doc1",
      "snippet": "La inteligencia artificial tiene múltiples aplicaciones...",
      "score": 0.89
    },
    {
      "id": "doc2",
      "title": "Avances en IA",
      "url": "http://ejemplo.com/documentos/doc2",
      "snippet": "Entre las aplicaciones más importantes...",
      "score": 0.76
    }
  ],
  "llm_provider": "OpenAI GPT-4",
  "model": "gpt-4o",
  "processing_time_ms": 1250,
  "query_id": "query123",
  "timestamp": "2025-03-28T10:30:45Z"
}
```

### Gestión de Documentos

#### Subir Documento Personal

```
POST /documents/personal
```

Formato: `multipart/form-data`

Campos:
- `file`: Archivo a subir
- `title`: Título del documento
- `description`: Descripción del documento (opcional)
- `tags`: Etiquetas separadas por comas (opcional)

Respuesta:
```json
{
  "id": "doc123",
  "title": "Informe de Proyecto",
  "description": "Informe final del proyecto de investigación",
  "file_name": "informe.pdf",
  "file_size": 1024567,
  "file_type": "application/pdf",
  "doc_type": "pdf",
  "scope": "personal",
  "owner_id": "user123",
  "tags": ["informe", "proyecto", "investigación"],
  "created_at": "2025-03-28T09:15:30Z",
  "updated_at": "2025-03-28T09:15:30Z",
  "download_url": "http://ejemplo.com/documents/personal/doc123/content"
}
```

### Gestión de Áreas

#### Crear Área de Conocimiento

```
POST /knowledge/admin/areas
```

Payload:
```json
{
  "name": "Inteligencia Artificial",
  "description": "Área dedicada a la IA y sus aplicaciones",
  "icon": "brain",
  "color": "#3498DB",
  "tags": ["IA", "Machine Learning", "Deep Learning"]
}
```

Respuesta:
```json
{
  "id": "area123",
  "name": "Inteligencia Artificial",
  "description": "Área dedicada a la IA y sus aplicaciones",
  "icon": "brain",
  "color": "#3498DB",
  "tags": ["IA", "Machine Learning", "Deep Learning"],
  "mcp_context_id": "ctx123",
  "active": true,
  "created_at": "2025-03-28T08:45:12Z",
  "updated_at": "2025-03-28T08:45:12Z"
}
```

### Gestión de Proveedores LLM

#### Añadir Proveedor LLM

```
POST /llm/providers
```

Payload:
```json
{
  "name": "OpenAI GPT-4",
  "type": "openai",
  "api_key": "sk-...",
  "model": "gpt-4o",
  "default": true,
  "temperature": 0.0,
  "max_tokens": 4096,
  "metadata": {
    "organization_id": "org-..."
  }
}
```

Respuesta:
```json
{
  "id": "provider123",
  "name": "OpenAI GPT-4",
  "type": "openai",
  "model": "gpt-4o",
  "default": true,
  "temperature": 0.0,
  "max_tokens": 4096,
  "metadata": {
    "organization_id": "org-..."
  },
  "created_at": "2025-03-28T11:20:15Z",
  "updated_at": "2025-03-28T11:20:15Z"
}
```