# Configuración de Docker con Proxy Inverso

Esta guía explica cómo configurar el sistema correctamente utilizando un proxy inverso en el frontend para comunicarse con la API Gateway dentro de la red Docker.

## Arquitectura Recomendada

```
   Internet/Red Externa
          |
          ↓
  +---------------+
  |   Frontend    | ← Los usuarios se conectan aquí (puerto 80/443)
  | (Nginx/Proxy) |
  +-------+-------+
          |
          ↓
  +---------------+
  |  API Gateway  | ← No expuesto externamente, solo accesible desde la red Docker
  +-------+-------+
          |
          ↓
+------------------+
| Servicios Internos | ← Solo accesibles dentro de la red Docker
+------------------+
```

## Configuración Docker Compose

Ejemplo básico de configuración en `docker-compose.yml`:

```yaml
version: '3.8'

services:
  frontend:
    build: ./frontend
    ports:
      - "80:80"      # Expuesto al host (y potencialmente a Internet)
      - "443:443"    # HTTPS (recomendado para producción)
    networks:
      - internal_network
    depends_on:
      - api-gateway
  
  api-gateway:
    build: ./api-gateway
    # Sin puertos expuestos al host
    networks:
      - internal_network
    depends_on:
      - user-service
      - document-service
      # otros servicios...
  
  # Servicios adicionales...
  user-service:
    build: ./core-services/user-service
    networks:
      - internal_network
  
  # ... otros servicios

networks:
  internal_network:
    driver: bridge
```

## Configuración del Proxy Inverso en Frontend

### Ejemplo con Nginx

Archivo `nginx.conf` dentro del contenedor frontend:

```nginx
server {
    listen 80;
    # Configuración SSL para producción
    # listen 443 ssl;
    # ssl_certificate /etc/nginx/ssl/cert.pem;
    # ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    # Servir archivos estáticos del frontend
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
    
    # Proxy de API - todas las peticiones a /api se envían a api-gateway
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
    }
}
```

### Dockerfile para Frontend con Nginx

```dockerfile
FROM node:16 as build

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine

# Copiar configuración de Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiar archivos estáticos del frontend
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
```

## Ventajas de Esta Configuración

1. **Seguridad Mejorada**: La API Gateway no está directamente expuesta a la red externa.
2. **Simplicidad para Clientes**: Los usuarios/clientes solo necesitan comunicarse con un único punto de entrada.
3. **No Problemas de CORS**: Al usar el proxy, todas las solicitudes parecen provenir del mismo origen.
4. **TLS Simplificado**: Solo necesitas configurar HTTPS en el frontend.

## Notas sobre la Configuración de CORS

Como la API Gateway está configurada para permitir cualquier origen cuando se utiliza con un proxy inverso, es importante asegurar que:

1. Solo el frontend dentro de la red Docker puede comunicarse con la API Gateway.
2. Se utilizan headers como `X-Real-IP` y `X-Forwarded-For` para mantener la información de los clientes reales.

## Entorno de Desarrollo

Para el entorno de desarrollo, puedes exponer la API Gateway localmente para facilitar el debugging:

```yaml
api-gateway:
  ports:
    - "127.0.0.1:8080:8080"  # Solo expuesto en localhost
```

## Consideraciones de Seguridad

- Asegúrate de que los servicios sólo escuchan en la interfaz de red interna Docker.
- Considera usar redes Docker diferentes para separar aún más los servicios (frontend, backend, datos).
- Implementa autenticación JWT robusta entre el frontend y la API Gateway.
- Considera utilizar un WAF (Web Application Firewall) delante del frontend para mayor seguridad.