#!/bin/bash
set -euo pipefail

# ==============================================================================
# Tier 1 CI Script: Setup Dependencies for IDE Orchestrator Testing
# ==============================================================================
# Purpose: Clone, build, and deploy deepagents-runtime service for testing
# Called by: GitHub Actions workflow before ide-orchestrator deployment
# Usage: ./setup-dependencies.sh
#
# This script ensures deepagents-runtime service is available for ide-orchestrator
# integration tests by:
# 1. Cloning deepagents-runtime repository
# 2. Building deepagents-runtime Docker image
# 3. Deploying deepagents-runtime using its own scripts
# 4. Validating deepagents-runtime is healthy
# ==============================================================================

# Configuration
DEEPAGENTS_REPO="https://github.com/arun4infra/deepagents-runtime.git"
DEEPAGENTS_DIR="/tmp/deepagents-runtime"
DEEPAGENTS_NAMESPACE="intelligence-deepagents"
DEEPAGENTS_IMAGE="deepagents-runtime:ci-test"
KIND_CLUSTER_NAME="zerotouch-preview"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[SETUP-DEPS]${NC} $*"; }
log_success() { echo -e "${GREEN}[SETUP-DEPS]${NC} $*"; }
log_error() { echo -e "${RED}[SETUP-DEPS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[SETUP-DEPS]${NC} $*"; }

echo "================================================================================"
echo "Setting up DeepAgents Runtime Dependency for IDE Orchestrator Testing"
echo "================================================================================"
echo "  Target Namespace: ${DEEPAGENTS_NAMESPACE}"
echo "  Image:            ${DEEPAGENTS_IMAGE}"
echo "  Kind Cluster:     ${KIND_CLUSTER_NAME}"
echo "================================================================================"

# Step 1: Clone deepagents-runtime repository
log_info "Cloning deepagents-runtime repository..."
if [ -d "${DEEPAGENTS_DIR}" ]; then
    log_warn "Directory ${DEEPAGENTS_DIR} already exists, removing..."
    rm -rf "${DEEPAGENTS_DIR}"
fi

git clone "${DEEPAGENTS_REPO}" "${DEEPAGENTS_DIR}"
cd "${DEEPAGENTS_DIR}"

log_success "Repository cloned to ${DEEPAGENTS_DIR}"

# Step 2: Build deepagents-runtime Docker image
log_info "Building deepagents-runtime Docker image..."
docker build -t "${DEEPAGENTS_IMAGE}" .

log_success "Docker image built: ${DEEPAGENTS_IMAGE}"

# Step 3: Load image into Kind cluster
log_info "Loading image into Kind cluster..."
kind load docker-image "${DEEPAGENTS_IMAGE}" --name "${KIND_CLUSTER_NAME}"

log_success "Image loaded into Kind cluster"

# Step 4: Run deepagents-runtime pre-deploy diagnostics
log_info "Running deepagents-runtime pre-deploy diagnostics..."
chmod +x scripts/ci/pre-deploy-diagnostics.sh
./scripts/ci/pre-deploy-diagnostics.sh

log_success "Pre-deploy diagnostics passed"

# Step 5: Deploy deepagents-runtime service
log_info "Deploying deepagents-runtime service..."
export IMAGE_TAG="ci-test"
export NAMESPACE="${DEEPAGENTS_NAMESPACE}"

chmod +x scripts/ci/deploy.sh
./scripts/ci/deploy.sh preview

log_success "DeepAgents Runtime deployed"

# Step 6: Run deepagents-runtime post-deploy diagnostics
log_info "Running deepagents-runtime post-deploy diagnostics..."
chmod +x scripts/ci/post-deploy-diagnostics.sh
./scripts/ci/post-deploy-diagnostics.sh "${DEEPAGENTS_NAMESPACE}" deepagents-runtime

log_success "Post-deploy diagnostics passed"

# Step 7: Validate deepagents-runtime service is healthy
log_info "Validating deepagents-runtime service health..."

# Wait for service to be ready
log_info "Waiting for deepagents-runtime service to be ready..."
kubectl wait deployment/deepagents-runtime \
    -n "${DEEPAGENTS_NAMESPACE}" \
    --for=condition=Available \
    --timeout=300s

