#!/bin/bash
set -euo pipefail

# PostgreSQL Readiness Validation Script
# Waits for PostgreSQL database to be ready

# Default values
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
SLEEP_INTERVAL="${SLEEP_INTERVAL:-2}"
TIMEOUT="${TIMEOUT:-60}"

# Database connection parameters
POSTGRES_HOST="${POSTGRES_HOST:-ide-orchestrator-db-rw.intelligence-platform.svc.cluster.local}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ide-orchestrator-db}"

echo "⏳ Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}..."

# Function to test database connection
test_connection() {
    if [[ -n "${DATABASE_URL:-}" ]]; then
        # Use DATABASE_URL if available
        psql "${DATABASE_URL}" -c "SELECT 1;" &>/dev/null
    else
        # Use individual parameters
        PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
            -h "${POSTGRES_HOST}" \
            -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" \
            -d "${POSTGRES_DB}" \
            -c "SELECT 1;" &>/dev/null
    fi
}

# Wait for PostgreSQL to be ready
attempt=1
start_time=$(date +%s)

while [[ ${attempt} -le ${MAX_ATTEMPTS} ]]; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    
    if [[ ${elapsed} -ge ${TIMEOUT} ]]; then
        echo "❌ Timeout after ${TIMEOUT} seconds waiting for PostgreSQL"
        exit 1
    fi
    
    echo "🔍 Attempt ${attempt}/${MAX_ATTEMPTS}: Testing PostgreSQL connection..."
    
    if test_connection; then
        echo "✅ PostgreSQL is ready!"
        exit 0
    fi
    
    echo "⏳ PostgreSQL not ready, waiting ${SLEEP_INTERVAL} seconds..."
    sleep ${SLEEP_INTERVAL}
    ((attempt++))
done

echo "❌ PostgreSQL failed to become ready after ${MAX_ATTEMPTS} attempts"
exit 1