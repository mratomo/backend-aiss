# Terminal Services

## Visión General

Terminal Services proporciona una capa de integración con terminales de servidores remotos, permitiendo la interacción SSH segura a través de una interfaz web. Estos servicios incluyen funcionalidades avanzadas como sugerencias inteligentes basadas en comandos, análisis de contexto y gestión de sesiones con capacidades colaborativas.

## Arquitectura

```
┌───────────────────────────────────────────────────────────────┐
│                     Terminal Services                          │
│                                                               │
│  ┌───────────────────┐         ┌───────────────────┐          │
│  │                   │         │                   │          │
│  │ Terminal Gateway  │◀───────▶│ Terminal Session  │          │
│  │ Service           │         │ Service           │          │
│  │                   │         │                   │          │
│  └───────┬───────────┘         └─────────┬─────────┘          │
│          │                               │                    │
│          │                               │                    │
│          ▼                               ▼                    │
│  ┌───────────────────┐         ┌───────────────────┐          │
│  │                   │         │                   │          │
│  │   SSH Manager     │         │ Command Analysis  │          │
│  │                   │         │ Service           │          │
│  │                   │         │                   │          │
│  └───────────────────┘         └───────────────────┘          │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## Componentes Principales

### Terminal Gateway Service

Actúa como punto de entrada para todas las conexiones de terminal, gestionando la autenticación, conexión SSH y comunicación WebSocket en tiempo real.

#### Características Principales

- **WebSocket para terminal interactiva**: Comunicación bidireccional en tiempo real
- **Gestión de sesiones SSH**: Establecimiento y mantenimiento de conexiones seguras
- **Autenticación múltiple**: Soporte para contraseñas y claves SSH
- **Detección de sistema operativo**: Identificación automática del entorno remoto
- **Redimensionamiento de terminal**: Ajuste dinámico del tamaño de ventana PTY
- **Broadcast de eventos**: Soporte para sesiones compartidas y colaborativas

#### API Endpoints

- **POST /api/v1/terminal/sessions**: Crear nueva sesión
- **GET /api/v1/terminal/sessions**: Listar sesiones
- **GET /api/v1/terminal/sessions/{id}**: Obtener detalles de sesión
- **DELETE /api/v1/terminal/sessions/{id}**: Terminar sesión
- **GET /api/v1/terminal/sessions/{id}/connect**: Obtener URL WebSocket para conexión

### Terminal Session Service

Gestiona el estado, metadatos y análisis de las sesiones de terminal, proporcionando capacidades de sugerencia inteligente y análisis de comandos.

#### Características Principales

- **Historial de comandos**: Almacenamiento y consulta de comandos ejecutados
- **Análisis de comandos**: Procesamiento y categorización de comandos
- **Sugerencias inteligentes**: Recomendaciones basadas en contexto e historial
- **Métricas de uso**: Estadísticas sobre sesiones y patrones de uso
- **Integración de contexto**: Asociación de comandos con áreas de conocimiento

#### API Endpoints

- **GET /api/v1/terminal/sessions/{id}/commands**: Historial de comandos
- **GET /api/v1/terminal/suggestions**: Obtener sugerencias para comandos
- **POST /api/v1/terminal/sessions/{id}/participants**: Gestionar participantes
- **POST /api/v1/terminal/feedback**: Enviar feedback sobre sugerencias

## Flujo de Operación

### 1. Establecimiento de Sesión

```
┌───────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────┐
│  Cliente  │───▶│  API Gateway  │───▶│    Terminal   │───▶│ Servidor  │
│  Web      │    │               │    │    Gateway    │    │ SSH       │
└───────────┘    └───────────────┘    └───────────────┘    └───────────┘
     │                                        │                  │
     │      1. Request conexión SSH           │                  │
     │────────────────────────────────────────▶                  │
     │                                        │                  │
     │                                        │   2. SSH Auth    │
     │                                        │─────────────────▶│
     │                                        │                  │
     │                                        │   3. OK/Error    │
     │                                        │◀─────────────────│
     │                                        │                  │
     │      4. WebSocket URL                  │                  │
     │◀────────────────────────────────────────                  │
     │                                        │                  │
     │      5. Connect WebSocket              │                  │
     │────────────────────────────────────────▶                  │
     │                                        │                  │
     │      6. Terminal I/O                   │   7. SSH I/O     │
     │◀───────────────────────────────────────▶◀────────────────▶│
