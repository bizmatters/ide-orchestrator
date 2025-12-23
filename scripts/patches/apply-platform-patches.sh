#!/bin/bash
set -euo pipefail

# ==============================================================================
# Apply Platform Patches for IDE Orchestrator
# ==============================================================================
# Applies ide-orchestrator-specific patches to the platform BEFORE bootstrap
# This disables Kagent for preview mode to save CPU resources
# ==============================================================================

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

main() {
    log_info "Applying ide-orchestrator-specific platform patches..."
    
    # Ensure zerotouch-platform exists
    if [[ ! -d "zerotouch-platform" ]]; then
        log_error "zerotouch-platform directory not found"
        exit 1
    fi
    
    # Make Kagent optional in preview mode
    WAIT_SCRIPT="zerotouch-platform/scripts/bootstrap/wait/12a-wait-apps-healthy.sh"
    
    if [[ -f "$WAIT_SCRIPT" ]]; then
        log_info "Making Kagent optional for preview mode..."
        
        # Check if already patched
        if grep -q '"kagent"' "$WAIT_SCRIPT" 2>/dev/null; then
            log_warn "Kagent already marked as optional, skipping..."
        else
            # Add kagent to PREVIEW_OPTIONAL_APPS array - find closing parenthesis and add before it
            sed -i.bak '/PREVIEW_OPTIONAL_APPS=(/,/)/ {
                /)/ i\
    "kagent"                    # Resource intensive, can fail in Kind clusters
            }' "$WAIT_SCRIPT"
            
            log_success "Kagent marked as optional for preview mode"
            log_info "Bootstrap will succeed even if Kagent fails to start"
        fi
    else
        log_error "Wait script not found: $WAIT_SCRIPT"
        exit 1
    fi
    
    log_success "Platform patches applied successfully"
}

main "$@"
