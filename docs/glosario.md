# Glosario de Términos Técnicos

Este glosario define los términos técnicos utilizados en la documentación del Backend AISS, estableciendo una terminología estándar para mantener la consistencia en todos los documentos.

## Terminología General

| Término en Inglés | Término en Español | Descripción |
|-------------------|-------------------|-------------|
| Backend | Backend | Sistema de procesamiento que opera en segundo plano |
| Microservices | Microservicios | Arquitectura de desarrollo de software donde las aplicaciones se construyen como conjuntos de servicios independientes |
| API | API | Interfaz de Programación de Aplicaciones |
| REST/RESTful | REST/RESTful | Transferencia de Estado Representacional, estilo de arquitectura para APIs |
| Endpoints | Endpoints | Puntos de acceso a la API |
| Gateway | Puerta de enlace | Componente que actúa como intermediario entre el cliente y los servicios |
| Middleware | Middleware | Software intermediario que proporciona funcionalidades comunes a las aplicaciones |
| Database | Base de datos | Sistema de almacenamiento de información estructurada |
| Schema | Esquema | Estructura de organización de datos en una base de datos |
| Query | Consulta | Solicitud de información a una base de datos |
| Implementation | Implementación | Proceso de poner en funcionamiento un sistema o característica |
| Authentication | Autenticación | Proceso de verificar la identidad de un usuario |
| Authorization | Autorización | Proceso de verificar los permisos de un usuario |
| Rate Limiting | Limitación de tasa | Restricción del número de solicitudes que un cliente puede realizar en un período de tiempo |

## Términos Específicos de IA

| Término en Inglés | Término en Español | Descripción |
|-------------------|-------------------|-------------|
| RAG | RAG (Generación Aumentada por Recuperación) | Técnica que combina recuperación de información con generación de texto |
| LLM | LLM (Modelo de Lenguaje de Gran Escala) | Modelo de inteligencia artificial entrenado para comprender y generar lenguaje natural |
| Embedding | Embedding (Representación vectorial) | Representación numérica de texto en un espacio vectorial multidimensional |
| Model | Modelo | Representación computacional de un sistema de IA |
| Context | Contexto | Información relevante utilizada para generar respuestas |
| Prompt | Prompt | Instrucción o solicitud al modelo |
| Vector | Vector | Representación matemática de datos multidimensionales |
| Inference | Inferencia | Proceso de generar respuestas utilizando un modelo entrenado |
| Tokens | Tokens | Unidades básicas de procesamiento de texto para modelos de lenguaje |
| Fine-tuning | Ajuste fino | Proceso de especializar un modelo pre-entrenado para tareas específicas |
| Temperature | Temperatura | Parámetro que controla la aleatoriedad de las respuestas generadas |
| Similarity Search | Búsqueda por similitud | Técnica para encontrar vectores similares en un espacio vectorial |

## Términos de Arquitectura del Sistema

| Término en Inglés | Término en Español | Descripción |
|-------------------|-------------------|-------------|
| Core Services | Servicios Core | Servicios fundamentales del sistema |
| MCP Services | Servicios MCP | Servicios que implementan el Model Context Protocol |
| Distributed Architecture | Arquitectura distribuida | Sistema compuesto por componentes independientes que operan en diferentes ubicaciones |
| Load Balancing | Balanceo de carga | Distribución equitativa de trabajo entre múltiples recursos |
| Scalability | Escalabilidad | Capacidad de un sistema para adaptarse a cargas de trabajo crecientes |
| Availability | Disponibilidad | Tiempo que un sistema está funcionando correctamente |
| Redundancy | Redundancia | Duplicación de componentes críticos para aumentar la fiabilidad |
| Containerization | Contenerización | Técnica de empaquetado de aplicaciones y sus dependencias en contenedores |
| API Gateway | API Gateway | Servicio que actúa como punto de entrada único para todas las API |
| Document Service | Servicio de Documentos | Servicio que gestiona el ciclo de vida de los documentos |
| User Service | Servicio de Usuarios | Servicio que gestiona usuarios y autenticación |
| Context Service | Servicio de Contexto | Servicio que gestiona contextos y áreas de conocimiento |
| Embedding Service | Servicio de Embeddings | Servicio que genera y gestiona representaciones vectoriales |
| Terminal Services | Servicios de Terminal | Servicios para integración con terminal y shell |
| DB Services | Servicios de BD | Servicios para integración con bases de datos externas |

## Términos de Infraestructura

| Término en Inglés | Término en Español | Descripción |
|-------------------|-------------------|-------------|
| Docker | Docker | Plataforma de contenerización de aplicaciones |
| Kubernetes | Kubernetes | Sistema de orquestación de contenedores |
| MongoDB | MongoDB | Base de datos NoSQL orientada a documentos |
| Qdrant | Qdrant | Base de datos vectorial para almacenamiento y búsqueda de embeddings |
| MinIO | MinIO | Almacenamiento de objetos compatible con Amazon S3 |
| Ollama | Ollama | Servicio para ejecución de modelos LLM locales |
| Prometheus | Prometheus | Sistema de monitorización y alerta |
| Grafana | Grafana | Plataforma de análisis y visualización de datos |

## Convenciones de Uso

1. **Primera mención**: Al mencionar un término técnico por primera vez en un documento, incluir su traducción en paréntesis.
   Ejemplo: "RAG (Retrieval Augmented Generation, Generación Aumentada por Recuperación)"

2. **Coherencia**: Usar siempre el mismo término para referirse al mismo concepto en toda la documentación.

3. **Siglas y acrónimos**: Mantener las siglas originales en inglés, pero proporcionar la explicación completa en español en la primera mención.

4. **Términos universales**: Algunos términos técnicos como API, Docker, MongoDB, etc., se mantienen sin traducción por ser universalmente reconocidos.