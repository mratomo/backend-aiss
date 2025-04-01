# Integración del Frontend con el Backend

Este documento proporciona la información necesaria para que el equipo frontend pueda integrar correctamente su aplicación con los servicios backend.

## Configuración de Red Docker

### Nombre de la Red Docker

Para conectarse a los servicios backend, el contenedor frontend debe unirse a la siguiente red Docker:

```
mcp-network
```

En el archivo `docker-compose.yml` del frontend, debes incluir:

```yaml
networks:
  mcp-network:
    external: true  # Indica que esta red ya existe y es externa
```

### Endpoints de los Servicios

Los siguientes servicios están disponibles en la red Docker interna:

| Servicio                        | Nombre de Host Docker      | Puerto Interno |
|---------------------------------|----------------------------|----------------|
| API Gateway                     | api-gateway                | 8080           |
| Gateway de Terminal             | terminal-gateway-service   | 8090           |

## Configuración del Proxy Inverso

El frontend debe implementar un proxy inverso (como Nginx) para redireccionar las solicitudes a los servicios backend. A continuación se muestra una configuración Nginx recomendada:

```nginx
# Configurar como /etc/nginx/conf.d/default.conf dentro del contenedor frontend

server {
    listen 80;
    # Configuración SSL para producción
    # listen 443 ssl;
    # ssl_certificate /etc/nginx/ssl/cert.pem;
    # ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    # Servir archivos estáticos del frontend
    location / {
        root /usr/share/nginx/html;  # Ajustar según la estructura de tu frontend
        index index.html;
        try_files $uri $uri/ /index.html;
    }
    
    # Proxy para API Gateway
    location /api/ {
        proxy_pass http://api-gateway:8080/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;  # Aumentar para consultas largas
    }
    
    # Proxy para conexiones WebSocket (terminal)
    location /ws/ {
        proxy_pass http://terminal-gateway-service:8090/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;  # Conexiones WebSocket de larga duración
    }
    
    # Recomendaciones de seguridad
    add_header X-XSS-Protection "1; mode=block";
    add_header X-Content-Type-Options "nosniff";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
}
```

## Configuración del Frontend

### URLs de API

En tu aplicación frontend, configura las URLs de API de la siguiente manera:

```javascript
// Ejemplo de configuración para React
const API_BASE_URL = '/api';  // El proxy redirigirá a http://api-gateway:8080/api/
const WS_BASE_URL = '/ws';    // El proxy redirigirá a http://terminal-gateway-service:8090/ws/

// Ejemplo de uso
fetch(`${API_BASE_URL}/users/profile`)
  .then(response => response.json())
  .then(data => console.log(data));

// Ejemplo para WebSocket
const socket = new WebSocket(`${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${WS_BASE_URL}/terminal/connect`);
```

### Autenticación

Todas las APIs requieren autenticación mediante tokens JWT:

1. Usa `/api/auth/login` para obtener un token
2. Almacena el token (localStorage, sessionStorage o cookies)
3. Incluye el token en todas las solicitudes:

```javascript
fetch(`${API_BASE_URL}/users/profile`, {
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
})
```

## Consideraciones para el Desarrollo

Durante el desarrollo local, puedes usar dos enfoques:

### 1. Desarrollo con Proxy Local

Configura un proxy en tu herramienta de desarrollo frontend:

```javascript
// Para Create React App, en package.json
"proxy": "http://localhost:8080"

// Para Vite, en vite.config.js
server: {
  proxy: {
    '/api': 'http://localhost:8080',
    '/ws': {
      target: 'http://localhost:8090',
      ws: true
    }
  }
}
```

### 2. Desarrollo con Contenedor

Utiliza la red Docker desde tu contenedor frontend:

```yaml
# docker-compose.frontend.yml
version: '3.8'

services:
  frontend:
    build: .
    ports:
      - "80:80"
    networks:
      - mcp-network

networks:
  mcp-network:
    external: true
```

## Anexo: Docker Compose Completo para Frontend

```yaml
version: '3.8'

services:
  frontend:
    build: .
    ports:
      - "80:80"
      - "443:443"  # Si se usa HTTPS
    networks:
      - mcp-network
    restart: unless-stopped

networks:
  mcp-network:
    external: true
```