# Wait for pods to be ready
log_info "Waiting for deepagents-runtime pods to be ready..."
kubectl wait pod \
    -l app.kubernetes.io/name=deepagents-runtime \
    -n "${DEEPAGENTS_NAMESPACE}" \
    --for=condition=Ready \
    --timeout=300s

# Test service connectivity
log_info "Testing deepagents-runtime service connectivity..."
SERVICE_IP=$(kubectl get svc deepagents-runtime -n "${DEEPAGENTS_NAMESPACE}" -o jsonpath='{.spec.clusterIP}')
if [ -n "${SERVICE_IP}" ]; then
    log_info "Service IP: ${SERVICE_IP}"
    
    # Test readiness endpoint
    log_info "Testing readiness endpoint..."
    kubectl run connectivity-test --image=curlimages/curl:latest --rm -i --restart=Never -- \
        curl -f -m 10 "http://${SERVICE_IP}:8080/ready" || {
        log_error "Readiness endpoint test failed"
        
        # Debug information
        echo ""
        echo "=== Service Debug Information ==="
        kubectl get svc deepagents-runtime -n "${DEEPAGENTS_NAMESPACE}" -o wide
        kubectl get pods -n "${DEEPAGENTS_NAMESPACE}" -l app.kubernetes.io/name=deepagents-runtime -o wide
        kubectl describe svc deepagents-runtime -n "${DEEPAGENTS_NAMESPACE}"
        
        # Get pod logs
        POD_NAME=$(kubectl get pods -n "${DEEPAGENTS_NAMESPACE}" -l app.kubernetes.io/name=deepagents-runtime -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [ -n "${POD_NAME}" ]; then
            echo ""
            echo "=== Pod Logs: ${POD_NAME} ==="
            kubectl logs "${POD_NAME}" -n "${DEEPAGENTS_NAMESPACE}" --tail=50
        fi
        
        exit 1
    }
    
    log_success "Service connectivity test passed"
else
    log_error "Could not get service IP"
    kubectl get svc deepagents-runtime -n "${DEEPAGENTS_NAMESPACE}" -o wide
    exit 1
fi

# Step 8: Verify cross-namespace service resolution
log_info "Verifying cross-namespace service resolution..."
CROSS_NS_SERVICE="deepagents-runtime.${DEEPAGENTS_NAMESPACE}.svc.cluster.local"
kubectl run dns-test --image=curlimages/curl:latest --rm -i --restart=Never -- \
    nslookup "${CROSS_NS_SERVICE}" || {
    log_error "Cross-namespace DNS resolution failed"
    echo "Expected service: ${CROSS_NS_SERVICE}"
    exit 1
}

log_success "Cross-namespace service resolution verified"

# Step 9: Final validation summary
log_info "Final validation summary..."
echo ""
echo "=== DeepAgents Runtime Status ==="
kubectl get deployment,pods,svc -n "${DEEPAGENTS_NAMESPACE}" -l app.kubernetes.io/name=deepagents-runtime
echo ""
echo "=== Dependencies Status ==="
kubectl get pods -n "${DEEPAGENTS_NAMESPACE}" -l 'app.kubernetes.io/name in (deepagents-runtime-db,deepagents-runtime-cache)'
echo ""
echo "=== Service Endpoints ==="
echo "Internal: http://deepagents-runtime.${DEEPAGENTS_NAMESPACE}.svc.cluster.local:8080"
echo "Cluster:  http://${SERVICE_IP}:8080"
echo ""

log_success "DeepAgents Runtime dependency setup completed successfully"
echo ""
echo "================================================================================"
echo "DEPENDENCY SETUP SUMMARY"
echo "================================================================================"
echo "  Repository:       ${DEEPAGENTS_REPO}"
echo "  Local Path:       ${DEEPAGENTS_DIR}"
echo "  Namespace:        ${DEEPAGENTS_NAMESPACE}"
echo "  Image:            ${DEEPAGENTS_IMAGE}"
echo "  Service Endpoint: http://deepagents-runtime.${DEEPAGENTS_NAMESPACE}.svc.cluster.local:8080"
echo ""
echo "IDE Orchestrator can now connect to DeepAgents Runtime for integration testing."
echo "================================================================================"

# Cleanup
cd - > /dev/null
log_info "Dependency setup script completed"