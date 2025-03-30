# Ejemplos de Uso del Sistema de Gestión de Conocimiento con MCP

Este documento proporciona ejemplos prácticos para utilizar el Sistema de Gestión de Conocimiento con Model Context Protocol (MCP). Los ejemplos incluyen tanto comandos curl como snippets de código en diferentes lenguajes de programación.

## Índice

1. [Autenticación](#1-autenticación)
2. [Gestión de Áreas de Conocimiento](#2-gestión-de-áreas-de-conocimiento)
3. [Gestión de Documentos](#3-gestión-de-documentos)
4. [Consultas RAG](#4-consultas-rag)
5. [Gestión de Proveedores LLM](#5-gestión-de-proveedores-llm)
6. [Flujo de Trabajo Completo](#6-flujo-de-trabajo-completo)

## 1. Autenticación

### Registro de Usuario

**curl:**
```bash
curl -X POST http://localhost:8080/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "usuario",
    "email": "usuario@ejemplo.com",
    "password": "contraseña123"
  }'
```

**Python:**
```python
import requests

url = "http://localhost:8080/auth/register"
payload = {
    "username": "usuario",
    "email": "usuario@ejemplo.com",
    "password": "contraseña123"
}
response = requests.post(url, json=payload)
print(response.json())

# Guardar token para uso posterior
token = response.json()["access_token"]
```

### Inicio de Sesión

**curl:**
```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "usuario",
    "password": "contraseña123"
  }'
```

**JavaScript:**
```javascript
async function login() {
  const response = await fetch('http://localhost:8080/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      username: 'usuario',
      password: 'contraseña123'
    })
  });
  
  const data = await response.json();
  
  // Guardar token en localStorage
  localStorage.setItem('token', data.access_token);
  return data;
}
```

## 2. Gestión de Áreas de Conocimiento

### Crear Área de Conocimiento (Admin)

**curl:**
```bash
curl -X POST http://localhost:8080/knowledge/admin/areas \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Inteligencia Artificial",
    "description": "Área dedicada a la IA y sus aplicaciones",
    "icon": "brain",
    "color": "#3498DB",
    "tags": ["IA", "Machine Learning", "Deep Learning"]
  }'
```

**Go:**
```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "net/http"
)

func createKnowledgeArea(token string) {
    url := "http://localhost:8080/knowledge/admin/areas"
    
    // Crear estructura de datos
    payload := map[string]interface{}{
        "name": "Inteligencia Artificial",
        "description": "Área dedicada a la IA y sus aplicaciones",
        "icon": "brain",
        "color": "#3498DB",
        "tags": []string{"IA", "Machine Learning", "Deep Learning"},
    }
    
    // Convertir a JSON
    jsonData, _ := json.Marshal(payload)
    
    // Crear solicitud
    req, _ := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+token)
    
    // Enviar solicitud
    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        fmt.Println("Error:", err)
        return
    }
    defer resp.Body.Close()
    
    // Procesar respuesta
    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)
    fmt.Println("Área creada:", result)
}
```

### Listar Áreas de Conocimiento

**curl:**
```bash
curl -X GET http://localhost:8080/knowledge/areas \
  -H "Authorization: Bearer TOKEN_AQUI"
```

**Python:**
```python
import requests

def list_knowledge_areas(token):
    url = "http://localhost:8080/knowledge/areas"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    response = requests.get(url, headers=headers)
    return response.json()

# Uso
token = "tu_token_aqui"
areas = list_knowledge_areas(token)
for area in areas:
    print(f"{area['name']} - {area['description']}")
```

## 3. Gestión de Documentos

### Subir Documento Personal

**curl:**
```bash
curl -X POST http://localhost:8080/documents/personal \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -F "file=@/ruta/al/documento.pdf" \
  -F "title=Informe de Proyecto" \
  -F "description=Informe final del proyecto de investigación" \
  -F "tags=informe,proyecto,investigación"
```

**JavaScript:**
```javascript
async function uploadPersonalDocument(token, file) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', 'Informe de Proyecto');
  formData.append('description', 'Informe final del proyecto de investigación');
  formData.append('tags', 'informe,proyecto,investigación');
  
  const response = await fetch('http://localhost:8080/documents/personal', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData
  });
  
  return await response.json();
}

// Uso (en un formulario HTML)
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('fileInput');
  const token = localStorage.getItem('token');
  
  if (fileInput.files.length > 0) {
    const result = await uploadPersonalDocument(token, fileInput.files[0]);
    console.log('Documento subido:', result);
  }
});
```

### Subir Documento Compartido (Admin)

**curl:**
```bash
curl -X POST http://localhost:8080/documents/admin/shared \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -F "file=@/ruta/al/documento.pdf" \
  -F "title=Guía de Machine Learning" \
  -F "description=Guía completa de ML para principiantes" \
  -F "area_id=area123" \
  -F "tags=ML,guía,principiantes"
```

**Python:**
```python
import requests

def upload_shared_document(token, file_path, title, description, area_id, tags):
    url = "http://localhost:8080/documents/admin/shared"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    files = {
        'file': open(file_path, 'rb')
    }
    
    data = {
        'title': title,
        'description': description,
        'area_id': area_id,
        'tags': tags
    }
    
    response = requests.post(url, headers=headers, files=files, data=data)
    return response.json()

# Uso
token = "tu_token_admin_aqui"
result = upload_shared_document(
    token,
    "/ruta/al/documento.pdf", 
    "Guía de Machine Learning", 
    "Guía completa de ML para principiantes", 
    "area123", 
    "ML,guía,principiantes"
)
print("Documento subido:", result)
```

### Buscar Documentos

**curl:**
```bash
curl -X GET "http://localhost:8080/documents/search?query=machine%20learning&scope=shared&area_id=area123" \
  -H "Authorization: Bearer TOKEN_AQUI"
```

**Go:**
```go
package main

import (
    "encoding/json"
    "fmt"
    "net/http"
    "net/url"
)

func searchDocuments(token, query, scope, areaID string) {
    baseURL := "http://localhost:8080/documents/search"
    
    // Construir URL con parámetros
    params := url.Values{}
    params.Add("query", query)
    if scope != "" {
        params.Add("scope", scope)
    }
    if areaID != "" {
        params.Add("area_id", areaID)
    }
    
    // Crear solicitud
    req, _ := http.NewRequest("GET", baseURL+"?"+params.Encode(), nil)
    req.Header.Set("Authorization", "Bearer "+token)
    
    // Enviar solicitud
    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        fmt.Println("Error:", err)
        return
    }
    defer resp.Body.Close()
    
    // Procesar respuesta
    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)
    fmt.Println("Resultados de búsqueda:", result)
}
```

## 4. Consultas RAG

### Realizar Consulta General

**curl:**
```bash
curl -X POST http://localhost:8080/queries \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "¿Cuáles son las principales aplicaciones de la inteligencia artificial?",
    "user_id": "user123",
    "include_personal": true,
    "area_ids": ["area123"],
    "max_sources": 5
  }'
```

**JavaScript:**
```javascript
async function performQuery(token, queryText) {
  const userId = getUserIdFromToken(token); // Función para extraer user_id del token
  
  const response = await fetch('http://localhost:8080/queries', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      query: queryText,
      user_id: userId,
      include_personal: true,
      area_ids: ["area123"], // ID del área de IA
      max_sources: 5
    })
  });
  
  return await response.json();
}

// Función para extraer user_id del token JWT
function getUserIdFromToken(token) {
  const base64Url = token.split('.')[1];
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
  }).join(''));

  return JSON.parse(jsonPayload).user_id;
}

// Uso en una interfaz de chat
document.getElementById('queryForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const queryInput = document.getElementById('queryInput').value;
  const token = localStorage.getItem('token');
  
  const result = await performQuery(token, queryInput);
  
  // Mostrar respuesta
  const responseElement = document.getElementById('response');
  responseElement.innerHTML = `
    <div class="answer">${result.answer}</div>
    <div class="sources">
      <h4>Fuentes:</h4>
      <ul>
        ${result.sources.map(s => `<li><strong>${s.title}</strong>: ${s.snippet} (Score: ${s.score})</li>`).join('')}
      </ul>
    </div>
  `;
});
```

### Realizar Consulta en Área Específica

**curl:**
```bash
curl -X POST http://localhost:8080/queries/area/area123 \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "¿Qué es el aprendizaje profundo?",
    "user_id": "user123",
    "max_sources": 3
  }'
```

**Python:**
```python
import requests

def query_specific_area(token, area_id, query_text, user_id, max_sources=3):
    url = f"http://localhost:8080/queries/area/{area_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "query": query_text,
        "user_id": user_id,
        "max_sources": max_sources
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Uso
token = "tu_token_aqui"
user_id = "user123"
area_id = "area123"  # ID del área de IA
query = "¿Qué es el aprendizaje profundo?"

result = query_specific_area(token, area_id, query, user_id)
print(f"Respuesta: {result['answer']}")
print("\nFuentes:")
for source in result['sources']:
    print(f"- {source['title']}: {source['snippet'][:100]}...")
```

## 5. Gestión de Proveedores LLM

### Añadir Proveedor OpenAI (Admin)

**curl:**
```bash
curl -X POST http://localhost:8080/llm/providers \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OpenAI GPT-4",
    "type": "openai",
    "api_key": "sk-your_openai_key",
    "model": "gpt-4o",
    "default": true,
    "temperature": 0.0,
    "max_tokens": 4096
  }'
```

**Go:**
```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "net/http"
)

func addLLMProvider(token string) {
    url := "http://localhost:8080/llm/providers"
    
    // Crear estructura de datos
    payload := map[string]interface{}{
        "name": "OpenAI GPT-4",
        "type": "openai",
        "api_key": "sk-your_openai_key",
        "model": "gpt-4o",
        "default": true,
        "temperature": 0.0,
        "max_tokens": 4096,
    }
    
    // Convertir a JSON
    jsonData, _ := json.Marshal(payload)
    
    // Crear solicitud
    req, _ := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+token)
    
    // Enviar solicitud
    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        fmt.Println("Error:", err)
        return
    }
    defer resp.Body.Close()
    
    // Procesar respuesta
    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)
    fmt.Println("Proveedor añadido:", result)
}
```

### Añadir Proveedor Ollama Local (Admin)

**curl:**
```bash
curl -X POST http://localhost:8080/llm/providers \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ollama Local",
    "type": "ollama",
    "api_endpoint": "http://ollama:11434",
    "model": "llama3",
    "default": false,
    "temperature": 0.1,
    "max_tokens": 2048
  }'
```

**Python:**
```python
import requests

def add_ollama_provider(token):
    url = "http://localhost:8080/llm/providers"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "name": "Ollama Local",
        "type": "ollama",
        "api_endpoint": "http://ollama:11434",
        "model": "llama3",
        "default": False,
        "temperature": 0.1,
        "max_tokens": 2048
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Uso
admin_token = "tu_token_admin_aqui"
result = add_ollama_provider(admin_token)
print("Proveedor Ollama añadido:", result)
```

### Probar un Proveedor LLM (Admin)

**curl:**
```bash
curl -X POST "http://localhost:8080/llm/providers/provider123/test?prompt=Responde%20con%20un%20'%C2%A1Hola%20mundo!'" \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI"
```

**JavaScript:**
```javascript
async function testLLMProvider(token, providerId, prompt = "Responde con un '¡Hola mundo!'") {
  const url = `http://localhost:8080/llm/providers/${providerId}/test?prompt=${encodeURIComponent(prompt)}`;
  
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  return await response.json();
}

// Uso
const adminToken = localStorage.getItem('adminToken');
const providerId = 'provider123';

testLLMProvider(adminToken, providerId)
  .then(result => {
    console.log('Resultado del test:', result);
    console.log('Respuesta del modelo:', result.response.text);
    console.log('Latencia:', result.response.latency_ms, 'ms');
  })
  .catch(error => {
    console.error('Error al probar el proveedor:', error);
  });
```

## 6. Flujo de Trabajo Completo

A continuación se presenta un ejemplo de flujo de trabajo completo para implementar un asistente de IA basado en una base de conocimiento personalizada:

### 1. Configuración Inicial (Admin)

**Python:**
```python
import requests
import json
import time
from getpass import getpass

# Configuración base
BASE_URL = "http://localhost:8080"

# Función para iniciar sesión
def login(username, password):
    url = f"{BASE_URL}/auth/login"
    payload = {
        "username": username,
        "password": password
    }
    response = requests.post(url, json=payload)
    return response.json()

# Función para crear un área de conocimiento
def create_knowledge_area(token, name, description, tags=None):
    url = f"{BASE_URL}/knowledge/admin/areas"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "name": name,
        "description": description,
        "icon": "brain", 
        "color": "#3498DB"
    }
    if tags:
        payload["tags"] = tags
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Función para añadir un proveedor LLM
def add_llm_provider(token, name, provider_type, model, api_key=None, api_endpoint=None, is_default=False):
    url = f"{BASE_URL}/llm/providers"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "name": name,
        "type": provider_type,
        "model": model,
        "default": is_default,
        "temperature": 0.0,
        "max_tokens": 4096
    }
    
    if api_key:
        payload["api_key"] = api_key
    
    if api_endpoint:
        payload["api_endpoint"] = api_endpoint
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Función para subir un documento compartido
def upload_shared_document(token, file_path, title, description, area_id, tags=None):
    url = f"{BASE_URL}/documents/admin/shared"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    files = {
        'file': open(file_path, 'rb')
    }
    
    data = {
        'title': title,
        'description': description,
        'area_id': area_id
    }
    
    if tags:
        data['tags'] = tags
    
    response = requests.post(url, headers=headers, files=files, data=data)
    return response.json()

# Iniciar sesión como administrador
print("=== Configuración Inicial ===")
admin_username = "admin"
admin_password = getpass("Ingrese la contraseña de administrador: ")

auth_response = login(admin_username, admin_password)
admin_token = auth_response["access_token"]
print("Inicio de sesión exitoso como administrador.")

# Crear área de conocimiento para IA
print("\nCreando área de conocimiento para IA...")
ia_area = create_knowledge_area(
    admin_token,
    "Inteligencia Artificial",
    "Conocimiento sobre IA, aprendizaje automático y redes neuronales",
    ["IA", "Machine Learning", "Deep Learning"]
)
print(f"Área creada: {ia_area['id']} - {ia_area['name']}")

# Añadir proveedor LLM (OpenAI)
print("\nConfigurando proveedor LLM (OpenAI)...")
openai_api_key = getpass("Ingrese su API key de OpenAI: ")
llm_provider = add_llm_provider(
    admin_token,
    "OpenAI GPT-4",
    "openai",
    "gpt-4o",
    api_key=openai_api_key,
    is_default=True
)
print(f"Proveedor añadido: {llm_provider['id']} - {llm_provider['name']}")

# Subir documentos de ejemplo al área de IA
print("\nSubiendo documentos al área de IA...")
documents = [
    {
        "path": "documentos/introduccion_ia.pdf",
        "title": "Introducción a la IA",
        "description": "Guía introductoria a la inteligencia artificial",
        "tags": "introducción,IA,conceptos básicos"
    },
    {
        "path": "documentos/deep_learning.pdf",
        "title": "Deep Learning: Fundamentos",
        "description": "Fundamentos del aprendizaje profundo y redes neuronales",
        "tags": "deep learning,redes neuronales,fundamentos"
    }
]

for doc in documents:
    try:
        response = upload_shared_document(
            admin_token,
            doc["path"],
            doc["title"],
            doc["description"],
            ia_area["id"],
            doc["tags"]
        )
        print(f"Documento subido: {response['id']} - {response['title']}")
    except Exception as e:
        print(f"Error al subir {doc['title']}: {str(e)}")

print("\nConfiguración inicial completada con éxito.")
```

### 2. Uso por Usuario Regular

**JavaScript:**
```javascript
// script.js - Interfaz de usuario para consultas RAG

let token = null;
let currentUser = null;
let knowledgeAreas = [];

// Función para iniciar sesión
async function login() {
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  
  try {
    const response = await fetch('http://localhost:8080/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    
    const data = await response.json();
    
    if (response.ok) {
      token = data.access_token;
      localStorage.setItem('token', token);
      
      // Extraer información del usuario del token
      currentUser = parseJwt(token);
      
      // Cargar áreas de conocimiento
      await loadKnowledgeAreas();
      
      // Mostrar interfaz principal
      document.getElementById('loginContainer').style.display = 'none';
      document.getElementById('mainContainer').style.display = 'block';
      
      // Actualizar UI
      document.getElementById('userGreeting').textContent = `Hola, ${currentUser.username}`;
    } else {
      showError('Error de inicio de sesión: ' + (data.error || 'Credenciales inválidas'));
    }
  } catch (error) {
    showError('Error de conexión: ' + error.message);
  }
}

// Función para cargar áreas de conocimiento
async function loadKnowledgeAreas() {
  try {
    const response = await fetch('http://localhost:8080/knowledge/areas', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      knowledgeAreas = await response.json();
      
      // Actualizar UI con áreas disponibles
      const areasContainer = document.getElementById('knowledgeAreas');
      areasContainer.innerHTML = '';
      
      knowledgeAreas.forEach(area => {
        const checkbox = document.createElement('div');
        checkbox.className = 'area-checkbox';
        checkbox.innerHTML = `
          <input type="checkbox" id="area-${area.id}" value="${area.id}">
          <label for="area-${area.id}" style="color: ${area.color}">
            ${area.name}
          </label>
        `;
        areasContainer.appendChild(checkbox);
      });
    } else {
      showError('Error al cargar áreas de conocimiento');
    }
  } catch (error) {
    showError('Error de conexión: ' + error.message);
  }
}

// Función para enviar consulta
async function sendQuery() {
  const queryText = document.getElementById('queryInput').value;
  
  if (!queryText.trim()) {
    showError('Por favor, ingrese una consulta');
    return;
  }
  
  // Recopilar áreas seleccionadas
  const selectedAreas = [];
  knowledgeAreas.forEach(area => {
    const checkbox = document.getElementById(`area-${area.id}`);
    if (checkbox && checkbox.checked) {
      selectedAreas.push(area.id);
    }
  });
  
  // Verificar si se debe incluir conocimiento personal
  const includePersonal = document.getElementById('includePersonal').checked;
  
  // Preparar UI para respuesta
  document.getElementById('responseContainer').innerHTML = '<div class="loading">Procesando consulta...</div>';
  
  try {
    const response = await fetch('http://localhost:8080/queries', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query: queryText,
        user_id: currentUser.user_id,
        include_personal: includePersonal,
        area_ids: selectedAreas.length > 0 ? selectedAreas : undefined,
        max_sources: 5
      })
    });
    
    if (response.ok) {
      const result = await response.json();
      displayResponse(result);
      saveToHistory(result);
    } else {
      const error = await response.json();
      showError('Error en la consulta: ' + (error.detail || error.error || 'Error desconocido'));
    }
  } catch (error) {
    showError('Error de conexión: ' + error.message);
  }
}

// Función para mostrar la respuesta
function displayResponse(result) {
  const container = document.getElementById('responseContainer');
  
  // Crear HTML para la respuesta
  const html = `
    <div class="response-card">
      <div class="response-header">
        <span class="model-info">${result.llm_provider} - ${result.model}</span>
        <span class="timing">${result.processing_time_ms}ms</span>
      </div>
      <div class="response-body">
        ${result.answer}
      </div>
      <div class="response-sources">
        <h4>Fuentes (${result.sources.length}):</h4>
        <ul>
          ${result.sources.map(source => `
            <li>
              <div class="source-title">[${source.score.toFixed(2)}] ${source.title}</div>
              <div class="source-snippet">${source.snippet}</div>
              ${source.url ? `<a href="${source.url}" target="_blank" class="source-link">Ver documento</a>` : ''}
            </li>
          `).join('')}
        </ul>
      </div>
    </div>
  `;
  
  container.innerHTML = html;
}

// Función para subir un documento personal
async function uploadPersonalDocument() {
  const fileInput = document.getElementById('fileInput');
  const title = document.getElementById('docTitle').value;
  const description = document.getElementById('docDescription').value;
  const tags = document.getElementById('docTags').value;
  
  if (!fileInput.files.length) {
    showError('Por favor, seleccione un archivo');
    return;
  }
  
  if (!title) {
    showError('El título es obligatorio');
    return;
  }
  
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('title', title);
  formData.append('description', description);
  formData.append('tags', tags);
  
  try {
    const response = await fetch('http://localhost:8080/documents/personal', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });
    
    if (response.ok) {
      const result = await response.json();
      showMessage(`Documento "${result.title}" subido correctamente`);
      
      // Limpiar formulario
      document.getElementById('uploadForm').reset();
    } else {
      const error = await response.json();
      showError('Error al subir documento: ' + (error.detail || error.error || 'Error desconocido'));
    }
  } catch (error) {
    showError('Error de conexión: ' + error.message);
  }
}

