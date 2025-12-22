#!/bin/bash
set -euo pipefail

# CI Deploy Script for ide-orchestrator
# GitOps service deployment automation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default values
ENVIRONMENT="${1:-ci}"
IMAGE_TAG="${2:-latest}"
NAMESPACE="${NAMESPACE:-intelligence-platform}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300}"

echo "🚀 Deploying ide-orchestrator to ${ENVIRONMENT} environment..."

cd "${PROJECT_ROOT}"

# Validate environment
case "${ENVIRONMENT}" in
    ci|staging|production)
        echo "✅ Valid environment: ${ENVIRONMENT}"
        ;;
    *)
        echo "❌ Invalid environment: ${ENVIRONMENT}. Must be ci, staging, or production"
        exit 1
        ;;
esac

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

# Check cluster connectivity
echo "🔍 Checking cluster connectivity..."
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to Kubernetes cluster"
    exit 1
fi

# Create namespace if it doesn't exist
echo "📁 Ensuring namespace exists..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Apply GitOps manifests
echo "📋 Applying Kubernetes manifests..."
if [[ -d "k8s/${ENVIRONMENT}" ]]; then
    # Environment-specific manifests
    kubectl apply -f "k8s/${ENVIRONMENT}/" -n "${NAMESPACE}"
elif [[ -d "k8s/base" ]]; then
    # Base manifests with kustomization
    kubectl apply -k "k8s/base" -n "${NAMESPACE}"
else
    echo "❌ No Kubernetes manifests found in k8s/${ENVIRONMENT} or k8s/base"
    exit 1
fi

# Update image tag if provided
if [[ "${IMAGE_TAG}" != "latest" ]]; then
    echo "🏷️  Updating image tag to ${IMAGE_TAG}..."
    kubectl set image deployment/ide-orchestrator \
        ide-orchestrator="ide-orchestrator:${IMAGE_TAG}" \
        -n "${NAMESPACE}"
fi

# Wait for deployment to be ready
echo "⏳ Waiting for deployment to be ready..."
kubectl rollout status deployment/ide-orchestrator \
    -n "${NAMESPACE}" \
    --timeout="${WAIT_TIMEOUT}s"

# Verify deployment
echo "🔍 Verifying deployment..."
READY_REPLICAS=$(kubectl get deployment ide-orchestrator -n "${NAMESPACE}" -o jsonpath='{.status.readyReplicas}')
DESIRED_REPLICAS=$(kubectl get deployment ide-orchestrator -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}')

if [[ "${READY_REPLICAS}" == "${DESIRED_REPLICAS}" ]]; then
    echo "✅ Deployment successful: ${READY_REPLICAS}/${DESIRED_REPLICAS} replicas ready"
else
    echo "❌ Deployment failed: ${READY_REPLICAS}/${DESIRED_REPLICAS} replicas ready"
    exit 1
fi

# Show service endpoints
echo "🌐 Service endpoints:"
kubectl get services -n "${NAMESPACE}" -l app=ide-orchestrator

echo "🎉 Deployment completed successfully!"