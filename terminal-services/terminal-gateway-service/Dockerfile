FROM golang:1.23-alpine AS builder

WORKDIR /app

# Copy go files with better handling of workspace files
COPY go.mod go.sum ./
# go.mod y go.work ahora son compatibles (ambos especifican Go 1.22)
# Descargar y verificar dependencias con manejo de errores
RUN go mod download && go mod verify || true

# Now that go.mod and go.work versions are aligned, we can copy all files
COPY . .

# Build the application with simplified dependencies
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o terminal-gateway-service .


# Use a minimal alpine image for the final stage
FROM alpine:3.18

RUN apk --no-cache add ca-certificates openssh-client tzdata

WORKDIR /app

# Copy the binary from the builder stage
COPY --from=builder /app/terminal-gateway-service .

# Expose the port the application will run on
EXPOSE 8090

# Command to run the application
CMD ["./terminal-gateway-service"]