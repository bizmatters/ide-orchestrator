#!/bin/bash
set -euo pipefail

# ==============================================================================
# Apply Patches Script
# ==============================================================================
# Applies resource optimization patches for CI environment
# Used by both local testing and CI workflows
# ==============================================================================

FORCE="${1:-false}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

main() {
    log_info "Applying patches for CI environment..."
    
    # Apply preview environment patches for resource optimization
    if [[ -f "scripts/patches/00-apply-all-patches.sh" ]]; then
        chmod +x scripts/patches/00-apply-all-patches.sh
        if [[ "$FORCE" == "true" ]]; then
            ./scripts/patches/00-apply-all-patches.sh --force
        else
            ./scripts/patches/00-apply-all-patches.sh
        fi
    else
        log_info "No patches script found, skipping..."
    fi
    
    log_success "Patches applied"
}

main "$@"