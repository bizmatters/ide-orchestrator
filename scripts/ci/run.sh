#!/bin/bash
set -euo pipefail

# ==============================================================================
# Tier 3 CI Script: Service Entrypoint
# ==============================================================================
# Purpose: Start the ide-orchestrator service inside the production container
# Owner: Backend Developer
# Called by: Dockerfile ENTRYPOINT
#
# Environment Variables (Container runtime):
#   - PORT: HTTP server port (default: 8080)
#   - LOG_LEVEL: Logging verbosity (default: info)
#   - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
#   - IDEO_SPEC_ENGINE_URL: deepagents-runtime service URL
#   - JWT_SECRET: JWT signing secret
#
# Assumptions:
#   - Dependencies already installed (handled by Dockerfile)
#   - Infrastructure pre-provisioned (PostgreSQL)
#   - Service connects using environment variables from Kubernetes Secrets
# ==============================================================================

# Configuration
PORT="${PORT:-8080}"
LOG_LEVEL="${LOG_LEVEL:-info}"

echo "================================================================================"
echo "Starting IDE Orchestrator Service (CI/Production Mode)"
echo "================================================================================"
echo "  Port:                 ${PORT}"
echo "  Log Level:            ${LOG_LEVEL}"
echo "  Postgres Host:        ${POSTGRES_HOST:-not set}"
echo "  Spec Engine URL:      ${SPEC_ENGINE_URL:-${IDEO_SPEC_ENGINE_URL:-not set}}"
echo "================================================================================"

# 1. Construct DATABASE_URL from platform-provided granular variables
# These are injected via envFrom: ide-orchestrator-db-conn
if [[ -n "${POSTGRES_HOST:-}" ]]; then
    export DATABASE_URL="postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}?sslmode=disable"
    echo "🔍 Constructed DATABASE_URL for ${POSTGRES_HOST}"
    
    # Wait up to 30 seconds for the port to open (additional safety check)
    echo "🔍 Verifying database connectivity..."
    TIMEOUT=30
    while ! nc -z "$POSTGRES_HOST" "$POSTGRES_PORT" && [ $TIMEOUT -gt 0 ]; do
        echo "Waiting for database port... ($TIMEOUT seconds remaining)"
        sleep 1
        let TIMEOUT-=1
    done
    
    if [ $TIMEOUT -eq 0 ]; then
        echo "⚠️ Database port check timed out, but continuing (app will retry)"
    else
        echo "✅ Database port is open"
    fi
fi

# Validate required environment variables
if [ -z "${POSTGRES_HOST:-}" ]; then
    echo "❌ ERROR: POSTGRES_HOST environment variable is required"
    exit 1
fi

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "❌ ERROR: POSTGRES_PASSWORD environment variable is required"
    exit 1
fi

if [ -z "${JWT_SECRET:-}" ]; then
    echo "❌ ERROR: JWT_SECRET environment variable is required"
    exit 1
fi

# 2. Map platform environment variables to application variables
# Map spec engine URL from platform naming to application naming
if [[ -n "${IDEO_SPEC_ENGINE_URL:-}" ]]; then
    export DEEPAGENTS_RUNTIME_URL="${IDEO_SPEC_ENGINE_URL}"
    echo "🔍 Mapped DEEPAGENTS_RUNTIME_URL to ${DEEPAGENTS_RUNTIME_URL}"
elif [[ -n "${SPEC_ENGINE_URL:-}" ]]; then
    export DEEPAGENTS_RUNTIME_URL="${SPEC_ENGINE_URL}"
    echo "🔍 Mapped DEEPAGENTS_RUNTIME_URL to ${DEEPAGENTS_RUNTIME_URL}"
else
    echo "⚠️ No spec engine URL provided, using default"
fi

echo "🔍 Final DEEPAGENTS_RUNTIME_URL: ${DEEPAGENTS_RUNTIME_URL:-not set}"

# 3. Start the application using uvicorn
# - Dependencies pre-installed in container
# - Application code at /app/ 
# - Uvicorn runs the FastAPI app from api.main:app
echo "🚀 Starting ide-orchestrator service..."

exec uvicorn api.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --log-level "${LOG_LEVEL}" \
    --no-access-log \
    --proxy-headers