#!/bin/bash
set -euo pipefail

# ==============================================================================
# Platform Bootstrap Script
# ==============================================================================
# Bootstraps the zerotouch platform for testing
# Used by both local testing and CI workflows
# ==============================================================================

MODE="${1:-preview}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

main() {
    log_info "Bootstrapping platform in $MODE mode..."
    
    # Ensure zerotouch-platform exists
    if [[ ! -d "zerotouch-platform" ]]; then
        log_error "zerotouch-platform directory not found"
        exit 1
    fi
    
    # Bootstrap the platform using the existing zerotouch-platform
    cd zerotouch-platform
    chmod +x scripts/bootstrap/01-master-bootstrap.sh
    ./scripts/bootstrap/01-master-bootstrap.sh --mode $MODE
    cd ..
    
    log_success "Platform bootstrap completed"
}

main "$@"