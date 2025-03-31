# DB Services

## Visión General

Los DB Services proporcionan una capa de integración con bases de datos externas, permitiendo a los usuarios conectarse, explorar y consultar diferentes sistemas de bases de datos a través de una interfaz unificada. Estos servicios facilitan tanto consultas SQL directas como consultas en lenguaje natural, que son traducidas automáticamente a SQL mediante la integración con modelos de lenguaje.

## Arquitectura

```
┌───────────────────────────────────────────────────────────┐
│                     DB Services                            │
│                                                           │
│  ┌─────────────────────┐       ┌─────────────────────┐    │
│  │                     │       │                     │    │
│  │   DB Connection     │◀─────▶│    DB Agent        │    │
│  │   Service           │       │    Service         │    │
│  │                     │       │                     │    │
│  └─────────────┬───────┘       └─────────┬───────────┘    │
│                │                         │                │
│                ▼                         ▼                │
│  ┌─────────────────────┐       ┌─────────────────────┐    │
│  │                     │       │                     │    │
│  │  External Databases │       │   RAG Agent         │    │
│  │                     │       │   (LLM)             │    │
│  └─────────────────────┘       └─────────────────────┘    │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

## Componentes Principales

### DB Connection Service

El DB Connection Service gestiona las conexiones a diferentes bases de datos y proporciona funcionalidades para explorar esquemas y ejecutar consultas SQL.

#### Características Principales

- **Gestión de conexiones**: Creación, prueba y eliminación de conexiones
- **Soporte multi-base de datos**: Compatible con PostgreSQL, MySQL, SQLite, MS SQL
- **Exploración de esquemas**: Descubrimiento de tablas, columnas y relaciones
- **Ejecución de consultas**: Ejecución segura de consultas SQL con límites y timeouts
- **Pool de conexiones**: Administración eficiente de conexiones activas
- **Gestión de credenciales**: Almacenamiento seguro de información de acceso

#### Tecnologías Utilizadas

- **Go**: Lenguaje de programación principal
- **sqlx**: Extensión de la biblioteca estándar database/sql
- **drivers específicos**: Controladores para cada tipo de base de datos
- **MongoDB**: Almacenamiento de configuraciones de conexión

### DB Agent Service

El DB Agent Service proporciona capacidades avanzadas basadas en IA para interactuar con bases de datos usando lenguaje natural.

#### Características Principales

- **Consultas en lenguaje natural**: Traducción de preguntas a SQL
- **Explicación de consultas**: Descripción detallada de las consultas generadas
- **Sugerencias inteligentes**: Recomendaciones basadas en el esquema
- **Análisis de datos**: Insights automáticos sobre los resultados
- **Asistencia contextual**: Ajuste de consultas basado en conversaciones previas

#### Tecnologías Utilizadas

- **Go**: Lenguaje de programación principal
- **Python**: Para componentes de procesamiento de lenguaje natural
- **RAG Agent**: Integración con el sistema RAG para procesamiento de consultas
- **MongoDB**: Almacenamiento de consultas y conversaciones

## Estructura Interna

### DB Connection Service

#### Estructura de Datos de Conexión

```go
// DBConnection representa una conexión a una base de datos externa
type DBConnection struct {
    ID          string    `json:"id" bson:"_id,omitempty"`
    Name        string    `json:"name" bson:"name"`
    Description string    `json:"description" bson:"description"`
    DBType      string    `json:"db_type" bson:"db_type"` // postgresql, mysql, sqlite, mssql
    Host        string    `json:"host" bson:"host"`
    Port        int       `json:"port" bson:"port"`
    Database    string    `json:"database" bson:"database"`
    Username    string    `json:"username" bson:"username"`
    // Password almacenado cifrado
    PasswordEnc string    `json:"-" bson:"password_enc"`
    SSLMode     string    `json:"ssl_mode" bson:"ssl_mode"`
    Options     string    `json:"options" bson:"options"`
    CreatedBy   string    `json:"created_by" bson:"created_by"`
    CreatedAt   time.Time `json:"created_at" bson:"created_at"`
    UpdatedAt   time.Time `json:"updated_at" bson:"updated_at"`
    LastUsed    time.Time `json:"last_used" bson:"last_used"`
    Status      string    `json:"status" bson:"status"` // connected, disconnected, error
    LastError   string    `json:"last_error,omitempty" bson:"last_error,omitempty"`
    
    // Configuración avanzada
    MaxOpenConns    int  `json:"max_open_conns" bson:"max_open_conns"`
    MaxIdleConns    int  `json:"max_idle_conns" bson:"max_idle_conns"`
    ConnMaxLifetime int  `json:"conn_max_lifetime" bson:"conn_max_lifetime"` // segundos
    ReadOnly        bool `json:"read_only" bson:"read_only"`
    QueryTimeout    int  `json:"query_timeout" bson:"query_timeout"` // segundos
}
```

#### Gestor de Conexiones

```go
// DBConnectionManager gestiona las conexiones a bases de datos
type DBConnectionManager struct {
    connPool     map[string]*sql.DB        // Pool de conexiones activas
    connInfo     map[string]*DBConnection  // Información de conexiones
    poolMutex    sync.RWMutex              // Mutex para el pool
    cryptoKey    []byte                    // Clave para cifrado/descifrado
    maxConns     int                       // Número máximo de conexiones simultáneas
    defaultLimit int                       // Límite por defecto para filas devueltas
    repository   *DBConnectionRepository   // Acceso a almacenamiento
}

