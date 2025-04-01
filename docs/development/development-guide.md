# Guía de Desarrollo

Esta guía proporciona información esencial para desarrolladores que desean contribuir o extender el sistema Backend AISS.

## Índice

1. [Configuración del Entorno de Desarrollo](#configuración-del-entorno-de-desarrollo)
2. [Estructura del Proyecto](#estructura-del-proyecto)
3. [Estándares de Código](#estándares-de-código)
4. [Flujo de Trabajo de Desarrollo](#flujo-de-trabajo-de-desarrollo)
5. [Pruebas](#pruebas)
6. [Depuración](#depuración)
7. [Contribuciones](#contribuciones)

## Configuración del Entorno de Desarrollo

### Requisitos Previos

- Docker y Docker Compose (v20.10.0+)
- Go (1.18+) para servicios en Go
- Python (3.10+) para servicios en Python
- Git

### Configuración Inicial

1. Clone el repositorio:
   ```bash
   git clone https://github.com/your-organization/backend-aiss.git
   cd backend-aiss
   ```

2. Cree un archivo `.env` basado en el ejemplo:
   ```bash
   cp .env.example .env
   ```

3. Configure las variables de entorno según sus necesidades locales:
   - Modifique los puertos si es necesario
   - Establezca claves de API para servicios externos (si aplica)
   - Configure credenciales seguras para desarrollo

4. Inicie los servicios en modo desarrollo:
   ```bash
   docker-compose -f docker-compose.dev.yml up
   ```

Este comando iniciará todos los servicios con volúmenes montados para permitir el desarrollo en vivo.

### Entornos de Desarrollo Específicos

#### Para Servicios Go:

```bash
cd api-gateway  # o cualquier otro servicio Go
go mod tidy
go run main.go
```

#### Para Servicios Python:

```bash
cd rag-agent  # o cualquier otro servicio Python
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Estructura del Proyecto

El proyecto sigue una arquitectura de microservicios con la siguiente estructura:

```
backend-aiss/
├── api-gateway/           # API Gateway principal (Go)
├── core-services/         # Servicios Core
│   ├── user-service/      # Servicio de Usuarios (Go)
│   └── document-service/  # Servicio de Documentos (Go)
├── mcp-services/          # Servicios MCP
│   ├── context-service/   # Servicio de Contexto (Python)
│   └── embedding-service/ # Servicio de Embeddings (Python)
├── rag-agent/             # Agente RAG (Python)
├── terminal-services/     # Servicios de Terminal
├── db-services/           # Servicios de BD
└── db/                    # Configuraciones de bases de datos
```

Cada servicio sigue una estructura similar:

- **config/**: Configuración y settings
- **controllers/**: Controladores de API o endpoints
- **models/**: Definiciones de datos
- **services/**: Lógica de negocio
- **repositories/**: Acceso a datos
- **main.go / main.py**: Punto de entrada

## Estándares de Código

### Go

- Seguir [Effective Go](https://golang.org/doc/effective_go) y [Go Code Review Comments](https://github.com/golang/go/wiki/CodeReviewComments)
- Usar `gofmt` para formatear código
- Documentar todas las funciones exportadas
- Implementar manejo de errores adecuado
- Tests unitarios para funciones críticas

### Python

- Seguir [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Usar tipado estático con type hints
- Documentar con docstrings (formato Google)
- Utilizar ambientes virtuales
- Implementar tests unitarios con pytest

### Generales

- Nombres descriptivos para variables y funciones
- Comentarios claros para código complejo
- Evitar código redundante (principio DRY)
- Mantener funciones pequeñas y con responsabilidad única
- Gestionar dependencias de manera explícita

## Flujo de Trabajo de Desarrollo

1. **Crear una rama para cada característica o corrección**:
   ```bash
   git checkout -b feature/nombre-caracteristica
   ```

2. **Realizar commits frecuentes con mensajes descriptivos**:
   ```bash
   git commit -m "Añadir: funcionalidad X para resolver problema Y"
   ```

3. **Mantener la rama actualizada con main**:
   ```bash
   git fetch origin
   git rebase origin/main
   ```

4. **Ejecutar pruebas antes de solicitar revisión**:
   ```bash
   go test ./...  # Para servicios Go
   pytest         # Para servicios Python
   ```

5. **Crear Pull Request con descripción detallada**:
   - Describir qué cambia y por qué
   - Agregar instrucciones de prueba
   - Mencionar problemas relacionados

## Pruebas

### Tipos de Pruebas

1. **Pruebas Unitarias**: Para funciones y componentes individuales
2. **Pruebas de Integración**: Para interacciones entre servicios
3. **Pruebas de API**: Para endpoints RESTful
4. **Pruebas End-to-End**: Para flujos completos

### Ejecución de Pruebas

#### Pruebas Go:

```bash
cd api-gateway
go test -v ./...
```

#### Pruebas Python:

```bash
cd rag-agent
python -m pytest
```

#### Pruebas con Cobertura:

```bash
go test -cover ./...
pytest --cov=.
```

## Depuración

### Servicios Go

1. **Logs**: Utilice el paquete de logs para información detallada
   ```go
   log.Printf("Procesando solicitud: %v", request)
   ```

2. **Depuración con Delve**:
   ```bash
   dlv debug main.go
   ```

### Servicios Python

1. **Logs**: Use el módulo `logging` para información detallada
   ```python
   import logging
   logging.debug("Procesando solicitud: %s", request)
   ```

2. **Depuración con pdb**:
   ```python
   import pdb; pdb.set_trace()
   ```

### Depuración en Docker

Para conectar un depurador a un servicio en Docker:

1. Modificar `docker-compose.dev.yml` para exponer puertos de depuración
2. Usar herramientas como remote-debugging para conectarse

## Contribuciones

### Proceso para Contribuciones

1. Revise los issues abiertos o cree uno nuevo
2. Discuta el cambio propuesto
3. Realice los cambios en una rama separada
4. Asegúrese de que todas las pruebas pasen
5. Envíe un Pull Request
6. Espere revisión y aprobación

### Revisión de Código

- Todo el código debe ser revisado por al menos un desarrollador
- Los comentarios de revisión deben ser abordados antes de la fusión
- Se deben mantener los estándares de código y calidad

### Documentación

- Actualizar la documentación relevante con los cambios
- Incluir ejemplos de uso para nuevas características
- Mantener documentación de API actualizada