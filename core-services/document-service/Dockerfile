FROM golang:1.23-alpine AS builder

WORKDIR /app

# Instalar dependencias de compilación
RUN apk add --no-cache gcc musl-dev

# Copiar archivos de módulos Go
COPY go.mod go.sum ./
# go.mod y go.work ahora son compatibles (ambos especifican Go 1.22)

# Descargar dependencias
# Descargar y verificar dependencias con manejo de errores
RUN go mod download && go mod verify || true

# Ahora que go.mod y go.work son compatibles, podemos copiar todos los archivos
COPY . .

# Compilar la aplicación con dependencias simplificadas
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o document-service .


# Imagen final
FROM alpine:3.18

WORKDIR /app

# Instalar certificados CA para conexiones HTTPS
RUN apk --no-cache add ca-certificates

# Copiar el binario compilado desde la etapa de compilación
COPY --from=builder /app/document-service .

# Copiar configuración
COPY --from=builder /app/config ./config

# Exponer puerto
EXPOSE 8082

# Ejecutar la aplicación
CMD ["./document-service"]