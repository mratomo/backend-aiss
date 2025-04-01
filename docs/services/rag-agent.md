# Agente RAG

## Visión General

El Agente RAG (Generación Aumentada por Recuperación) es un componente clave del sistema que implementa capacidades de generación de respuestas aumentadas con recuperación de contexto. Este servicio coordina la recuperación de información relevante desde la base de conocimiento y utiliza Modelos de Lenguaje de Gran Escala (LLM) para generar respuestas precisas, contextuales y basadas en evidencia.

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        Servicio Agente RAG                      │
│                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐     │
│  │                │  │                │  │                │     │
│  │ Servicio de    │  │  Servicio de   │  │  Servicio LLM  │     │
│  │ Consultas      │  │  Recuperación  │  │                │     │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘     │
│          │                   │                   │              │
│          └───────────┬───────┘                   │              │
│                      │                           │              │
│  ┌────────────────┐  │                   ┌───────┴────────┐     │
│  │                │  │                   │                │     │
│  │   Servicio de  │◀─┘                   │  Conector de   │     │
│  │   Contexto     │                      │  Proveedor LLM │     │
│  │                │                      │                │     │
│  └────────────────┘                      └────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Componentes Principales

### Servicio de Consultas

Gestiona las consultas de los usuarios y coordina el proceso de generación de respuestas.

**Responsabilidades:**
- Procesar y analizar las consultas de los usuarios
- Coordinar el flujo de recuperación y generación
- Gestionar historial de conversaciones y contexto
- Aplicar filtros y restricciones a las consultas
- Implementar estrategias de reintento y recuperación de errores

### Servicio de Recuperación

Recupera información relevante desde la base de conocimiento para aumentar la respuesta.

**Responsabilidades:**
- Comunicación con Servicio de Contexto para búsqueda de información
- Selección de estrategia de búsqueda óptima según tipo de consulta
- Filtrado y reordenamiento de resultados por relevancia
- Combinación de resultados de diferentes fuentes
- Optimización del contexto recuperado para maximizar relevancia

### Servicio LLM

Gestiona la comunicación con diferentes proveedores de modelos de lenguaje.

**Responsabilidades:**
- Abstracción de diferentes proveedores de LLM (OpenAI, Anthropic, Ollama)
- Gestión de plantillas de prompts para generación de respuestas
- Control de parámetros de generación (temperatura, tokens, etc.)
- Monitoreo de uso y costes de LLM
- Implementación de mecanismos de fallback entre proveedores

### Conector de Proveedor LLM

Implementa la conexión con proveedores específicos de LLM.

**Responsabilidades:**
- Integración con APIs específicas de cada proveedor
- Manejo de errores específicos de cada proveedor
- Gestión de autenticación y claves API
- Implementación de límites de tasa y reintento
- Transformación de respuestas a formato unificado

## Flujo de Procesamiento

```
┌────────────┐      ┌───────────────┐      ┌───────────────┐
│            │      │               │      │               │
│   Usuario  │─────▶│ Servicio de   │─────▶│  Servicio de  │
│            │      │ Consultas     │      │  Recuperación │
└────────────┘      └───────────────┘      └───────┬───────┘
                           │                       │
                           │                       │
                           │                       │
                           │                       ▼
┌────────────┐      ┌───────────────┐      ┌───────────────┐
│            │      │               │      │               │
│  Respuesta │◀─────│ Servicio LLM  │◀─────│  Servicio de  │
│            │      │               │      │  Contexto     │
└────────────┘      └───────────────┘      └───────────────┘
```

### 1. Recepción y Análisis de Consulta

1. El usuario envía una consulta al sistema
2. El Servicio de Consultas recibe la consulta y analiza:
   - Tipo de consulta (informativa, acción, etc.)
   - Entidades y conceptos clave
   - Contexto de conversación previo
   - Restricciones (área de conocimiento, idioma, etc.)

### 2. Recuperación de Contexto

1. El Servicio de Recuperación formula una estrategia de búsqueda basada en el análisis
2. Comunica con Servicio de Contexto/Servicio de Embeddings para:
   - Búsqueda semántica por similitud vector
   - Búsqueda por palabras clave cuando es relevante
   - Filtrado por área de conocimiento y metadatos
3. Procesa los resultados:
   - Ordena por relevancia
   - Elimina duplicados y redundancias
   - Selecciona fragmentos más informativos
   - Optimiza el contenido para el LLM (trunca, resume)

### 3. Generación de Respuesta

