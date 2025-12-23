#!/bin/bash
set -euo pipefail

# Kubernetes Secret Availability Validation Script
# Waits for a specific Kubernetes secret to be available

# Parameters
SECRET_NAME="${1:-}"
NAMESPACE="${2:-intelligence-orchestrator}"

# Default values
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
SLEEP_INTERVAL="${SLEEP_INTERVAL:-2}"
TIMEOUT="${TIMEOUT:-60}"

if [[ -z "${SECRET_NAME}" ]]; then
    echo "❌ Usage: $0 <secret-name> [namespace]"
    exit 1
fi

echo "⏳ Waiting for secret ${SECRET_NAME} in namespace ${NAMESPACE}..."

# Function to check if secret exists and has data
check_secret() {
    # Check if secret exists
    if ! kubectl get secret "${SECRET_NAME}" -n "${NAMESPACE}" &>/dev/null; then
        return 1
    fi
    
    # Check if secret has data
    local data_count
    data_count=$(kubectl get secret "${SECRET_NAME}" -n "${NAMESPACE}" -o jsonpath='{.data}' | jq -r 'keys | length' 2>/dev/null || echo "0")
    
    if [[ "${data_count}" -gt 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Wait for secret to be ready
attempt=1
start_time=$(date +%s)

while [[ ${attempt} -le ${MAX_ATTEMPTS} ]]; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    
    if [[ ${elapsed} -ge ${TIMEOUT} ]]; then
        echo "❌ Timeout after ${TIMEOUT} seconds waiting for secret ${SECRET_NAME}"
        exit 1
    fi
    
    echo "🔍 Attempt ${attempt}/${MAX_ATTEMPTS}: Checking secret ${SECRET_NAME}..."
    
    if check_secret; then
        echo "✅ Secret ${SECRET_NAME} is ready!"
        
        # Show secret info (without revealing data)
        echo "📋 Secret details:"
        kubectl get secret "${SECRET_NAME}" -n "${NAMESPACE}" -o wide
        
        exit 0
    fi
    
    echo "⏳ Secret ${SECRET_NAME} not ready, waiting ${SLEEP_INTERVAL} seconds..."
    sleep ${SLEEP_INTERVAL}
    ((attempt++))
done

echo "❌ Secret ${SECRET_NAME} failed to become ready after ${MAX_ATTEMPTS} attempts"
echo "🔍 Current namespace secrets:"
kubectl get secrets -n "${NAMESPACE}"

exit 1