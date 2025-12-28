#!/bin/bash
# Downsize IDE Orchestrator application for preview environments
# Reduces: medium → small (50m-200m CPU, 128Mi-256Mi RAM)

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
    echo -e "${BLUE}🔧 Optimizing IDE Orchestrator application resources for preview mode...${NC}"
    
    IDE_ORCHESTRATOR_DEPLOYMENT="$REPO_ROOT/platform/claims/intelligence-orchestrator/ide-orchestrator-deployment.yaml"
    
    if [ -f "$IDE_ORCHESTRATOR_DEPLOYMENT" ]; then
        # Reduce replicas to 1 for preview
        if grep -q "replicas: [2-9]" "$IDE_ORCHESTRATOR_DEPLOYMENT" 2>/dev/null; then
            sed -i.bak 's/replicas: [2-9]/replicas: 1/g' "$IDE_ORCHESTRATOR_DEPLOYMENT"
            rm -f "$IDE_ORCHESTRATOR_DEPLOYMENT.bak"
            echo -e "  ${GREEN}✓${NC} IDE Orchestrator: reduced to 1 replica"
        fi
        
        # Reduce CPU requests if they're high
        if grep -q "cpu: [5-9][0-9][0-9]m" "$IDE_ORCHESTRATOR_DEPLOYMENT" 2>/dev/null; then
            sed -i.bak 's/cpu: [5-9][0-9][0-9]m/cpu: 50m/g' "$IDE_ORCHESTRATOR_DEPLOYMENT"
            rm -f "$IDE_ORCHESTRATOR_DEPLOYMENT.bak"
            echo -e "  ${GREEN}✓${NC} IDE Orchestrator: reduced CPU request to 50m"
        fi
        
        # Reduce memory requests if they're high
        if grep -q "memory: [5-9][0-9][0-9]Mi" "$IDE_ORCHESTRATOR_DEPLOYMENT" 2>/dev/null; then
            sed -i.bak 's/memory: [5-9][0-9][0-9]Mi/memory: 128Mi/g' "$IDE_ORCHESTRATOR_DEPLOYMENT"
            rm -f "$IDE_ORCHESTRATOR_DEPLOYMENT.bak"
            echo -e "  ${GREEN}✓${NC} IDE Orchestrator: reduced memory request to 128Mi"
        fi
        
        echo -e "${GREEN}✓ IDE Orchestrator optimization complete${NC}"
    else
        echo -e "  ${YELLOW}⊘${NC} IDE Orchestrator deployment file not found"
        echo -e "  ${BLUE}ℹ${NC}  Application will use default resource settings"
    fi
else
    echo -e "${YELLOW}⊘${NC} Not in preview mode - skipping IDE Orchestrator optimization"
fi

exit 0