// GetConnection obtiene una conexión activa o la crea si no existe
func (m *DBConnectionManager) GetConnection(connectionID string) (*sql.DB, error) {
    m.poolMutex.RLock()
    conn, exists := m.connPool[connectionID]
    m.poolMutex.RUnlock()
    
    if exists {
        // Verificar que la conexión sigue activa
        if err := conn.Ping(); err == nil {
            return conn, nil
        }
        // Conexión inactiva, eliminarla del pool
        m.poolMutex.Lock()
        delete(m.connPool, connectionID)
        m.poolMutex.Unlock()
    }
    
    // Crear nueva conexión
    connInfo, err := m.repository.GetByID(connectionID)
    if err != nil {
        return nil, fmt.Errorf("connection not found: %w", err)
    }
    
    // Descifrar contraseña
    password, err := m.decryptPassword(connInfo.PasswordEnc)
    if err != nil {
        return nil, fmt.Errorf("failed to decrypt password: %w", err)
    }
    
    // Construir DSN según el tipo de base de datos
    dsn, err := m.buildDSN(connInfo, password)
    if err != nil {
        return nil, err
    }
    
    // Abrir conexión
    db, err := sql.Open(connInfo.DBType, dsn)
    if err != nil {
        return nil, fmt.Errorf("failed to open connection: %w", err)
    }
    
    // Configurar la conexión
    db.SetMaxOpenConns(connInfo.MaxOpenConns)
    db.SetMaxIdleConns(connInfo.MaxIdleConns)
    db.SetConnMaxLifetime(time.Duration(connInfo.ConnMaxLifetime) * time.Second)
    
    // Verificar la conexión
    if err := db.Ping(); err != nil {
        db.Close()
        return nil, fmt.Errorf("failed to ping database: %w", err)
    }
    
    // Actualizar estado y último uso
    connInfo.Status = "connected"
    connInfo.LastUsed = time.Now()
    connInfo.LastError = ""
    m.repository.Update(connInfo)
    
    // Almacenar en el pool
    m.poolMutex.Lock()
    m.connPool[connectionID] = db
    m.poolMutex.Unlock()
    
    return db, nil
}
```

#### Explorador de Esquemas

```go
// SchemaExplorer proporciona funcionalidades para explorar esquemas de bases de datos
type SchemaExplorer struct {
    connManager *DBConnectionManager
}

