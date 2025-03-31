# Guía de Seguridad

## Visión General

Este documento proporciona una visión general de las medidas de seguridad implementadas en el backend AISS. La seguridad es una prioridad fundamental en el diseño y desarrollo del sistema, especialmente considerando la naturaleza sensible de los datos que se procesan.

## Modelo de Seguridad

El sistema implementa un modelo de seguridad en profundidad con múltiples capas de protección:

```
┌────────────────────────────────────────────────────────────┐
│                     Perímetro de Red                        │
│ ┌────────────────────────────────────────────────────────┐ │
│ │                   API Gateway                           │ │
│ │ ┌────────────────────────────────────────────────────┐ │ │
│ │ │               Autenticación y Autorización         │ │ │
│ │ │ ┌────────────────────────────────────────────────┐ │ │ │
│ │ │ │             Seguridad a Nivel de Servicio      │ │ │ │
│ │ │ │ ┌────────────────────────────────────────────┐ │ │ │ │
│ │ │ │ │          Seguridad a Nivel de Datos        │ │ │ │ │
│ │ │ │ └────────────────────────────────────────────┘ │ │ │ │
│ │ │ └────────────────────────────────────────────────┘ │ │ │
│ │ └────────────────────────────────────────────────────┘ │ │
│ └────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

## Autenticación y Autorización

### Sistema de Autenticación

El sistema utiliza autenticación basada en JWT (JSON Web Tokens) con los siguientes componentes:

1. **Access Token**: 
   - Corta duración (30 minutos por defecto)
   - Contiene información del usuario y permisos
   - Firmado con una clave secreta utilizando HMAC-SHA256

2. **Refresh Token**:
   - Larga duración (7 días por defecto)
   - Utilizado para obtener nuevos access tokens
   - Almacenado en base de datos con asociación al dispositivo

3. **Flujo de Autenticación**:

```
┌─────────┐                                    ┌────────────┐
│ Cliente │                                    │ API        │
│         │                                    │ Gateway    │
└────┬────┘                                    └─────┬──────┘
     │                                               │
     │  POST /api/v1/auth/login                     │
     │  {username, password}                        │
     │─────────────────────────────────────────────▶│
     │                                              │
     │                                              │
     │                                     ┌────────┴─────────┐
     │                                     │ Validar          │
     │                                     │ credenciales     │
     │                                     └────────┬─────────┘
     │                                              │
     │  200 OK                                      │
     │  {access_token, refresh_token, expires_in}   │
     │◀─────────────────────────────────────────────│
     │                                              │
     │  GET /api/v1/resource                        │
     │  Authorization: Bearer {access_token}        │
     │─────────────────────────────────────────────▶│
     │                                              │
     │                                     ┌────────┴─────────┐
     │                                     │ Validar token    │
     │                                     │ y permisos       │
     │                                     └────────┬─────────┘
     │                                              │
     │  Respuesta al recurso solicitado             │
     │◀─────────────────────────────────────────────│
```

### Control de Acceso Basado en Roles (RBAC)

El sistema implementa RBAC con los siguientes roles:

| Rol | Descripción | Permisos |
|-----|-------------|----------|
| `admin` | Administrador del sistema | Acceso completo a todos los recursos |
| `manager` | Gestor de usuarios y contenidos | Gestión de usuarios y documentos |
| `editor` | Editor de contenidos | Creación y edición de documentos |
| `user` | Usuario estándar | Lectura de documentos, consultas RAG |
| `guest` | Usuario invitado | Acceso limitado a recursos públicos |

## Seguridad de API Gateway

### Protecciones Implementadas

1. **Limitación de Tasa (Rate Limiting)**:
   - Basado en dirección IP y/o usuario autenticado
   - Límites configurables por ruta y método
   - Protección contra ataques de fuerza bruta y DDoS

2. **Configuración CORS**:
   - Lista blanca de orígenes permitidos
   - Control preciso de métodos y cabeceras permitidas
   - Configuración específica por ruta

3. **Validación de Entrada**:
   - Sanitización estricta de parámetros de entrada
   - Validación de esquema JSON
   - Protección contra inyección y XSS

4. **Cabeceras de Seguridad**:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Content-Security-Policy: default-src 'self'`
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains`

## Seguridad de Datos

### Almacenamiento Seguro

1. **Credenciales**:
   - Contraseñas hasheadas con bcrypt (factor de costo 12+)
   - Tokens de API cifrados en reposo
   - Rotación periódica de claves secretas

2. **Información Personal**:
   - Cifrado de datos sensibles en reposo
   - Enmascaramiento de información personal en logs
   - Política estricta de retención de datos

3. **Documentos y Contenido**:
   - Permisos granulares a nivel de documento
   - Control de acceso basado en área de conocimiento
   - URLs firmadas con tiempo de expiración para acceso a archivos

### Transferencia Segura

1. **TLS/SSL**:
   - TLS 1.2+ requerido para todas las comunicaciones
   - Configuración segura de cifrados (sin soporte a cifrados obsoletos)
   - Verificación de certificados para comunicaciones internas

2. **API Keys y Tokens**:
   - Rotación regular de claves y tokens
   - Validación de origen para peticiones con API keys
   - Revocación inmediata de tokens comprometidos

## Seguridad de Integración LLM

### Protecciones para APIs Externas

1. **Gestión de API Keys**:
   - Almacenamiento seguro de claves de API
   - Enmascaramiento en logs y respuestas
   - Restricción de acceso a nivel de usuario

2. **Validación de Prompts**:
   - Filtrado de contenido malicioso o inapropiado
   - Detección de intentos de prompt injection
   - Limitación de tamaño y complejidad

3. **Filtrado de Respuestas**:
   - Validación de contenido generado
   - Eliminación de información sensible o no autorizada
   - Monitoreo de tokens de respuesta

## Seguridad en Terminal Services

### Acceso SSH Seguro

1. **Autenticación SSH**:
   - Soporte para claves SSH con passphrases
   - Validación estricta de host keys
   - Opción para autenticación de múltiples factores

2. **Control de Sesión**:
   - Tiempo de expiración configurable
   - Monitoreo de comandos potencialmente peligrosos
   - Limitación de acceso por IP y usuario

3. **Auditoría y Logging**:
   - Registro completo de comandos ejecutados
   - Timestamps precisos para análisis forense
   - Alertas para comandos sospechosos

## Monitoreo y Respuesta a Incidentes

### Sistema de Monitoreo

1. **Alertas de Seguridad**:
   - Intentos fallidos de autenticación
   - Patrones de acceso sospechosos
   - Uso anómalo de recursos

2. **Auditoría**:
   - Registro completo de acciones sensibles
   - Logs a prueba de manipulación
   - Retención configurable de logs

### Respuesta a Incidentes

1. **Plan de Respuesta**:
   - Procedimientos definidos para diferentes tipos de incidentes
   - Contactos de emergencia
   - Proceso de escalamiento

2. **Mitigación**:
   - Bloqueo automático de IPs maliciosas
   - Revocación de tokens comprometidos
   - Aislamiento de componentes afectados

## Configuración Segura

### Variables de Entorno

La siguiente tabla muestra las variables de entorno relacionadas con seguridad:

| Variable | Descripción | Valor Predeterminado |
|----------|-------------|----------------------|
| `JWT_SECRET` | Clave secreta para firma de JWT | *Requerido* |
| `JWT_EXPIRATION` | Duración del access token | `30m` |
| `REFRESH_TOKEN_EXPIRATION` | Duración del refresh token | `7d` |
| `PASSWORD_SALT` | Sal adicional para hashing de contraseñas | *Requerido* |
| `API_RATE_LIMIT` | Límite global de peticiones por minuto | `60` |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para CORS | `http://localhost:3000` |
| `TLS_CERT_FILE` | Ruta al certificado TLS | `/certs/server.crt` |
| `TLS_KEY_FILE` | Ruta a la clave privada TLS | `/certs/server.key` |
| `ENABLE_SECURITY_HEADERS` | Activar cabeceras de seguridad | `true` |
| `LOG_SENSITIVE_DATA` | Permitir logging de datos sensibles | `false` |

