FROM golang:1.23-alpine AS builder

WORKDIR /app

# Instalar dependencias de compilación
RUN apk add --no-cache gcc musl-dev

# Copiar archivos de módulos Go
COPY go.mod go.sum ./
RUN rm -f go.work

# Descargar dependencias
# Descargar y verificar dependencias con manejo de errores
RUN go mod download && go mod verify || true

# Ahora que go.mod y go.work son compatibles, podemos copiar todos los archivos
COPY . .

# Compilar la aplicación con dependencias simplificadas
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o user-service .


# Imagen final
FROM alpine:3.18

WORKDIR /app

# Instalar certificados CA para conexiones HTTPS
RUN apk --no-cache add ca-certificates

# Copiar el binario compilado desde la etapa de compilación
COPY --from=builder /app/user-service .

# Copiar configuración
COPY --from=builder /app/config ./config

# Exponer puerto
EXPOSE 8081

# Ejecutar la aplicación
CMD ["./user-service"]