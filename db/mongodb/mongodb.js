// db/mongodb/mongodb
// Script de inicialización para MongoDB

db = db.getSiblingDB('mcp_knowledge_system');

// Crear colecciones
db.createCollection('users');
db.createCollection('documents');
db.createCollection('areas');
db.createCollection('embeddings');
db.createCollection('queries');
db.createCollection('llm_providers');

// Crear índices

// Índices para usuarios
db.users.createIndex({ 'username': 1 }, { unique: true });
db.users.createIndex({ 'email': 1 }, { unique: true });

// Índices para documentos
db.documents.createIndex({ 'title': 1 });
db.documents.createIndex({ 'scope': 1 });
db.documents.createIndex({ 'owner_id': 1 });
db.documents.createIndex({ 'area_id': 1 });
db.documents.createIndex({ 'tags': 1 });
db.documents.createIndex({ 'embedding_id': 1 });

// Índices para áreas
db.areas.createIndex({ 'name': 1 }, { unique: true });
db.areas.createIndex({ 'tags': 1 });

// Índices para embeddings
db.embeddings.createIndex({ 'doc_id': 1 });
db.embeddings.createIndex({ 'owner_id': 1 });
db.embeddings.createIndex({ 'embedding_type': 1 });

// Índices para consultas
db.queries.createIndex({ 'user_id': 1 });
db.queries.createIndex({ 'created_at': 1 });

// Índices para proveedores LLM
db.llm_providers.createIndex({ 'name': 1 }, { unique: true });
db.llm_providers.createIndex({ 'default': 1 });

print('Inicialización de la base de datos MongoDB completada');