```

### 2. Protocolo WebSocket

```
┌───────────┐                          ┌───────────────┐
│  Cliente  │                          │   Terminal    │
│  Web      │                          │   Gateway     │
└───────────┘                          └───────────────┘
      │                                       │
      │  {"type": "terminal_input",           │
      │   "data": {"data": "ls -la\n"}}       │
      │──────────────────────────────────────▶│
      │                                       │
      │  {"type": "terminal_output",          │
      │   "data": {"data": "total 32\n..."}}  │
      │◀──────────────────────────────────────│
      │                                       │
      │  {"type": "resize",                   │
      │   "data": {"cols": 100, "rows": 30}}  │
      │──────────────────────────────────────▶│
      │                                       │
      │  {"type": "suggestion_available",     │
      │   "data": {"id": "sug123", ...}}      │
      │◀──────────────────────────────────────│
      │                                       │
      │  {"type": "execute_suggestion",       │
      │   "data": {"suggestion_id": "sug123"}}│
      │──────────────────────────────────────▶│
```

### 3. Análisis de Comandos y Sugerencias

```
┌───────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────┐
│  Cliente  │───▶│    Terminal   │───▶│    Session    │───▶│  Context  │
│  Web      │    │    Gateway    │    │    Service    │    │  Service  │
└───────────┘    └───────────────┘    └───────────────┘    └───────────┘
     │                  │                    │                   │
     │   1. Comando     │                    │                   │
     │──────────────────▶                    │                   │
     │                  │                    │                   │
     │                  │  2. Registrar CMD  │                   │
     │                  │────────────────────▶                   │
     │                  │                    │                   │
     │                  │                    │   3. Análisis     │
     │                  │                    │───────────────────▶
     │                  │                    │                   │
     │                  │                    │   4. Sugerencias  │
     │                  │                    │◀───────────────────
     │                  │                    │                   │
     │                  │  5. Notificar      │                   │
     │                  │◀────────────────────                   │
     │                  │                    │                   │
     │   6. Sugerencia  │                    │                   │
     │◀──────────────────                    │                   │
```

## Estructura Interna

### SSH Manager

Componente central para la gestión de conexiones SSH con las siguientes características:

#### Gestión de Conexiones

```go
// SSHConnection representa una conexión SSH activa
type SSHConnection struct {
    SessionID   string
    UserID      string
    TargetHost  string
    Username    string
    Port        int
    ClientIP    string
    Status      SessionStatus
    ConnectedAt time.Time
    LastActive  time.Time
    Stdin       io.WriteCloser
    Stdout      io.Reader
    Stderr      io.Reader
    Close       func() error
    Lock        sync.Mutex
    Client      *ssh.Client
    WindowSize  struct {
        Cols int
        Rows int
    }
    TerminalType string
    OSInfo       struct {
        Type    string
        Version string
    }
    IsPaused      bool
    PausedAt      time.Time
    PauseChannels struct {
        Pause    chan bool
        IsPaused chan bool
        Timeout  time.Duration
    }
    MemStats struct {
        OutputBufferSize int64
        MaxBufferSize    int64
        LastBufferReset  time.Time
    }
}
```

#### WebSocket Handler

```go
// HandleWebSocket gestiona una conexión WebSocket para terminal I/O
func (m *SSHManager) HandleWebSocket(c *gin.Context, sessionID string) {
    // Upgrade HTTP connection to WebSocket
    ws, err := m.upgrader.Upgrade(c.Writer, c.Request, nil)
    if err != nil {
        log.Printf("Failed to upgrade to WebSocket: %v", err)
        return
    }
    defer ws.Close()

    // Get the SSH connection
    m.sessionMutex.RLock()
    conn, exists := m.sessions[sessionID]
    m.sessionMutex.RUnlock()

    if !exists {
        // Enviar error de sesión no encontrada
        return
    }
    
    // Registrar cliente WebSocket
    m.registerWebSocketClient(sessionID, ws)

    // Crear canales de comunicación
    done := make(chan struct{})
    defer close(done)

    // Goroutine para leer del WebSocket y escribir a SSH stdin
    go func() { ... }()

    // Goroutine para leer de SSH stdout/stderr y escribir al WebSocket
    go func() { ... }()

    // Goroutine para keep-alive
    go func() { ... }()

    // Esperar a que termine la sesión
    <-done
}
```

### Command Analysis Service

Servicio para analizar comandos y generar sugerencias inteligentes:

#### Estructura de Sugerencia

```go
// Suggestion representa una sugerencia de comando
type Suggestion struct {
    ID               string                 `json:"suggestion_id"`
    SuggestionType   string                 `json:"suggestion_type"`
    Title            string                 `json:"title"`
    Description      string                 `json:"description"`
    Command          string                 `json:"command"`
    RiskLevel        string                 `json:"risk_level"`
    RequiresApproval bool                   `json:"requires_approval"`
    Metadata         map[string]interface{} `json:"metadata"`
}
```

#### Análisis de Comandos

```go
// analyzeCommand analiza un comando para patrones y envía el análisis 
// al servicio de contexto
func (m *SSHManager) analyzeCommand(cmdInfo CommandAnalysis) {
    // Esperar un momento para permitir que se procese la salida
    time.Sleep(500 * time.Millisecond)
    
    // Registrar análisis de comando
    log.Printf("Analyzing command: %s (ID: %s, Suggested: %v)", 
        cmdInfo.Command, cmdInfo.ID, cmdInfo.IsSuggested)
        
    // En una implementación completa:
    // 1. Recuperar salida reciente del session service
    // 2. Enviarla al context aggregator para análisis
    // 3. Actualizar el registro de comandos con los resultados
}
```

## Configuración

El Terminal Gateway Service se configura mediante variables de entorno o archivo `.env`:

```
# Configuración del servidor
PORT=8086
ENVIRONMENT=production
LOG_LEVEL=info

