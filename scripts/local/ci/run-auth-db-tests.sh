#!/bin/bash
set -euo pipefail

# ==============================================================================
# IDE Orchestrator: Run Auth DB Tests Locally
# ==============================================================================
# Purpose: Run auth-db-tests using the centralized in-cluster-test script
# Usage: ./run-auth-db-tests.sh
# ==============================================================================

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[AUTH-DB-TEST]${NC} $*"; }
log_success() { echo -e "${GREEN}[AUTH-DB-TEST]${NC} $*"; }
log_error() { echo -e "${RED}[AUTH-DB-TEST]${NC} $*"; }

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "================================================================================"
echo "IDE Orchestrator: Auth DB Tests (Using Centralized Script)"
echo "================================================================================"

cd "${PROJECT_ROOT}"

# The centralized script will handle platform checkout itself
CENTRALIZED_SCRIPT="zerotouch-platform/scripts/bootstrap/preview/tenants/scripts/in-cluster-test.sh"

# Check if we can access the centralized script (it might be in a different location)
if [[ ! -f "$CENTRALIZED_SCRIPT" ]]; then
    # Try alternative locations or download it
    log_warn "Centralized script not found at expected location"
    log_info "The script will handle platform checkout automatically"
    
    # For now, assume the script is available via curl or we need to clone platform first
    if [[ ! -d "zerotouch-platform" ]]; then
        log_info "Cloning zerotouch-platform to access centralized script..."
        git clone -b refactor/services-shared-scripts https://github.com/arun4infra/zerotouch-platform.git zerotouch-platform
    fi
fi

if [[ ! -f "$CENTRALIZED_SCRIPT" ]]; then
    log_error "Centralized in-cluster-test script not found: $CENTRALIZED_SCRIPT"
    exit 1
fi

log_info "Using centralized script: $CENTRALIZED_SCRIPT"
log_info "Running auth-db integration tests..."

# Run the centralized script with auth-db specific parameters
chmod +x "$CENTRALIZED_SCRIPT"
"$CENTRALIZED_SCRIPT" \
    --service="ide-orchestrator" \
    --test-path="tests/integration/auth_db_integration_test.go" \
    --test-name="auth-db" \
    --timeout=300 \
    --image-tag="ci-test" \
    --namespace="intelligence-orchestrator" \
    --platform-branch="refactor/services-shared-scripts"

log_success "Auth DB tests completed using centralized script!"