### Configuración Recomendada para Producción

A continuación se muestra un ejemplo de configuración segura para entornos de producción:

```yaml
# security.yaml
api_gateway:
  rate_limit:
    enabled: true
    requests_per_minute: 60
    burst: 10
  cors:
    allowed_origins:
      - https://app.yourcompany.com
    allowed_methods:
      - GET
      - POST
      - PUT
      - DELETE
    allowed_headers:
      - Authorization
      - Content-Type
    max_age: 86400
  tls:
    enabled: true
    cert_file: /path/to/cert.pem
    key_file: /path/to/key.pem
    min_version: TLS1.2

authentication:
  jwt:
    algorithm: HS256
    access_token_expiry: 15m
    refresh_token_expiry: 7d
    refresh_token_reuse_detection: true
  passwords:
    min_length: 12
    require_uppercase: true
    require_lowercase: true
    require_number: true
    require_special: true
    bcrypt_cost: 14
  mfa:
    enabled: true
    methods:
      - totp
      - recovery_code

authorization:
  role_cache_ttl: 300s
  default_policy: deny
  superadmin_ips:
    - 10.0.0.1/32

logging:
  mask_sensitive_data: true
  audit_log_retention_days: 90
  security_events_to_syslog: true
```

## Mejores Prácticas

### Para Operadores del Sistema

1. **Gestión de Acceso**:
   - Implementar el principio de privilegio mínimo
   - Revisar permisos regularmente
   - Revocar accesos inmediatamente tras cambios de personal

2. **Actualizaciones**:
   - Mantener todos los componentes actualizados
   - Implementar un proceso de gestión de parches
   - Monitorear vulnerabilidades en dependencias

3. **Configuración**:
   - Cambiar todas las contraseñas predeterminadas
   - Limitar el acceso a la red interna
   - Implementar listas blancas de IPs cuando sea posible

### Para Desarrolladores

1. **Código Seguro**:
   - Seguir principios OWASP Top 10
   - Realizar revisiones de código de seguridad
   - Implementar tests de seguridad automatizados

2. **Gestión de Secretos**:
   - No almacenar secretos en el código
   - Utilizar gestión de secretos centralizada
   - Rotar credenciales regularmente

3. **Validación de Entrada**:
   - Validar todas las entradas del usuario
   - Implementar escape de datos de salida
   - Utilizar consultas parametrizadas

## Apéndice

### Referencias

- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [JWT Best Practices](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-jwt-bcp)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [Mozilla Web Security Guidelines](https://infosec.mozilla.org/guidelines/web_security)

### Verificación de Seguridad

Lista de verificación de seguridad para despliegue:

- [ ] Todas las comunicaciones utilizan TLS 1.2+
- [ ] Cabeceras de seguridad HTTP implementadas
- [ ] Contraseñas y secretos almacenados de forma segura
- [ ] Rate limiting configurado apropiadamente
- [ ] CORS configurado solo para orígenes necesarios
- [ ] Logs de seguridad activados y monitoreados
- [ ] Sistema de alertas configurado
- [ ] Backups regulares y cifrados
- [ ] Plan de respuesta a incidentes documentado y probado
- [ ] Todos los servicios ejecutados con privilegios mínimos