# Configuración SSH
SSH_TIMEOUT=30s
SSH_KEEP_ALIVE=30s
SSH_KEY_DIR=/keys
SSH_MAX_SESSIONS=100

# Configuración WebSocket
WS_PING_INTERVAL=30s
WS_WRITE_WAIT=10s
WS_READ_WAIT=60s
WS_MAX_MESSAGE_SIZE=8192

# Configuración CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.domain.com

# Session Service
SESSION_SERVICE_URL=http://terminal-session-service:8087
```

El Terminal Session Service se configura así:

```
# Configuración del servidor
PORT=8087
ENVIRONMENT=production
LOG_LEVEL=info

# Configuración MongoDB
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=terminal_service
MONGODB_COLLECTION_SESSIONS=sessions
MONGODB_COLLECTION_COMMANDS=commands
MONGODB_COLLECTION_SUGGESTIONS=suggestions

# Configuración de Context Service
CONTEXT_SERVICE_URL=http://context-service:8083

# Configuración de análisis
COMMAND_ANALYSIS_BATCH_SIZE=10
COMMAND_ANALYSIS_INTERVAL=5s
COMMAND_HISTORY_MAX_ITEMS=1000
SUGGESTION_TTL=3600
```

## Seguridad

### Medidas de Seguridad Implementadas

1. **Autenticación Segura**:
   - Soporte para claves SSH y contraseñas
   - Posibilidad de requerir MFA para conexiones

2. **Verificación de Host Keys**:
   - Almacenamiento seguro de claves conocidas
   - Advertencias para claves desconocidas
   - Opción de verificación estricta

3. **Cifrado de Comunicaciones**:
   - Todo el tráfico SSH cifrado de extremo a extremo
   - Conexiones WebSocket sobre TLS

4. **Validación de Comandos**:
   - Niveles de riesgo para comandos
   - Aprobación requerida para comandos peligrosos
   - Lista negra configurable de comandos prohibidos

5. **Auditoría Completa**:
   - Registro de todos los comandos ejecutados
   - Timestamping para análisis forense
   - Opciones de exportación para cumplimiento normativo

### Configuración de Seguridad

```yaml
# security.yaml para terminal-services
ssh:
  known_hosts_file: /keys/known_hosts
  host_key_verification: strict  # strict, warn, none
  private_key_permissions: 0600
  command_restrictions:
    enabled: true
    blocked_commands:
      - rm -rf /
      - dd if=/dev/zero
      - chmod -R 777 /
    risk_levels:
      high:
        - shutdown
        - reboot
        - mkfs
      medium:
        - chmod
        - chown
        - iptables
      low:
        - rm
        - mv
        - kill
    
