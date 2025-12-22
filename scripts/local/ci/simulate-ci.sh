#!/bin/bash
set -euo pipefail

# Local CI Simulation Script
# Simulates the CI pipeline locally for testing

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Default values
TEST_SUITE="${1:-integration}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_DEPLOY="${SKIP_DEPLOY:-false}"
NAMESPACE="${NAMESPACE:-intelligence-platform}"

echo "🧪 Simulating CI pipeline locally..."
echo "Test Suite: ${TEST_SUITE}"
echo "Namespace: ${NAMESPACE}"

cd "${PROJECT_ROOT}"

# Step 1: Validate dependencies
echo ""
echo "🔍 Step 1: Validating platform dependencies..."
if ! ./scripts/ci/validate-platform-dependencies.sh; then
    echo "❌ Platform dependency validation failed"
    exit 1
fi

# Step 2: Pre-deployment diagnostics
echo ""
echo "🔍 Step 2: Running pre-deployment diagnostics..."
if ! ./scripts/ci/pre-deploy-diagnostics.sh; then
    echo "❌ Pre-deployment diagnostics failed"
    exit 1
fi

# Step 3: Build (optional)
if [[ "${SKIP_BUILD}" != "true" ]]; then
    echo ""
    echo "🏗️  Step 3: Building application..."
    if ! ./scripts/ci/build.sh ci local-$(date +%s); then
        echo "❌ Build failed"
        exit 1
    fi
else
    echo ""
    echo "⏭️  Step 3: Skipping build (SKIP_BUILD=true)"
fi

# Step 4: Apply CI optimizations
echo ""
echo "🔧 Step 4: Applying CI optimizations..."
if ! ./scripts/patches/00-apply-all-patches.sh; then
    echo "❌ CI optimizations failed"
    exit 1
fi

# Step 5: Deploy (optional)
if [[ "${SKIP_DEPLOY}" != "true" ]]; then
    echo ""
    echo "🚀 Step 5: Deploying application..."
    if ! ./scripts/ci/deploy.sh ci; then
        echo "❌ Deployment failed"
        exit 1
    fi
else
    echo ""
    echo "⏭️  Step 5: Skipping deployment (SKIP_DEPLOY=true)"
fi

# Step 6: Run tests
echo ""
echo "🧪 Step 6: Running in-cluster tests..."
if ! ./scripts/ci/in-cluster-test.sh "${TEST_SUITE}"; then
    echo "❌ Tests failed"
    exit 1
fi

# Step 7: Post-deployment diagnostics
echo ""
echo "🔍 Step 7: Running post-deployment diagnostics..."
if ! ./scripts/ci/post-deploy-diagnostics.sh; then
    echo "❌ Post-deployment diagnostics failed"
    exit 1
fi

echo ""
echo "🎉 Local CI simulation completed successfully!"
echo "✅ All steps passed"