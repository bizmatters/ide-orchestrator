#!/bin/bash
set -euo pipefail

# ==============================================================================
# Kind Cluster Setup Script
# ==============================================================================
# Creates and configures a Kind cluster for testing
# Used by both local testing and CI workflows
# ==============================================================================

CLUSTER_NAME="${CLUSTER_NAME:-zerotouch-preview}"
IMAGE_TAG="${IMAGE_TAG:-ci-test}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

main() {
    log_info "Setting up Kind cluster: $CLUSTER_NAME"
    
    # Install kind if not available
    if ! command -v kind &> /dev/null; then
        log_info "Installing kind..."
        curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
        chmod +x ./kind
        sudo mv ./kind /usr/local/bin/kind
    fi
    
    # Create Kind config
    mkdir -p /tmp/kind
    cat > /tmp/kind/config.yaml << EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: $CLUSTER_NAME
nodes:
- role: control-plane
  extraPortMappings:
  # PostgreSQL port
  - containerPort: 30432
    hostPort: 5432
    protocol: TCP
  # DeepAgents Runtime port
  - containerPort: 30080
    hostPort: 8080
    protocol: TCP
  extraMounts:
  # Mount zerotouch-platform subdirectory for ArgoCD to sync from
  - hostPath: $(pwd)/zerotouch-platform
    containerPath: /repo
    readOnly: true
EOF

    # Create cluster if it doesn't exist
    if ! kind get clusters | grep -q "$CLUSTER_NAME"; then
        log_info "Creating Kind cluster..."
        kind create cluster --config /tmp/kind/config.yaml
    else
        log_info "Kind cluster '$CLUSTER_NAME' already exists"
    fi
    
    # Set kubectl context and label nodes
    kubectl config use-context kind-$CLUSTER_NAME
    kubectl label nodes --all workload.bizmatters.dev/databases=true --overwrite
    
    log_success "Kind cluster ready: $CLUSTER_NAME"
}

main "$@"