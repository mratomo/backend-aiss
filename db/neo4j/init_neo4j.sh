#!/bin/bash

# Script para inicializar Neo4j con constraints e indices para GraphRAG
# Este script se ejecuta como parte del proceso de inicialización de Neo4j en Docker

# Variables
NEO4J_HOST=${NEO4J_HOST:-neo4j}
NEO4J_PORT=${NEO4J_PORT:-7687}
NEO4J_USER=${NEO4J_USER:-neo4j}
NEO4J_PASSWORD=${NEO4J_PASSWORD:-supersecret}
MAX_ATTEMPTS=${MAX_ATTEMPTS:-60}
SLEEP_SECONDS=${SLEEP_SECONDS:-5}

echo "Initiating Neo4j setup for GraphRAG..."
echo "Connecting to Neo4j at $NEO4J_HOST:$NEO4J_PORT..."

# Esperar a que Neo4j esté disponible
attempt=1
while [ $attempt -le $MAX_ATTEMPTS ]; do
    echo "Attempt $attempt/$MAX_ATTEMPTS: Waiting for Neo4j to be ready..."
    
    # Verificar si podemos conectarnos a Neo4j usando cypher-shell
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u $NEO4J_USER -p $NEO4J_PASSWORD \
        "RETURN 'Neo4j is ready!' AS status;" 2>/dev/null; then
        echo "Neo4j is ready!"
        break
    fi
    
    if [ $attempt -eq $MAX_ATTEMPTS ]; then
        echo "Failed to connect to Neo4j after $MAX_ATTEMPTS attempts. Exiting."
        exit 1
    fi
    
    attempt=$((attempt + 1))
    sleep $SLEEP_SECONDS
done

echo "Creating constraints and indexes for GraphRAG..."

# Crear constraints para unicidad de IDs
cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u $NEO4J_USER -p $NEO4J_PASSWORD <<EOF
CREATE CONSTRAINT unique_database_id IF NOT EXISTS
FOR (d:Database)
REQUIRE d.connection_id IS UNIQUE;

CREATE CONSTRAINT unique_table_id IF NOT EXISTS
FOR (t:Table)
REQUIRE t.table_id IS UNIQUE;

CREATE CONSTRAINT unique_column_id IF NOT EXISTS
FOR (c:Column)
REQUIRE c.column_id IS UNIQUE;

CREATE INDEX database_name_index IF NOT EXISTS
FOR (d:Database)
ON (d.name);

CREATE INDEX table_name_index IF NOT EXISTS
FOR (t:Table)
ON (t.name);

CREATE INDEX column_name_index IF NOT EXISTS
FOR (c:Column)
ON (c.name);

CREATE INDEX table_schema_index IF NOT EXISTS
FOR (t:Table)
ON (t.schema);

RETURN 'Constraints and indexes created successfully!' AS status;
EOF

if [ $? -eq 0 ]; then
    echo "Neo4j setup completed successfully."
else
    echo "Neo4j setup encountered errors."
    exit 1
fi

# Verificar que los plugins APOC y GDS estén disponibles
cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u $NEO4J_USER -p $NEO4J_PASSWORD <<EOF
CALL dbms.procedures() YIELD name 
WHERE name STARTS WITH 'apoc.' OR name STARTS WITH 'gds.'
RETURN DISTINCT split(name, '.')[0] AS package, count(*) AS count;
EOF

echo "Neo4j initialization complete."