# Ollama MCP Server

## Visión General

El Ollama MCP Server es un componente especializado del sistema AISS que proporciona una implementación del Machine Conversation Protocol (MCP) para trabajar con modelos de lenguaje locales a través de Ollama. Este servicio permite integrar modelos de lenguaje locales en la arquitectura general del sistema, ofreciendo una alternativa a las APIs externas de LLM.

## Características Principales

- **Compatibilidad MCP**: Implementa el protocolo MCP para interactuar con el sistema general
- **Integración con Ollama**: Se conecta con el servicio Ollama para acceder a modelos locales
- **Operación Independiente**: Funciona como un servicio autónomo dentro de la arquitectura
- **Configuración Flexible**: Permite configurar diferentes modelos de Ollama según las necesidades

## Configuración

El Ollama MCP Server se configura a través de variables de entorno:

```
# Configuración básica
PORT=8095
ENVIRONMENT=production

# Configuración de Ollama
OLLAMA_API_BASE=http://ollama:11434
OLLAMA_DEFAULT_MODEL=llama3

# Configuración del servidor
RUN_STANDALONE_MCP_SERVER=true
DISABLE_MAIN_APP=true
```

## Integración con el Sistema

El Ollama MCP Server se integra con el resto del sistema AISS principalmente a través del RAG Agent, que puede enrutar solicitudes de generación de texto tanto a servicios externos (OpenAI, Anthropic) como a este servidor MCP local.

```
┌────────────────┐
│                │
│    RAG Agent   │
│                │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Ollama MCP     │
│ Server         │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│                │
│    Ollama      │
│                │
└────────────────┘
```

## Modelos Compatibles

El servicio es compatible con todos los modelos disponibles en Ollama, incluyendo:

- llama3
- llama2
- mistral
- mixtral
- phi
- y otros modelos que pueda ejecutar Ollama

## Ventajas

- **Privacidad**: Los datos no salen del entorno local
- **Control de Costos**: No requiere pago por uso como las APIs externas
- **Personalización**: Permite utilizar modelos ajustados para casos específicos
- **Operación sin Conexión**: Funciona sin necesidad de conexión a Internet

## Limitaciones

- **Recursos Locales**: Requiere hardware adecuado (especialmente GPU para modelos grandes)
- **Capacidades Reducidas**: Los modelos locales pueden tener menor rendimiento que los servicios en la nube
- **Mayor Latencia**: Tiempos de respuesta más largos para modelos grandes en hardware limitado

## Monitorización

El servicio expone endpoints para monitorización y diagnóstico:

- **GET /health**: Verifica el estado del servicio y su conexión con Ollama
- **GET /metrics**: Proporciona métricas en formato Prometheus

## Uso de Recursos

El uso de recursos varía según el modelo configurado:

| Modelo    | RAM mínima | GPU VRAM | CPU Cores |
|-----------|------------|----------|-----------|
| llama3    | 8GB        | 8GB      | 4+        |
| mixtral   | 16GB       | 24GB     | 8+        |
| phi-2     | 4GB        | 4GB      | 2+        |

## Seguridad

El servicio implementa las siguientes medidas de seguridad:

- No expone directamente puertos al exterior
- Validación de entrada para prevenir inyecciones
- Sin almacenamiento persistente de datos sensibles
- Configuración de límites para evitar abuso de recursos