// Función para mostrar el historial de consultas
async function showQueryHistory() {
  try {
    const response = await fetch(`http://localhost:8080/queries/history?user_id=${currentUser.user_id}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const history = await response.json();
      
      // Actualizar UI con historial
      const historyContainer = document.getElementById('historyContainer');
      historyContainer.innerHTML = '<h3>Historial de Consultas</h3>';
      
      if (history.length === 0) {
        historyContainer.innerHTML += '<p>No hay consultas en el historial.</p>';
        return;
      }
      
      const historyList = document.createElement('ul');
      historyList.className = 'history-list';
      
      history.forEach(item => {
        const historyItem = document.createElement('li');
        historyItem.className = 'history-item';
        historyItem.innerHTML = `
          <div class="history-query">${item.query}</div>
          <div class="history-date">${new Date(item.created_at).toLocaleString()}</div>
          <button class="history-view-btn" data-id="${item.query_id}">Ver</button>
        `;
        historyList.appendChild(historyItem);
      });
      
      historyContainer.appendChild(historyList);
      
      // Añadir event listeners para botones de ver
      document.querySelectorAll('.history-view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const historyItem = history.find(h => h.query_id === btn.dataset.id);
          if (historyItem) {
            displayResponse(historyItem);
          }
        });
      });
    } else {
      showError('Error al cargar historial');
    }
  } catch (error) {
    showError('Error de conexión: ' + error.message);
  }
}

// Funciones auxiliares
function parseJwt(token) {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
      return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));

    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

function showError(message) {
  const errorBox = document.getElementById('errorBox');
  errorBox.textContent = message;
  errorBox.style.display = 'block';
  
  setTimeout(() => {
    errorBox.style.display = 'none';
  }, 5000);
}

function showMessage(message) {
  const messageBox = document.getElementById('messageBox');
  messageBox.textContent = message;
  messageBox.style.display = 'block';
  
  setTimeout(() => {
    messageBox.style.display = 'none';
  }, 3000);
}

// Inicialización y event listeners
document.addEventListener('DOMContentLoaded', () => {
  // Verificar si hay un token guardado
  const savedToken = localStorage.getItem('token');
  if (savedToken) {
    token = savedToken;
    currentUser = parseJwt(token);
    
    if (currentUser) {
      // Auto-login
      loadKnowledgeAreas().then(() => {
        document.getElementById('loginContainer').style.display = 'none';
        document.getElementById('mainContainer').style.display = 'block';
        document.getElementById('userGreeting').textContent = `Hola, ${currentUser.username}`;
      });
    }
  }
  
  // Event listeners
  document.getElementById('loginForm').addEventListener('submit', (e) => {
    e.preventDefault();
    login();
  });
  
  document.getElementById('queryForm').addEventListener('submit', (e) => {
    e.preventDefault();
    sendQuery();
  });
  
  document.getElementById('uploadForm').addEventListener('submit', (e) => {
    e.preventDefault();
    uploadPersonalDocument();
  });
  
  document.getElementById('showHistoryBtn').addEventListener('click', () => {
    showQueryHistory();
  });
  
  document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('token');
    token = null;
    currentUser = null;
    document.getElementById('loginContainer').style.display = 'block';
    document.getElementById('mainContainer').style.display = 'none';
  });
});
```

El HTML básico para la interfaz anterior sería:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sistema de Gestión de Conocimiento MCP</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div class="container">
    <header>
      <h1>Sistema de Gestión de Conocimiento MCP</h1>
    </header>
    
    <!-- Mensajes de error y éxito -->
    <div id="errorBox" class="error-box"></div>
    <div id="messageBox" class="message-box"></div>
    
    <!-- Pantalla de login -->
    <div id="loginContainer" class="login-container">
      <h2>Iniciar Sesión</h2>
      <form id="loginForm">
        <div class="form-group">
          <label for="username">Usuario:</label>
          <input type="text" id="username" required>
        </div>
        <div class="form-group">
          <label for="password">Contraseña:</label>
          <input type="password" id="password" required>
        </div>
        <button type="submit" class="btn-primary">Ingresar</button>
      </form>
    </div>
    
    <!-- Contenedor principal -->
    <div id="mainContainer" class="main-container" style="display: none;">
      <div class="user-bar">
        <span id="userGreeting">Hola, Usuario</span>
        <button id="logoutBtn" class="btn-secondary">Cerrar Sesión</button>
      </div>
      
      <div class="tabs">
        <div class="tab-header">
          <div class="tab active" data-tab="query">Consultas</div>
          <div class="tab" data-tab="upload">Subir Documento</div>
          <div class="tab" data-tab="history">Historial</div>
        </div>
        
        <!-- Tab de Consultas -->
        <div class="tab-content active" id="queryTab">
          <h2>Realizar Consulta</h2>
          
          <div class="knowledge-areas-container">
            <h3>Áreas de Conocimiento</h3>
            <div id="knowledgeAreas" class="knowledge-areas">
              <!-- Áreas se cargarán dinámicamente -->
            </div>
            <div class="personal-toggle">
              <input type="checkbox" id="includePersonal" checked>
              <label for="includePersonal">Incluir conocimiento personal</label>
            </div>
          </div>
          
          <form id="queryForm">
            <div class="form-group">
              <label for="queryInput">Consulta:</label>
              <textarea id="queryInput" rows="3" placeholder="Escribe tu consulta aquí..." required></textarea>
            </div>
            <button type="submit" class="btn-primary">Enviar Consulta</button>
          </form>
          
          <div id="responseContainer" class="response-container">
            <!-- Aquí se mostrará la respuesta -->
          </div>
        </div>
        
        <!-- Tab de Subir Documento -->
        <div class="tab-content" id="uploadTab">
          <h2>Subir Documento Personal</h2>
          
          <form id="uploadForm">
            <div class="form-group">
              <label for="fileInput">Seleccionar Archivo:</label>
              <input type="file" id="fileInput" required>
            </div>
            <div class="form-group">
              <label for="docTitle">Título:</label>
              <input type="text" id="docTitle" required>
            </div>
            <div class="form-group">
              <label for="docDescription">Descripción:</label>
              <textarea id="docDescription" rows="2"></textarea>
            </div>
            <div class="form-group">
              <label for="docTags">Etiquetas (separadas por comas):</label>
              <input type="text" id="docTags">
            </div>
            <button type="submit" class="btn-primary">Subir Documento</button>
          </form>
        </div>
        
        <!-- Tab de Historial -->
        <div class="tab-content" id="historyTab">
          <div id="historyContainer">
            <!-- Historial se cargará aquí -->
            <button id="showHistoryBtn" class="btn-secondary">Cargar Historial</button>
          </div>
        </div>
      </div>
    </div>
  </div>
  
  <script src="script.js"></script>
</body>
</html>
```

Este ejemplo completo demuestra cómo interactuar con todos los componentes del sistema de gestión de conocimiento: autenticación, gestión de áreas de conocimiento, subida de documentos, y consultas RAG con la interfaz de usuario correspondiente.