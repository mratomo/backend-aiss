// db/mongodb/mongodb.js
// Script de inicialización para MongoDB

db = db.getSiblingDB('mcp_knowledge_system');

// También inicializar la base de datos para las sesiones de terminal
let terminalDb = db.getSiblingDB('terminal_sessions');

// Crear colecciones
db.createCollection('users');
db.createCollection('documents');
db.createCollection('areas');
db.createCollection('embeddings');
db.createCollection('queries');
db.createCollection('llm_providers');
db.createCollection('llm_settings');

// Crear índices para usuarios
db.users.createIndex({ 'username': 1 }, { unique: true });
db.users.createIndex({ 'email': 1 }, { unique: true });
db.users.createIndex({ 'role': 1 });
db.users.createIndex({ 'created_at': 1 });

// Índices para documentos
db.documents.createIndex({ 'title': 1 });
db.documents.createIndex({ 'scope': 1 });
db.documents.createIndex({ 'owner_id': 1 });
db.documents.createIndex({ 'area_id': 1 });
db.documents.createIndex({ 'tags': 1 });
db.documents.createIndex({ 'embedding_id': 1 });
db.documents.createIndex({ 'created_at': 1 });
db.documents.createIndex({ 'updated_at': 1 });

// Índices para áreas
db.areas.createIndex({ 'name': 1 }, { unique: true });
db.areas.createIndex({ 'tags': 1 });
db.areas.createIndex({ 'active': 1 });
db.areas.createIndex({ 'mcp_context_id': 1 });

// Índices para embeddings
db.embeddings.createIndex({ 'doc_id': 1 });
db.embeddings.createIndex({ 'owner_id': 1 });
db.embeddings.createIndex({ 'embedding_type': 1 });
db.embeddings.createIndex({ 'area_id': 1 });
db.embeddings.createIndex({ 'vector_id': 1 });
db.embeddings.createIndex({ 'created_at': 1 });

// Índices para consultas
db.queries.createIndex({ 'user_id': 1 });
db.queries.createIndex({ 'created_at': 1 });
db.queries.createIndex({ 'query_id': 1 }, { unique: true });
db.queries.createIndex({ 'llm_provider_id': 1 });

// Índices para proveedores LLM
db.llm_providers.createIndex({ 'name': 1 }, { unique: true });
db.llm_providers.createIndex({ 'default': 1 });
db.llm_providers.createIndex({ 'type': 1 });

// Crear admin por defecto si no existe
const adminExists = db.users.findOne({ username: 'admin' });
if (!adminExists) {
    db.users.insertOne({
        username: 'admin',
        email: 'admin@system.local',
        password_hash: '$2a$10$XEsvpVv.aU.ZGKVmJ/Y7peoMHFU5Fv5RnWR3hJPGmVyDVjqMUYjwe', // Valor por defecto: admin123
        role: 'admin',
        active: true,
        created_at: new Date(),
        updated_at: new Date()
    });
    print('Usuario admin creado con contraseña predeterminada');
}

// Crear documento de configuración de LLM si no existe
const llmSettingsExists = db.llm_settings.findOne({});
if (!llmSettingsExists) {
    db.llm_settings.insertOne({
        default_system_prompt: "Eres un asistente de inteligencia artificial especializado en responder preguntas basadas en la información proporcionada. Utiliza SOLO la información en el contexto para responder. Si la información no está en el contexto, indica que no tienes esa información. Proporciona respuestas detalladas y bien estructuradas.",
        last_updated: new Date(),
        updated_by: 'system_init'
    });
    print('Configuración LLM inicial creada');
}

// Crear colecciones para terminal_sessions
terminalDb.createCollection('sessions');
terminalDb.createCollection('commands');
terminalDb.createCollection('bookmarks');
terminalDb.createCollection('contexts');

// Índices para sessions
terminalDb.sessions.createIndex({ 'session_id': 1 }, { unique: true });
terminalDb.sessions.createIndex({ 'user_id': 1 });
terminalDb.sessions.createIndex({ 'status': 1 });
terminalDb.sessions.createIndex({ 'created_at': 1 });
terminalDb.sessions.createIndex({ 'last_active': 1 });
terminalDb.sessions.createIndex({ 'target_info.hostname': 1 });
terminalDb.sessions.createIndex({ 'target_info.os_detected': 1 });

// Índices para commands
terminalDb.commands.createIndex({ 'command_id': 1 }, { unique: true });
terminalDb.commands.createIndex({ 'session_id': 1 });
terminalDb.commands.createIndex({ 'user_id': 1 });
terminalDb.commands.createIndex({ 'timestamp': 1 });
terminalDb.commands.createIndex({ 'exit_code': 1 });
terminalDb.commands.createIndex({ 'is_suggested': 1 });
terminalDb.commands.createIndex({ 'tagged': 1 });
terminalDb.commands.createIndex({ 'error_detected': 1 });
terminalDb.commands.createIndex({ 'command': 'text' });

// Índices para bookmarks
terminalDb.bookmarks.createIndex({ 'bookmark_id': 1 }, { unique: true });
terminalDb.bookmarks.createIndex({ 'command_id': 1 });
terminalDb.bookmarks.createIndex({ 'session_id': 1 });
terminalDb.bookmarks.createIndex({ 'user_id': 1 });
terminalDb.bookmarks.createIndex({ 'created_at': 1 });

// Índices para contexts
terminalDb.contexts.createIndex({ 'session_id': 1 }, { unique: true });
terminalDb.contexts.createIndex({ 'user_id': 1 });
terminalDb.contexts.createIndex({ 'last_updated': 1 });

print('Inicialización de la base de datos MongoDB completada');