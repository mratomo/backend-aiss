# Guía de Solución de Problemas

Esta guía proporciona información para identificar, diagnosticar y resolver problemas comunes en el sistema Backend AISS.

## Índice

1. [Diagnóstico General](#diagnóstico-general)
2. [Problemas Comunes](#problemas-comunes)
3. [Problemas por Servicio](#problemas-por-servicio)
4. [Herramientas de Diagnóstico](#herramientas-de-diagnóstico)
5. [Recuperación de Datos](#recuperación-de-datos)
6. [Escalamiento de Incidentes](#escalamiento-de-incidentes)

## Diagnóstico General

### Enfoque Sistemático de Solución de Problemas

1. **Identificar síntomas**: Recoger información precisa sobre el problema.
2. **Aislar componentes**: Determinar qué componentes están afectados.
3. **Verificar logs**: Buscar mensajes de error o comportamientos anómalos.
4. **Comprobar cambios recientes**: Identificar si hay correlación con despliegues o configuraciones recientes.
5. **Revisar métricas**: Analizar patrones inusuales en rendimiento o recursos.
6. **Reproducir el problema**: Si es posible, en entorno de prueba.
7. **Aplicar solución**: De menor a mayor impacto.
8. **Verificar resolución**: Confirmar que el problema ha sido resuelto.
9. **Documentar**: Registrar el problema y la solución para referencia futura.

### Verificación de Estado del Sistema

```bash
# Verificar el estado de todos los contenedores
docker-compose ps

# Comprobar logs de un servicio específico
docker-compose logs --tail=100 <service-name>

# Verificar uso de recursos
docker stats

# Comprobar conectividad entre servicios
docker-compose exec api-gateway ping -c 3 mongodb

# Verificar puntos de salud de los servicios
curl http://localhost:8080/health
```

## Problemas Comunes

### Fallos en el Inicio del Sistema

**Síntomas**: Uno o más servicios no inician correctamente

**Posibles causas y soluciones**:

1. **Conflicto de puertos**
   - Síntoma: Error "port is already allocated"
   - Solución: Verificar y cambiar puertos en docker-compose.yml o detener servicios que usen esos puertos

2. **Variables de entorno faltantes**
   - Síntoma: Errores relacionados con configuración o valores nulos
   - Solución: Verificar archivo .env y variables requeridas

3. **Problemas de dependencia**
   - Síntoma: Servicios fallan esperando a otros servicios
   - Solución: Verificar el orden de inicio y health checks

4. **Problemas de permisos**
   - Síntoma: Errores de acceso a archivos o volúmenes
   - Solución: Verificar permisos en directorios de volúmenes

### Problemas de Autenticación

**Síntomas**: Errores 401/403, tokens rechazados, imposibilidad de iniciar sesión

**Posibles causas y soluciones**:

1. **JWT Secret incorrecto o no coincidente**
   - Síntoma: Todos los tokens son rechazados con "invalid signature"
   - Solución: Verificar JWT_SECRET en todos los servicios

2. **Token expirado**
   - Síntoma: Error "token expired"
   - Solución: Refrescar token o ajustar tiempos de expiración

3. **Reloj desincronizado**
   - Síntoma: Tokens válidos son rechazados por tiempo
   - Solución: Sincronizar relojes en hosts o contenedores

4. **Base de datos de usuarios inaccesible**
   - Síntoma: No se pueden verificar credenciales
   - Solución: Verificar conexión a MongoDB

### Problemas de Conexión entre Servicios

**Síntomas**: Errores de conexión, timeouts, servicios no responden

**Posibles causas y soluciones**:

1. **Red Docker mal configurada**
   - Síntoma: Servicios no pueden comunicarse entre sí
   - Solución: Verificar configuración de red en docker-compose.yml

2. **Nombres de host incorrectos**
   - Síntoma: Error "could not resolve host"
   - Solución: Verificar nombres de host en variables de entorno

3. **Timeouts en servicios sobrecargados**
   - Síntoma: Errores intermitentes de timeout
   - Solución: Aumentar timeouts o recursos asignados

### Problemas de Rendimiento

**Síntomas**: Alta latencia, tiempos de respuesta lentos, uso elevado de recursos

**Posibles causas y soluciones**:

1. **Recursos insuficientes**
   - Síntoma: CPU/memoria al límite
   - Solución: Aumentar límites de recursos o escalar horizontalmente

2. **Bases de datos sin optimizar**
   - Síntoma: Consultas lentas
   - Solución: Verificar índices, optimizar consultas

3. **Caching insuficiente**
   - Síntoma: Operaciones repetitivas lentas
   - Solución: Implementar o ajustar estrategias de caché

4. **Fugas de memoria**
   - Síntoma: Uso de memoria creciente sin liberación
   - Solución: Revisar código, reiniciar servicios problemáticos

## Problemas por Servicio

### API Gateway

**Problema**: Tasa alta de errores 500

**Diagnóstico**:
```bash
# Verificar logs
docker-compose logs --tail=100 api-gateway

# Comprobar servicios dependientes
curl http://localhost:8081/health  # User Service
curl http://localhost:8082/health  # Document Service
```

**Soluciones comunes**:
- Reiniciar servicios dependientes que estén fallando
- Verificar configuración de rutas y endpoints
- Comprobar límites de rate limiting

### Document Service

**Problema**: Procesamiento de documentos atascado

**Diagnóstico**:
```bash
# Verificar cola de procesamiento
docker-compose exec document-service curl http://localhost:8082/internal/queue/status

# Comprobar conexión con MinIO
docker-compose exec document-service curl -s http://minio:9000/minio/health/live

# Verificar logs específicos
docker-compose logs --tail=100 document-service | grep "processing document"
```

**Soluciones comunes**:
- Reiniciar servicio si la cola está bloqueada
- Verificar espacio en MinIO
- Comprobar conexión con Embedding Service

### Embedding Service

**Problema**: Fallos en generación de embeddings

**Diagnóstico**:
```bash
# Verificar logs
docker-compose logs --tail=100 embedding-service

# Comprobar uso de GPU
docker-compose exec embedding-service nvidia-smi

# Verificar conexión con Qdrant
docker-compose exec embedding-service curl http://qdrant:6333/collections
```

**Soluciones comunes**:
- Verificar disponibilidad de GPU o cambiar a modo CPU
- Reiniciar servicio si hay problemas de memoria
- Verificar disponibilidad y versión del modelo de embeddings

### RAG Agent

**Problema**: Respuestas incorrectas o timeout

**Diagnóstico**:
```bash
# Verificar logs
docker-compose logs --tail=100 rag-agent

# Comprobar conexión con servicios LLM
docker-compose exec rag-agent curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"

# Verificar conexión con Context Service
docker-compose exec rag-agent curl http://context-service:8083/health
```

**Soluciones comunes**:
- Verificar claves de API para servicios externos
- Ajustar timeouts para consultas complejas
- Comprobar límites de tokens y parámetros de generación

### Terminal Services

**Problema**: Sesiones SSH no se establecen

**Diagnóstico**:
```bash
# Verificar logs
docker-compose logs --tail=100 terminal-gateway-service

# Comprobar configuración SSH
docker-compose exec terminal-gateway-service cat /etc/ssh/sshd_config

# Verificar conectividad de red
docker-compose exec terminal-gateway-service telnet <target-host> 22
```

**Soluciones comunes**:
- Verificar credenciales y claves SSH
- Comprobar permisos en archivos de claves
- Verificar reglas de firewall en hosts destino

### Bases de Datos

#### MongoDB

**Problema**: Conexión rechazada o lenta

**Diagnóstico**:
```bash
# Verificar logs
docker-compose logs --tail=100 mongodb

# Comprobar estado
docker-compose exec mongodb mongo --eval "db.serverStatus()"

# Verificar uso de recursos
docker stats mongodb
```

**Soluciones comunes**:
- Verificar credenciales y autenticación
- Comprobar espacio disponible
- Verificar índices para consultas frecuentes

#### Qdrant

**Problema**: Búsqueda vectorial lenta o imprecisa

**Diagnóstico**:
```bash
# Verificar estado
curl http://localhost:6333/collections

# Comprobar configuración
docker-compose exec qdrant cat /qdrant/config/config.yaml

# Verificar logs
docker-compose logs --tail=100 qdrant
```

**Soluciones comunes**:
- Verificar configuración de colecciones
- Ajustar parámetros de búsqueda (effit/exact)
- Comprobar dimensionalidad de vectores

## Herramientas de Diagnóstico

### Logs y Monitoreo

```bash
# Ver logs en tiempo real
docker-compose logs -f <service-name>

# Filtrar logs por palabra clave
docker-compose logs <service-name> | grep "error"

# Verificar uso de recursos
docker stats

# Inspeccionar contenedor
docker inspect <container-id>
```

### Comandos de Depuración Avanzados

```bash
# Entrar en un contenedor
docker-compose exec <service-name> bash

# Capturar tráfico de red
docker-compose exec <service-name> tcpdump -i eth0 -n port 80

# Obtener stack traces (Go)
docker-compose exec <go-service> wget -O - http://localhost:8080/debug/pprof/goroutine?debug=2

# Obtener perfiles de memoria (Python)
docker-compose exec <python-service> python -m memory_profiler main.py
```

### Verificación de Dependencias Externas

```bash
# Verificar conexión a API externa
curl -v https://api.external-service.com/health

# Comprobar DNS
nslookup external-service.com

# Verificar latencia
ping -c 5 external-service.com

# Comprobar ruta de red
traceroute external-service.com
```

## Recuperación de Datos

### Respaldos y Recuperación de MongoDB

```bash
# Crear respaldo manualmente
docker-compose exec mongodb mongodump --out /backup/$(date +%Y-%m-%d)

# Restaurar desde respaldo
docker-compose exec mongodb mongorestore --drop /backup/2023-05-15/

# Verificar integridad
docker-compose exec mongodb mongo --eval "db.runCommand({dbHash:1})"
```

### Recuperación de Vectores en Qdrant

```bash
# Verificar puntos en colección
curl http://localhost:6333/collections/general_knowledge/points/count

# Crear un snapshot
curl -X POST http://localhost:6333/collections/general_knowledge/snapshots

# Restaurar desde snapshot
curl -X PUT http://localhost:6333/collections/general_knowledge/snapshots/restore -d '{"snapshot_path": "/path/to/snapshot"}'

# Reconstruir colección desde documentos originales
# (Usar script de regeneración de embeddings proporcionado en tools/)
```

### Recuperación de Documentos en MinIO

```bash
# Listar buckets
docker-compose exec minio mc ls local

# Verificar archivos en bucket
docker-compose exec minio mc ls local/documents

# Restaurar desde respaldo
docker-compose exec minio mc mirror /backup/minio local/documents
```

## Escalamiento de Incidentes

### Cuándo Escalar

- El problema persiste después de intentar soluciones estándar
- Impacto significativo en usuarios o funcionalidad crítica
- Sospecha de problemas de seguridad o pérdida de datos
- Problemas recurrentes sin causa clara

### Información a Proporcionar

1. **Descripción detallada**: Qué está ocurriendo vs. qué debería ocurrir
2. **Cronología**: Cuándo comenzó y si coincide con algún cambio
3. **Impacto**: Cuántos usuarios/sistemas afectados
4. **Acciones tomadas**: Qué soluciones se han intentado
5. **Logs relevantes**: Extractos de logs con errores
6. **Métricas**: Datos de rendimiento, uso de recursos
7. **Entorno**: Versión del sistema, configuración, etc.

### Proceso de Escalamiento

1. **Nivel 1**: Equipo de operaciones (problemas de infraestructura)
2. **Nivel 2**: Equipo de desarrollo (problemas de aplicación)
3. **Nivel 3**: Especialistas específicos (bases de datos, seguridad, etc.)
4. **Nivel 4**: Gestión de crisis (problemas críticos)

### Contactos de Escalamiento

| Nivel | Tipo de Problema | Contacto | Medio |
|-------|------------------|----------|-------|
| 1 | Infraestructura | Equipo DevOps | Slack #ops-support |
| 2 | Aplicación | Equipo de Desarrollo | Slack #dev-support |
| 3 | Bases de Datos | DBA Team | Email dba@example.com |
| 3 | Seguridad | Security Team | Slack #security-alerts |
| 4 | Crisis | Gestor de Incidentes | Teléfono +XX-XXX-XXXX |

Recuerde: Al escalar un incidente, proporcione toda la información diagnóstica disponible y mantenga actualizados a todos los involucrados sobre el progreso.