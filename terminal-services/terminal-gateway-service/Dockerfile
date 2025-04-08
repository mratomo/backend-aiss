FROM golang:1.22-alpine AS builder

WORKDIR /app

# Copy go files with better handling of workspace files
COPY go.mod go.sum go.work* ./
RUN go mod download || echo "Warning: Some dependencies may not have been downloaded"
RUN if [ -f go.work ]; then GOWORK=off go mod download || echo "Warning: Workspace dependencies may not have been downloaded"; fi

# Copy source code
COPY . .

# Build the application with more robust error handling
RUN CGO_ENABLED=0 GOOS=linux GOWORK=off go build -a -installsuffix cgo -ldflags="-s -w" -o terminal-gateway-service . || \
    (echo "Retrying build with Skip Resolve..." && \
     GOWORK=off go build -o terminal-gateway-service -tags skipresolver . || \
     (echo "Build failed even with skipresolver tag" && exit 1))

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