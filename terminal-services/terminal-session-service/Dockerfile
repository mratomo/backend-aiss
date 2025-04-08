FROM golang:1.22-alpine AS builder

WORKDIR /app

# Copy go files
COPY go.mod go.sum go.work ./
RUN go mod download || true
RUN GOWORK=off go mod download || true

# Copy source code
COPY . .

# Build the application (ignore dependency checks)
RUN CGO_ENABLED=0 GOOS=linux GOWORK=off go build -a -installsuffix cgo -ldflags="-s -w" -o terminal-session-service . || \
    (echo "Building with Skip Resolve..." && GOWORK=off go build -o terminal-session-service -tags skipresolver .)

# Use a minimal alpine image for the final stage
FROM alpine:3.18

RUN apk --no-cache add ca-certificates tzdata

WORKDIR /app

# Copy the binary from the builder stage
COPY --from=builder /app/terminal-session-service .

# Expose the port the application will run on
EXPOSE 8091

# Command to run the application
CMD ["./terminal-session-service"]