FROM golang:1.22-alpine AS builder

WORKDIR /app

# Instalar dependencias de compilación
RUN apk add --no-cache gcc musl-dev

# Copiar archivos de módulos Go
COPY go.mod go.sum go.work* ./

# Descargar dependencias (con mejor manejo de errores)
RUN go mod download || echo "Warning: Some dependencies may not have been downloaded"
RUN if [ -f go.work ]; then GOWORK=off go mod download || echo "Warning: Workspace dependencies may not have been downloaded"; fi

# Copiar código fuente
COPY . .

# Compilar la aplicación con manejo más robusto de errores
RUN CGO_ENABLED=0 GOWORK=off go build -ldflags="-s -w" -o api-gateway . || \
    (echo "Retrying build with Skip Resolve..." && \
     GOWORK=off go build -o api-gateway -tags skipresolver . || \
     (echo "Build failed even with skipresolver tag" && exit 1))

# Imagen final
FROM alpine:3.18

WORKDIR /app

# Instalar certificados CA para conexiones HTTPS
RUN apk --no-cache add ca-certificates

# Copiar el binario compilado desde la etapa de compilación
COPY --from=builder /app/api-gateway .

# Copiar configuración
COPY --from=builder /app/config ./config

# Exponer puerto
EXPOSE 8080

# Ejecutar la aplicación
CMD ["./api-gateway"]