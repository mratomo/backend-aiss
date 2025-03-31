# AISS - Advanced Intelligent Search System

AISS is a microservices-based RAG (Retrieval Augmented Generation) system that combines document management, vector search, and LLM-powered natural language querying with advanced database connectivity capabilities.

## System Overview

AISS is designed to be a comprehensive knowledge management platform that allows users to:

1. Store, process, and retrieve documents through vector search
2. Connect to various database systems and automatically discover schemas
3. Query both document repositories and databases using natural language
4. Use local or cloud-based LLMs for processing queries

The system is composed of multiple microservices built with Go and Python, containerized with Docker, and designed to work together to provide a seamless experience.

## Key Features

### Document Management
- Upload and manage documents of various formats (PDF, DOCX, TXT, etc.)
- Organize documents into knowledge areas
- Automatic content extraction and embedding generation
- Personal and shared document repositories

### Database Integration
- Connect to multiple database types (PostgreSQL, MySQL, MongoDB, etc.)
- Secure credential management with encryption
- Automatic schema discovery and vectorization
- Agent-based natural language to SQL conversion

### RAG Capabilities
- Hybrid RAG combining document search and database querying
- Customizable system prompts for specific use cases
- Context management for improved responses
- Source attribution and relevance scoring

### LLM Integration
- Support for multiple LLM providers (OpenAI, Anthropic, local models)
- Local LLM support via Ollama with GPU acceleration
- Configurable parameters (temperature, max tokens, etc.)
- Administration interface for model management

### Technical Features
- Microservices architecture for scalability
- API Gateway for unified access control
- JWT-based authentication and authorization
- Vectorized search with Qdrant
- Document storage with MinIO
- MongoDB for structured data storage
- GPU acceleration with fallback to CPU processing

## Architecture

The system is composed of the following components:

### Core Services (Go)
- **API Gateway**: Central entry point for all requests, handles routing and authentication
- **User Service**: Manages user accounts and authentication
- **Document Service**: Handles document upload, storage, and retrieval

### MCP Services (Python)
- **Context Service**: Manages context for RAG queries
- **Embedding Service**: Generates embeddings for documents and queries

### Database Services (Python)
- **DB Connection Service**: Manages database connections and credentials
- **Schema Discovery Service**: Analyzes database schemas and generates vectorized representations

### Agent Services (Python)
- **RAG Agent**: Core service that processes queries using both document and database sources

### Support Services
- **MongoDB**: Primary database for structured data
- **Qdrant**: Vector database for semantic search
- **MinIO**: Object storage for documents
- **Ollama**: Optional local LLM service with GPU support

## Getting Started

### Prerequisites
- Docker and Docker Compose
- NVIDIA drivers and NVIDIA Container Toolkit (optional, for GPU acceleration)
- 16GB+ RAM recommended (32GB+ for optimal performance)
- GPU recommended for embedding generation and local LLM usage

### Quick Start
1. Clone the repository
2. Create a `.env` file based on the example provided
3. Run `docker-compose up -d`
4. Access the API at `http://localhost:8080`

Detailed deployment instructions can be found in the [Deployment Guide](docs/deployment/deployment.md).

## API Documentation

The system exposes a comprehensive REST API for all operations. See the [API Reference](docs/api/api-reference.md) for details.

## Example Usage

See the [Examples](docs/examples/examples.md) for code samples and usage patterns.

## Development

### Project Structure
```
├── api-gateway/          # Go service for API routing
├── core-services/        # Core Go services
│   ├── user-service/     # User management service
│   └── document-service/ # Document management service
├── mcp-services/         # Model Context Protocol services
│   ├── context-service/  # Context management (Python)
│   └── embedding-service/# Embedding generation (Python)
├── db-services/          # Database integration services
│   ├── db-connection-service/    # Database connection management
│   └── schema-discovery-service/ # Schema analysis and vectorization
├── rag-agent/            # Query processing service
├── db/                   # Database initialization scripts
│   ├── mongodb/          # MongoDB scripts
│   ├── minio/            # MinIO initialization
│   └── qdrant/           # Qdrant configuration
├── docs/                 # Documentation
└── docker-compose.yml    # Service configuration
```

### Local Development Setup
1. Install the required dependencies for each service
2. Run MongoDB, MinIO, and Qdrant locally or via Docker
3. Configure environment variables for each service
4. Run each service individually in development mode

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.