session:
  idle_timeout: 3600  # segundos
  max_duration: 86400  # segundos
  max_commands: 10000
  
audit:
  log_all_commands: true
  log_command_output: true
  log_session_events: true
  retention_days: 90
```

## Sesiones Compartidas

El sistema permite compartir sesiones de terminal entre múltiples usuarios:

### Características de Sesiones Compartidas

- **Vista compartida en tiempo real**: Todos los participantes ven la misma terminal
- **Modos de acceso**: Observador (solo lectura) o colaborador (lectura/escritura)
- **Indicadores de actividad**: Muestra quién está escribiendo actualmente
- **Control de sesión**: Capacidad de pausar/reanudar para todos los participantes

### Gestión de Clientes WebSocket

```go
// registerWebSocketClient añade una conexión WebSocket a una sesión
func (m *SSHManager) registerWebSocketClient(sessionID string, ws *websocket.Conn) {
    m.wsClientsMutex.Lock()
    defer m.wsClientsMutex.Unlock()
    
    // Añadir esta conexión a la lista para esta sesión
    m.wsClients[sessionID] = append(m.wsClients[sessionID], ws)
    
    log.Printf("WebSocket client registered for session %s, total clients: %d", 
        sessionID, len(m.wsClients[sessionID]))
}

// broadcastToSession envía un mensaje a todos los clientes WebSocket de una sesión
func (m *SSHManager) broadcastToSession(sessionID string, msgType string, msgData interface{}) {
    m.wsClientsMutex.RLock()
    clients := m.wsClients[sessionID]
    m.wsClientsMutex.RUnlock()
    
    if len(clients) == 0 {
        return // No hay clientes conectados para esta sesión
    }
    
    message := models.WebSocketMessage{
        Type: msgType,
        Data: msgData,
    }
    
    // Enviar a todos los clientes
    for _, client := range clients {
        err := client.WriteJSON(message)
        if err != nil {
            log.Printf("Failed to send message to WebSocket client: %v", err)
        }
    }
}
```

## Optimización de Rendimiento

El Terminal Gateway Service implementa varias optimizaciones para mejorar el rendimiento y reducir el consumo de memoria:

### Buffer Adaptativo

```go
// Uso de buffer adaptativo basado en la actividad del terminal
const minBufferSize = 1024
const maxBufferSize = 16384
bufferSize := minBufferSize
buffer := make([]byte, bufferSize)

// Monitoreo de memoria
var totalBytesRead int64
lastResetTime := time.Now()
const memoryResetInterval = 5 * time.Minute
const memoryThreshold = 50 * 1024 * 1024 // 50MB threshold

