# Servicio MCP de Contextos (Model Context Protocol)

Este servicio implementa el estándar Model Context Protocol (MCP) para gestionar contextos de conocimiento, permitiendo integrar áreas de conocimiento, prompts de sistema y embeddings de documentos.

## Información Técnica

### Características principales

#### 1. Implementación estándar MCP 1.6.0 con FastMCP 0.4.1

El servicio implementa una integración completa con el protocolo MCP según las especificaciones oficiales:

- Usa las bibliotecas oficiales `mcp==1.6.0` y `fastmcp==0.4.1`
- Integración a través de Router FastAPI
- Detección automática de componentes faltantes con fallback transparente
- Exposición de endpoints estándar MCP en `/api/v1/mcp/`

#### 2. Implementación de cliente MCP estándar

Además del servidor MCP, los siguientes servicios utilizan la biblioteca cliente MCP oficial:

- `rag-agent`: Implementación completa del cliente oficial MCP con fallback HTTP
- `terminal-context-aggregator`: Cliente MCP para búsqueda y almacenamiento de contexto

#### 3. Extensiones del protocolo MCP

El servicio incluye la siguiente extensión al protocolo MCP estándar:

- `/api/v1/context/retrieve`: Endpoint especializado para recuperar contexto relevante para terminales
  Este endpoint mantiene compatibilidad con las herramientas estándar de MCP, pero añade funcionalidad
  específica para contextos de terminal.

#### 4. Configuración CORS

Para evitar errores de parsing del campo `CORS_ALLOWED_ORIGINS`, asegúrese de usar uno de estos formatos:

```bash
# Formato 1: Lista JSON correctamente formateada (RECOMENDADO)
CORS_ALLOWED_ORIGINS='["http://localhost:3000","http://localhost","http://localhost:80"]'

# Formato 2: Lista separada por comas
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost,http://localhost:80
```

**IMPORTANTE**: Para Docker Compose, usar siempre el Formato 1, ya que es el que está configurado actualmente.

## Funcionalidades principales

- Gestión de áreas de conocimiento con metadatos
- Activación/desactivación de contextos para los LLMs
- Integración con el servicio de embeddings
- Gestión de prompts de sistema por área de conocimiento
- Soporte para contexto terminal mediante extensión del protocolo

## Herramientas MCP estándar disponibles

- `store_document`: Almacena documentos y los convierte en embeddings
  - Parámetros: `information` (texto a almacenar), `metadata` (metadatos opcionales)
  - Retorno: Confirmación del almacenamiento

- `find_relevant`: Busca información relevante a partir de una consulta
  - Parámetros: `query` (consulta), `embedding_type` (tipo de embedding), `limit` (límite de resultados)
  - Retorno: Lista de fragmentos de información relevante

## Endpoints MCP estándar

- `GET /mcp/status`: Obtener el estado del servidor MCP
- `GET /mcp/active-contexts`: Listar contextos activos
- `POST /mcp/tools/{tool_name}`: Llamar a una herramienta específica

## Extensiones MCP (no estándar)

- `POST /api/v1/context/retrieve`: Recuperar contexto relevante para terminal
  - Request: `{ query: string, context: { terminal_context: {...}, user_id: string }, max_results?: number }`
  - Response: `{ relevant_context: any[], context_score: number }`

## Integración con otros servicios

- `embedding-service`: Gestión de embeddings vectoriales
- `rag-agent`: Integración de contexto en generación de respuestas
- `terminal-context-aggregator`: Contextualización de comandos de terminal
- MongoDB: Almacenamiento persistente de contextos y áreas