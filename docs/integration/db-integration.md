# Integración con Bases de Datos

## Visión General

El sistema proporciona capacidades para conectarse e interactuar con bases de datos externas a través de la funcionalidad DB Services. Esta integración permite a los usuarios conectarse a diferentes tipos de bases de datos, explorar su esquema y ejecutar consultas, tanto en SQL directo como a través de lenguaje natural.

## Arquitectura

```
┌─────────────────┐     ┌────────────────┐     ┌────────────────┐
│   API Gateway   │────▶│  DB Services   │────▶│   RAG Agent    │
└─────────────────┘     └────────────────┘     └────────────────┘
                               │                       │
                               ▼                       ▼
                        ┌────────────────┐     ┌────────────────┐
                        │     Bases      │     │ LLM Provider   │
                        │   de Datos     │     │                │
                        │    Externas    │     │                │
                        └────────────────┘     └────────────────┘
```

## Características Principales

### 1. Conexión a Múltiples Motores de BD

El sistema soporta conexión a los siguientes tipos de bases de datos:

- **PostgreSQL**
- **MySQL / MariaDB**
- **SQLite**
- **MS SQL Server**
- **Oracle Database** (requiere configuración adicional)

### 2. Gestión de Credenciales

Las credenciales se almacenan de forma segura:

- Cifrado de contraseñas en la base de datos
- Opción de utilizar la integración con sistemas de gestión de secretos
- Posibilidad de restringir el acceso a determinadas bases de datos por usuario

### 3. Exploración de Esquemas

El sistema permite:

- Listar tablas y vistas
- Obtener estructura de cada tabla (columnas, tipos, etc.)
- Visualizar relaciones entre tablas
- Ver estadísticas básicas de las tablas

### 4. Consultas SQL y de Lenguaje Natural

Ejecución de consultas de dos tipos:

- **SQL Directo**: Para usuarios con conocimientos de SQL
- **Lenguaje Natural**: Convertidas automáticamente a SQL mediante LLM

### 5. Seguridad y Control de Acceso

Medidas implementadas:

- Validación de consultas para prevenir inyección SQL
- Límites configurables de tiempo de ejecución
- Restricciones de tamaño de resultados
- Opciones de modo de solo lectura

## Configuración y Uso

### Endpoints Principales

- `/api/v1/db-connections`: CRUD de conexiones
- `/api/v1/db-connections/{id}/schema`: Exploración de esquemas
- `/api/v1/db-queries`: Ejecución de consultas
- `/api/v1/db-agents`: Configuración de agentes inteligentes

Ver el [API Reference](../api/api-reference.md) para más detalles.

### Configuración de Conexiones

Ejemplo de configuración de una nueva conexión a PostgreSQL:

```json
{
  "name": "Base de datos principal",
  "description": "PostgreSQL con datos de usuarios",
  "db_type": "postgresql",
  "host": "db.example.com",
  "port": 5432,
  "database": "maindb",
  "username": "dbuser",
  "password": "password123",
  "ssl_mode": "require"
}
```

### Ejecución de Consultas SQL

```http
POST /api/v1/db-queries
Content-Type: application/json
Authorization: Bearer <token>

{
  "connection_id": "conn123",
  "query_type": "sql",
  "query": "SELECT * FROM users WHERE created_at > $1 ORDER BY username LIMIT 100",
  "parameters": {
    "$1": "2023-01-01T00:00:00Z"
  }
}
```

### Ejecución de Consultas en Lenguaje Natural

```http
POST /api/v1/db-queries
Content-Type: application/json
Authorization: Bearer <token>

{
  "connection_id": "conn123",
  "query_type": "natural",
  "query": "Muéstrame los 10 usuarios más activos en el último mes, junto con su correo electrónico y ubicación",
  "parameters": {}
}
```

## Componentes Internos

### Gestor de Conexiones

Componente encargado de:
- Crear y validar conexiones
- Mantener pool de conexiones para optimizar rendimiento
- Monitorear el estado de las conexiones
- Implementar reintentos y manejo de fallos

### Analizador de Esquemas

Componente que:
- Extrae metadatos de las bases de datos
- Construye representación interna del esquema
- Detecta relaciones entre tablas
- Prepara información para exploración y consulta

### Procesador de Consultas

Componente que:
- Valida y sanitiza consultas SQL
- Previene inyecciones SQL
- Implementa límites y timeouts
- Formatea resultados para el cliente

### Traductor de Lenguaje Natural a SQL

Componente que:
- Interpreta la consulta en lenguaje natural
- Utiliza esquema de la base de datos como contexto
- Genera SQL válido para la base de datos específica
- Proporciona explicación de la consulta generada

## Mejores Prácticas

### Seguridad

1. **Crear usuarios específicos** con privilegios mínimos para cada conexión
2. **Utilizar SSL/TLS** para conexiones a bases de datos remotas
3. **Revisar consultas generadas** antes de permitir ejecución automática
4. **Activar modo solo lectura** para consultas de usuarios regulares

### Rendimiento

1. **Establecer límites adecuados** de rows/tiempo para evitar consultas costosas
2. **Utilizar conexiones persistentes** para bases de datos frecuentemente utilizadas
3. **Monitorear uso de memoria** durante ejecución de consultas grandes
4. **Configurar tamaño de pool de conexiones** según carga esperada

### Uso Efectivo

1. **Proporcionar contexto claro** en consultas de lenguaje natural
2. **Explorar esquema** antes de realizar consultas complejas
3. **Guardar consultas útiles** como favoritas para reutilización
4. **Configurar tablas permitidas** para restringir acceso a datos sensibles

## Limitaciones Actuales

- **Tamaño de resultados**: Limitado a 100MB por consulta
- **Tiempo de ejecución**: Máximo 30 segundos (configurable)
- **Tipos de consultas**: Solo SELECT para consultas en lenguaje natural
- **Bases de datos NoSQL**: Soporte limitado (MongoDB en desarrollo)

## Ejemplos de Uso

### Recuperar Datos de Ventas para Análisis

```json
{
  "connection_id": "sales_db",
  "query_type": "natural",
  "query": "Muestra el total de ventas mensuales por región en 2023, ordenadas de mayor a menor"
}
```

### Análisis de Comportamiento de Usuarios

```json
{
  "connection_id": "analytics_db",
  "query_type": "natural",
  "query": "¿Cuál es el porcentaje de retención de usuarios nuevos después de 30 días en los últimos 6 meses?"
}
```

### Monitoreo de Sistema

```json
{
  "connection_id": "monitoring_db",
  "query_type": "sql",
  "query": "SELECT service_name, COUNT(*) as error_count FROM system_logs WHERE level = 'ERROR' AND timestamp > $1 GROUP BY service_name ORDER BY error_count DESC",
  "parameters": {
    "$1": "2023-06-01T00:00:00Z"
  }
}
```