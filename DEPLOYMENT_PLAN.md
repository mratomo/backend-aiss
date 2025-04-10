# Plan de Despliegue y Prueba de Servicios AISS

Este documento define el proceso paso a paso para probar y desplegar cada servicio individualmente, asegurando que cada componente funcione correctamente antes de integrarlos.

## Fase 1: Servicios de Base de Datos

### MongoDB
- [x] Verificar Docker image: `mongo:6.0.5`
  - ✅ Imagen descargada correctamente
  - ✅ Contenedor configurado correctamente
- [x] Comprobar inicialización con `mongodb.js`
  - ✅ Script ejecutado manualmente sin errores
- [x] Verificar conectividad en puerto 27017
  - ✅ Puerto expuesto correctamente
  - ✅ Healthcheck pasando
- [x] Confirmar creación de colecciones e índices
  - ✅ Colecciones users, documents, areas, embeddings, queries, llm_providers creadas
  - ✅ Colecciones para terminal_sessions creadas
  - ✅ Índices creados correctamente
- [x] Validar usuario admin
  - ✅ Usuario admin creado con contraseña por defecto

### Weaviate
- [x] Verificar Docker image: `semitechnologies/weaviate:1.24.3`
  - ✅ Imagen descargada correctamente
  - ✅ Contenedor configurado correctamente
- [x] Comprobar script de inicialización
  - ✅ Creados scripts manualmente tras resolver problemas con el script original
- [x] Verificar creación de esquema (clases GeneralKnowledge y PersonalKnowledge)
  - ✅ Ambas clases creadas con propiedades necesarias
  - ✅ Configuración vectorial correcta (cosine distance)
- [x] Confirmar acceso en puerto 6333 (mapeado a 8080 interno)
  - ✅ Puerto expuesto correctamente
  - ✅ Healthcheck pasando

### Neo4j
- [x] Verificar Docker image: `neo4j:5.9.0`
  - ✅ Imagen descargada correctamente
  - ✅ Contenedor configurado correctamente
- [x] Comprobar inicialización y Graph Data Science
  - ✅ Plugin GDS detectado y funcionando
  - ✅ Inicialización correcta
- [x] Confirmar acceso a la UI (puerto 7474) y Bolt (puerto 7687)
  - ✅ Puertos expuestos correctamente
  - ✅ Healthcheck pasando
- [x] Verificar creación de índices y restricciones necesarias
  - ✅ Índices default creados (LOOKUP)

### MinIO
- [x] Verificar Docker image: `minio/minio:RELEASE.2023-07-21T21-12-44Z`
  - ✅ Imagen descargada correctamente
  - ✅ Contenedor configurado correctamente
- [x] Comprobar inicialización de buckets
  - ✅ Buckets creados manualmente (documents, uploads, temp, personal-documents, shared-documents)
- [x] Verificar acceso a la UI (puerto 9001) y API (puerto 9000)
  - ✅ Puertos expuestos correctamente
  - ✅ Healthcheck pasando
- [x] Confirmar permisos correctos
  - ✅ Permisos configurados correctamente:
    - documents: download
    - uploads: upload
    - temp: public
    - personal-documents: download
    - shared-documents: download

## Fase 2: Servicios Core

### User Service
- [x] Compilar servicio (Go): `docker build -t aiss-user-service ./backend-aiss/core-services/user-service`
  - ✅ Compilación exitosa con Go 1.23
  - ✅ Dockerfile optimizado para minimizar tamaño final
- [x] Ejecutar con variables de entorno correctas (ver docker-compose.yml)
  - ✅ Variables configuradas para MongoDB, JWT y autenticación
  - ✅ Puerto 8081 expuesto correctamente
- [x] Verificar endpoints de autenticación y gestión de usuarios
  - ✅ Endpoints de registro, login y gestión funcionando
  - ✅ Admin inicial creado automáticamente
- [x] Comprobar integración con MongoDB
  - ✅ Conexión a MongoDB establecida exitosamente
  - ✅ Colección users accesible y funcionando
- [x] Confirmar generación y validación correcta de JWT
  - ✅ Tokens generados y validados correctamente
  - ✅ Implementado refresh token para sesiones prolongadas

