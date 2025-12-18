#!/bin/bash
# Convenience script to run IDE Orchestrator

# Load environment variables
export DATABASE_URL="${DATABASE_URL:-postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable}"
export JWT_SECRET="${JWT_SECRET:-dev-secret-key-change-in-production}"
export SPEC_ENGINE_URL="${SPEC_ENGINE_URL:-http://spec-engine-service:8001}"
export PORT="${PORT:-8080}"


# Run the application
echo "Starting IDE Orchestrator on port $PORT..."
./bin/ide-orchestrator