1. El Servicio LLM prepara el prompt con:
   - Consulta original
   - Contexto recuperado
   - Instrucciones específicas para el LLM
   - Historial de conversación relevante
2. Selecciona el proveedor LLM adecuado según:
   - Configuración del usuario
   - Tipo de consulta
   - Disponibilidad y costo
3. Envía la petición al proveedor LLM
4. Recibe y procesa la respuesta:
   - Validación de formato y contenido
   - Extracción de metadatos (fuentes citadas)
   - Ajustes de formato final

### 4. Entrega y Retroalimentación

1. La respuesta se devuelve al usuario con:
   - Texto generado por el LLM
   - Fuentes y referencias a documentos originales
   - Nivel de confianza de la respuesta
2. Se registra la interacción para:
   - Análisis de rendimiento
   - Mejora continua
   - Historial de conversaciones

## Modelos y Proveedores LLM Soportados

### OpenAI

- **Modelos**:
  - GPT-4 (recomendado para tareas complejas)
  - GPT-3.5 Turbo (equilibrio rendimiento/costo)
- **Características**:
  - Alto rendimiento en generación de texto
  - Excelente comprensión contextual
  - Soporte para inserción de fuentes
  - Limitación de 8K-32K tokens según el modelo

### Anthropic

- **Modelos**:
  - Claude 2 (alta capacidad de contexto)
  - Claude Instant (más rápido, menor costo)
- **Características**:
  - Ventaja en seguimiento de instrucciones
  - Capacidad de contexto extendida (100K tokens)
  - Razonamiento orientado a seguridad
  - Generación de respuestas más concisas

### Ollama (Local)

- **Modelos**:
  - Llama 2 (7B, 13B, 70B)
  - Mistral (7B)
- **Características**:
  - Despliegue completamente local
  - Sin costos de API ni dependencias externas
  - Menor latencia por proximidad
  - Privacidad de datos garantizada
  - Potencialmente menor rendimiento según hardware

## Prompt Engineering

El RAG Agent implementa técnicas avanzadas de prompt engineering para optimizar las respuestas:

### Estructura de Prompts

```
[INSTRUCTIONS]
Eres un asistente de IA especializado en {domain}. 
Responde a la consulta basándote exclusivamente en el contexto proporcionado.
Si la información no está en el contexto, indica que no tienes suficiente información.
Cita las fuentes específicas usando [Documento X] para cada afirmación.

[CONTEXT]
{context_chunks}

[QUERY]
{user_query}

[CHAT HISTORY]
{relevant_history}
```

### Estrategias Implementadas

1. **Chain-of-Thought**: Induce razonamiento paso a paso para consultas complejas
2. **Few-Shot Learning**: Incluye ejemplos del formato esperado para respuestas
3. **Retrieval Re-ranking**: Refina la búsqueda con retroalimentación del LLM
4. **System Guidance**: Instrucciones específicas según tipo de consulta
5. **Citations Formatting**: Formato estandarizado para citar fuentes

## Integración con el Sistema

### API Endpoints

#### Consultas RAG

- **POST /api/v1/rag/query**: Realizar una consulta RAG
  ```json
  {
    "query": "¿Cuáles son los pasos para configurar el servicio X?",
    "area_id": "area123",
    "conversation_id": "conv456",
    "llm_settings": {
      "provider": "openai",
      "model": "gpt-4",
      "temperature": 0.3,
      "max_tokens": 1000
    }
  }
  ```

- **GET /api/v1/rag/history**: Obtener historial de consultas
- **GET /api/v1/rag/conversations**: Obtener conversaciones del usuario
- **POST /api/v1/rag/feedback**: Enviar feedback sobre una respuesta

#### Ajustes LLM

- **GET /api/v1/llm/providers**: Obtener proveedores disponibles
- **GET /api/v1/llm/settings**: Obtener configuración del usuario
- **PUT /api/v1/llm/settings**: Actualizar configuración del usuario

## Configuración

El RAG Agent se configura mediante variables de entorno o archivo `.env`:

```
# Configuración del servidor
PORT=8085
ENVIRONMENT=production
LOG_LEVEL=info

# Configuración de servicios
CONTEXT_SERVICE_URL=http://context-service:8083
EMBEDDING_SERVICE_URL=http://embedding-service:8084

# Configuración de LLM Providers
DEFAULT_LLM_PROVIDER=openai
DEFAULT_LLM_MODEL=gpt-4
DEFAULT_TEMPERATURE=0.7
DEFAULT_MAX_TOKENS=1000

# API Keys (opcionales, pueden configurarse por usuario)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...

# Configuración de Ollama (opcional)
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama2:13b

# Configuración RAG
MAX_CONTEXT_CHUNKS=10
MAX_RELEVANT_HISTORY=5
SIMILARITY_THRESHOLD=0.75
```

