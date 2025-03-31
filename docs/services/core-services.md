# Core Services

## Visión General

Los Core Services constituyen la columna vertebral del sistema backend, proporcionando funcionalidades fundamentales como autenticación, gestión de usuarios y gestión de documentos. Están implementados en Go para maximizar el rendimiento y la eficiencia.

## Arquitectura General

```
┌───────────────────────────────────────────────────────────┐
│                     Core Services                          │
│                                                           │
│  ┌─────────────────────┐       ┌─────────────────────┐    │
│  │                     │       │                     │    │
│  │    User Service     │◀─────▶│  Document Service   │    │
│  │                     │       │                     │    │
│  └─────────────┬───────┘       └─────────┬───────────┘    │
│                │                         │                │
│                ▼                         ▼                │
│  ┌─────────────────────┐       ┌─────────────────────┐    │
│  │                     │       │                     │    │
│  │     MongoDB         │       │       MinIO         │    │
│  │                     │       │                     │    │
│  └─────────────────────┘       └─────────────────────┘    │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

## User Service

El User Service gestiona todos los aspectos relacionados con usuarios, autenticación y autorización.

### Características Principales

- **Gestión de Usuarios**: Registro, actualización y eliminación de cuentas
- **Autenticación**: Login con JWT (tokens de acceso y refresh)
- **Autorización**: Control de acceso basado en roles (RBAC)
- **Gestión de Perfiles**: Información de usuario y preferencias
- **Seguridad**: Protección contra ataques comunes y hashing de contraseñas

### Estructura del Servicio

```
user-service/
├── config/              # Configuración del servicio
├── controllers/         # Controladores HTTP
├── models/              # Definiciones de datos
├── repositories/        # Acceso a base de datos
├── services/            # Lógica de negocio
├── main.go              # Punto de entrada
└── Dockerfile           # Configuración de Docker
```

### API Endpoints

- **POST /api/v1/auth/login**: Inicia sesión y emite tokens
- **POST /api/v1/auth/refresh**: Renueva el token de acceso
- **POST /api/v1/auth/logout**: Invalida tokens actuales
- **GET /api/v1/users**: Lista usuarios (solo admin)
- **GET /api/v1/users/{id}**: Obtiene un usuario específico
- **POST /api/v1/users**: Crea un nuevo usuario
- **PUT /api/v1/users/{id}**: Actualiza un usuario existente
- **DELETE /api/v1/users/{id}**: Elimina un usuario

### Estructura de Datos

#### Usuario

```go
type User struct {
    ID           string     `json:"id" bson:"_id,omitempty"`
    Username     string     `json:"username" bson:"username"`
    PasswordHash string     `json:"-" bson:"password_hash"`
    Name         string     `json:"name" bson:"name"`
    Email        string     `json:"email" bson:"email"`
    Role         string     `json:"role" bson:"role"`
    Active       bool       `json:"active" bson:"active"`
    CreatedAt    time.Time  `json:"created_at" bson:"created_at"`
    UpdatedAt    time.Time  `json:"updated_at" bson:"updated_at"`
    LastLogin    *time.Time `json:"last_login,omitempty" bson:"last_login,omitempty"`
    Preferences  UserPreferences `json:"preferences" bson:"preferences"`
}

type UserPreferences struct {
    Theme         string          `json:"theme" bson:"theme"`
    Language      string          `json:"language" bson:"language"`
    LLMSettings   LLMSettings     `json:"llm_settings" bson:"llm_settings"`
    Notifications bool            `json:"notifications" bson:"notifications"`
}

type LLMSettings struct {
    DefaultProvider string            `json:"default_provider" bson:"default_provider"`
    DefaultModel    string            `json:"default_model" bson:"default_model"`
    Temperature     float64           `json:"temperature" bson:"temperature"`
    MaxTokens       int               `json:"max_tokens" bson:"max_tokens"`
    ApiKeys         map[string]string `json:"api_keys" bson:"api_keys"`
}
```

#### Token

```go
type TokenPair struct {
    AccessToken  string `json:"access_token"`
    RefreshToken string `json:"refresh_token"`
    ExpiresIn    int    `json:"expires_in"` // Seconds until access token expires
}

