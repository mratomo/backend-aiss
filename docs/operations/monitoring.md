# Monitoreo y Observabilidad

Esta guía describe las estrategias y herramientas de monitoreo para el sistema Backend AISS en entornos de producción.

## Índice

1. [Filosofía de Monitoreo](#filosofía-de-monitoreo)
2. [Métricas Clave](#métricas-clave)
3. [Herramientas de Monitoreo](#herramientas-de-monitoreo)
4. [Configuración de Alertas](#configuración-de-alertas)
5. [Logging](#logging)
6. [Trazabilidad](#trazabilidad)
7. [Dashboards](#dashboards)
8. [Auditoría y Seguridad](#auditoría-y-seguridad)
9. [Respuesta a Incidentes](#respuesta-a-incidentes)

## Filosofía de Monitoreo

El monitoreo en Backend AISS se basa en los siguientes principios:

- **Monitoreo proactivo**: Detectar problemas antes de que afecten a los usuarios.
- **Observabilidad completa**: Combinar logs, métricas y trazas para entender el sistema.
- **Contexto significativo**: Proporcionar información suficiente para diagnosticar problemas.
- **Automatización**: Automatizar la recolección, análisis y respuesta cuando sea posible.
- **Mejora continua**: Utilizar datos de monitoreo para optimizar el sistema.

## Métricas Clave

### Métricas de Disponibilidad

- **Uptime**: Tiempo de actividad de cada servicio.
- **Health checks**: Estado de salud de cada servicio.
- **SLA/SLO**: Cumplimiento de acuerdos de nivel de servicio.

### Métricas de Rendimiento

- **Latencia**: Tiempos de respuesta (promedio, p50, p95, p99).
- **Throughput**: Solicitudes por segundo.
- **Tasa de error**: Porcentaje de solicitudes fallidas.
- **Saturación**: Uso de recursos (CPU, memoria, disco, red).

### Métricas Específicas por Servicio

#### API Gateway
- Solicitudes por segundo (por endpoint)
- Distribución de códigos de estado HTTP
- Tiempo de procesamiento de solicitudes
- Tasa de throttling/rate limiting

#### Document Service
- Tiempo de procesamiento de documentos
- Tamaño de documentos procesados
- Tiempo de carga/descarga de MinIO
- Estado de la cola de procesamiento

#### Embedding Service
- Tiempo de generación de embeddings
- Uso de GPU/CPU
- Tamaño de vectores procesados
- Éxito/fallo de operaciones en Qdrant

#### RAG Agent
- Tiempo de generación de respuestas
- Tokens procesados por solicitud
- Aciertos/fallos en búsqueda de contexto
- Uso de tokens por proveedor de LLM

#### Terminal Services
- Número de sesiones activas
- Duración de sesiones
- Comandos ejecutados por minuto
- Uso de recursos por sesión

#### DB Services
- Tiempo de ejecución de consultas
- Número de conexiones activas por base de datos
- Tasa de éxito en traducción de consultas
- Tamaño de resultados devueltos

## Herramientas de Monitoreo

### Recolección de Métricas

- **Prometheus**: Sistema principal de recolección de métricas.
- **Grafana**: Visualización de métricas y dashboards.
- **Prometheus Exporters**: Exportadores específicos para bases de datos y servicios.

### Logging

- **Elasticsearch**: Almacenamiento y búsqueda de logs.
- **Logstash**: Agregación y procesamiento de logs.
- **Kibana**: Visualización y análisis de logs.
- **Filebeat**: Recolección de logs de archivos.

### Tracing

- **Jaeger**: Trazabilidad distribuida.
- **OpenTelemetry**: Instrumentación de código.

### Monitoreo de Infraestructura

- **Node Exporter**: Métricas de host.
- **cAdvisor**: Métricas de contenedores.
- **Docker/Kubernetes metrics**: Métricas de plataforma.

### Verificación de Disponibilidad

- **Blackbox Exporter**: Sondeo externo de endpoints.
- **Synthetic monitoring**: Pruebas automatizadas periódicas.

## Configuración de Alertas

### Estrategia de Alertas

Las alertas deben ser:
- **Accionables**: Corresponder a problemas que requieren intervención.
- **Precisas**: Minimizar falsos positivos y negativos.
- **Claras**: Proporcionar información suficiente para diagnóstico.
- **Priorizadas**: Diferentes niveles según severidad.

### Niveles de Severidad

1. **Crítico**: Impacto inmediato en usuarios, requiere acción inmediata.
2. **Alto**: Degradación significativa, requiere acción pronta.
3. **Medio**: Problemas que deberían resolverse durante horas laborables.
4. **Bajo**: Anomalías a investigar cuando sea conveniente.

### Alertas Recomendadas

#### Disponibilidad
- Servicio no responde a health checks (Crítico)
- Tasa de error > 5% durante 5 minutos (Alto)
- Tiempo de respuesta p95 > umbral por 10 minutos (Alto)

#### Recursos
- Uso de CPU > 85% durante 5 minutos (Alto)
- Uso de memoria > 85% durante 5 minutos (Alto)
- Disco > 85% lleno (Alto)
- Predicción de disco lleno en 24h (Medio)

#### Específicas por Servicio
- Cola de procesamiento de documentos creciendo constantemente (Alto)
- Errores de conexión a bases de datos externas (Alto)
- Fallo en generación de embeddings > 5% (Alto)
- Errores en llamadas a APIs externas de LLM (Alto)

### Implementación en Prometheus

```yaml
# Ejemplo de reglas de alerta en Prometheus
groups:
- name: service_alerts
  rules:
  - alert: ServiceDown
    expr: up == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Servicio caído: {{ $labels.instance }}"
      description: "El servicio {{ $labels.job }} en {{ $labels.instance }} lleva caído más de 1 minuto."

  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
    for: 5m
    labels:
      severity: high
    annotations:
      summary: "Alta tasa de errores: {{ $labels.instance }}"
      description: "El servicio {{ $labels.job }} tiene una tasa de error superior al 5% durante los últimos 5 minutos."

  - alert: SlowResponses
    expr: http_request_duration_seconds{quantile="0.95"} > 1
    for: 10m
    labels:
      severity: high
    annotations:
      summary: "Respuestas lentas: {{ $labels.instance }}"
      description: "El tiempo de respuesta p95 para {{ $labels.handler }} es superior a 1 segundo durante los últimos 10 minutos."
```

## Logging

### Estructura de Logs

Todos los servicios deben generar logs estructurados en formato JSON:

```json
{
  "timestamp": "2023-05-10T12:34:56Z",
  "level": "info",
  "service": "document-service",
  "trace_id": "abc123def456",
  "message": "Documento procesado correctamente",
  "details": {
    "document_id": "doc123",
    "user_id": "user456",
    "processing_time_ms": 235,
    "size_bytes": 1048576
  }
}
```

### Niveles de Log

- **ERROR**: Errores que requieren intervención.
- **WARN**: Condiciones anómalas que no son errores críticos.
- **INFO**: Información de eventos normales importantes.
- **DEBUG**: Información detallada para depuración (solo en entornos no productivos).
- **TRACE**: Información muy detallada (solo para diagnósticos específicos).

### Implementación en Servicios Go

```go
// Ejemplo de configuración de logger estructurado en Go
package logger

import (
    "os"
    "go.uber.org/zap"
    "go.uber.org/zap/zapcore"
)

func NewLogger(service string) (*zap.SugaredLogger, error) {
    config := zap.NewProductionConfig()
    config.EncoderConfig.TimeKey = "timestamp"
    config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
    
    // Añadir el nombre del servicio a todos los logs
    config.InitialFields = map[string]interface{}{
        "service": service,
    }
    
    logger, err := config.Build()
    if err != nil {
        return nil, err
    }
    
    return logger.Sugar(), nil
}
```

### Implementación en Servicios Python

```python
# Ejemplo de configuración de logger estructurado en Python
import logging
import json
from datetime import datetime

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": record.name,
            "message": record.getMessage(),
        }
        
        # Añadir detalles adicionales si existen
        if hasattr(record, "details"):
            log_record["details"] = record.details
        
        # Añadir trace_id si existe
        if hasattr(record, "trace_id"):
            log_record["trace_id"] = record.trace_id
        
        # Añadir información de excepción si existe
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_record)

def setup_logger(service_name):
    logger = logging.getLogger(service_name)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
```

### Centralización de Logs

1. Cada servicio escribe logs en stdout/stderr.
2. Filebeat recolecta logs de contenedores.
3. Logstash procesa y enriquece logs.
4. Elasticsearch almacena logs de forma indexada.
5. Kibana proporciona visualización y análisis.

## Trazabilidad

La trazabilidad distribuida permite seguir una solicitud a través de múltiples servicios.

### Implementación con OpenTelemetry

#### En servicios Go:

```go
package main

import (
    "context"
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/exporters/jaeger"
    "go.opentelemetry.io/otel/sdk/resource"
    "go.opentelemetry.io/otel/sdk/trace"
    semconv "go.opentelemetry.io/otel/semconv/v1.4.0"
)

func initTracer(serviceName string) (*trace.TracerProvider, error) {
    exporter, err := jaeger.New(jaeger.WithCollectorEndpoint(
        jaeger.WithEndpoint("http://jaeger:14268/api/traces"),
    ))
    if err != nil {
        return nil, err
    }
    
    tp := trace.NewTracerProvider(
        trace.WithBatcher(exporter),
        trace.WithResource(resource.NewWithAttributes(
            semconv.SchemaURL,
            semconv.ServiceNameKey.String(serviceName),
        )),
    )
    otel.SetTracerProvider(tp)
    
    return tp, nil
}

func main() {
    tp, err := initTracer("api-gateway")
    if err != nil {
        log.Fatal(err)
    }
    defer tp.Shutdown(context.Background())
    
    // Resto del código...
}
```

#### En servicios Python:

```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def init_tracer(service_name):
    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger",
        agent_port=6831,
    )
    
    resource = Resource(attributes={
        SERVICE_NAME: service_name
    })
    
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(jaeger_exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
    return trace.get_tracer(service_name)

# Uso en una función
def process_document(document_id):
    tracer = init_tracer("document-service")
    with tracer.start_as_current_span("process_document") as span:
        span.set_attribute("document_id", document_id)
        
        # Lógica de procesamiento...
        result = extract_text(document_id)
        
        # Añadir más información al span
        span.set_attribute("document_size", len(result))
        
        return result
```

## Dashboards

### Dashboard Principal (Overview)

- Estado general del sistema
- Métricas de disponibilidad
- Alertas activas
- Gráficos de tráfico
- Tasas de error
- Uso de recursos

### Dashboards por Servicio

Cada servicio principal debe tener su propio dashboard que muestre:

- Métricas específicas del servicio
- Tendencias de uso
- Distribución de tiempos de respuesta
- Tasas de error detalladas
- Logs relevantes
- Recursos consumidos

### Dashboard de Usuarios

- Número de usuarios activos
- Operaciones por usuario
- Distribución de roles
- Patrones de uso

### Dashboard RAG

- Consultas por minuto
- Tiempos de respuesta
- Uso de tokens por proveedor
- Calidad de respuestas (basada en feedback)
- Distribución de áreas consultadas

## Auditoría y Seguridad

### Eventos de Auditoría

Los siguientes eventos deben registrarse para auditoría:

- Acciones de autenticación (éxito/fallo)
- Operaciones CRUD en recursos importantes
- Cambios de configuración
- Consultas a datos sensibles
- Operaciones administrativas

### Formato de Logs de Auditoría

```json
{
  "timestamp": "2023-05-10T12:34:56Z",
  "event": "authentication",
  "outcome": "success",
  "user_id": "user123",
  "username": "admin@example.com",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0...",
  "details": {
    "method": "password",
    "session_id": "sess789"
  }
}
```

### Monitoreo de Seguridad

- Detección de intentos fallidos de autenticación repetidos
- Patrones de acceso anómalos
- Actividad fuera de horario normal
- Accesos desde ubicaciones inusuales
- Alertas sobre vulnerabilidades detectadas

## Respuesta a Incidentes

### Proceso de Respuesta

1. **Detección**: Alerta generada por el sistema de monitoreo.
2. **Triage**: Evaluación inicial de la severidad y el impacto.
3. **Investigación**: Análisis de logs, métricas y trazas.
4. **Mitigación**: Acciones para resolver o reducir el impacto.
5. **Resolución**: Solución completa del problema.
6. **Postmortem**: Análisis posterior al incidente.

### Playbooks para Incidentes Comunes

#### Servicio no responde:

1. Verificar logs del servicio.
2. Verificar estado del contenedor.
3. Comprobar conectividad con dependencias.
4. Reiniciar el servicio si es necesario.
5. Escalar si persiste el problema.

#### Alta latencia:

1. Verificar uso de recursos (CPU, memoria).
2. Comprobar tráfico y patrones de uso anómalos.
3. Verificar tiempos de respuesta de servicios dependientes.
4. Escalar recursos temporalmente si es posible.
5. Considerar rate limiting si es por exceso de uso.

#### Errores en proceso de documentos:

1. Verificar logs específicos del Document Service.
2. Comprobar conectividad con MinIO.
3. Verificar que el Embedding Service funciona correctamente.
4. Comprobar tamaño y formato de documentos problemáticos.
5. Reiniciar el procesamiento manual si es necesario.

### Herramientas de Diagnóstico

- **Kibana**: Búsqueda y análisis de logs.
- **Grafana**: Visualización de métricas en el tiempo del incidente.
- **Jaeger UI**: Análisis de trazas para identificar componentes lentos o fallidos.
- **Prometheus Alert Manager**: Gestión y silenciamiento de alertas.
- **Herramientas de conexión remota**: Para diagnóstico directo si es necesario.