### Document Service
- [x] Compilar servicio (Go): `docker build -t aiss-document-service ./backend-aiss/core-services/document-service`
  - ✅ Compilación exitosa con Go 1.23
  - ✅ Dockerfile optimizado para un rendimiento eficiente
- [x] Ejecutar con variables de entorno correctas
  - ✅ Variables configuradas para MongoDB, MinIO y otros servicios
  - ✅ Puerto 8082 expuesto correctamente
- [x] Verificar endpoints de gestión de documentos
  - ✅ Endpoints para documentos personales y compartidos funcionando
  - ✅ API de búsqueda funcionando correctamente
- [x] Comprobar integración con MongoDB y MinIO
  - ✅ Conexión a MongoDB establecida con reintentos robustos
  - ✅ Conexión a MinIO con verificación/creación de buckets
- [x] Validar operaciones CRUD con archivos
  - ✅ Subida de archivos funcionando correctamente
  - ✅ Descarga, actualización y eliminación verificadas
  - ✅ Metadatos almacenados correctamente en MongoDB

## Fase 3: Servicios MCP

### Context Service
- ✅Compilar servicio (Python): `docker build -t aiss-context-service ./backend-aiss/mcp-services/context-service`
  - ✅Compilación exitosa
  - ✅ Dependencias MCP instaladas correctamente (mcp=1.6.0, fastmcp=0.4.1)
- ✅ Ejecutar con variables de entorno correctas
- ✅ Verificar API de gestión de contextos
- ✅ Comprobar endpoint MCP SSE
- ✅ Validar integración con MongoDB

### Embedding Service
- ✅ Compilar servicio (Python): `docker build -t aiss-embedding-service ./backend-aiss/mcp-services/embedding-service`
  - ✅ Requiere compilación en un host con GPU NVIDIA
  - ✅ Proceso de compilación largo por modelos de embedding
  - ✅ Usa correctamente base CUDA para soporte GPU
  - ✅  Implementado manejo robusto de errores de GPU con fallback a CPU
  - ✅ Mejorada la integración con MCP Context Service (httpx, verificación de disponibilidad)
  - ✅ Implementado health check detallado para diagnóstico
- ✅ Ejecutar con variables de entorno correctas
- [ ] Verificar soporte para GPU (si aplica)
- [ ] Comprobar carga del modelo Nomic
- [ ] Validar integración con Weaviate
- [ ] Probar generación de embeddings

### RAG Agent
- [x] Compilar servicio (Python): `docker build -t aiss-rag-agent ./backend-aiss/rag-agent`
  - ✅ Después de modificar Dockerfile para eliminar dependencias git+https
  - ✅ Todas las dependencias instaladas correctamente
  - ✅ MCP y FastMCP cargados correctamente
  - ✅ Soporte para GraphRAG con Neo4j incluido
- [ ] Ejecutar con variables de entorno correctas
- [ ] Verificar API para consultas y LLM
- [ ] Comprobar integración con Context Service
- [ ] Validar conexión con Ollama
- [ ] Probar GraphRAG con Neo4j

## Fase 4: Servicios DB

### DB Connection Service
- [ ] Compilar servicio (Python): `docker build -t aiss-db-connection-service ./backend-aiss/db-services/db-connection-service`
- [ ] Ejecutar con variables de entorno correctas
- [ ] Verificar API de gestión de conexiones
- [ ] Comprobar encriptación de credenciales
- [ ] Validar soporte para diferentes tipos de BD

### Schema Discovery Service
- [ ] Compilar servicio (Python): `docker build -t aiss-schema-discovery-service ./backend-aiss/db-services/schema-discovery-service`
- [ ] Ejecutar con variables de entorno correctas
- [ ] Verificar proceso de descubrimiento
- [ ] Comprobar generación de grafos en Neo4j
- [ ] Validar vectorización de esquemas

### Attack Vulnerability Service
- [ ] Compilar servicio (Python): `docker build -t aiss-attack-vulnerability-service ./backend-aiss/attack-vulnerability-service`
- [ ] Ejecutar con variables de entorno correctas
- [ ] Verificar API de análisis de vulnerabilidades
- [ ] Comprobar integración con RAG Agent para LLM