// GetTableInfo obtiene información sobre una tabla específica
func (e *SchemaExplorer) GetTableInfo(connectionID, tableName string) (*TableInfo, error) {
    db, err := e.connManager.GetConnection(connectionID)
    if err != nil {
        return nil, err
    }
    
    connInfo, _ := e.connManager.GetConnectionInfo(connectionID)
    
    // Seleccionar la consulta adecuada según el tipo de base de datos
    var query string
    switch connInfo.DBType {
    case "postgresql":
        query = `
            SELECT 
                c.column_name, 
                c.data_type, 
                c.is_nullable = 'YES' as is_nullable,
                c.column_default,
                (
                    SELECT count(*) = 1 
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_name = $1
                    AND ccu.column_name = c.column_name
                ) as is_primary_key
            FROM information_schema.columns c
            WHERE c.table_name = $1
            ORDER BY c.ordinal_position
        `
    case "mysql":
        query = `
            SELECT 
                COLUMN_NAME as column_name, 
                DATA_TYPE as data_type, 
                IS_NULLABLE = 'YES' as is_nullable,
                COLUMN_DEFAULT as column_default,
                COLUMN_KEY = 'PRI' as is_primary_key
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            AND TABLE_SCHEMA = ?
            ORDER BY ORDINAL_POSITION
        `
        // Otras bases de datos...
    }
    
    // Ejecutar la consulta apropiada
    var rows *sql.Rows
    if connInfo.DBType == "mysql" {
        rows, err = db.Query(query, tableName, connInfo.Database)
    } else {
        rows, err = db.Query(query, tableName)
    }
    if err != nil {
        return nil, fmt.Errorf("failed to query table info: %w", err)
    }
    defer rows.Close()
    
    // Procesar resultados
    var columns []Column
    for rows.Next() {
        var col Column
        var defaultValue sql.NullString
        if err := rows.Scan(&col.Name, &col.Type, &col.IsNullable, &defaultValue, &col.IsPrimaryKey); err != nil {
            return nil, fmt.Errorf("error scanning column: %w", err)
        }
        if defaultValue.Valid {
            col.Default = defaultValue.String
        }
        columns = append(columns, col)
    }
    
    // Obtener conteo aproximado de filas
    var rowCount int64
    countQuery := fmt.Sprintf("SELECT COUNT(*) FROM %s", tableName)
    if err := db.QueryRow(countQuery).Scan(&rowCount); err != nil {
        // Si falla, no es crítico, continuamos
        rowCount = -1
    }
    
    return &TableInfo{
        Name:     tableName,
        Columns:  columns,
        RowCount: rowCount,
    }, nil
}

// GetTables obtiene la lista de tablas en la base de datos
func (e *SchemaExplorer) GetTables(connectionID string) ([]string, error) {
    // Implementación similar, adaptada por tipo de base de datos
}

// GetRelationships obtiene las relaciones entre tablas
func (e *SchemaExplorer) GetRelationships(connectionID string) ([]Relationship, error) {
    // Implementación similar, adaptada por tipo de base de datos
}
```

#### Ejecutor de Consultas

```go
// QueryExecutor ejecuta consultas SQL en bases de datos
type QueryExecutor struct {
    connManager *DBConnectionManager
}

