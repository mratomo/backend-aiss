FROM golang:1.24-alpine AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o terminal-gateway-service .

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