type JWTClaims struct {
    UserID   string   `json:"user_id"`
    Username string   `json:"username"`
    Role     string   `json:"role"`
    Roles    []string `json:"roles,omitempty"`
    jwt.StandardClaims
}
```

## Document Service

El Document Service gestiona el ciclo de vida completo de los documentos, incluyendo carga, procesamiento, indexación y recuperación.

### Características Principales

- **Gestión de Documentos**: Carga, actualización y eliminación de documentos
- **Procesamiento de Archivos**: Extracción de texto, metadata y chunking
- **Indexación**: Integración con Embedding Service para búsqueda semántica
- **Almacenamiento**: Persistencia segura de documentos en MinIO
- **Recuperación**: Acceso eficiente a documentos y fragmentos

### Estructura del Servicio

```
document-service/
├── config/              # Configuración del servicio
├── controllers/         # Controladores HTTP
├── models/              # Definiciones de datos
├── repositories/        # Acceso a base de datos
├── services/            # Lógica de negocio
│   ├── document.go      # Gestión de documentos
│   ├── storage.go       # Almacenamiento (MinIO)
│   ├── processor.go     # Procesamiento de documentos
│   └── embedding.go     # Integración con Embedding Service
├── main.go              # Punto de entrada
└── Dockerfile           # Configuración de Docker
```

### API Endpoints

- **GET /api/v1/documents**: Lista documentos con filtros opcionales
- **GET /api/v1/documents/{id}**: Obtiene un documento específico
- **POST /api/v1/documents**: Crea un nuevo documento (multipart/form-data)
- **PUT /api/v1/documents/{id}**: Actualiza un documento existente
- **DELETE /api/v1/documents/{id}**: Elimina un documento
- **GET /api/v1/documents/{id}/content**: Obtiene el contenido del documento
- **GET /api/v1/documents/search**: Busca documentos (texto o semántica)

### Estructura de Datos

#### Documento

```go
type Document struct {
    ID              string    `json:"id" bson:"_id,omitempty"`
    Title           string    `json:"title" bson:"title"`
    Description     string    `json:"description" bson:"description"`
    FileName        string    `json:"file_name" bson:"file_name"`
    FileType        string    `json:"file_type" bson:"file_type"`
    FileSize        int64     `json:"file_size" bson:"file_size"`
    StoragePath     string    `json:"-" bson:"storage_path"`
    AreaID          string    `json:"area_id" bson:"area_id"`
    CreatedBy       string    `json:"created_by" bson:"created_by"`
    CreatedAt       time.Time `json:"created_at" bson:"created_at"`
    UpdatedAt       time.Time `json:"updated_at" bson:"updated_at"`
    Tags            []string  `json:"tags" bson:"tags"`
    EmbeddingStatus string    `json:"embedding_status" bson:"embedding_status"`
    ProcessingError string    `json:"processing_error,omitempty" bson:"processing_error,omitempty"`
    Metadata        DocumentMetadata `json:"metadata" bson:"metadata"`
    ChunksCount     int       `json:"chunks_count" bson:"chunks_count"`
    TotalTokens     int       `json:"total_tokens" bson:"total_tokens"`
}

type DocumentMetadata struct {
    Author       string    `json:"author" bson:"author"`
    CreationDate time.Time `json:"creation_date" bson:"creation_date"`
    PageCount    int       `json:"page_count" bson:"page_count"`
    Language     string    `json:"language" bson:"language"`
    Keywords     []string  `json:"keywords" bson:"keywords"`
    Custom       map[string]interface{} `json:"custom" bson:"custom"`
}
```

#### Fragmento de Documento (Chunk)

```go
type DocumentChunk struct {
    ID          string    `json:"id" bson:"_id,omitempty"`
    DocumentID  string    `json:"document_id" bson:"document_id"`
    Content     string    `json:"content" bson:"content"`
    Page        int       `json:"page" bson:"page"`
    ChunkIndex  int       `json:"chunk_index" bson:"chunk_index"`
    TokenCount  int       `json:"token_count" bson:"token_count"`
    EmbeddingID string    `json:"embedding_id" bson:"embedding_id"`
    CreatedAt   time.Time `json:"created_at" bson:"created_at"`
    Metadata    map[string]interface{} `json:"metadata" bson:"metadata"`
}
```

## Flujos de Operación

### 1. Autenticación de Usuario

```
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │───▶│  API Gateway  │───▶│ User Service  │
│           │    │               │    │               │
└───────────┘    └───────────────┘    └───────┬───────┘
                                              │
                                              │ Valida credenciales
                                              ▼
                                      ┌───────────────┐
                                      │   MongoDB     │
                                      │   (Users)     │
                                      └───────┬───────┘
                                              │
                                              │ Credenciales OK
                                              ▼
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │◀───│  API Gateway  │◀───│ User Service  │
│ con token │    │               │    │  genera JWT   │
└───────────┘    └───────────────┘    └───────────────┘
```

### 2. Carga y Procesamiento de Documento

```
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │───▶│  API Gateway  │───▶│   Document    │
│ (upload)  │    │               │    │   Service     │
└───────────┘    └───────────────┘    └───────┬───────┘
                                              │
                                              │ Valida documento
                                              ▼
                                      ┌───────────────┐
                                      │    MinIO      │──┐
                                      │ (almacena)    │  │
                                      └───────────────┘  │
                                                         │
                                      ┌───────────────┐  │
                                      │   Document    │◀─┘
                                      │  Processor    │
                                      └───────┬───────┘
                                              │
                                              │ Extrae texto
                                              ▼
                                      ┌───────────────┐
                                      │   MongoDB     │
                                      │ (metadatos)   │
                                      └───────┬───────┘
                                              │
                                              │ Documento procesado
                                              ▼
                                      ┌───────────────┐
                                      │   Embedding   │
                                      │   Service     │
                                      └───────────────┘