// ExecuteQuery ejecuta una consulta SQL y devuelve los resultados
func (e *QueryExecutor) ExecuteQuery(connectionID, query string, params map[string]interface{}, options QueryOptions) (*QueryResult, error) {
    // Obtener conexión
    db, err := e.connManager.GetConnection(connectionID)
    if err != nil {
        return nil, err
    }
    
    connInfo, _ := e.connManager.GetConnectionInfo(connectionID)
    
    // Verificar modo de solo lectura si está habilitado
    if connInfo.ReadOnly && !isReadOnlyQuery(query) {
        return nil, errors.New("write operations are not allowed in read-only mode")
    }
    
    // Aplicar límite si no está especificado en la consulta
    if options.Limit > 0 && !containsLimitClause(query) {
        query = addLimitToQuery(query, options.Limit, connInfo.DBType)
    }
    
    // Preparar la consulta con un contexto que tenga timeout
    timeout := options.Timeout
    if timeout == 0 {
        timeout = time.Duration(connInfo.QueryTimeout) * time.Second
    }
    
    ctx, cancel := context.WithTimeout(context.Background(), timeout)
    defer cancel()
    
    // Preparar la consulta
    stmt, err := db.PrepareContext(ctx, query)
    if err != nil {
        return nil, fmt.Errorf("failed to prepare query: %w", err)
    }
    defer stmt.Close()
    
    // Preparar parámetros en el orden correcto
    args := make([]interface{}, 0)
    if len(params) > 0 {
        paramNames := extractParamNames(query, connInfo.DBType)
        for _, name := range paramNames {
            if value, exists := params[name]; exists {
                args = append(args, value)
            } else {
                return nil, fmt.Errorf("missing parameter: %s", name)
            }
        }
    }
    
    // Ejecutar la consulta
    start := time.Now()
    rows, err := stmt.QueryContext(ctx, args...)
    if err != nil {
        return nil, fmt.Errorf("query execution failed: %w", err)
    }
    defer rows.Close()
    
    // Obtener nombres de columnas
    columns, err := rows.Columns()
    if err != nil {
        return nil, fmt.Errorf("failed to get column names: %w", err)
    }
    
    // Preparar resultado
    result := &QueryResult{
        Columns:       columns,
        Rows:          make([][]interface{}, 0),
        RowCount:      0,
        ExecutionTime: time.Since(start),
    }
    
    // Escanear filas
    for rows.Next() {
        // Crear slice de interfaces para escanear valores
        values := make([]interface{}, len(columns))
        scanArgs := make([]interface{}, len(columns))
        for i := range values {
            scanArgs[i] = &values[i]
        }
        
        // Escanear fila
        if err := rows.Scan(scanArgs...); err != nil {
            return nil, fmt.Errorf("error scanning row: %w", err)
        }
        
        // Convertir valores nil a nil de Go
        for i := range values {
            if v, ok := values[i].([]byte); ok {
                values[i] = string(v)
            }
        }
        
        result.Rows = append(result.Rows, values)
        result.RowCount++
    }
    
    // Verificar errores después de la iteración
    if err := rows.Err(); err != nil {
        return nil, fmt.Errorf("error iterating rows: %w", err)
    }
    
    return result, nil
}
```

### DB Agent Service

#### Natural Language to SQL

```go
// NLToSQLConverter convierte consultas en lenguaje natural a SQL
type NLToSQLConverter struct {
    schemaExplorer *SchemaExplorer
    ragClient      *rag.Client
    queryHistory   *QueryHistoryRepository
}

// ConvertToSQL convierte una consulta en lenguaje natural a SQL
func (c *NLToSQLConverter) ConvertToSQL(connectionID, naturalQuery string, options ConversionOptions) (*SQLConversion, error) {
    // Obtener información del esquema
    schema, err := c.getSchemaInfo(connectionID)
    if err != nil {
        return nil, err
    }
    
    // Preparar prompt para el LLM
    prompt := c.buildPrompt(naturalQuery, schema, options)
    
    // Enviar al RAG Agent
    resp, err := c.ragClient.Query(&rag.QueryRequest{
        Query:       prompt,
        MaxTokens:   1000,
        Temperature: 0.1,
        Provider:    options.LLMProvider,
        Model:       options.LLMModel,
    })
    if err != nil {
        return nil, fmt.Errorf("RAG query failed: %w", err)
    }
    
    // Procesar respuesta
    conversion, err := c.parseRagResponse(resp.Answer)
    if err != nil {
        return nil, fmt.Errorf("failed to parse RAG response: %w", err)
    }
    
    // Validar el SQL generado
    if err := c.validateSQL(connectionID, conversion.SQL); err != nil {
        return nil, fmt.Errorf("generated SQL is invalid: %w", err)
    }
    
    // Guardar en historial
    c.saveToHistory(connectionID, naturalQuery, conversion)
    
    return conversion, nil
}

