#!/bin/bash
set -euo pipefail

# Master Patch Application Script
# Applies all CI environment optimizations

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${NAMESPACE:-intelligence-platform}"

echo "🔧 Applying all CI environment patches..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed"
    exit 1
fi

# Check cluster connectivity
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to Kubernetes cluster"
    exit 1
fi

# Apply patches in order
patches=(
    "01-downsize-postgres.sh"
    "02-downsize-deepagents-runtime.sh"
    "03-downsize-application.sh"
)

for patch in "${patches[@]}"; do
    patch_file="${SCRIPT_DIR}/${patch}"
    
    if [[ -f "${patch_file}" ]]; then
        echo "🔧 Applying patch: ${patch}"
        bash "${patch_file}"
        
        if [[ $? -eq 0 ]]; then
            echo "✅ Patch ${patch} applied successfully"
        else
            echo "❌ Patch ${patch} failed"
            exit 1
        fi
    else
        echo "⚠️  Patch file not found: ${patch_file}"
    fi
done

echo "✅ All CI environment patches applied successfully!"

# Show resource usage after patches
echo "📊 Resource usage after patches:"
kubectl top nodes 2>/dev/null || echo "Metrics not available"
kubectl get pods -n "${NAMESPACE}" -o wide