#!/bin/bash
# Sync IDE Orchestrator Secrets to AWS SSM
# This script syncs all service secrets from GitHub Secrets to AWS SSM Parameter Store

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVICE_NAME="ide-orchestrator"
ENVIRONMENT="${1:-prod}"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Sync IDE Orchestrator Secrets to AWS SSM                  ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Service: $SERVICE_NAME${NC}"
echo -e "${GREEN}Environment: $ENVIRONMENT${NC}"
echo ""

# Validate AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo -e "${RED}✗ AWS CLI not found. Please install AWS CLI.${NC}"
    exit 1
fi

# Validate AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}✗ AWS credentials not configured or invalid.${NC}"
    exit 1
fi

SYNCED_COUNT=0
MISSING_COUNT=0
FAILED_COUNT=0

# Define service-specific secret keys to sync
# The actual values come from environment variables (GitHub Secrets)
# Variable names must match those in zerotouch-platform/scripts/bootstrap/helpers/generate-env-ssm.sh
SECRET_KEYS=(
    "IDEO_DATABASE_URL"
    "IDEO_JWT_SECRET"
    "IDEO_SPEC_ENGINE_URL"
)

# Sync each secret to SSM
for KEY_NAME in "${SECRET_KEYS[@]}"; do
    VALUE="${!KEY_NAME}"
    
    if [[ -z "$VALUE" ]]; then
        echo -e "${YELLOW}⚠️  Warning: Secret '$KEY_NAME' is empty or not set. Skipping.${NC}"
        MISSING_COUNT=$((MISSING_COUNT + 1))
        continue
    fi
    
    # Convert KEY_NAME to SSM parameter name
    # IDEO_DATABASE_URL -> database_url
    # IDEO_JWT_SECRET -> jwt-secret
    # IDEO_SPEC_ENGINE_URL -> spec-engine-url
    PARAM_KEY=$(echo "$KEY_NAME" | sed 's/^IDEO_//' | tr '[:upper:]' '[:lower:]' | tr '_' '-')
    
    # Construct SSM Path
    SSM_PATH="/zerotouch/${ENVIRONMENT}/${SERVICE_NAME}/${PARAM_KEY}"
    
    echo -e "${BLUE}→ Syncing $KEY_NAME to $SSM_PATH${NC}"
    
    # Push to AWS SSM
    if aws ssm put-parameter \
        --name "$SSM_PATH" \
        --value "$VALUE" \
        --type "SecureString" \
        --overwrite \
        --no-cli-pager > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Successfully synced $KEY_NAME${NC}"
        SYNCED_COUNT=$((SYNCED_COUNT + 1))
    else
        echo -e "${RED}✗ Failed to sync $KEY_NAME${NC}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
done

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Summary                                                    ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✓ Secrets synced: $SYNCED_COUNT${NC}"

if [ $MISSING_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Secrets missing: $MISSING_COUNT${NC}"
fi

if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "${RED}✗ Secrets failed: $FAILED_COUNT${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Secret sync completed successfully${NC}"

exit 0
