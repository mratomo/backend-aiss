# Backend AISS - Documentación Técnica

## Índice

1. [Visión General](#visión-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Instalación y Configuración](#instalación-y-configuración)
4. [API Reference](#api-reference)
5. [Servicios del Sistema](#servicios-del-sistema)
6. [Integración con Bases de Datos](#integración-con-bases-de-datos)
7. [Integración con Terminal](#integración-con-terminal)
8. [Guías de Desarrollo](#guías-de-desarrollo)
9. [Seguridad](#seguridad)
10. [Monitoreo y Mantenimiento](#monitoreo-y-mantenimiento)

## Visión General

El Backend AISS es un sistema distribuido para gestión de conocimiento con capacidades RAG (Retrieval Augmented Generation) que implementa el Model Context Protocol (MCP). Está diseñado como una arquitectura de microservicios que proporciona:

- Gestión de usuarios y autenticación
- Procesamiento y almacenamiento de documentos
- Generación y búsqueda de embeddings
- Integración con modelos de lenguaje de gran escala (LLMs)
- Gestión de contextos y áreas de conocimiento
- Capacidades avanzadas de consulta y análisis

El sistema está implementado en varios lenguajes (Go para servicios core, Python para servicios MCP) y se comunica a través de APIs REST.

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  API Gateway  │────▶│ Core Services │────▶│ MCP Services  │
└───────────────┘     └───────────────┘     └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Frontend    │     │  Databases    │     │   RAG Agent   │
└───────────────┘     └───────────────┘     └───────────────┘
```

## Arquitectura del Sistema

La documentación detallada de la arquitectura del sistema se encuentra en [architecture.md](architecture.md).

## Instalación y Configuración

Las instrucciones completas para la instalación y configuración del sistema se encuentran en [deployment/deployment.md](deployment/deployment.md).

## API Reference

La documentación completa de la API se encuentra en [api/api-reference.md](api/api-reference.md).

## Servicios del Sistema

- [Core Services](services/core-services.md)
- [MCP Services](services/mcp-services.md)
- [RAG Agent](services/rag-agent.md)
- [Terminal Services](services/terminal-services.md)
- [DB Services](services/db-services.md)

## Integración con Bases de Datos

La documentación sobre integración con bases de datos se encuentra en [integration/db-integration.md](integration/db-integration.md).

## Integración con Terminal

La documentación sobre integración con terminal se encuentra en [integration/terminal-integration.md](integration/terminal-integration.md).

## Guías de Desarrollo

- [Guía de Desarrollo](development/development-guide.md)
- [Estándares de Código](development/code-standards.md)
- [Testing](development/testing.md)

## Seguridad

La documentación de seguridad se encuentra en [security/security.md](security/security.md).

## Monitoreo y Mantenimiento

La documentación sobre monitoreo y mantenimiento se encuentra en [operations/monitoring.md](operations/monitoring.md).