```

### 3. Búsqueda de Documentos

```
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │───▶│  API Gateway  │───▶│   Document    │
│ (search)  │    │               │    │   Service     │
└───────────┘    └───────────────┘    └───────┬───────┘
                                              │
                                              │ Consulta semántica
                                              ▼
                                      ┌───────────────┐
                                      │   Embedding   │
                                      │   Service     │
                                      └───────┬───────┘
                                              │
                                              │ Embeddings similares
                                              ▼
                                      ┌───────────────┐
                                      │    Qdrant     │
                                      │ (vectores)    │
                                      └───────┬───────┘
                                              │
                                              │ IDs de documentos
                                              ▼
                                      ┌───────────────┐
                                      │   MongoDB     │
                                      │ (documentos)  │
                                      └───────┬───────┘
                                              │
                                              │ Resultados
                                              ▼
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │◀───│  API Gateway  │◀───│   Document    │
│           │    │               │    │   Service     │
└───────────┘    └───────────────┘    └───────────────┘
```

## Configuración

### User Service

```yaml
# Configuración por variables de entorno o archivo config.yaml
server:
  port: 8081
  timeout: 30s

database:
  uri: mongodb://mongodb:27017
  name: user_service
  collection: users

jwt:
  secret: ${JWT_SECRET}
  access_expiry: 30m
  refresh_expiry: 7d

security:
  password_salt: ${PASSWORD_SALT}
  bcrypt_cost: 10
  rate_limit: 100
```

### Document Service

```yaml
# Configuración por variables de entorno o archivo config.yaml
server:
  port: 8082
  timeout: 60s
  max_upload_size: 50MB

database:
  uri: mongodb://mongodb:27017
  name: document_service
  collections:
    documents: documents
    chunks: document_chunks

storage:
  provider: minio
  endpoint: minio:9000
  bucket: documents
  access_key: ${MINIO_ACCESS_KEY}
  secret_key: ${MINIO_SECRET_KEY}
  secure: false

embedding:
  service_url: http://embedding-service:8084
  batch_size: 10
  max_retries: 3
  timeout: 120s

processing:
  chunk_size: 1000
  chunk_overlap: 200
  supported_formats:
    - application/pdf
    - text/plain
    - application/vnd.openxmlformats-officedocument.wordprocessingml.document
    - text/markdown
    - text/html
```

## Rendimiento y Escalabilidad

### Optimizaciones Implementadas

#### User Service

1. **Caché de usuarios**: Implementación de caché en memoria para usuarios frecuentes
2. **Índices optimizados**: MongoDB indexado por username, email y últimos accesos
3. **Conexiones pooling**: Pool de conexiones a MongoDB para mayor rendimiento
4. **Validación eficiente de JWT**: Implementación rápida de validación sin llamadas DB

#### Document Service

1. **Procesamiento asíncrono**: Subida rápida con procesamiento en background
2. **Streaming de archivos**: Manejo eficiente de archivos grandes
3. **Caché de documentos populares**: Documentos frecuentemente accedidos en memoria
4. **Procesamiento por lotes**: Generación de embeddings en batch
5. **URLs firmadas**: Generación de URLs presignadas para acceso directo a MinIO

### Escalabilidad

- **Horizontal**: Todos los servicios son stateless y pueden escalar horizontalmente
- **Particionamiento**: Posibilidad de particionar por usuario o área de conocimiento
- **Configuración**: Parámetros ajustables para diferentes cargas de trabajo

## Monitoreo y Diagnóstico

### Endpoints de Salud y Métricas

- **GET /health**: Devuelve estado del servicio y sus dependencias
- **GET /metrics**: Métricas en formato Prometheus

### Logs Estructurados

Formato de log JSON:

```json
{
  "level": "info",
  "timestamp": "2023-05-10T12:34:56Z",
  "service": "document-service",
  "trace_id": "abc123",
  "message": "Document processed successfully",
  "document_id": "doc123",
  "processing_time_ms": 345,
  "file_size_bytes": 1048576
}
```

## Referencias

- [Go Programming Language](https://golang.org/)
- [MongoDB Documentation](https://docs.mongodb.com/)
- [MinIO Documentation](https://docs.min.io/)
- [JWT Authentication](https://jwt.io/)