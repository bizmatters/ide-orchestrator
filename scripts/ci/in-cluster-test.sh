#!/bin/bash
set -euo pipefail

# ==============================================================================
# Local In-Cluster Testing Simulation
# ==============================================================================
# Purpose: Simulate the GitHub Actions workflow locally for development/testing
# Usage: ./scripts/ci/in-cluster-test.sh <test_path> [test_name] [timeout]
# Examples:
#   ./scripts/ci/in-cluster-test.sh "./tests/integration" integration-tests
#   ./scripts/ci/in-cluster-test.sh "./internal/..." unit-tests 900
#
# This script does the SAME job as the GitHub workflow but in local environment
# ==============================================================================

# Parameters
TEST_PATH="${1:-./tests/integration}"
TEST_NAME="${2:-integration-tests}"
TIMEOUT="${3:-600}"
NAMESPACE="${NAMESPACE:-intelligence-deepagents}"
IMAGE_TAG="${IMAGE_TAG:-ci-test}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $*" >&2; }

# Validate inputs
if [[ -z "$TEST_PATH" ]]; then
    log_error "Test path is required"
    echo "Usage: $0 <test_path> [test_name] [timeout]"
    exit 1
fi

log_info "Starting LOCAL in-cluster test simulation"
log_info "Test Path: $TEST_PATH"
log_info "Test Name: $TEST_NAME"
log_info "Timeout: ${TIMEOUT}s"
log_info "Namespace: $NAMESPACE"
log_info "Image Tag: $IMAGE_TAG"

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if kind is installed
    if ! command -v kind &> /dev/null; then
        log_error "kind is not installed. Please install kind first:"
        echo "curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64"
        echo "chmod +x ./kind"
        echo "sudo mv ./kind /usr/local/bin/kind"
        exit 1
    fi
    
    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi
    
    # Check if docker is running
    if ! docker info &> /dev/null; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    # Check if zerotouch-platform exists
    if [[ ! -d "zerotouch-platform" ]]; then
        log_warn "zerotouch-platform directory not found. Cloning..."
        git clone https://github.com/arun4infra/zerotouch-platform.git zerotouch-platform
    fi
    
    log_success "Prerequisites check passed"
}

# Build test image (same as workflow)
build_test_image() {
    log_info "Building test image..."
    docker build -f Dockerfile.test -t ide-orchestrator:$IMAGE_TAG .
    log_success "Test image built: ide-orchestrator:$IMAGE_TAG"
}

# Create Kind cluster (same as workflow)
create_kind_cluster() {
    log_info "Creating Kind cluster..."
    ./scripts/ci/setup-kind-cluster.sh
    log_success "Kind cluster ready"
}

# Load Docker image into Kind (same as workflow)
load_image_to_kind() {
    log_info "Loading Docker image into Kind..."
    kind load docker-image ide-orchestrator:$IMAGE_TAG --name zerotouch-preview
    log_success "Image loaded into Kind cluster"
}

# Bootstrap platform (simplified for local testing)
bootstrap_platform() {
    log_info "Setting up minimal platform for local testing..."
    
    # Skip full bootstrap and just set up ArgoCD manually for local testing
    log_info "Installing ArgoCD..."
    kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
    
    # Wait for ArgoCD to be ready
    log_info "Waiting for ArgoCD to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd
    
    log_success "Minimal platform setup completed"
}

# Apply preview patches (simplified for local testing)
apply_patches() {
    log_info "Applying patches for local testing..."
    ./scripts/ci/apply-local-patches.sh $NAMESPACE
    log_success "Local patches applied"
}

# Run pre-deploy diagnostics (simplified for local testing)
run_pre_deploy_diagnostics() {
    log_info "Running basic diagnostics..."
    
    # Check if namespace exists
    kubectl get namespace intelligence-deepagents >/dev/null 2>&1 || {
        log_error "intelligence-deepagents namespace not found"
        return 1
    }
    
    log_success "Basic diagnostics completed"
}

# Deploy service (use shared script for local deployment)
deploy_service() {
    log_info "Deploying IDE Orchestrator service..."
    ./scripts/ci/deploy-local-service.sh $NAMESPACE $IMAGE_TAG
    log_success "Service deployment completed"
}

# Run database migrations (use shared script)
run_migrations() {
    log_info "Running database migrations..."
    ./scripts/ci/run-migrations.sh $NAMESPACE
    log_success "Database migrations completed"
}

# Run post-deploy diagnostics (same as workflow)
run_post_deploy_diagnostics() {
    log_info "Running post-deploy diagnostics..."
    chmod +x scripts/ci/post-deploy-diagnostics.sh
    ./scripts/ci/post-deploy-diagnostics.sh $NAMESPACE ide-orchestrator
    log_success "Post-deploy diagnostics completed"
}

# Run in-cluster tests (use shared script)
run_in_cluster_tests() {
    log_info "Running in-cluster tests using shared script..."
    
    if ./scripts/ci/run-test-job.sh "$TEST_PATH" "$TEST_NAME" "$TIMEOUT" "$NAMESPACE" "$IMAGE_TAG"; then
        log_success "Tests completed successfully!"
        return 0
    else
        log_error "Tests failed!"
        return 1
    fi
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    
    # Clean up any remaining test jobs
    kubectl delete jobs -n $NAMESPACE -l test-suite=$TEST_NAME --ignore-not-found=true 2>/dev/null || true
    
    # Optionally clean up Kind cluster (uncomment if desired)
    # log_warn "To clean up the Kind cluster, run: kind delete cluster --name zerotouch-preview"
}

# Error handler
error_handler() {
    local exit_code=$?
    local line_number=$1
    log_error "Script failed at line $line_number with exit code $exit_code"
    log_error "Last command: $BASH_COMMAND"
    cleanup
    exit $exit_code
}

trap 'error_handler $LINENO' ERR
trap cleanup EXIT

# Main execution (same steps as workflow in correct order)
main() {
    check_prerequisites
    create_kind_cluster
    bootstrap_platform
    apply_patches
    run_pre_deploy_diagnostics
    build_test_image
    load_image_to_kind
    deploy_service
    run_migrations  # Add migration step before tests
    
    # Skip post-deploy diagnostics since we're running test binary, not service
    log_info "Skipping post-deploy diagnostics (running test binary, not service)"
    
    if run_in_cluster_tests; then
        log_success "LOCAL in-cluster tests completed successfully!"
        echo ""
        echo "🎉 All tests passed! Your changes are ready for CI."
        exit 0
    else
        log_error "LOCAL in-cluster tests failed!"
        echo ""
        echo "❌ Tests failed. Please fix the issues before pushing to CI."
        exit 1
    fi
}

# Execute main function
main "$@"