# Configuración de Bases de Datos

Este directorio contiene la configuración y los scripts de inicialización para las bases de datos utilizadas en el Sistema de Gestión de Conocimiento con Model Context Protocol (MCP).

## Estructura

```
db/
├── minio/           # Almacenamiento de objetos para documentos
│   └── minio        # Script de inicialización de buckets (se usa como referencia)
│
├── mongodb/         # Base de datos para metadatos y usuarios
│   └── mongodb      # Script de inicialización de MongoDB
│
└── qdrant/          # Base de datos vectorial para embeddings
    ├── qdrant       # Configuración de Qdrant
    └── init_collections.sh # Script para crear colecciones e índices
```

## MongoDB

MongoDB se utiliza para almacenar metadatos, información de usuarios, documentos y consultas. El archivo `mongodb` contiene un script que se ejecuta al iniciar el contenedor y crea:

- **Colecciones**:
  - `users`: Información de usuarios y permisos
  - `documents`: Metadatos de documentos
  - `areas`: Áreas de conocimiento
  - `embeddings`: Referencias a embeddings
  - `queries`: Historial de consultas
  - `llm_providers`: Configuración de proveedores LLM

- **Índices**:
  - Índices optimizados para búsquedas por username, email, title, etc.
  - Índices para mejorar el rendimiento en búsquedas de documentos por área o etiquetas

## Qdrant

Qdrant es una base de datos vectorial utilizada para almacenar los embeddings de documentos y texto, permitiendo búsqueda semántica. El archivo `qdrant` contiene la configuración del servidor, mientras que `init_collections.sh` puede utilizarse para inicializar:

- **Colecciones**:
  - `general_knowledge`: Para embeddings de documentos compartidos y áreas de conocimiento
  - `personal_knowledge`: Para embeddings de documentos personales de usuarios

- **Índices**:
  - Índices para búsqueda por propietario, tipo de documento, área, etc.
  - Configurado para búsqueda por similitud coseno

## MinIO

MinIO se utiliza como almacenamiento de objetos compatible con S3 para guardar los documentos cargados. El archivo `minio` sirve como referencia para la inicialización que se realiza a través del servicio `minio-setup` definido en el docker-compose:

- **Buckets**:
  - `shared-documents`: Para documentos compartidos entre todos los usuarios
  - `personal-documents`: Para documentos personales de cada usuario

- **Políticas**:
  - Configuración de políticas de acceso para documentos compartidos y personales

## Despliegue

Estos componentes están configurados para ser desplegados con Docker Compose. El archivo `docker-compose.yml` en el directorio raíz ya incluye la configuración para montar estos archivos como volúmenes en los contenedores correspondientes.

## Volúmenes

Para mantener los datos persistentes, se utilizan volúmenes de Docker:

- `mongodb-data`: Datos de MongoDB
- `qdrant-data`: Datos de Qdrant
- `minio-data`: Documentos almacenados en MinIO

## Consideraciones de Seguridad

- Asegúrate de cambiar las credenciales por defecto en un entorno de producción
- Configura adecuadamente las variables de entorno en el archivo `.env`
- Considera utilizar secretos de Docker para gestionar credenciales sensiblesedenciales sensibles