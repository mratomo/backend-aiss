#!/bin/bash

# Códigos de color para la salida
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # Sin color

# Detectar comando de Docker Compose
detect_docker_compose() {
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
    elif docker compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
    else
        echo -e "${RED}Error: Docker Compose no encontrado. Por favor, instale Docker Compose.${NC}"
        exit 1
    fi
}

# Array de bases de datos y sus configuraciones
DATABASE_SERVICES=(
    "mongodb"
    "weaviate"
    "neo4j"
    "minio"
    "mongodb-setup"
    "weaviate-setup"
    "neo4j-setup"
    "minio-setup"
)

# Array de servicios core restantes
CORE_SERVICES=(
    "user-service"
    "document-service"
    "api-gateway"
    "context-service"
    "embedding-service"
    "rag-agent"
    "db-connection-service"
    "schema-discovery-service"
    "attack-vulnerability-service"
    "ollama"
    "terminal-session-service"
    "terminal-gateway-service"
    "terminal-context-aggregator"
    "terminal-suggestion-service"
)

# Función para verificar si Docker está funcionando
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}Docker no está en ejecución. Por favor, inicie Docker e intente de nuevo.${NC}"
        exit 1
    fi
}

# Función para validar la existencia del servicio en docker-compose
check_service_exists() {
    local service_name=$1
    if ! $DOCKER_COMPOSE_CMD config --services | grep -q "^$service_name$"; then
        echo -e "${RED}El servicio $service_name no existe en docker-compose.yml${NC}"
        return 1
    fi
    return 0
}

# Función para manejar servicios de setup
handle_setup_service() {
    local service_name=$1
    local container_name="aiss-${service_name}"

    # Verificar si el contenedor existe
    if ! docker ps -a --format '{{.Names}}' | grep -q "$container_name"; then
        echo -e "${RED}Contenedor $container_name no encontrado.${NC}"
        return 1
    fi

    # Verificar el estado final del contenedor
    local exit_code
    exit_code=$(docker inspect "$container_name" --format='{{.State.ExitCode}}')

    if [[ "$exit_code" == "0" ]]; then
        echo -e "${GREEN}Servicio $service_name completado exitosamente.${NC}"
        return 0
    else
        echo -e "${RED}Servicio $service_name falló con código de salida $exit_code.${NC}"

        # Mostrar logs para diagnóstico
        docker logs "$container_name"
        return 1
    fi
}

# Función para iniciar un servicio
start_service() {
    local service_name=$1
    local continue_service=0
    local with_dependencies="s" # Por defecto, con dependencias

    # Limpiar pantalla
    clear

    # Banner de inicio de servicio
    echo -e "${YELLOW}===== INICIANDO SERVICIO: $service_name =====${NC}"

    # Verificar existencia del servicio
    if ! check_service_exists "$service_name"; then
        echo -e "${RED}No se puede iniciar $service_name porque no existe en la configuración.${NC}"
        read -p "¿Continuar con el siguiente servicio? (s/n): " continue_choice
        if [[ $continue_choice == [sS] ]]; then
            return 0
        else
            return 1
        fi
    fi

    # Confirmar antes de iniciar
    read -p "Presione Enter para iniciar $service_name (o 'n' para omitir): " confirm
    if [[ $confirm == [nN] ]]; then
        return 0
    fi

    # Preguntar si incluir dependencias
    read -p "¿Desea iniciar $service_name con sus dependencias? (s/n): " with_dependencies

    echo -e "${YELLOW}Iniciando $service_name...${NC}"

    # Intentar levantar el servicio con o sin dependencias
    if [[ $with_dependencies == [nN] ]]; then
        echo -e "${YELLOW}Iniciando sin dependencias...${NC}"
        if ! $DOCKER_COMPOSE_CMD up -d --no-deps "$service_name"; then
            echo -e "${RED}No se pudo iniciar el servicio $service_name${NC}"
            read -p "¿Continuar con el siguiente servicio? (s/n): " continue_choice
            if [[ $continue_choice == [sS] ]]; then
                return 0
            else
                return 1
            fi
        fi
    else
        echo -e "${YELLOW}Iniciando con dependencias...${NC}"
        if ! $DOCKER_COMPOSE_CMD up -d "$service_name"; then
            echo -e "${RED}No se pudo iniciar el servicio $service_name${NC}"
            read -p "¿Continuar con el siguiente servicio? (s/n): " continue_choice
            if [[ $continue_choice == [sS] ]]; then
                return 0
            else
                return 1
            fi
        fi
    fi

    # Esperar un momento para que el servicio se estabilice
    sleep 5

    # Manejo especial para servicios de setup
    if [[ "$service_name" == *"-setup" ]]; then
        if ! handle_setup_service "$service_name"; then
            echo -e "${RED}Servicio $service_name no completó su configuración correctamente.${NC}"
            read -p "¿Continuar con el siguiente servicio? (s/n): " continue_choice
            if [[ $continue_choice == [sS] ]]; then
                return 0
            else
                return 1
            fi
        fi
    else
        # Verificar estado para servicios normales
        local container_status
        container_status=$($DOCKER_COMPOSE_CMD ps -q "$service_name" | xargs -I {} docker inspect -f '{{.State.Status}}' {})

        if [[ "$container_status" != "running" ]]; then
            echo -e "${RED}$service_name no está en estado de ejecución${NC}"
            $DOCKER_COMPOSE_CMD logs "$service_name"
            read -p "¿Continuar con el siguiente servicio? (s/n): " continue_choice
            if [[ $continue_choice == [sS] ]]; then
                return 0
            else
                return 1
            fi
        fi
    fi

    echo -e "${GREEN}$service_name iniciado exitosamente!${NC}"

    # Preguntar si continuar
    read -p "Presione Enter para continuar, o 'n' para salir: " continue_choice
    if [[ $continue_choice == [nN] ]]; then
        return 1
    fi

    return 0
}

# Función principal de inicio
main() {
    # Detectar comando de Docker Compose
    detect_docker_compose

    # Verificar si Docker está en ejecución
    check_docker

    # Verificar si existe el archivo docker-compose.yml
    if [ ! -f docker-compose.yml ]; then
        echo -e "${RED}docker-compose.yml no encontrado en el directorio actual!${NC}"
        exit 1
    fi

    # Preguntar si se quieren descargar las últimas imágenes
    read -p "¿Desea descargar las últimas imágenes? (s/n): " pull_choice
    if [[ $pull_choice == [sS] ]]; then
        echo -e "${YELLOW}Descargando últimas imágenes...${NC}"
        $DOCKER_COMPOSE_CMD pull
    fi

    # Inicio de bases de datos y sus configuraciones
    echo -e "${GREEN}===== INICIANDO BASES DE DATOS Y CONFIGURACIONES =====${NC}"
    for service in "${DATABASE_SERVICES[@]}"; do
        # Intentar iniciar el servicio
        if ! start_service "$service"; then
            break
        fi
    done

    # Pausa breve después de configurar bases de datos
    echo -e "${YELLOW}Esperando 30 segundos para asegurar configuración completa de bases de datos...${NC}"
    sleep 30

    # Inicio de servicios core restantes
    echo -e "${GREEN}===== INICIANDO SERVICIOS CORE =====${NC}"
    for service in "${CORE_SERVICES[@]}"; do
        # Intentar iniciar el servicio
        if ! start_service "$service"; then
            break
        fi
    done

    echo -e "${GREEN}Proceso de inicio de servicios completado!${NC}"
}

# Ejecutar función principal
main