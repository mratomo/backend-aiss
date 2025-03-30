#!/bin/sh
# db/minio/minio
# Script para inicializar MinIO

set -e

# Configurar el cliente MinIO
mc config host add myminio http://minio:9000 ${MINIO_ROOT_USER:-minioadmin} ${MINIO_ROOT_PASSWORD:-minioadmin}

# Crear buckets
mc mb --ignore-existing myminio/shared-documents
mc mb --ignore-existing myminio/personal-documents

# Configurar políticas de acceso
mc anonymous set download myminio/shared-documents

echo "Inicialización de MinIO completada"