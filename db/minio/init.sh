#!/bin/bash
# db/minio/init.sh
# Script para inicializar MinIO SOLO PARA REFERENCIA, SE CONFIGURA EN DOCKER COMPOSE

set -e

# Variables de entorno con valores por defecto
MINIO_SERVER=${MINIO_SERVER:-minio:9000}
MINIO_USER=${MINIO_ROOT_USER:-minioadmin}
MINIO_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
SHARED_BUCKET=${MINIO_SHARED_BUCKET:-shared-documents}
PERSONAL_BUCKET=${MINIO_PERSONAL_BUCKET:-personal-documents}

# Función para verificar disponibilidad de MinIO
check_minio_available() {
  echo "Verificando disponibilidad de MinIO en $MINIO_SERVER..."
  local max_attempts=30
  local attempt=0

  while [ $attempt -lt $max_attempts ]; do
    if mc admin info myminio &>/dev/null; then
      echo "MinIO está disponible"
      return 0
    fi

    attempt=$((attempt + 1))
    echo "Esperando a que MinIO esté disponible (intento $attempt/$max_attempts)..."
    sleep 2
  done

  echo "Error: MinIO no está disponible después de $max_attempts intentos"
  return 1
}

# Configurar el cliente MinIO
echo "Configurando cliente MinIO..."
mc config host add myminio http://$MINIO_SERVER $MINIO_USER $MINIO_PASSWORD

# Verificar disponibilidad
check_minio_available || exit 1

# Crear buckets
echo "Creando buckets..."
mc mb --ignore-existing myminio/$SHARED_BUCKET
echo "Bucket $SHARED_BUCKET creado o ya existente"

mc mb --ignore-existing myminio/$PERSONAL_BUCKET
echo "Bucket $PERSONAL_BUCKET creado o ya existente"

# Configurar políticas de acceso
echo "Configurando políticas de acceso..."
mc anonymous set download myminio/$SHARED_BUCKET
echo "Permisos de descarga anónima establecidos para $SHARED_BUCKET"

# Verificar que los buckets se crearon correctamente
echo "Verificando buckets..."
if mc ls myminio | grep -q $SHARED_BUCKET; then
  echo "✓ Bucket $SHARED_BUCKET verificado"
else
  echo "✗ Error: Bucket $SHARED_BUCKET no encontrado"
  exit 1
fi

if mc ls myminio | grep -q $PERSONAL_BUCKET; then
  echo "✓ Bucket $PERSONAL_BUCKET verificado"
else
  echo "✗ Error: Bucket $PERSONAL_BUCKET no encontrado"
  exit 1
fi

# Crear una pequeña estructura de directorios de ejemplo
echo "Creando estructura de directorios inicial..."
mc mb --ignore-existing myminio/$SHARED_BUCKET/public
mc mb --ignore-existing myminio/$SHARED_BUCKET/templates
mc mb --ignore-existing myminio/$PERSONAL_BUCKET/samples

echo "Inicialización de MinIO completada exitosamente"