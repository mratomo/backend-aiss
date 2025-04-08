# GraphRAG: Hybrid RAG with Knowledge Graphs

GraphRAG es una implementación avanzada de Retrieval-Augmented Generation (RAG) que incorpora representaciones en forma de grafo de conocimiento para mejorar la calidad y contexto de las respuestas.

## Arquitectura

El sistema GraphRAG combina lo mejor de RAG tradicional (recuperación por similitud vectorial) con representaciones estructuradas de grafos para mejorar la comprensión del contexto, especialmente en consultas que involucran relaciones entre entidades.

### Componentes

1. **Neo4j**: Base de datos de grafos que almacena la estructura de esquemas de bases de datos como grafos de conocimiento.
2. **LangGraph**: Framework para orquestar flujos complejos de razonamiento sobre grafos.
3. **Servicio de Extracción de Grafos**: Convierte esquemas de bases de datos en representaciones de grafos.
4. **Servicio GraphRAG**: Combina RAG tradicional con exploración de grafos para responder consultas.
5. **Administración de Grafos**: Interfaz para visualizar y editar grafos directamente.

### Flujo de Trabajo

El flujo de trabajo de GraphRAG consta de los siguientes pasos:

1. **Análisis de Consulta**: Se analiza la consulta para determinar su tipo (directa, exploración, análisis).
2. **Recuperación Inicial**: Se realiza una recuperación vectorial tradicional para obtener contexto inicial.
3. **Identificación de Entidades**: Se identifican las entidades (tablas, esquemas) mencionadas en la consulta.
4. **Exploración del Grafo**: Se explora el grafo para obtener relaciones, caminos y estructura.
5. **Generación de Subconsultas**: Se generan subconsultas para explorar aspectos específicos del grafo.
6. **Agregación de Contexto**: Se combina toda la información (vectorial + grafo) en un contexto enriquecido.
7. **Generación de Respuesta**: Se genera una respuesta precisa utilizando el contexto enriquecido.

## Beneficios

- **Comprensión Contextual Mejorada**: Entiende relaciones entre entidades más allá de la similitud vectorial.
- **Explicabilidad**: Puede explicar las relaciones entre entidades como caminos en el grafo.
- **Exploración Dinámica**: Puede explorar el grafo en tiempo real para responder a consultas complejas.
- **Comprensión Estructural**: Capta la estructura de las bases de datos de manera más precisa.
- **Resiliente a Consultas Ambiguas**: Puede manejar consultas que referencian múltiples entidades de manera ambigua.

## Uso de la API

### Consulta Básica

```http
POST /query/graph
Content-Type: application/json

{
  "query": "¿Cómo se relaciona la tabla users con la tabla orders?",
  "user_id": "user123",
  "area_ids": ["schema123"]
}
```

### Consulta Avanzada

```http
POST /query/graph/advanced
Content-Type: application/json

{
  "query": "Muestra todas las tablas relacionadas con customers y explica sus relaciones",
  "user_id": "user123",
  "connection_id": "postgres123",
  "exploration_depth": 3,
  "include_communities": true,
  "include_paths": true
}
```

## Parámetros Avanzados

- **exploration_depth**: Profundidad de exploración del grafo (1-5)
- **include_communities**: Incluir información de comunidades de tablas detectadas
- **include_paths**: Incluir caminos entre entidades relevantes
- **connection_id**: ID de conexión específica de base de datos

## Integración con el Flujo de Trabajo

### 1. Descubrimiento de Esquema

Primero se debe descubrir el esquema de la base de datos:

```http
POST /schema/discover
Content-Type: application/json

{
  "connection_id": "postgres123"
}
```

### 2. Extracción del Grafo

Luego se extrae el grafo de conocimiento:

```http
GET /schema/{connection_id}/graph
```

### 3. Consulta GraphRAG

Finalmente se realizan consultas utilizando GraphRAG:

```http
POST /query/graph
Content-Type: application/json

{
  "query": "¿Cuáles son las tablas principales del sistema y cómo se relacionan?",
  "user_id": "user123",
  "connection_id": "postgres123"
}
```

## Administración de Grafos

### Endpoints para Administración

#### Obtener Información del Grafo

```http
GET /schema/{connection_id}/graph/info
```

Recupera información general sobre el grafo de conocimiento, incluyendo estadísticas sobre nodos, relaciones y comunidades.

#### Exportar Grafo Completo

```http
GET /schema/{connection_id}/graph/export
```

Exporta la representación completa del grafo en formato JSON para visualización externa.

#### Visualizar Grafo

```http
GET /schema/{connection_id}/graph/visualize
```

Devuelve datos formateados específicamente para visualización en D3.js o bibliotecas similares.

#### Editar Relación en el Grafo

```http
PUT /schema/{connection_id}/graph/relationship
Content-Type: application/json

{
  "source_id": "table1",
  "target_id": "table2",
  "relationship_type": "RELATES_TO",
  "properties": {
    "strength": 0.8,
    "description": "Relación corregida manualmente"
  }
}
```

#### Editar Metadatos de Nodo

```http
PUT /schema/{connection_id}/graph/node
Content-Type: application/json

{
  "node_id": "table1",
  "properties": {
    "description": "Descripción actualizada de esta tabla",
    "importance": "high",
    "custom_category": "transactional"
  }
}
```

#### Añadir Nodo al Grafo

```http
POST /schema/{connection_id}/graph/node
Content-Type: application/json

{
  "name": "derived_metrics",
  "type": "view",
  "schema": "reporting",
  "description": "Vista materializada para métricas derivadas",
  "properties": {
    "refresh_frequency": "daily"
  }
}
```

### Interfaz de Administración

Para administrar los grafos, se proporciona una interfaz web integrada en el frontend que permite:

1. **Visualización Interactiva**: Ver el grafo con posibilidad de acercar, alejar y reorganizar nodos.
2. **Edición de Relaciones**: Modificar, añadir o eliminar relaciones entre entidades.
3. **Edición de Metadatos**: Actualizar descripciones, categorías o propiedades de los nodos.
4. **Corrección de Ontología**: Reorganizar comunidades o categorías de entidades.
5. **Validación de Estructura**: Verificar la integridad y coherencia del grafo.

#### Acceso a Neo4j Browser

Además de la interfaz integrada, los administradores pueden acceder directamente a Neo4j Browser para operaciones avanzadas:

- **URL**: http://<host>:7474
- **Credenciales**: Configuradas en las variables de entorno (NEO4J_USERNAME, NEO4J_PASSWORD)

Esta interfaz proporciona capacidades avanzadas de:
- Exploración visual del grafo completo
- Ejecución de consultas Cypher personalizadas
- Exportación e importación avanzada
- Análisis con algoritmos de Graph Data Science

## Ejemplos de Consultas

### Comprensión de Estructura

```
"¿Cuáles son las tablas principales del sistema?"
```

### Exploración de Relaciones

```
"¿Cómo se relaciona la tabla orders con la tabla customers?"
```

### Análisis de Esquema

```
"¿Qué tablas contienen información de usuarios y cómo están conectadas?"
```

### Búsqueda de Caminos

```
"¿Hay alguna relación entre la tabla products y la tabla shipments?"
```

### Análisis de Comunidades

```
"¿Qué grupos de tablas relacionadas existen en el sistema?"
```

## Notas Técnicas

- El servicio requiere Neo4j con los plugins APOC y Graph Data Science.
- Se recomienda explorar el grafo visualmente utilizando Neo4j Browser (puerto 7474).
- Las consultas GraphRAG son más lentas que las consultas RAG tradicionales, pero proporcionan mayor precisión y contexto para consultas sobre relaciones entre entidades.