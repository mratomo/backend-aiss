#!/bin/sh
# Enhanced MinIO init script with robust error handling

echo "Starting MinIO initialization..."

# Variables
MAX_RETRIES=30
RETRY_INTERVAL=5
MINIO_SERVER="http://minio:9000"
MINIO_USER="minioadmin"
MINIO_PASSWORD="minioadmin"

# Wait for MinIO to be available with proper checking
echo "Waiting for MinIO to be available at $MINIO_SERVER..."
for i in $(seq 1 $MAX_RETRIES); do
    if mc alias set local $MINIO_SERVER $MINIO_USER $MINIO_PASSWORD &>/dev/null; then
        echo "✓ Successfully connected to MinIO on attempt $i"
        break
    fi
    
    if [ $i -eq $MAX_RETRIES ]; then
        echo "✗ Failed to connect to MinIO after $MAX_RETRIES attempts"
        exit 1
    fi
    
    echo "- Attempt $i/$MAX_RETRIES: MinIO not yet available, waiting $RETRY_INTERVAL seconds..."
    sleep $RETRY_INTERVAL
done

# Verify connection is working by testing a basic command
echo "Verifying MinIO connection..."
if ! mc ls local &>/dev/null; then
    echo "✗ Failed to list buckets - connection appears broken"
    
    # Try to reconnect
    echo "Attempting to reconnect..."
    mc alias set local $MINIO_SERVER $MINIO_USER $MINIO_PASSWORD
    
    # Verify again
    if ! mc ls local &>/dev/null; then
        echo "✗ Reconnection failed - aborting"
        exit 1
    fi
else
    echo "✓ Connection verified successfully"
fi

# Create required buckets
echo "Creating required buckets..."
BUCKETS=("documents" "uploads" "temp" "personal-documents" "shared-documents")

for bucket in "${BUCKETS[@]}"; do
    echo "- Creating bucket: local/$bucket"
    if mc mb --ignore-existing local/$bucket; then
        echo "  ✓ Bucket local/$bucket created or already exists"
    else
        echo "  ✗ Failed to create bucket local/$bucket"
    fi
done

# Wait a moment for bucket creation to stabilize
sleep 2

# Set access policies
echo "Setting access policies..."
POLICIES=(
    "download:documents"
    "upload:uploads"
    "public:temp"
    "download:personal-documents"
    "download:shared-documents"
)

for policy_pair in "${POLICIES[@]}"; do
    policy="${policy_pair%%:*}"
    bucket="${policy_pair#*:}"
    
    echo "- Setting $policy policy on local/$bucket"
    if mc anonymous set $policy local/$bucket; then
        echo "  ✓ Policy set successfully"
    else
        echo "  ✗ Failed to set policy, retrying once..."
        # Retry once
        sleep 2
        mc anonymous set $policy local/$bucket || echo "  ✗ Policy setting failed on retry"
    fi
done

# Verify buckets exist
echo "Verifying buckets..."
mc ls local

echo "MinIO initialization complete!"
exit 0