// buildPrompt construye el prompt para el LLM
func (c *NLToSQLConverter) buildPrompt(query string, schema SchemaInfo, options ConversionOptions) string {
    prompt := `
You are an expert SQL writer. Convert the following natural language query to SQL code.

Database Schema:
`
    // Añadir tablas
    for _, table := range schema.Tables {
        prompt += fmt.Sprintf("Table: %s\n", table.Name)
        for _, column := range table.Columns {
            primaryKey := ""
            if column.IsPrimaryKey {
                primaryKey = "PRIMARY KEY"
            }
            nullable := "NOT NULL"
            if column.IsNullable {
                nullable = "NULL"
            }
            prompt += fmt.Sprintf("  - %s (%s) %s %s\n", 
                column.Name, column.Type, nullable, primaryKey)
        }
        prompt += "\n"
    }
    
    // Añadir relaciones
    if len(schema.Relationships) > 0 {
        prompt += "Relationships:\n"
        for _, rel := range schema.Relationships {
            prompt += fmt.Sprintf("  - %s.%s -> %s.%s\n", 
                rel.Table, rel.Column, rel.ReferencesTable, rel.ReferencesColumn)
        }
        prompt += "\n"
    }
    
    // Añadir la consulta
    prompt += fmt.Sprintf("Natural Language Query: %s\n\n", query)
    
    // Añadir contexto adicional si está disponible
    if options.Context != "" {
        prompt += fmt.Sprintf("Additional Context: %s\n\n", options.Context)
    }
    
    // Añadir instrucciones específicas
    prompt += `
Output format:
1. SQL Query: The SQL query that answers the question. Use the exact table and column names from the schema.
2. Explanation: Explain the SQL query in simple terms, step by step.

Important guidelines:
- Use standard SQL syntax compatible with the database type.
- Include appropriate JOINs based on the relationships.
- Use aliases for readability where appropriate.
- Include reasonable LIMIT clause if returning potentially large result sets.
- For aggregations, include appropriate GROUP BY clauses.
- Never use columns or tables that don't exist in the schema.
- If the query cannot be answered with the available schema, explain why.

SQL Query:
`
    
    return prompt
}

// parseRagResponse extrae el SQL y la explicación de la respuesta del RAG
func (c *NLToSQLConverter) parseRagResponse(response string) (*SQLConversion, error) {
    // Extraer la parte SQL
    sqlRegex := regexp.MustCompile(`(?s)SQL Query:\s*\n(.*?)(?:\n\n|$)`)
    sqlMatches := sqlRegex.FindStringSubmatch(response)
    
    if len(sqlMatches) < 2 {
        return nil, errors.New("could not extract SQL query from response")
    }
    
    // Extraer la explicación
    explanationRegex := regexp.MustCompile(`(?s)Explanation:\s*\n(.*?)(?:\n\n|$)`)
    explanationMatches := explanationRegex.FindStringSubmatch(response)
    
    explanation := ""
    if len(explanationMatches) >= 2 {
        explanation = strings.TrimSpace(explanationMatches[1])
    }
    
    // Limpiar el SQL
    sql := strings.TrimSpace(sqlMatches[1])
    
    return &SQLConversion{
        SQL:         sql,
        Explanation: explanation,
    }, nil
}
```

## Flujos de Operación

### 1. Conexión a Base de Datos

```
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │───▶│  API Gateway  │───▶│ DB Connection │
│           │    │               │    │ Service       │
└───────────┘    └───────────────┘    └───────┬───────┘
                                              │
                                              │ Validar y cifrar credenciales
                                              ▼
                                      ┌───────────────┐
                                      │   MongoDB     │
                                      │ (conexiones)  │
                                      └───────┬───────┘
                                              │
                                              │ Probar conexión
                                              ▼
                                      ┌───────────────┐
                                      │   Base de     │
                                      │   Datos       │
                                      └───────┬───────┘
                                              │
                                              │ Conexión exitosa
                                              ▼
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │◀───│  API Gateway  │◀───│ DB Connection │
│           │    │               │    │ Service       │
└───────────┘    └───────────────┘    └───────────────┘
```

### 2. Consulta SQL

```
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │───▶│  API Gateway  │───▶│ DB Connection │
│ (SQL)     │    │               │    │ Service       │
└───────────┘    └───────────────┘    └───────┬───────┘
                                              │
                                              │ Validar y ejecutar
                                              ▼
                                      ┌───────────────┐
                                      │  Base de      │
                                      │  Datos        │
                                      └───────┬───────┘
                                              │
                                              │ Resultados
                                              ▼
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │◀───│  API Gateway  │◀───│ DB Connection │
│           │    │               │    │ Service       │
└───────────┘    └───────────────┘    └───────────────┘
```

### 3. Consulta en Lenguaje Natural

```
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │───▶│  API Gateway  │───▶│  DB Agent     │
│ (Natural) │    │               │    │  Service      │
└───────────┘    └───────────────┘    └───────┬───────┘
                                              │
                                              │ Obtener esquema
                                              ▼
                                      ┌───────────────┐
                                      │ DB Connection │
                                      │ Service       │
                                      └───────┬───────┘
                                              │
                                              │ Esquema
                                              ▼
                                      ┌───────────────┐
                                      │ RAG Agent     │
                                      │ (LLM)         │
                                      └───────┬───────┘
                                              │
                                              │ SQL generado
                                              ▼
                                      ┌───────────────┐
                                      │ DB Connection │
                                      │ Service       │
                                      └───────┬───────┘
                                              │
                                              │ Ejecutar SQL
                                              ▼
                                      ┌───────────────┐
                                      │  Base de      │
                                      │  Datos        │
                                      └───────┬───────┘
                                              │
                                              │ Resultados
                                              ▼
