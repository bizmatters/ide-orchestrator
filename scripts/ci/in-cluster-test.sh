#!/bin/bash
set -euo pipefail

# ==============================================================================
# Centralized In-Cluster Testing Framework
# ==============================================================================
# Purpose: Reusable script for running any test suite in Kubernetes cluster
# Usage: ./scripts/ci/in-cluster-test.sh <test_path> [test_name] [timeout]
# Examples:
#   ./scripts/ci/in-cluster-test.sh tests/integration/... integration-tests
#   ./scripts/ci/in-cluster-test.sh ./internal/... unit-tests 900
# ==============================================================================

# Parameters
TEST_PATH="${1:-tests/integration/...}"
TEST_NAME="${2:-integration-tests}"
TIMEOUT="${3:-600}"
NAMESPACE="${NAMESPACE:-intelligence-platform}"
IMAGE="${IMAGE:-ide-orchestrator:ci-test}"

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

log_info "Starting in-cluster test execution"
log_info "Test Path: $TEST_PATH"
log_info "Test Name: $TEST_NAME"
log_info "Timeout: ${TIMEOUT}s"
log_info "Namespace: $NAMESPACE"
log_info "Image: $IMAGE"

# Generate unique job name
JOB_NAME="${TEST_NAME}-$(date +%s)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create test job from template
create_test_job() {
    local job_file="/tmp/${JOB_NAME}.yaml"
    local template_file="$SCRIPT_DIR/test-job-template.yaml"
    
    log_info "Creating test job: $JOB_NAME"
    
    # Use the template file and substitute variables
    if [[ -f "$template_file" ]]; then
        log_info "Using template file: $template_file"
        
        sed -e "s/{{JOB_NAME}}/$JOB_NAME/g" \
            -e "s/{{NAMESPACE}}/$NAMESPACE/g" \
            -e "s/{{IMAGE}}/$IMAGE/g" \
            -e "s|{{TEST_PATH}}|$TEST_PATH|g" \
            -e "s/{{TEST_NAME}}/$TEST_NAME/g" \
            "$template_file" > "$job_file"
    else
        log_error "Template file not found: $template_file"
        exit 1
    fi

    echo "$job_file"
}

# Deploy and monitor test job
run_test_job() {
    local job_file="$1"
    
    # Clean up any existing job
    kubectl delete job "$JOB_NAME" -n "$NAMESPACE" 2>/dev/null || true
    
    # Deploy test job
    log_info "Deploying in-cluster test job..."
    kubectl apply -f "$job_file"
    
    # Monitor job progress
    log_info "Waiting for test job to complete..."
    local elapsed=0
    local status=""
    local pod_name=""
    
    while [[ $elapsed -lt $TIMEOUT ]]; do
        # Get job status
        status=$(kubectl get job "$JOB_NAME" -n "$NAMESPACE" -o jsonpath='{.status.conditions[0].type}' 2>/dev/null || echo "Pending")
        
        # Get pod info
        pod_name=$(kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        
        if [[ -n "$pod_name" ]]; then
            pod_status=$(kubectl get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
            pod_ready=$(kubectl get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || echo "false")
            
            # Check for specific failure reasons
            if [[ "$pod_status" == "Failed" ]]; then
                failure_reason=$(kubectl get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null || echo "Unknown")
                log_error "Pod failed with reason: $failure_reason"
                if [[ "$failure_reason" == "OOMKilled" ]]; then
                    log_error "Pod was killed due to Out of Memory. Consider increasing memory limits."
                fi
                return 1
            fi
        else
            pod_status="Pending"
            pod_ready="false"
        fi
        
        log_info "[${elapsed}s/${TIMEOUT}s] Job: $status, Pod: $pod_status, Ready: $pod_ready"
        
        # Show recent logs if pod is running
        if [[ "$pod_status" == "Running" && -n "$pod_name" ]]; then
            log_info "Recent logs:"
            kubectl logs "$pod_name" -n "$NAMESPACE" --tail=5 2>/dev/null | sed 's/^/  /' || true
        fi
        
        # Check if job completed
        if [[ "$status" == "Complete" ]]; then
            log_success "Test job completed successfully"
            return 0
        elif [[ "$status" == "Failed" ]]; then
            log_error "Test job failed"
            return 1
        fi
        
        sleep 10
        elapsed=$((elapsed + 10))
    done
    
    log_error "Test job timed out after ${TIMEOUT}s"
    return 1
}

# Copy artifacts from completed pod
copy_artifacts() {
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME" -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null || echo "")
    
    if [[ -n "$pod_name" ]]; then
        log_info "Copying artifacts from pod: $pod_name"
        
        # Create local artifacts directory
        mkdir -p artifacts
        
        # Copy test results and coverage
        kubectl cp "$NAMESPACE/$pod_name:/app/artifacts/test-results.json" "./artifacts/test-results.json" 2>/dev/null || log_warn "No test-results.json to copy"
        kubectl cp "$NAMESPACE/$pod_name:/app/artifacts/coverage.out" "./artifacts/coverage.out" 2>/dev/null || log_warn "No coverage.out to copy"
        
        log_info "Artifacts copied to ./artifacts/"
    else
        log_warn "No pod found to copy artifacts from"
    fi
}

# Get final test results
get_test_results() {
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME" -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null || echo "")
    
    if [[ -n "$pod_name" ]]; then
        log_info "Getting test results..."
        kubectl logs "$pod_name" -n "$NAMESPACE" | tail -50
    fi
}

# Enhanced error handling
error_handler() {
    local exit_code=$?
    local line_number=$1
    log_error "Script failed at line $line_number with exit code $exit_code"
    log_error "Last command: $BASH_COMMAND"
    
    # Get pod logs for debugging
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME" -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$pod_name" ]]; then
        log_error "Pod logs for debugging:"
        kubectl logs "$pod_name" -n "$NAMESPACE" --tail=50 2>/dev/null || true
    fi
    
    return $exit_code
}

trap 'error_handler $LINENO' ERR

# Cleanup function
cleanup() {
    log_info "Cleaning up test job: $JOB_NAME"
    kubectl delete job "$JOB_NAME" -n "$NAMESPACE" 2>/dev/null || true
    rm -f "/tmp/${JOB_NAME}.yaml" 2>/dev/null || true
}

# Main execution
main() {
    # Quick dependency check (in-cluster validation will be done by the test job)
    log_info "Checking dependencies..."
    log_info "✅ PostgreSQL service exists: $(kubectl get svc ide-orchestrator-db-rw -n intelligence-platform --no-headers 2>/dev/null | awk '{print $1}' || echo 'NOT FOUND')"
    log_info "✅ DeepAgents Runtime service exists: $(kubectl get svc deepagents-runtime -n intelligence-deepagents --no-headers 2>/dev/null | awk '{print $1}' || echo 'NOT FOUND')"
    
    # Create test job
    job_file=$(create_test_job)
    
    # Set up cleanup trap
    trap cleanup EXIT
    
    # Run the test
    if run_test_job "$job_file"; then
        copy_artifacts
        get_test_results
        log_success "In-cluster tests completed successfully"
        exit 0
    else
        copy_artifacts
        get_test_results
        log_error "In-cluster tests failed"
        exit 1
    fi
}

# Execute main function
main "$@"