## Estrategias de Recuperación

El servicio implementa varias estrategias de recuperación que pueden combinarse:

### Búsqueda por Similitud Semántica

Utiliza embeddings (representaciones vectoriales) para encontrar contenido semánticamente similar a la consulta:

```python
# Pseudocódigo
def semantic_search(query, area_id=None, limit=10):
    # Generar embedding para la consulta
    query_embedding = embedding_service.generate_embedding(query)
    
    # Buscar en Qdrant
    search_params = {
        "vector": query_embedding,
        "limit": limit,
        "filter": {"area_id": area_id} if area_id else None
    }
    results = qdrant_client.search(**search_params)
    
    return results
```

### Reordenamiento con Retroalimentación del LLM

Mejora los resultados pidiendo al LLM que los reordene por relevancia:

```python
# Pseudocódigo
def rerank_with_llm(query, initial_results, limit=5):
    # Preparar prompt para reranking
    prompt = f"""
    [TASK]
    Reordenar los siguientes fragmentos por relevancia para la consulta.
    
    [QUERY]
    {query}
    
    [FRAGMENTS]
    {format_fragments(initial_results)}
    
    [OUTPUT]
    Proporciona una lista de índices ordenados por relevancia, del más al menos relevante.
    """
    
    # Obtener reranking del LLM
    response = llm_service.generate(prompt, temperature=0.3)
    ranked_indices = parse_ranking(response)
    
    # Reordenar resultados
    return [initial_results[i] for i in ranked_indices[:limit]]
```

### Búsqueda Híbrida

Combina búsqueda semántica con búsqueda por palabras clave para mejorar la precisión:

```python
# Pseudocódigo
def hybrid_search(query, area_id=None, limit=10):
    # Obtener resultados semánticos
    semantic_results = semantic_search(query, area_id, limit)
    
    # Extraer keywords importantes
    keywords = extract_keywords(query)
    
    # Búsqueda por keywords
    keyword_results = keyword_search(keywords, area_id, limit)
    
    # Combinar y reordenar resultados
    combined_results = combine_results(semantic_results, keyword_results)
    
    return combined_results[:limit]
```

## Monitoreo y Métricas

### Indicadores Clave (KPIs)

1. **Latencia**:
   - Tiempo total de respuesta
   - Tiempo de recuperación
   - Tiempo de generación LLM

2. **Calidad**:
   - Puntuación de relevancia
   - Ratio de citas correctas
   - Tasa de respuestas "no sé"

3. **Utilización**:
   - Llamadas a LLM por hora
   - Tokens procesados
   - Consultas por usuario/área

### Dashboard de Métricas

El servicio expone métricas en formato Prometheus:

```
# HELP rag_queries_total Total number of RAG queries processed
# TYPE rag_queries_total counter
rag_queries_total{provider="openai",model="gpt-4"} 1250
rag_queries_total{provider="anthropic",model="claude-2"} 356

# HELP rag_response_time_seconds Response time for RAG queries
# TYPE rag_response_time_seconds histogram
rag_response_time_seconds_bucket{le="0.5"} 145
rag_response_time_seconds_bucket{le="1.0"} 450
rag_response_time_seconds_bucket{le="2.0"} 892
```

## Limitaciones Actuales

1. **Contexto Fijo**: La cantidad de fragmentos recuperados está limitada
2. **Hallucinations**: Posibles respuestas no basadas en contexto en casos complejos
3. **Consistencia**: Variabilidad en respuestas según proveedor LLM
4. **Multi-idioma**: Soporte limitado para idiomas distintos al inglés y español
5. **Razonamiento Numérico**: Limitación en cálculos y análisis estadísticos complejos

## Roadmap

### Próximas Mejoras

1. **Multi-step Retrieval**: Recuperación en múltiples pasos para consultas complejas
2. **Personalización**: Ajustes por usuario basados en feedback y preferencias
3. **Retrieval Adaptativo**: Selección dinámica de estrategia según tipo de consulta
4. **Verificación de Respuestas**: Validación automática de precisión factual
5. **Soporte Multimodal**: Integración con análisis de imágenes y diagramas