┌───────────┐    ┌───────────────┐    ┌───────────────┐
│  Cliente  │◀───│  API Gateway  │◀───│  DB Agent     │
│           │    │               │    │  Service      │
└───────────┘    └───────────────┘    └───────────────┘
```

## Ejemplos de Uso

### Consulta SQL Directa

```json
// Request
POST /api/v1/db-queries
{
  "connection_id": "conn123",
  "query_type": "sql",
  "query": "SELECT * FROM customers WHERE country = $1 ORDER BY last_purchase_date DESC LIMIT 10",
  "parameters": {
    "$1": "Spain"
  }
}

// Response
{
  "status": "success",
  "data": {
    "columns": [
      "id",
      "first_name",
      "last_name",
      "email",
      "country",
      "last_purchase_date"
    ],
    "rows": [
      [1, "María", "García", "maria@example.com", "Spain", "2023-05-10T15:30:00Z"],
      [2, "Juan", "Pérez", "juan@example.com", "Spain", "2023-05-05T10:15:00Z"],
      // ... más filas
    ],
    "row_count": 10,
    "execution_time_ms": 25
  }
}
```

### Consulta en Lenguaje Natural

```json
// Request
POST /api/v1/db-queries
{
  "connection_id": "conn123",
  "query_type": "natural",
  "query": "¿Quiénes son los 10 clientes más recientes de España?"
}

// Response
{
  "status": "success",
  "data": {
    "sql": "SELECT * FROM customers WHERE country = 'Spain' ORDER BY last_purchase_date DESC LIMIT 10",
    "explanation": "Esta consulta selecciona todos los clientes cuyo país es España, los ordena por fecha de última compra en orden descendente (del más reciente al más antiguo) y limita los resultados a los 10 primeros registros.",
    "columns": [
      "id",
      "first_name",
      "last_name",
      "email",
      "country",
      "last_purchase_date"
    ],
    "rows": [
      [1, "María", "García", "maria@example.com", "Spain", "2023-05-10T15:30:00Z"],
      [2, "Juan", "Pérez", "juan@example.com", "Spain", "2023-05-05T10:15:00Z"],
      // ... más filas
    ],
    "row_count": 10,
    "execution_time_ms": 125
  }
}
```

## Configuración

### DB Connection Service

El DB Connection Service se configura mediante variables de entorno o archivo `.env`:

```
# Configuración del servidor
PORT=8088
ENVIRONMENT=production
LOG_LEVEL=info
HTTP_TIMEOUT=60s

# Configuración de MongoDB
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=db_services
MONGODB_COLLECTION_CONNECTIONS=db_connections
MONGODB_COLLECTION_QUERIES=db_queries

# Configuración de seguridad
ENCRYPTION_KEY=${ENCRYPTION_KEY}
MAX_CONNECTIONS=20
DEFAULT_QUERY_TIMEOUT=30
DEFAULT_QUERY_LIMIT=1000
READ_ONLY_MODE=false

