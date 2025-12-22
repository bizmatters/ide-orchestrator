#!/bin/bash
set -euo pipefail

# Database Migration Execution Script
# Runs database migrations using golang-migrate

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default values
MIGRATIONS_DIR="${MIGRATIONS_DIR:-${PROJECT_ROOT}/migrations}"
POSTGRES_HOST="${POSTGRES_HOST}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB}"
POSTGRES_USER="${POSTGRES_USER}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"

echo "🗄️  Running database migrations..."

# Validate required environment variables
if [[ -z "${POSTGRES_HOST:-}" ]]; then
    echo "❌ POSTGRES_HOST environment variable is required"
    exit 1
fi

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    echo "❌ POSTGRES_PASSWORD environment variable is required"
    exit 1
fi

# Check if migrations directory exists
if [[ ! -d "${MIGRATIONS_DIR}" ]]; then
    echo "⚠️  Migrations directory not found: ${MIGRATIONS_DIR}"
    echo "ℹ️  Skipping migrations..."
    exit 0
fi

# Construct DATABASE_URL
export DATABASE_URL="postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}?sslmode=disable"

# Check if migrate tool is available
if ! command -v migrate &> /dev/null; then
    echo "⚠️  golang-migrate tool not found"
    echo "ℹ️  Installing migrate tool..."
    
    # Install migrate tool
    if command -v go &> /dev/null; then
        go install -tags 'postgres' github.com/golang-migrate/migrate/v4/cmd/migrate@latest
        export PATH=$PATH:$(go env GOPATH)/bin
    else
        echo "❌ Go is not installed, cannot install migrate tool"
        exit 1
    fi
fi

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
"${SCRIPT_DIR}/../helpers/wait-for-postgres.sh"

# Run migrations
echo "📋 Applying database migrations..."
migrate \
    -path "${MIGRATIONS_DIR}" \
    -database "${DATABASE_URL}" \
    up

# Check migration status
echo "📊 Migration status:"
migrate \
    -path "${MIGRATIONS_DIR}" \
    -database "${DATABASE_URL}" \
    version

echo "✅ Database migrations completed successfully!"