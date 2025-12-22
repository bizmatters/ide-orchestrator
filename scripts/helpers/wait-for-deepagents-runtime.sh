#!/bin/bash
set -euo pipefail

# DeepAgents Runtime Service Readiness Validation Script
# Waits for deepagents-runtime service to be ready

# Default values
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
SLEEP_INTERVAL="${SLEEP_INTERVAL:-2}"
TIMEOUT="${TIMEOUT:-60}"

# Service connection parameters
SERVICE_URL="${SPEC_ENGINE_URL:-http://deepagents-runtime.intelligence-deepagents.svc:8080}"
HEALTH_ENDPOINT="${SERVICE_URL}/api/health"

echo "⏳ Waiting for DeepAgents Runtime at ${SERVICE_URL}..."

# Function to test service health
test_service_health() {
    local response
    local http_code
    
    # Use curl to test the health endpoint
    response=$(curl -s -w "%{http_code}" "${HEALTH_ENDPOINT}" 2>/dev/null || echo "000")
    http_code="${response: -3}"
    
    if [[ "${http_code}" == "200" ]]; then
        return 0
    else
        return 1
    fi
}

# Function to test basic connectivity
test_connectivity() {
    # Extract host and port from URL
    local host_port
    host_port=$(echo "${SERVICE_URL}" | sed -E 's|^https?://([^/]+).*|\1|')
    
    # Test if we can connect to the service
    if command -v nc &> /dev/null; then
        # Use netcat if available
        local host port
        host=$(echo "${host_port}" | cut -d: -f1)
        port=$(echo "${host_port}" | cut -d: -f2)
        nc -z "${host}" "${port}" 2>/dev/null
    else
        # Fallback to curl for basic connectivity
        curl -s --connect-timeout 5 "${SERVICE_URL}" &>/dev/null
    fi
}

# Wait for service to be ready
attempt=1
start_time=$(date +%s)

while [[ ${attempt} -le ${MAX_ATTEMPTS} ]]; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    
    if [[ ${elapsed} -ge ${TIMEOUT} ]]; then
        echo "❌ Timeout after ${TIMEOUT} seconds waiting for DeepAgents Runtime"
        exit 1
    fi
    
    echo "🔍 Attempt ${attempt}/${MAX_ATTEMPTS}: Testing DeepAgents Runtime..."
    
    # First test basic connectivity
    if test_connectivity; then
        echo "🔗 Basic connectivity established"
        
        # Then test health endpoint
        if test_service_health; then
            echo "✅ DeepAgents Runtime is ready!"
            exit 0
        else
            echo "⚠️  Service responding but health check failed"
        fi
    else
        echo "🔌 Cannot connect to service"
    fi
    
    echo "⏳ DeepAgents Runtime not ready, waiting ${SLEEP_INTERVAL} seconds..."
    sleep ${SLEEP_INTERVAL}
    ((attempt++))
done

echo "❌ DeepAgents Runtime failed to become ready after ${MAX_ATTEMPTS} attempts"
echo "🔍 Final connectivity test:"
curl -v "${HEALTH_ENDPOINT}" || true
exit 1