## Fase 5: Servicios Terminal

### Terminal Session Service
- [ ] Compilar servicio (Go): `docker build -t aiss-terminal-session-service ./backend-aiss/terminal-services/terminal-session-service`
- [ ] Ejecutar con variables de entorno correctas
- [ ] Verificar API de gestión de sesiones
- [ ] Comprobar almacenamiento en MongoDB

### Terminal Gateway Service
- [ ] Compilar servicio (Go): `docker build -t aiss-terminal-gateway-service ./backend-aiss/terminal-services/terminal-gateway-service`
- [ ] Ejecutar con variables de entorno correctas
- [ ] Verificar gestión de conexiones SSH
- [ ] Comprobar manejo de websockets
- [ ] Validar integración con Session Service

### Terminal Context Aggregator
- [ ] Compilar servicio (Python): `docker build -t aiss-terminal-context-aggregator ./backend-aiss/terminal-services/terminal-context-aggregator`
- [ ] Ejecutar con variables de entorno correctas
- [ ] Verificar procesamiento de contexto terminal
- [ ] Comprobar integración con Context Service

### Terminal Suggestion Service
- [ ] Compilar servicio (Python): `docker build -t aiss-terminal-suggestion-service ./backend-aiss/terminal-services/terminal-suggestion-service`
- [ ] Ejecutar con variables de entorno correctas
- [ ] Verificar API de sugerencias
- [ ] Comprobar integración con LLM

## Fase 6: API Gateway e Integración

### API Gateway
- [x] Compilar servicio (Go): `docker build -t aiss-api-gateway ./backend-aiss/api-gateway`
  - ✅ Compilación exitosa con Go 1.23
  - ✅ Dockerfile optimizado para entorno de producción 
- [x] Ejecutar con variables de entorno correctas
  - ✅ Variables para todos los servicios correctamente configuradas
  - ✅ Configuración de CORS específica por ambiente
  - ✅ Puerto 8088 expuesto correctamente
- [x] Verificar enrutamiento a todos los servicios
  - ✅ Enrutamiento a User Service funcionando correctamente
  - ✅ Enrutamiento a Document Service funcionando correctamente
  - ✅ Configuración de proxies para el resto de servicios implementada
- [x] Comprobar autenticación y autorización
  - ✅ Middleware de autenticación JWT funcionando
  - ✅ Validación de permisos correcta
- [x] Validar manejo de errores y circuit breaker
  - ✅ Manejo robusto de errores implementado
  - ✅ Circuit breaker configurado para evitar fallos en cascada

### Integración Completa
- [x] Actualizar docker-compose.yml para corregir dependencias y configuraciones
  - ✅ Corregidos números de puerto para todos los servicios
  - ✅ Agregadas variables de entorno faltantes 
  - ✅ Mejorada secuencia de inicio para manejar dependencias
  - ✅ Actualizados healthchecks para mejor detección de fallos
  - ✅ Corregidas rutas de contextos de construcción en todos los servicios
- [x] Desplegar Fase 1 (Servicios de Bases de Datos) con `docker-compose up -d`
  - ✅ MongoDB, Weaviate, Neo4j y MinIO desplegados y funcionando
  - ✅ Scripts de inicialización ejecutados correctamente
- [x] Desplegar Fase 2 (Servicios Core) con `docker-compose up -d`
  - ✅ User Service desplegado y verificado
  - ✅ Document Service desplegado y verificado
  - ✅ API Gateway desplegado y verificado
  - ✅ Resueltos problemas de compatibilidad en tokens JWT
  - ✅ Añadidos campos requeridos (issuer, audience, jti) en tokens
- [x] Verificar comunicación entre servicios básicos 
  - ✅ User Service ↔ MongoDB
  - ✅ Document Service ↔ MongoDB y MinIO
  - ✅ API Gateway ↔ User Service y Document Service
- [x] Mejorar integración entre Context Service y Embedding Service
  - ✅ Implementación de verificación de disponibilidad de servicios
  - ✅ Mejor manejo de errores de comunicación entre servicios
  - ✅ Soporte para httpx optimizado para MCP
  - ✅ Manejo robusto de errores de hardware (GPU fallback)
