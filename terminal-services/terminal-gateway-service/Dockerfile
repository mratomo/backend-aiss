FROM golang:1.22-alpine AS builder

WORKDIR /app

# Copy go files
COPY go.mod go.sum go.work ./
RUN go mod download || true
RUN GOWORK=off go mod download || true

# Copy source code
COPY . .

# Build the application (ignore dependency checks)
RUN CGO_ENABLED=0 GOOS=linux GOWORK=off go build -a -installsuffix cgo -ldflags="-s -w" -o terminal-gateway-service . || \
    (echo "Building with Skip Resolve..." && GOWORK=off go build -o terminal-gateway-service -tags skipresolver .)

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