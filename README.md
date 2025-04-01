# Backend AISS

![Versión](https://img.shields.io/badge/versión-0.1.0-blue.svg)
![Licencia](https://img.shields.io/badge/licencia-MIT-green.svg)

Sistema distribuido para gestión de conocimiento con capacidades RAG (Generación Aumentada por Recuperación) que implementa el Model Context Protocol (MCP).

## Características Principales

- 🔐 **Gestión de usuarios y autenticación**
- 📄 **Procesamiento y almacenamiento de documentos**
- 🔍 **Generación y búsqueda de embeddings**
- 🤖 **Integración con modelos de lenguaje (LLMs)**
- 🧠 **Gestión de contextos y áreas de conocimiento**
- 💾 **Integración con bases de datos externas**
- 💻 **Funcionalidades de terminal interactiva**

## Arquitectura

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  API Gateway  │────▶│ Servicios Core│────▶│ Servicios MCP │
└───────────────┘     └───────────────┘     └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Frontend    │     │ Bases de Datos│     │  Agente RAG   │
└───────────────┘     └───────────────┘     └───────────────┘
```

## Inicio Rápido

### Requisitos

- Docker y Docker Compose (v20.10.0+)
- Git

### Instalación

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/your-organization/backend-aiss.git
   cd backend-aiss
   ```

2. Crear archivo de configuración:
   ```bash
   cp .env.example .env
   ```

3. Iniciar los servicios:
   ```bash
   docker-compose up -d
   ```

4. Verificar que todos los servicios estén funcionando:
   ```bash
   docker-compose ps
   ```

La API estará disponible en http://localhost:8080

## Documentación

Consulte nuestra [documentación completa](docs/README.md) para información detallada sobre:

- [Arquitectura del Sistema](docs/architecture.md)
- [Guía de Instalación y Configuración](docs/deployment/deployment.md)
- [Referencia de API](docs/api/api-reference.md)
- [Servicios del Sistema](docs/services/)
- [Seguridad](docs/security/security.md)
- [Ejemplos de Uso](docs/examples/examples.md)
- [Guía de Desarrollo](docs/development/development-guide.md)
- [Monitoreo y Mantenimiento](docs/operations/monitoring.md)
- [Glosario de Términos](docs/glosario.md)

## Solución de Problemas

Consulte nuestra [guía de solución de problemas](docs/operations/troubleshooting.md) para resolver los problemas más comunes.

## Contribuir

Si desea contribuir al proyecto, por favor consulte nuestra [guía de contribución](docs/contributing.md).

## Licencia

Este proyecto está licenciado bajo la Licencia MIT - vea el archivo [LICENSE](LICENSE) para más detalles.

## Contacto

Para preguntas o soporte, por favor abra un issue en este repositorio.