- [x] Comprobar flujos básicos completos 
  - ✅ Registro de usuario (POST /api/v1/auth/register)
  - ✅ Autenticación y obtención de tokens (POST /api/v1/auth/login)
  - ✅ Validación de tokens
  - ✅ Acceso a recursos protegidos (GET /api/v1/users/{id})
  - ✅ Verificación de restricciones de acceso por roles
- [ ] Desplegar Fase 3 (Servicios MCP) con `docker-compose up -d`
- [ ] Verificar comunicación entre servicios MCP
- [ ] Desplegar Fase 4 (Servicios DB)
- [ ] Validar resiliencia ante fallos

## Comandos Útiles

```bash
# Compilar un servicio específico
docker build -t [nombre-imagen] ./backend-aiss/[ruta-servicio]

# Ejecutar un servicio específico con variables de entorno
docker run -d --name [nombre-contenedor] \
  -e VAR1=valor1 -e VAR2=valor2 \
  -p [puerto-host]:[puerto-contenedor] \
  [nombre-imagen]

# Ver logs de un contenedor
docker logs -f [nombre-contenedor]

# Comprobar estado de los contenedores
docker ps -a

# Detener y eliminar todos los contenedores
docker stop $(docker ps -aq) && docker rm $(docker ps -aq)

# Reiniciar un contenedor específico
docker restart [nombre-contenedor]
```

## Procedimiento de Prueba para cada Servicio

1. Compilar el servicio individualmente con Docker
2. Verificar que no haya errores de compilación
3. Ejecutar el servicio con las variables de entorno necesarias
4. Comprobar logs por posibles errores o advertencias
5. Verificar el endpoint de salud del servicio
6. Probar las API principales con herramientas como curl o Postman
7. Confirmar que los datos se persisten correctamente (si aplica)
8. Documentar cualquier problema o solución aplicada

## Problemas Comunes y Soluciones

### Errores de Conectividad
- Verificar que los nombres de host en variables de entorno coincidan con los nombres de servicio en docker-compose
- Comprobar que los puertos expuestos sean correctos
- Asegurar que las dependencias estén en ejecución primero
- Verificar que los healthchecks estén configurados correctamente en docker-compose.yml
- Revisar los logs de cada servicio para identificar problemas de comunicación entre servicios

### Errores de Autenticación
- Verificar que las credenciales en las variables de entorno sean correctas
- Comprobar que los secretos JWT coincidan entre servicios

### Problemas con GPU
- Asegurar que los drivers NVIDIA estén instalados y funcionando
- Comprobar que docker runtime esté configurado correctamente
- Verificar compatibilidad entre versión de CUDA y modelos
- Utilizar la configuración `fallback_to_cpu=true` para asegurar que los servicios funcionen aún sin GPU
- Comprobar el endpoint /health para diagnosticar problemas de GPU (muestra detalles de hardware)

### Errores en Modelos de ML
- Verificar la descarga correcta de pesos de modelos
- Comprobar espacio en disco y memoria suficientes
- Asegurar que los modelos sean compatibles con la configuración (GPU/CPU)
- Revisar los logs en busca de errores específicos de los modelos

### Problemas con Servicios MCP
- Verificar que las variables MCP_SERVICE_URL estén correctamente configuradas
- Asegurar que el Context Service esté en funcionamiento antes de iniciar servicios dependientes
- Comprobar que httpx esté disponible para servicios que lo utilicen con MCP
- Utilizar herramientas de diagnóstico como el script test_integration.py creado para verificar comunicación
- Consultar los endpoints /health para obtener información detallada del estado de cada servicio

### Problemas de Secuencia de Inicio
- Seguir el orden recomendado en este plan de despliegue (Fase 1 → Fase 6)
- Utilizar docker-compose con `depends_on` y healthchecks para garantizar el orden correcto
- Para pruebas manuales, iniciar servicios de base de datos primero, luego MCP, y finalmente los servicios de aplicación
- Dar tiempo suficiente para la inicialización de cada servicio, especialmente con modelos pesados