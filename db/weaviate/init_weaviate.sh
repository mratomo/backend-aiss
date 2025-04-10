#!/bin/sh
# Script para inicializar clases en Weaviate

# Variables de configuración
WEAVIATE_URL=${WEAVIATE_URL:-http://weaviate:8080}
GENERAL_CLASS=${WEAVIATE_CLASS_GENERAL:-GeneralKnowledge}
PERSONAL_CLASS=${WEAVIATE_CLASS_PERSONAL:-PersonalKnowledge}

echo "Esperando a que Weaviate esté disponible..."

# Enfoque tolerante con límite máximo de intentos
max_retries=30
retries=0

while [ $retries -lt $max_retries ]; do
  # Usar curl con timeout para evitar bloqueos
  if curl -s -m 2 "${WEAVIATE_URL}/v1/.well-known/ready" > /dev/null 2>&1; then
    echo "Weaviate está disponible"
    break
  fi

  retries=$((retries+1))
  echo "Esperando a que Weaviate esté disponible (intento ${retries}/${max_retries})..."
  sleep 3
done

# Incluso si no respondió después de los intentos, continuamos de todos modos
if [ $retries -eq $max_retries ]; then
  echo "ADVERTENCIA: No se pudo conectar a Weaviate después de $max_retries intentos."
  echo "Continuando de todos modos, asumiendo que estará disponible cuando se necesite."
fi

# Breve pausa para permitir inicialización
echo "Dando tiempo para que Weaviate se inicialice completamente..."
sleep 5

# Verificar si una clase existe
check_class() {
  local name=$1
  echo "Verificando si la clase '$name' existe..."
  
  # Verificación de la clase
  response=$(curl -s "${WEAVIATE_URL}/v1/schema/${name}")
  if [ $? -eq 0 ] && ! echo "$response" | grep -q "\"error\""; then
    echo "Clase '$name' ya existe"
    return 0
  else
    echo "Clase '$name' no existe o error en verificación: $response"
    return 1
  fi
}

# Crear una clase
create_class() {
  local name=$1

  if ! check_class "$name"; then
    echo "Clase '$name' no encontrada. Creando..."
    
    curl -X POST "${WEAVIATE_URL}/v1/schema" \
      -H "Content-Type: application/json" \
      -d '{
        "class": "'"${name}"'",
        "vectorizer": "none",
        "vectorIndexConfig": {
          "distance": "cosine"
        },
        "properties": [
          {
            "name": "doc_id",
            "dataType": ["string"],
            "description": "ID del documento",
            "indexFilterable": true,
            "indexSearchable": true
          },
          {
            "name": "owner_id",
            "dataType": ["string"],
            "description": "ID del propietario",
            "indexFilterable": true,
            "indexSearchable": true
          },
          {
            "name": "area_id",
            "dataType": ["string"],
            "description": "ID del área",
            "indexFilterable": true,
            "indexSearchable": true
          },
          {
            "name": "text",
            "dataType": ["text"],
            "description": "Texto del embedding",
            "indexFilterable": true,
            "indexSearchable": true,
            "tokenization": "field"
          },
          {
            "name": "metadata",
            "dataType": ["object"],
            "description": "Metadatos adicionales",
            "indexFilterable": false,
            "indexSearchable": false
          }
        ]
      }'

    if [ $? -eq 0 ]; then
      echo "Clase '$name' creada exitosamente"
    else
      echo "Error al crear la clase '$name'"
      exit 1
    fi
  fi
}

# Crear las clases
create_class "${GENERAL_CLASS}"
create_class "${PERSONAL_CLASS}"

# Verificar que todo se creó correctamente
echo "Verificando configuración de clases..."

# Función para verificar clase con detalles y manejo de fallos
verify_class() {
    local name=$1
    echo "Verificando clase $name..."
    
    # Usar curl con timeout para evitar bloqueos
    local response=$(curl -s -m 3 "${WEAVIATE_URL}/v1/schema/${name}" || echo '{"error":"timeout"}')
    
    if ! echo "$response" | grep -q "\"error\""; then
        echo "✓ Clase $name verificada correctamente"
        return 0
    else
        echo "✗ Problema con clase $name"
        
        # Si la clase no existe, intentar crearla de nuevo
        echo "  Intentando recrear clase $name..."
        create_class "$name"
        
        # No retornamos error para permitir que el script continúe
        echo "  Continuando con el resto del proceso..."
        return 0
    fi
}

# Verificar cada clase
verify_class "${GENERAL_CLASS}"
verify_class "${PERSONAL_CLASS}"

# Verificación final
echo "Esperar 5 segundos para verificación final..."
sleep 5
echo "Lista de clases disponibles:"
curl -s "${WEAVIATE_URL}/v1/schema" | grep -o '"class":"[^"]*"' || echo "No hay clases disponibles todavía"

echo "Inicialización de Weaviate completada"
exit 0