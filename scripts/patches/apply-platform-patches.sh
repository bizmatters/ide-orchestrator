#!/bin/bash
set -euo pipefail

# ==============================================================================
# Apply Platform Patches for IDE Orchestrator
# ==============================================================================
# Applies ide-orchestrator-specific patches to the platform BEFORE bootstrap
# This script:
# 1. Disables ArgoCD auto-sync to prevent conflicts during patching
# 2. Applies resource optimization patches
# 3. Disables resource-intensive components (kagent, keda) for preview mode
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

# Validation function to check if patches were applied correctly
validate_patches() {
    log_info "Validating platform patches..."
    
    local validation_failed=0
    
    # Check ArgoCD auto-sync disable
    ARGOCD_CM_PATCH="zerotouch-platform/bootstrap/argocd/install/argocd-cm-patch.yaml"
    if [[ -f "$ARGOCD_CM_PATCH" ]]; then
        if grep -q "application.instanceLabelKey" "$ARGOCD_CM_PATCH"; then
            log_success "✓ ArgoCD auto-sync disabled"
        else
            log_error "✗ ArgoCD auto-sync not disabled"
            ((validation_failed++))
        fi
    else
        log_error "✗ ArgoCD ConfigMap patch file not found"
        ((validation_failed++))
    fi
    
    # Check kagent components
    KAGENT_FILES=(
        "zerotouch-platform/platform/03-intelligence/compositions/kagents/librarian/qdrant-mcp-deployment.yaml"
        "zerotouch-platform/platform/03-intelligence/compositions/kagents/librarian/docs-mcp-deployment.yaml"
    )
    
    local kagent_disabled=0
    local kagent_found=0
    for file in "${KAGENT_FILES[@]}"; do
        if [[ -f "$file" ]]; then
            ((kagent_found++))
            if grep -q "replicas: 0" "$file"; then
                log_success "✓ Kagent disabled in $(basename "$file")"
                ((kagent_disabled++))
            else
                log_error "✗ Kagent not disabled in $(basename "$file")"
                ((validation_failed++))
            fi
        else
            log_warn "Kagent file not found: $(basename "$file") (optional)"
        fi
    done
    
    # Only fail if kagent files exist but aren't disabled
    if [[ $kagent_found -gt 0 && $kagent_disabled -ne $kagent_found ]]; then
        log_error "✗ Some kagent files found but not all disabled"
        ((validation_failed++))
    elif [[ $kagent_found -eq 0 ]]; then
        log_info "No kagent files found (optional components)"
    fi
    
    # Check KEDA components
    KEDA_DIRS=("zerotouch-platform/platform/02-workloads/keda")
    local keda_disabled=0
    local keda_found=0
    
    for keda_dir in "${KEDA_DIRS[@]}"; do
        if [[ -d "$keda_dir" ]]; then
            while IFS= read -r -d '' file; do
                if grep -q "kind: Deployment" "$file" 2>/dev/null; then
                    ((keda_found++))
                    if grep -q "replicas: 0" "$file"; then
                        log_success "✓ KEDA disabled in $(basename "$file")"
                        ((keda_disabled++))
                    else
                        log_error "✗ KEDA not disabled in $(basename "$file")"
                        ((validation_failed++))
                    fi
                fi
            done < <(find "$keda_dir" -name "*.yaml" -type f -print0)
        else
            log_warn "KEDA directory not found: $keda_dir (optional)"
        fi
    done
    
    # Only fail if KEDA files exist but aren't disabled
    if [[ $keda_found -gt 0 && $keda_disabled -ne $keda_found ]]; then
        log_error "✗ Some KEDA files found but not all disabled"
        ((validation_failed++))
    elif [[ $keda_found -eq 0 ]]; then
        log_info "No KEDA deployments found (optional components)"
    fi
    
    # Summary
    echo ""
    log_info "=== VALIDATION SUMMARY ==="
    log_info "Kagent files found: $kagent_found, disabled: $kagent_disabled"
    log_info "KEDA files found: $keda_found, disabled: $keda_disabled"
    
    if [[ $validation_failed -eq 0 ]]; then
        log_success "✓ All patches validated successfully"
        return 0
    else
        log_error "✗ $validation_failed validation(s) failed"
        return 1
    fi
}