// Ajuste periódico del tamaño del buffer
if time.Since(lastResetTime) > memoryResetInterval {
    // Registrar estadísticas de memoria antes del reset
    log.Printf("Memory stats for session %s: %d bytes read since last reset", 
        conn.SessionID, totalBytesRead)
    
    // Actualizar estadísticas de memoria de la sesión
    conn.Lock.Lock()
    conn.MemStats.OutputBufferSize = totalBytesRead
    conn.MemStats.LastBufferReset = time.Now()
    conn.Lock.Unlock()
    
    // Reset de contadores
    totalBytesRead = 0
    lastResetTime = time.Now()
    
    // Forzar recolección de basura si hemos procesado muchos datos
    if totalBytesRead > memoryThreshold {
        runtime.GC()
    }
    
    // Redimensionar buffer según uso reciente
    if conn.MemStats.OutputBufferSize > 10*maxBufferSize {
        bufferSize = maxBufferSize
    } else if conn.MemStats.OutputBufferSize < minBufferSize {
        bufferSize = minBufferSize
    } else {
        bufferSize = int(conn.MemStats.OutputBufferSize / 8)
        if bufferSize < minBufferSize {
            bufferSize = minBufferSize
        } else if bufferSize > maxBufferSize {
            bufferSize = maxBufferSize
        }
    }
    
    // Recrear buffer con tamaño óptimo
    buffer = make([]byte, bufferSize)
}
```

### Timeouts en Canales

```go
// Manejo de señales de pausa/reanudación con timeout
select {
case pauseState, ok := <-conn.PauseChannels.Pause:
    if !ok {
        // Canal cerrado, sesión de terminal terminando
        return
    }
    isPaused = pauseState
    
    // Enviar confirmación con timeout
    select {
    case conn.PauseChannels.IsPaused <- isPaused:
        // Confirmación enviada
    case <-time.After(conn.PauseChannels.Timeout):
        // Timeout, nadie está escuchando la confirmación
        log.Printf("Warning: Pause confirmation timed out for session %s", conn.SessionID)
    }
    
    if isPaused {
        log.Printf("Reader paused for session %s", conn.SessionID)
    } else {
        log.Printf("Reader resumed for session %s", conn.SessionID)
    }
    continue
case <-time.After(10 * time.Millisecond):
    // No hay señal de pausa/reanudación, continuar operación normal
}
```

## Integración con Context Service

El Terminal Session Service integra con el Context Service para proporcionar sugerencias contextuales y análisis de comandos:

### Flujo de Integración

```
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│  Terminal     │      │  Terminal     │      │  Context      │
│  Gateway      │─────▶│  Session      │─────▶│  Service      │
│  Service      │      │  Service      │      │               │
└───────────────┘      └───────────────┘      └───────────────┘
        │                     │                      │
        │ Command             │ Command History      │ Knowledge Areas
        │ Execution           │ and Analysis         │ and Context
        ▼                     ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│  SSH          │      │  MongoDB      │      │  Qdrant &     │
│  Servers      │      │  (Commands)   │      │  MongoDB      │
└───────────────┘      └───────────────┘      └───────────────┘
```

### Ejemplo de Integración

```go
// Enviar comando para análisis de contexto
func (s *SessionService) SendCommandForAnalysis(cmd models.TerminalCommand) error {
    // Preparar datos para envío al Context Service
    contextData := map[string]interface{}{
        "session_id":     cmd.SessionID,
        "user_id":        cmd.UserID,
        "command":        cmd.Command,
        "output":         cmd.Output,
        "exit_code":      cmd.ExitCode,
        "working_dir":    cmd.WorkingDir,
        "timestamp":      cmd.ExecutedAt,
        "environment":    cmd.Metadata["environment"],
        "command_type":   detectCommandType(cmd.Command),
        "command_tokens": tokenizeCommand(cmd.Command),
    }
    
    // Enviar al endpoint de análisis de comandos
    resp, err := s.httpClient.Post(
        fmt.Sprintf("%s/api/v1/terminal/analyze", s.contextServiceURL),
        "application/json",
        bytes.NewBuffer(jsonData),
    )
    if err != nil {
        return fmt.Errorf("failed to send command for analysis: %w", err)
    }
    defer resp.Body.Close()
    
    // Procesar sugerencias recibidas
    if resp.StatusCode == http.StatusOK {
        var result struct {
            Suggestions []models.Suggestion `json:"suggestions"`
            Context     map[string]interface{} `json:"context"`
        }
        if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
            return fmt.Errorf("failed to decode response: %w", err)
        }
        
        // Almacenar sugerencias para uso futuro
        for _, suggestion := range result.Suggestions {
            if err := s.storeSuggestion(cmd.SessionID, suggestion); err != nil {
                log.Printf("Failed to store suggestion: %v", err)
            }
        }
        
        // Actualizar contexto de la sesión
        if err := s.updateSessionContext(cmd.SessionID, result.Context); err != nil {
            log.Printf("Failed to update session context: %v", err)
        }
    }
    
    return nil
}
```

## Referencias

- [Go WebSocket Documentation](https://pkg.go.dev/github.com/gorilla/websocket)
- [Golang SSH Package](https://pkg.go.dev/golang.org/x/crypto/ssh)
- [Terminal PTY Documentation](https://www.unix.com/man-page/linux/7/pty/)
- [xterm.js Documentation](https://xtermjs.org/docs/)