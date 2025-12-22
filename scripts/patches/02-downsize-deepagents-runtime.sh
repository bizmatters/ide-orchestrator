#!/bin/bash
set -euo pipefail

# DeepAgents Runtime Resource Optimization for CI
# Reduces deepagents-runtime service resource requirements for CI environment

NAMESPACE="${NAMESPACE:-intelligence-deepagents}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-deepagents-runtime}"

echo "🔧 Optimizing DeepAgents Runtime resources for CI..."

# Check if deployment exists
if ! kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" &>/dev/null; then
    echo "⚠️  Deployment ${DEPLOYMENT_NAME} not found in namespace ${NAMESPACE}"
    echo "ℹ️  Skipping DeepAgents Runtime optimization..."
    exit 0
fi

# Apply resource optimizations
echo "📉 Reducing DeepAgents Runtime resource requirements..."

kubectl patch deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --type='merge' -p='
{
  "spec": {
    "replicas": 1,
    "template": {
      "spec": {
        "containers": [
          {
            "name": "deepagents-runtime",
            "resources": {
              "requests": {
                "memory": "512Mi",
                "cpu": "200m"
              },
              "limits": {
                "memory": "1Gi",
                "cpu": "1000m"
              }
            },
            "env": [
              {
                "name": "WORKERS",
                "value": "2"
              },
              {
                "name": "MAX_CONCURRENT_REQUESTS",
                "value": "10"
              },
              {
                "name": "CACHE_SIZE",
                "value": "100"
              }
            ]
          }
        ]
      }
    }
  }
}'

# Wait for deployment to be ready
echo "⏳ Waiting for DeepAgents Runtime deployment to be ready..."
kubectl rollout status deployment/"${DEPLOYMENT_NAME}" \
    -n "${NAMESPACE}" \
    --timeout=300s

echo "✅ DeepAgents Runtime resources optimized for CI"

# Show current resource usage
echo "📊 Current DeepAgents Runtime resource usage:"
kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" -o wide
kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" -o wide