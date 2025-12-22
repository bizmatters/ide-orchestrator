#!/bin/bash
set -euo pipefail

# External Secrets Operator Validation Script
# Waits for External Secrets to be synced and available

# Default values
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
SLEEP_INTERVAL="${SLEEP_INTERVAL:-2}"
TIMEOUT="${TIMEOUT:-60}"
NAMESPACE="${NAMESPACE:-intelligence-platform}"

# Secret names to wait for
SECRETS=(
    "ide-orchestrator-db-app"
    "ide-orchestrator-secrets"
)

echo "⏳ Waiting for External Secrets in namespace ${NAMESPACE}..."

# Function to check if a secret exists and is ready
check_secret() {
    local secret_name="$1"
    
    # Check if secret exists
    if ! kubectl get secret "${secret_name}" -n "${NAMESPACE}" &>/dev/null; then
        return 1
    fi
    
    # Check if secret has data
    local data_count
    data_count=$(kubectl get secret "${secret_name}" -n "${NAMESPACE}" -o jsonpath='{.data}' | jq -r 'keys | length' 2>/dev/null || echo "0")
    
    if [[ "${data_count}" -gt 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check ExternalSecret status
check_external_secret_status() {
    local secret_name="$1"
    local external_secret_name="${secret_name}-external"
    
    # Check if ExternalSecret exists
    if kubectl get externalsecret "${external_secret_name}" -n "${NAMESPACE}" &>/dev/null; then
        # Check if ExternalSecret is ready
        local status
        status=$(kubectl get externalsecret "${external_secret_name}" -n "${NAMESPACE}" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
        
        if [[ "${status}" == "True" ]]; then
            return 0
        fi
    fi
    
    return 1
}

# Wait for all secrets to be ready
attempt=1
start_time=$(date +%s)

while [[ ${attempt} -le ${MAX_ATTEMPTS} ]]; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    
    if [[ ${elapsed} -ge ${TIMEOUT} ]]; then
        echo "❌ Timeout after ${TIMEOUT} seconds waiting for External Secrets"
        exit 1
    fi
    
    echo "🔍 Attempt ${attempt}/${MAX_ATTEMPTS}: Checking External Secrets..."
    
    all_ready=true
    
    for secret in "${SECRETS[@]}"; do
        if check_secret "${secret}"; then
            echo "✅ Secret ${secret} is ready"
        else
            echo "⏳ Secret ${secret} not ready"
            all_ready=false
            
            # Show ExternalSecret status for debugging
            if check_external_secret_status "${secret}"; then
                echo "ℹ️  ExternalSecret for ${secret} is ready, waiting for sync..."
            else
                echo "⚠️  ExternalSecret for ${secret} not ready"
            fi
        fi
    done
    
    if [[ "${all_ready}" == "true" ]]; then
        echo "✅ All External Secrets are ready!"
        exit 0
    fi
    
    echo "⏳ Waiting ${SLEEP_INTERVAL} seconds for secrets to sync..."
    sleep ${SLEEP_INTERVAL}
    ((attempt++))
done

echo "❌ External Secrets failed to become ready after ${MAX_ATTEMPTS} attempts"
echo "🔍 Current secret status:"
for secret in "${SECRETS[@]}"; do
    kubectl get secret "${secret}" -n "${NAMESPACE}" -o wide 2>/dev/null || echo "Secret ${secret} not found"
done

exit 1