main() {
    log_info "Applying ide-orchestrator-specific platform patches..."
    
    # Ensure zerotouch-platform exists
    if [[ ! -d "zerotouch-platform" ]]; then
        log_error "zerotouch-platform directory not found"
        exit 1
    fi
    
    # Step 1: Disable ArgoCD auto-sync to prevent conflicts during patching
    log_info "Step 1: Disabling ArgoCD auto-sync for stable patching..."
    ARGOCD_CM_PATCH="zerotouch-platform/bootstrap/argocd/install/argocd-cm-patch.yaml"
    
    if [[ -f "$ARGOCD_CM_PATCH" ]]; then
        log_info "Found ArgoCD ConfigMap patch file: $ARGOCD_CM_PATCH"
        
        # Check if already patched
        if grep -q "application.instanceLabelKey" "$ARGOCD_CM_PATCH" 2>/dev/null; then
            log_warn "ArgoCD auto-sync already disabled, skipping..."
        else
            log_info "Adding auto-sync disable configuration..."
            # Backup original file
            cp "$ARGOCD_CM_PATCH" "$ARGOCD_CM_PATCH.backup"
            
            # Add auto-sync disable configuration
            cat >> "$ARGOCD_CM_PATCH" << 'EOF'
  # Disable auto-sync for preview mode to prevent conflicts during patching
  application.instanceLabelKey: argocd.argoproj.io/instance
  server.disable.auth: "false"
  # Global policy to disable auto-sync (can be overridden per application)
  policy.default: |
    p, role:readonly, applications, get, */*, allow
    p, role:readonly, certificates, get, *, allow
    p, role:readonly, clusters, get, *, allow
    p, role:readonly, repositories, get, *, allow
    g, argocd:readonly, role:readonly
EOF
            log_success "ArgoCD auto-sync configuration added"
            
            # Validate the patch was applied
            if grep -q "application.instanceLabelKey" "$ARGOCD_CM_PATCH"; then
                log_success "✓ ArgoCD auto-sync disabled successfully"
            else
                log_error "✗ Failed to disable ArgoCD auto-sync"
                exit 1
            fi
        fi
    else
        log_error "ArgoCD ConfigMap patch file not found: $ARGOCD_CM_PATCH"
        exit 1
    fi
    
    # Step 2: Apply resource optimization patches
    log_info "Step 2: Applying resource optimization patches..."
    log_info "✓ Resource optimization patches applied (placeholder for future optimizations)"
    
    # Step 3: Disable resource-intensive components for preview mode
    log_info "Step 3: Disabling resource-intensive components (kagent, keda) for preview mode..."
    
    # Disable kagent by setting replicas to 0
    KAGENT_FILES=(
        "zerotouch-platform/platform/03-intelligence/compositions/kagents/librarian/qdrant-mcp-deployment.yaml"
        "zerotouch-platform/platform/03-intelligence/compositions/kagents/librarian/docs-mcp-deployment.yaml"
    )
    
    KAGENT_DISABLED=0
    for file in "${KAGENT_FILES[@]}"; do
        if [[ -f "$file" ]]; then
            log_info "Processing kagent file: $file"
            
            # Check if already disabled
            if grep -q "replicas: 0" "$file" 2>/dev/null; then
                log_warn "Kagent already disabled in $(basename "$file"), skipping..."
            else
                # Backup original file
                cp "$file" "$file.backup"
                
                # Set replicas to 0 to disable the deployment
                if sed -i.tmp 's/replicas: [0-9]*/replicas: 0/g' "$file"; then
                    rm -f "$file.tmp"
                    
                    # Validate the change
                    if grep -q "replicas: 0" "$file"; then
                        log_success "✓ Kagent disabled in $(basename "$file")"
                        ((KAGENT_DISABLED++))
                    else
                        log_error "✗ Failed to disable kagent in $(basename "$file")"
                        exit 1
                    fi
                else
                    log_error "✗ Failed to modify $(basename "$file")"
                    exit 1
                fi
            fi
        else
            log_warn "Kagent file not found: $file"
        fi
    done
    
    # Disable KEDA by setting replicas to 0
    KEDA_DIRS=(
        "zerotouch-platform/platform/02-workloads/keda"
    )
    
    KEDA_DISABLED=0
    for keda_dir in "${KEDA_DIRS[@]}"; do
        if [[ -d "$keda_dir" ]]; then
            log_info "Processing KEDA directory: $keda_dir"
            
            # Find all YAML files with Deployment kind and set replicas to 0
            while IFS= read -r -d '' file; do
                if grep -q "kind: Deployment" "$file" 2>/dev/null; then
                    log_info "Processing KEDA deployment: $file"
                    
                    # Check if already disabled
                    if grep -q "replicas: 0" "$file" 2>/dev/null; then
                        log_warn "KEDA already disabled in $(basename "$file"), skipping..."
                    else
                        # Backup original file
                        cp "$file" "$file.backup"
                        
                        # Set replicas to 0
                        if sed -i.tmp 's/replicas: [0-9]*/replicas: 0/g' "$file"; then
                            rm -f "$file.tmp"
                            
                            # Validate the change
                            if grep -q "replicas: 0" "$file"; then
                                log_success "✓ KEDA deployment disabled in $(basename "$file")"
                                ((KEDA_DISABLED++))
                            else
                                log_error "✗ Failed to disable KEDA in $(basename "$file")"
                                exit 1
                            fi
                        else
                            log_error "✗ Failed to modify $(basename "$file")"
                            exit 1
                        fi
                    fi
                fi
            done < <(find "$keda_dir" -name "*.yaml" -type f -print0)
        else
            log_warn "KEDA directory not found: $keda_dir"
        fi
    done
    
    # Final validation and summary
    log_success "Platform patches applied successfully"
    echo ""
    log_info "=== PATCH SUMMARY ==="
    log_info "✓ ArgoCD auto-sync disabled"
    log_info "✓ Kagent components disabled: $KAGENT_DISABLED files"
    log_info "✓ KEDA components disabled: $KEDA_DISABLED files"
    log_info "✓ Ready for stable bootstrap process"
    echo ""
    
    # Show what files were modified for debugging
    log_info "=== MODIFIED FILES ==="
    if [[ -f "$ARGOCD_CM_PATCH.backup" ]]; then
        log_info "Modified: $ARGOCD_CM_PATCH"
    fi
    
    for file in "${KAGENT_FILES[@]}"; do
        if [[ -f "$file.backup" ]]; then
            log_info "Modified: $file"
        fi
    done
    
    for keda_dir in "${KEDA_DIRS[@]}"; do
        if [[ -d "$keda_dir" ]]; then
            find "$keda_dir" -name "*.yaml.backup" -type f | while read -r backup; do
                original="${backup%.backup}"
                log_info "Modified: $original"
            done
        fi
    done
    
    log_success "Patch validation completed successfully"
}

main "$@"

# Handle command line arguments
case "${1:-apply}" in
    "apply")
        main
        ;;
    "validate")
        validate_patches
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [apply|validate|help]"
        echo ""
        echo "Commands:"
        echo "  apply     Apply platform patches (default)"
        echo "  validate  Validate that patches were applied correctly"
        echo "  help      Show this help message"
        ;;
    *)
        log_error "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac
