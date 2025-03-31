# Integración con Terminal

## Visión General

La integración con terminal permite a los usuarios interactuar con servidores remotos a través de una interfaz de terminal web completamente segura. Este componente proporciona además capacidades avanzadas como sugerencias inteligentes basadas en comandos, análisis de contexto y sesiones compartidas.

## Arquitectura

```
┌────────────────────────┐
│       Frontend         │
│ (Terminal Web Client)  │
└──────────┬─────────────┘
           │ WebSocket
           ▼
┌──────────────────────────────────────┐
│           API Gateway                │
└──────────────┬───────────────────────┘
               │
    ┌──────────┴─────────┐  
    │  Terminal Gateway  │◀────┐
    │     Service        │     │
    └──────────┬─────────┘     │
               │               │
    ┌──────────┴─────────┐     │ Event
    │   SSH Manager      │     │ Bus
    └──────────┬─────────┘     │
               │               │
               │               │
┌──────────────┴─────────┐     │
│ Terminal Session       │─────┘
│ Service                │
└──────────┬─────────────┘
           │
┌──────────┴─────────┐
│  Context Service   │
└────────────────────┘
```

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
     │                                        │   6. Terminal IO │
     │                                        │◀────────────────▶│
     │      7. Terminal IO                    │                  │
     │◀────────────────────────────────────────                  │
```

### 2. Análisis de Comandos y Sugerencias

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

## Componentes Principales

### Terminal Gateway Service

Este servicio actúa como punto de entrada para todas las sesiones de terminal:

- **Gestión de sesiones SSH**: Establece y mantiene conexiones
- **WebSocket para I/O de terminal**: Comunicación bidireccional en tiempo real
- **Manejo de autenticación**: Soporta autenticación por contraseña y clave SSH
- **Detección de sistema operativo**: Identifica automáticamente el SO remoto
- **Registro de sesiones**: Mantiene historial de conexiones

### SSH Manager

Componente central que gestiona todas las conexiones SSH:

- **Pool de conexiones**: Manejo eficiente de múltiples sesiones
- **Seguridad avanzada**: Verificación de host keys, conexiones cifradas
- **Redimensionamiento de terminal**: Ajuste dinámico del tamaño PTY
- **Modo compartido**: Permite sesiones compartidas entre usuarios
- **Gestión de pausa/reanudación**: Control de flujo para sesiones

### Terminal Session Service

Servicio que mantiene el estado y metadatos de las sesiones:

- **Almacenamiento de historial**: Guarda comandos y resultados
- **Análisis de comandos**: Procesa y categoriza comandos ejecutados
- **Sugerencias contextuales**: Genera recomendaciones basadas en historial
- **Estadísticas de uso**: Métricas sobre sesiones y comandos
- **Gestión de permisos**: Control de acceso a sesiones compartidas

### Context Service Integration

Integración con el servicio de contexto para mejorar la experiencia:

- **Análisis semántico**: Comprensión de comandos y su propósito
- **Conocimiento contextual**: Relaciona comandos con áreas de conocimiento
- **Recomendaciones inteligentes**: Sugiere comandos basados en el contexto actual
- **Aprendizaje continuo**: Mejora con el uso del sistema

## Configuración y Uso

### Endpoints Principales

- `/api/v1/terminal/sessions`: CRUD de sesiones de terminal
- `/api/v1/terminal/sessions/{id}/connect`: Obtiene URL de WebSocket para conexión
- `/api/v1/terminal/sessions/{id}/commands`: Historial de comandos
- `/api/v1/terminal/suggestions`: Obtiene sugerencias basadas en contexto

Ver el [API Reference](../api/api-reference.md) para más detalles.

### Crear una Nueva Sesión

```http
POST /api/v1/terminal/sessions
Content-Type: application/json
Authorization: Bearer <token>

{
  "target_host": "server.example.com",
  "port": 22,
  "username": "admin",
  "auth_method": "key",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----",
  "passphrase": "",
  "options": {
    "terminal_type": "xterm-256color",
    "window_size": {
      "cols": 80,
      "rows": 24
    }
  }
}
```

### Conexión WebSocket

Después de crear una sesión, se establece una conexión WebSocket:

```javascript
// Ejemplo de código JavaScript (Frontend)
const ws = new WebSocket("wss://api.example.com/ws/terminal/session123");

// Enviar entrada de terminal
ws.send(JSON.stringify({
  type: "terminal_input",
  data: { data: "ls -la\n" }
}));

// Recibir salida de terminal
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.type === "terminal_output") {
    console.log(message.data.data);
  }
};

// Redimensionar terminal
ws.send(JSON.stringify({
  type: "resize",
  data: { cols: 100, rows: 30 }
}));
```

### Protocolo WebSocket

Los mensajes WebSocket siguen este formato:

```json
{
  "type": "tipo_mensaje",
  "data": { ... }
}
```

Tipos de mensajes soportados:

| Tipo | Dirección | Descripción |
|------|-----------|-------------|
| `terminal_input` | Cliente → Servidor | Envío de datos al terminal |
| `terminal_output` | Servidor → Cliente | Salida del terminal |
| `resize` | Cliente → Servidor | Cambio de tamaño del terminal |
| `session_status` | Servidor → Cliente | Cambios en el estado de la sesión |
| `suggestion_available` | Servidor → Cliente | Nuevas sugerencias disponibles |
| `execute_suggestion` | Cliente → Servidor | Ejecutar una sugerencia |
| `session_control` | Cliente → Servidor | Control de sesión (pausa, reanudación) |

## Sugerencias Inteligentes

El sistema analiza comandos y proporciona sugerencias contextuales:

### Tipos de Sugerencias

- **Completado de comandos**: Basado en historial y comandos comunes
- **Corrección de errores**: Detecta errores de sintaxis y propone soluciones
- **Comandos relacionados**: Sugiere comandos complementarios al actual
- **Comandos optimizados**: Versiones más eficientes de comandos frecuentes
- **Recordatorios de seguridad**: Advertencias sobre comandos potencialmente peligrosos

### Estructura de una Sugerencia

```json
{
  "id": "sug123",
  "command": "docker ps -a",
  "description": "Listar todos los contenedores Docker, incluyendo los que no están en ejecución",
  "reason": "Se detectó que está trabajando con Docker y ejecutó 'docker ps' recientemente",
  "risk_level": "low",
  "requires_approval": false,
  "created_at": "2023-05-10T14:30:00Z"
}
```

## Seguridad

### Medidas de Seguridad Implementadas

1. **Autenticación robusta**:
   - Soporte para claves SSH y contraseñas
   - Posibilidad de requerir MFA para conexiones

2. **Verificación de host keys**:
   - Almacenamiento seguro de claves conocidas
   - Advertencias para claves desconocidas
   - Opción de verificación estricta

3. **Cifrado de comunicaciones**:
   - Todo el tráfico SSH cifrado de extremo a extremo
   - Conexiones WebSocket sobre TLS

4. **Validación de comandos**:
   - Niveles de riesgo para comandos
   - Aprobación requerida para comandos peligrosos
   - Lista negra configurable de comandos prohibidos

5. **Auditoría completa**:
   - Registro de todos los comandos ejecutados
   - Timestamping para análisis forense
   - Opciones de exportación para cumplimiento normativo

## Sesiones Compartidas

El sistema permite compartir sesiones de terminal entre múltiples usuarios:

### Características de Sesiones Compartidas

- **Vista compartida en tiempo real**: Todos los participantes ven la misma terminal
- **Modos de acceso**: Observador (solo lectura) o colaborador (lectura/escritura)
- **Indicadores de actividad**: Muestra quién está escribiendo actualmente
- **Chat integrado**: Comunicación entre participantes sin interrumpir la terminal
- **Control de sesión**: Capacidad de pausar/reanudar para todos los participantes

### Ejemplo de Invitación a Sesión Compartida

```http
POST /api/v1/terminal/sessions/session123/participants
Content-Type: application/json
Authorization: Bearer <token>

{
  "user_id": "user456",
  "access_level": "observer",
  "expiration": "2023-05-15T23:59:59Z",
  "message": "Por favor, revisa la configuración de Nginx conmigo"
}
```

## Integración con Frontend

### Componentes Recomendados

- **xterm.js**: Terminal web compatible
- **Socket.IO**: Manejo simplificado de WebSockets
- **Monaco Editor**: Para visualización de comandos y resultados

### Eventos de Terminal

| Evento | Descripción |
|--------|-------------|
| `connect` | Conexión establecida |
| `disconnect` | Conexión terminada |
| `data` | Datos recibidos del terminal |
| `resize` | Cambio de tamaño de terminal |
| `suggestion` | Nueva sugerencia disponible |
| `status_change` | Cambio en estado de sesión |
| `error` | Error en la sesión |

## Limitaciones Actuales

- **Transferencia de archivos**: Limitada a comandos FTP/SCP (sin drag-and-drop)
- **Resolución de pantalla**: No soporta aplicaciones gráficas (solo terminal)
- **Sesiones inactivas**: Timeout automático después de 1 hora de inactividad
- **Tamaño de buffer**: Limitado a 1MB para salida de comandos individuales

## Próximas Mejoras

- Soporte para transferencia de archivos integrada
- Integración con sistema de archivos web
- Grabación y reproducción de sesiones
- Sincronización de historial entre dispositivos
- Sugerencias proactivas basadas en IA