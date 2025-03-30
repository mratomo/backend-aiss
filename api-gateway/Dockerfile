FROM golang:1.21-alpine AS builder

WORKDIR /app

# Instalar dependencias de compilación
RUN apk add --no-cache gcc musl-dev

# Copiar archivos de módulos Go
COPY go.mod go.sum ./

# Descargar dependencias
RUN go mod download

# Copiar código fuente
COPY . .

# Compilar la aplicación
RUN go build -o api-gateway .

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