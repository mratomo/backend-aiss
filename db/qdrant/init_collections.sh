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
  if curl -s "${QDRANT_URL}/collections/${name}" | grep -q "not found"; then
    echo "Creando colección '$name'..."

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

    echo
    echo "Colección '$name' creada exitosamente"
  else
    echo "Colección '$name' ya existe"
  fi
}

# Función para crear un índice
create_index() {
  local collection_name=$1
  local field_name=$2
  local field_schema=$3

  echo "Creando índice para '$field_name' en colección '$collection_name'..."

  curl -X PUT "${QDRANT_URL}/collections/${collection_name}/index" \
    -H "Content-Type: application/json" \
    -d '{
      "field_name": "'"${field_name}"'",
      "field_schema": "'"${field_schema}"'"
    }'

  echo
}

# Crear colecciones
create_collection "${GENERAL_COLLECTION}" "${VECTOR_SIZE}"
create_collection "${PERSONAL_COLLECTION}" "${VECTOR_SIZE}"

# Crear índices para la colección general
create_index "${GENERAL_COLLECTION}" "area_id" "keyword"
create_index "${GENERAL_COLLECTION}" "doc_id" "keyword"
create_index "${GENERAL_COLLECTION}" "doc_title" "text"
create_index "${GENERAL_COLLECTION}" "doc_type" "keyword"
create_index "${GENERAL_COLLECTION}" "created_at" "datetime"

# Crear índices para la colección personal
create_index "${PERSONAL_COLLECTION}" "owner_id" "keyword"
create_index "${PERSONAL_COLLECTION}" "doc_id" "keyword"
create_index "${PERSONAL_COLLECTION}" "doc_title" "text"
create_index "${PERSONAL_COLLECTION}" "doc_type" "keyword"
create_index "${PERSONAL_COLLECTION}" "created_at" "datetime"

echo "Inicialización de Qdrant completada"