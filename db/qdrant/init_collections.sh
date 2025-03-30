#!/bin/bash
# db/qdrant/init_collections.sh
# Script para crear colecciones e índices en Qdrant

QDRANT_URL=${QDRANT_URL:-http://qdrant:6333}
GENERAL_COLLECTION=${QDRANT_COLLECTION_GENERAL:-general_knowledge}
PERSONAL_COLLECTION=${QDRANT_COLLECTION_PERSONAL:-personal_knowledge}
VECTOR_SIZE=${VECTOR_SIZE:-384}

echo "Esperando a que Qdrant esté disponible..."
max_retries=20
retries=0
while [ $retries -lt $max_retries ]; do
  if curl -s -f "${QDRANT_URL}/healthz" > /dev/null; then
    echo "Qdrant está disponible"
    break
  fi

  retries=$((retries+1))
  echo "Esperando a que Qdrant esté disponible (intento ${retries}/${max_retries})..."
  sleep 5
done

if [ $retries -eq $max_retries ]; then
  echo "Error: No se pudo conectar a Qdrant"
  exit 1
fi

# Función para crear una colección
create_collection() {
  local name=$1
  local vector_size=$2

  echo "Verificando si la colección '$name' existe..."

  # Verificación mejorada usando código de estado HTTP
  if ! curl -s -f "${QDRANT_URL}/collections/${name}" > /dev/null; then
    echo "Colección '$name' no encontrada. Creando..."

    curl -X PUT "${QDRANT_URL}/collections/${name}" \
      -H "Content-Type: application/json" \
      -d '{
        "vectors": {
          "size": '"${vector_size}"',
          "distance": "Cosine"
        },
        "optimizers_config": {
          "default_segment_number": 2
        },
        "replication_factor": 1,
        "write_consistency_factor": 1,
        "on_disk_payload": true
      }'

    if [ $? -eq 0 ]; then
      echo "Colección '$name' creada exitosamente"
    else
      echo "Error al crear la colección '$name'"
      return 1
    fi
  else
    echo "Colección '$name' ya existe"
  fi

  return 0
}

# Función para crear un índice
create_index() {
  local collection_name=$1
  local field_name=$2
  local field_schema=$3

  echo "Creando índice para '$field_name' en colección '$collection_name'..."

  # Verificar si el índice ya existe
  local index_check=$(curl -s "${QDRANT_URL}/collections/${collection_name}" | grep -c "\"${field_name}\"")

  if [ "$index_check" -gt 0 ]; then
    echo "El índice '$field_name' ya existe en la colección '$collection_name'"
    return 0
  fi

  curl -X PUT "${QDRANT_URL}/collections/${collection_name}/index" \
    -H "Content-Type: application/json" \
    -d '{
      "field_name": "'"${field_name}"'",
      "field_schema": "'"${field_schema}"'"
    }'

  if [ $? -eq 0 ]; then
    echo "Índice '$field_name' creado exitosamente en '$collection_name'"
  else
    echo "Error al crear índice '$field_name' en '$collection_name'"
    return 1
  fi

  return 0
}

# Crear colecciones
create_collection "${GENERAL_COLLECTION}" "${VECTOR_SIZE}" || exit 1
create_collection "${PERSONAL_COLLECTION}" "${VECTOR_SIZE}" || exit 1

# Campos comunes para ambas colecciones
common_fields=(
  "doc_id:keyword"
  "doc_title:text"
  "doc_type:keyword"
  "created_at:datetime"
  "metadata.score:float"
  "metadata.file_type:keyword"
)

# Crear índices para la colección general
create_index "${GENERAL_COLLECTION}" "metadata.area_id" "keyword" || echo "Advertencia: Fallo al crear índice area_id"
for field in "${common_fields[@]}"; do
  IFS=':' read -r field_name field_type <<< "$field"
  create_index "${GENERAL_COLLECTION}" "$field_name" "$field_type" || echo "Advertencia: Fallo al crear índice $field_name"
done

# Crear índices para la colección personal
create_index "${PERSONAL_COLLECTION}" "metadata.owner_id" "keyword" || echo "Advertencia: Fallo al crear índice owner_id"
for field in "${common_fields[@]}"; do
  IFS=':' read -r field_name field_type <<< "$field"
  create_index "${PERSONAL_COLLECTION}" "$field_name" "$field_type" || echo "Advertencia: Fallo al crear índice $field_name"
done

echo "Verificando configuración de colecciones..."
curl -s "${QDRANT_URL}/collections/${GENERAL_COLLECTION}" | grep -q "\"name\": \"${GENERAL_COLLECTION}\"" && \
  echo "✓ Colección ${GENERAL_COLLECTION} verificada" || echo "✗ Problema con colección ${GENERAL_COLLECTION}"
curl -s "${QDRANT_URL}/collections/${PERSONAL_COLLECTION}" | grep -q "\"name\": \"${PERSONAL_COLLECTION}\"" && \
  echo "✓ Colección ${PERSONAL_COLLECTION} verificada" || echo "✗ Problema con colección ${PERSONAL_COLLECTION}"

echo "Inicialización de Qdrant completada"