#!/bin/bash
# Downsize PostgreSQL instance for preview environments
# Reduces: medium → micro (100m-500m CPU, 256Mi-1Gi RAM)
# Storage: 20GB → 2GB for Kind clusters

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

FORCE_UPDATE=false

# Parse arguments
if [ "$1" = "--force" ]; then
    FORCE_UPDATE=true
fi

# Check if this is preview mode
IS_PREVIEW_MODE=false

if [ "$FORCE_UPDATE" = true ]; then
    IS_PREVIEW_MODE=true
elif command -v kubectl > /dev/null 2>&1 && kubectl cluster-info > /dev/null 2>&1; then
    # Check if running on Kind cluster (no control-plane taints on nodes)
    if ! kubectl get nodes -o jsonpath='{.items[*].spec.taints[?(@.key=="node-role.kubernetes.io/control-plane")]}' 2>/dev/null | grep -q "control-plane"; then
        IS_PREVIEW_MODE=true
    fi
fi

if [ "$IS_PREVIEW_MODE" = true ]; then
    echo -e "${BLUE}🔧 Optimizing PostgreSQL resources for preview mode...${NC}"
    
    POSTGRES_CLAIM="$REPO_ROOT/platform/claims/intelligence-orchestrator/postgres-claim.yaml"
    
    if [ -f "$POSTGRES_CLAIM" ]; then
        # Downsize from medium to micro (for Kind clusters, go directly to micro)
        if grep -q "size: medium" "$POSTGRES_CLAIM" 2>/dev/null; then
            sed -i.bak 's/size: medium/size: micro/g' "$POSTGRES_CLAIM"
            rm -f "$POSTGRES_CLAIM.bak"
            echo -e "  ${GREEN}✓${NC} PostgreSQL: medium → micro (100m-500m CPU, 256Mi-1Gi RAM)"
        elif grep -q "size: small" "$POSTGRES_CLAIM" 2>/dev/null; then
            sed -i.bak 's/size: small/size: micro/g' "$POSTGRES_CLAIM"
            rm -f "$POSTGRES_CLAIM.bak"
            echo -e "  ${GREEN}✓${NC} PostgreSQL: small → micro (100m-500m CPU, 256Mi-1Gi RAM)"
        else
            echo -e "  ${YELLOW}⊘${NC} PostgreSQL already at micro size"
        fi
        
        # Reduce storage for Kind clusters (minimum 2GB for testing)
        if grep -q "storageGB: 20" "$POSTGRES_CLAIM" 2>/dev/null; then
            sed -i.bak 's/storageGB: 20/storageGB: 2/g' "$POSTGRES_CLAIM"
            rm -f "$POSTGRES_CLAIM.bak"
            echo -e "  ${GREEN}✓${NC} PostgreSQL storage: 20GB → 2GB"
        elif grep -q "storageGB: 10" "$POSTGRES_CLAIM" 2>/dev/null; then
            sed -i.bak 's/storageGB: 10/storageGB: 2/g' "$POSTGRES_CLAIM"
            rm -f "$POSTGRES_CLAIM.bak"
            echo -e "  ${GREEN}✓${NC} PostgreSQL storage: 10GB → 2GB"
        else
            echo -e "  ${YELLOW}⊘${NC} PostgreSQL storage already optimized"
        fi
        
        echo -e "${GREEN}✓ PostgreSQL optimization complete${NC}"
    else
        echo -e "${YELLOW}⚠${NC} PostgreSQL claim not found: $POSTGRES_CLAIM"
        echo -e "${YELLOW}  Skipping PostgreSQL optimization...${NC}"
    fi
else
    echo -e "${YELLOW}⊘${NC} Not in preview mode - skipping PostgreSQL optimization"
fi

exit 0