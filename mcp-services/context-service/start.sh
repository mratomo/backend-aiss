#!/bin/bash
# Script para asegurar que los módulos MCP estén disponibles antes de iniciar el servicio

echo "Verificando módulos MCP críticos..."

# Verificar si los módulos MCP están disponibles
python -c "
import sys
try:
    import mcp
    import fastmcp
    print('✅ Módulos MCP cargados correctamente')
    print(f'   mcp versión: {getattr(mcp, \"__version__\", \"desconocida\")}')
    print(f'   fastmcp versión: {getattr(fastmcp, \"__version__\", \"desconocida\")}')
except ImportError as e:
    print(f'❌ Error crítico: No se pudieron cargar los módulos MCP: {e}')
    print('   Los módulos MCP son esenciales para el funcionamiento del servicio.')
    sys.exit(1)
"

# Si python falla, salir con error
if [ $? -ne 0 ]; then
    echo "❌ Error crítico en la verificación de módulos MCP. El servicio no puede iniciar."
    exit 1
fi

echo "Iniciando servicio context-service..."
echo "Ambiente: ${ENVIRONMENT:-development}"

# Mostrar configuración para diagnóstico
echo "Configuración de conexiones:"
echo "- MongoDB URI: ${MONGODB_URI:-mongodb://not-configured:27017}"
echo "- Embedding Service: ${EMBEDDING_SERVICE_URL:-http://not-configured:8084}"

# Pre-compilar para detectar problemas de sintaxis
echo "Pre-compilando el código para verificar sintaxis..."
python -m py_compile main.py
if [ $? -ne 0 ]; then
    echo "❌ Error de compilación en main.py"
    exit 1
fi

# Iniciar la aplicación con parámetros adecuados
echo "Iniciando aplicación..."
if [ "${ENVIRONMENT:-development}" = "development" ]; then
    exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8083} --reload
else
    exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8083}
fi