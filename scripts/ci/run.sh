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
#   - DATABASE_URL: PostgreSQL connection string
#   - DEEPAGENTS_RUNTIME_URL: deepagents-runtime service URL
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
echo "  Deepagents Runtime URL:      ${DEEPAGENTS_RUNTIME_URL:-not set}"
echo "================================================================================"

# Validate required environment variables
if [ -z "${DATABASE_URL:-}" ]; then
    echo "❌ ERROR: DATABASE_URL environment variable is required"
    exit 1
fi

# 2. Map platform environment variables to application variables
# Map spec engine URL from platform naming to application naming
if [[ -n "${DEEPAGENTS_RUNTIME_URL:-}" ]]; then
    export DEEPAGENTS_RUNTIME_URL="${DEEPAGENTS_RUNTIME_URL}"
    echo "🔍 Mapped DEEPAGENTS_RUNTIME_URL to ${DEEPAGENTS_RUNTIME_URL}"
elif [[ -n "${DEEPAGENTS_RUNTIME_URL:-}" ]]; then
    export DEEPAGENTS_RUNTIME_URL="${DEEPAGENTS_RUNTIME_URL}"
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