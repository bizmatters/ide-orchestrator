#!/bin/bash
set -euo pipefail

# Go Service Runtime Execution Script
# Starts the ide-orchestrator service with proper configuration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default values
PORT="${PORT:-8080}"
LOG_LEVEL="${LOG_LEVEL:-info}"
GO_ENV="${GO_ENV:-production}"

echo "🚀 Starting ide-orchestrator service..."

cd "${PROJECT_ROOT}"

# Validate environment variables
required_vars=(
    "DATABASE_URL"
    "JWT_SECRET"
)

for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        echo "❌ Required environment variable ${var} is not set"
        exit 1
    fi
done

# Wait for dependencies in production
if [[ "${GO_ENV}" != "development" ]]; then
    echo "⏳ Waiting for dependencies..."
    "${SCRIPT_DIR}/../helpers/wait-for-postgres.sh"
    
    if [[ -n "${SPEC_ENGINE_URL:-}" ]]; then
        "${SCRIPT_DIR}/../helpers/wait-for-deepagents-runtime.sh"
    fi
fi

# Run database migrations
echo "🗄️  Running database migrations..."
if [[ -f "${SCRIPT_DIR}/run-migrations.sh" ]]; then
    "${SCRIPT_DIR}/run-migrations.sh"
else
    echo "⚠️  No migration script found, skipping..."
fi

# Start the service
echo "🎯 Starting service on port ${PORT}..."
exec ./bin/ide-orchestrator \
    --port="${PORT}" \
    --log-level="${LOG_LEVEL}" \
    --env="${GO_ENV}"