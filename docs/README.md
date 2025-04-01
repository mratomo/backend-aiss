# Backend AISS - Documentación Técnica

Esta documentación ofrece información detallada sobre el sistema Backend AISS, su arquitectura, instalación, configuración y uso.

## Índice

1. [Visión General](#visión-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Instalación y Configuración](#instalación-y-configuración)
4. [Referencia de API](#referencia-de-api)
5. [Servicios del Sistema](#servicios-del-sistema)
6. [Integración con Bases de Datos](#integración-con-bases-de-datos)
7. [Integración con Terminal](#integración-con-terminal)
8. [Seguridad](#seguridad)
9. [Ejemplos y Casos de Uso](#ejemplos-y-casos-de-uso)
10. [Desarrollo y Contribución](#desarrollo-y-contribución)
11. [Monitoreo y Mantenimiento](#monitoreo-y-mantenimiento)
12. [Glosario](#glosario)

## Visión General

El Backend AISS es un sistema distribuido para gestión de conocimiento con capacidades RAG (Retrieval Augmented Generation, Generación Aumentada por Recuperación) que implementa el Model Context Protocol (MCP). Está diseñado como una arquitectura de microservicios que proporciona:

- Gestión de usuarios y autenticación
- Procesamiento y almacenamiento de documentos
- Generación y búsqueda de embeddings (representaciones vectoriales)
- Integración con modelos de lenguaje de gran escala (LLMs)
- Gestión de contextos y áreas de conocimiento
- Capacidades avanzadas de consulta y análisis
- Integración con bases de datos externas
- Funcionalidades de terminal interactiva con sugerencias inteligentes

El sistema está implementado en varios lenguajes (Go para servicios core, Python para servicios MCP) y se comunica a través de APIs REST.

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  API Gateway  │────▶│ Servicios Core│────▶│ Servicios MCP │
└───────────────┘     └───────────────┘     └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Frontend    │     │  Bases de Datos│     │ Agente RAG   │
└───────────────┘     └───────────────┘     └───────────────┘
```

## Arquitectura del Sistema

El Backend AISS sigue una arquitectura de microservicios, con componentes específicos para cada funcionalidad principal. Para entender la estructura completa, consulte nuestra [documentación de arquitectura](architecture.md), que incluye:

- Diagrama detallado de arquitectura
- Configuración de red Docker
- Descripción de cada componente
- Flujos de datos principales
- Comunicación entre servicios
- Consideraciones de seguridad y escalabilidad

## Instalación y Configuración

Para instalar y configurar el sistema, siga nuestra [guía de despliegue](deployment/deployment.md), que cubre:

- Requisitos del sistema
- Preparación del entorno
- Instalación mediante Docker Compose
- Verificación de la instalación
- Configuración para producción
- Solución de problemas comunes

## Referencia de API

El sistema expone una API REST completa para interactuar con todas sus funcionalidades. Consulte nuestra [referencia de API](api/api-reference.md) para información detallada sobre:

- Autenticación y autorización
- Endpoints de usuarios
- Gestión de documentos y áreas de conocimiento
- Consultas RAG
- Configuración de LLMs
- Integración con bases de datos externas
- Servicios de terminal
- Configuración de Ollama

## Servicios del Sistema

El Backend AISS está compuesto por múltiples servicios especializados:

- [Servicios Core](services/core-services.md) - Servicios base para autenticación y gestión de documentos
- [Servicios MCP](services/mcp-services.md) - Servicios para gestión de contexto y embeddings
- [Agente RAG](services/rag-agent.md) - Agente para generar respuestas con RAG
- [Servicios de Terminal](services/terminal-services.md) - Servicios para integración con terminal
- [Servicios de BD](services/db-services.md) - Servicios para integración con bases de datos externas

## Integración con Bases de Datos

El sistema ofrece capacidades avanzadas de integración con bases de datos externas. Para más información, consulte nuestra [guía de integración con bases de datos](integration/db-integration.md).

## Integración con Terminal

Para conocer cómo usar las capacidades de terminal, consulte nuestra [guía de integración con terminal](integration/terminal-integration.md).

## Seguridad

La seguridad es una prioridad en el Backend AISS. Nuestra [documentación de seguridad](security/security.md) detalla:

- Modelo de seguridad en profundidad
- Autenticación y autorización
- Seguridad en el API Gateway
- Almacenamiento seguro de datos
- Integración segura con LLMs
- Seguridad en servicios de terminal
- Monitoreo y respuesta a incidentes

## Ejemplos y Casos de Uso

Para ayudarlo a entender mejor el sistema, hemos preparado una serie de ejemplos de uso:

- [Ejemplos Generales](examples/examples.md)
- [Ejemplos de Integración con Bases de Datos](examples/db-examples.md)

## Desarrollo y Contribución

Si desea contribuir al desarrollo del Backend AISS o extender su funcionalidad, consulte:

- [Guía de Desarrollo](development/development-guide.md)
- [Estándares de Código](development/code-standards.md)
- [Pruebas](development/testing.md)
- [Guía de Contribución](contributing.md)

## Monitoreo y Mantenimiento

Para información sobre el monitoreo y mantenimiento del sistema en producción:

- [Monitoreo y Observabilidad](operations/monitoring.md)
- [Solución de Problemas](operations/troubleshooting.md)

## Glosario

Para asegurar una comprensión clara y consistente de la terminología técnica utilizada en este proyecto, consulte nuestro [glosario de términos](glosario.md).