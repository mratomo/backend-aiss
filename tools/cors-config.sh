#!/bin/bash

# Script para configurar CORS dinámicamente en el API Gateway
# Uso: ./cors-config.sh <command> [arguments]
# Comandos:
#   get - Obtener configuración CORS actual
#   set - Establecer nuevos valores CORS: ./cors-config.sh set "http://localhost:3000" "http://192.168.1.100:8080" "*"

# Configuración
API_URL="http://localhost:8080"
API_ENDPOINT="/admin/system/config/cors"
TOKEN=""  # Token JWT de un usuario con permisos de admin

# Funciones
get_cors_config() {
    curl -s -X GET \
        -H "Authorization: Bearer $TOKEN" \
        "$API_URL$API_ENDPOINT" | jq .
}

set_cors_config() {
    if [ $# -eq 0 ]; then
        echo "Error: Debe proporcionar al menos un origen CORS para configurar"
        echo "Uso: ./cors-config.sh set \"http://localhost:3000\" \"http://192.168.1.100:8080\" \"*\""
        exit 1
    fi

    # Crear array JSON con los orígenes proporcionados
    origins_json="["
    for origin in "$@"; do
        origins_json+="\"$origin\","
    done
    # Eliminar la última coma y cerrar el array
    origins_json=${origins_json%,}"]"

    # Crear JSON completo
    json_data="{\"origins\": $origins_json}"

    # Enviar solicitud
    curl -s -X PUT \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$json_data" \
        "$API_URL$API_ENDPOINT" | jq .
}

# Punto de entrada principal
if [ $# -lt 1 ]; then
    echo "Uso: ./cors-config.sh <command> [arguments]"
    echo "Comandos:"
    echo "  get - Obtener configuración CORS actual"
    echo "  set - Establecer nuevos valores CORS: ./cors-config.sh set \"http://localhost:3000\" \"http://192.168.1.100:8080\" \"*\""
    exit 1
fi

# Token para autenticación (debe ser obtenido primero)
if [ -z "$TOKEN" ]; then
    echo "ADVERTENCIA: No se ha configurado un token de autenticación. Edite este script y actualice la variable TOKEN."
    echo "Puede obtener un token usando:"
    echo "  curl -X POST -H \"Content-Type: application/json\" -d '{\"username\":\"admin\",\"password\":\"YOUR_PASSWORD\"}' $API_URL/api/v1/auth/login"
    if [ "$1" != "help" ]; then
        exit 1
    fi
fi

# Ejecutar comando
case "$1" in
    "get")
        get_cors_config
        ;;
    "set")
        shift  # Eliminar el primer argumento (comando)
        set_cors_config "$@"
        ;;
    "help")
        echo "Gestión de configuración CORS para API Gateway"
        echo ""
        echo "Uso: ./cors-config.sh <command> [arguments]"
        echo ""
        echo "Comandos:"
        echo "  get - Obtener configuración CORS actual"
        echo "  set - Establecer nuevos valores CORS"
        echo ""
        echo "Ejemplos:"
        echo "  ./cors-config.sh get"
        echo "  ./cors-config.sh set \"http://localhost:3000\" \"http://192.168.1.100:8080\""
        echo "  ./cors-config.sh set \"*\"  # Permitir todos los orígenes (NO RECOMENDADO EN PRODUCCIÓN)"
        ;;
    *)
        echo "Comando desconocido: $1"
        echo "Use 'help' para ver comandos disponibles"
        exit 1
        ;;
esac

exit 0