# Límites y restricciones
MAX_QUERY_ROWS=10000
MAX_QUERY_SIZE_BYTES=102400
BLOCKED_KEYWORDS=DROP TABLE,DROP DATABASE,TRUNCATE TABLE,DELETE FROM
```

### DB Agent Service

El DB Agent Service se configura mediante variables de entorno o archivo `.env`:

```
# Configuración del servidor
PORT=8089
ENVIRONMENT=production
LOG_LEVEL=info
HTTP_TIMEOUT=120s

# Configuración de RAG
RAG_SERVICE_URL=http://rag-agent:8085
LLM_DEFAULT_PROVIDER=openai
LLM_DEFAULT_MODEL=gpt-4
LLM_MAX_TOKENS=2000
LLM_TEMPERATURE=0.1

# Configuración de DB Service
DB_CONNECTION_SERVICE_URL=http://db-connection-service:8088

# Configuración de cache
CACHE_ENABLED=true
CACHE_TTL_SECONDS=300
```

## Seguridad

### Medidas de Seguridad Implementadas

1. **Credenciales Cifradas**:
   - Contraseñas de bases de datos cifradas en reposo
   - Uso de encriptación AES-256 para credenciales
   - Rotación periódica de claves de cifrado

2. **Validación de Consultas**:
   - Lista negra de comandos peligrosos (DROP, TRUNCATE, etc.)
   - Detección de inyección SQL en consultas
   - Límites configurables para tamaño y tiempo de ejecución

3. **Modo de Solo Lectura**:
   - Opción para restringir a operaciones SELECT
   - Aplicable por conexión o globalmente
   - Validación estricta de todas las consultas

4. **Control de Acceso**:
   - Permisos granulares por usuario y conexión
   - Historial de acceso y auditoría
   - Restricciones por IP para conexiones sensibles

### Configuración de Seguridad

```yaml
# security.yaml para DB Services
database_connections:
  encryption:
    algorithm: AES-256-GCM
    key_rotation_days: 90
  
  validation:
    block_dangerous_commands: true
    dangerous_commands:
      - DROP TABLE
      - DROP DATABASE
      - TRUNCATE TABLE
      - DELETE FROM .* WHERE .*
    max_query_size_bytes: 102400
    query_timeout_seconds: 30
  
  query_limits:
    max_rows: 1000
    default_limit: 100
    max_execution_time_seconds: 60
  
  read_only:
    global_read_only: false
    enforce_by_default: true
    allowed_overrides:
      - admin
      - data_engineer
```

## Rendimiento y Escalabilidad

### Optimizaciones Implementadas

1. **Pool de Conexiones**:
   - Reutilización de conexiones para reducir sobrecarga
   - Manejo inteligente de conexiones inactivas
   - Límites configurables por tipo de base de datos

2. **Consultas Preparadas**:
   - Uso de prepared statements para todas las consultas
   - Reutilización de planes de ejecución
   - Protección contra inyección SQL

3. **Caché de Esquemas**:
   - Almacenamiento en caché de metadatos de esquema
   - Invalidación automática tras cambios detectados
   - TTL configurable para metadatos

4. **Caché de Consultas**:
   - Memorización de resultados para consultas frecuentes
   - Hash único basado en consulta y parámetros
   - TTL configurable por tipo de consulta

### Métricas de Rendimiento

| Operación | Tiempo Promedio | Notas |
|-----------|-----------------|-------|
| Conexión a BD | 100-500ms | Depende del tipo de BD y ubicación |
| Consulta SQL directa | 10-100ms | Para consultas simples |
| Consulta lenguaje natural | 1-3s | Incluye generación de SQL |
| Exploración de esquema | 200-500ms | Depende del tamaño de la BD |

## Referencias

- [SQL Query Optimization Techniques](https://use-the-index-luke.com/)
- [Go SQL Driver Interface](https://golang.org/pkg/database/sql/)
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- [Database Connection Pooling](https://github.com/brettwooldridge/HikariCP)