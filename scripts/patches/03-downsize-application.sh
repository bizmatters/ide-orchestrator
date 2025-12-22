#!/bin/bash
set -euo pipefail

# IDE Orchestrator Application Resource Optimization for CI
# Reduces ide-orchestrator application resource requirements for CI environment

NAMESPACE="${NAMESPACE:-intelligence-platform}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-ide-orchestrator}"

echo "🔧 Optimizing IDE Orchestrator application resources for CI..."

# Check if deployment exists
if ! kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" &>/dev/null; then
    echo "⚠️  Deployment ${DEPLOYMENT_NAME} not found in namespace ${NAMESPACE}"
    echo "ℹ️  Skipping IDE Orchestrator optimization..."
    exit 0
fi

# Apply resource optimizations
echo "📉 Reducing IDE Orchestrator resource requirements..."

kubectl patch deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --type='merge' -p='
{
  "spec": {
    "replicas": 1,
    "template": {
      "spec": {
        "containers": [
          {
            "name": "ide-orchestrator",
            "resources": {
              "requests": {
                "memory": "128Mi",
                "cpu": "50m"
              },
              "limits": {
                "memory": "256Mi",
                "cpu": "200m"
              }
            },
            "env": [
              {
                "name": "GO_ENV",
                "value": "ci"
              },
              {
                "name": "LOG_LEVEL",
                "value": "info"
              },
              {
                "name": "MAX_CONNECTIONS",
                "value": "10"
              },
              {
                "name": "REQUEST_TIMEOUT",
                "value": "30s"
              }
            ]
          }
        ]
      }
    }
  }
}'

# Wait for deployment to be ready
echo "⏳ Waiting for IDE Orchestrator deployment to be ready..."
kubectl rollout status deployment/"${DEPLOYMENT_NAME}" \
    -n "${NAMESPACE}" \
    --timeout=300s

echo "✅ IDE Orchestrator resources optimized for CI"

# Show current resource usage
echo "📊 Current IDE Orchestrator resource usage:"
kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" -o wide
kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" -o wide