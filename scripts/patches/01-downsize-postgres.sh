#!/bin/bash
set -euo pipefail

# PostgreSQL Resource Optimization for CI
# Reduces PostgreSQL resource requirements for CI environment

NAMESPACE="${NAMESPACE:-intelligence-platform}"
CLUSTER_NAME="${CLUSTER_NAME:-ide-orchestrator-db}"

echo "🔧 Optimizing PostgreSQL resources for CI..."

# Check if PostgreSQL cluster exists
if ! kubectl get cluster.postgresql.cnpg.io "${CLUSTER_NAME}" -n "${NAMESPACE}" &>/dev/null; then
    echo "⚠️  PostgreSQL cluster ${CLUSTER_NAME} not found in namespace ${NAMESPACE}"
    echo "ℹ️  Skipping PostgreSQL optimization..."
    exit 0
fi

# Apply resource optimizations
echo "📉 Reducing PostgreSQL resource requirements..."

kubectl patch cluster.postgresql.cnpg.io "${CLUSTER_NAME}" -n "${NAMESPACE}" --type='merge' -p='
{
  "spec": {
    "instances": 1,
    "postgresql": {
      "parameters": {
        "max_connections": "50",
        "shared_buffers": "32MB",
        "effective_cache_size": "128MB",
        "maintenance_work_mem": "16MB",
        "checkpoint_completion_target": "0.9",
        "wal_buffers": "1MB",
        "default_statistics_target": "50",
        "random_page_cost": "1.1",
        "effective_io_concurrency": "200",
        "work_mem": "2MB",
        "min_wal_size": "32MB",
        "max_wal_size": "128MB"
      }
    },
    "resources": {
      "requests": {
        "memory": "256Mi",
        "cpu": "100m"
      },
      "limits": {
        "memory": "512Mi",
        "cpu": "500m"
      }
    },
    "storage": {
      "size": "2Gi"
    }
  }
}'

# Wait for cluster to be ready
echo "⏳ Waiting for PostgreSQL cluster to be ready..."
kubectl wait --for=condition=ready \
    cluster.postgresql.cnpg.io/"${CLUSTER_NAME}" \
    -n "${NAMESPACE}" \
    --timeout=300s

echo "✅ PostgreSQL resources optimized for CI"

# Show current resource usage
echo "📊 Current PostgreSQL resource usage:"
kubectl get cluster.postgresql.cnpg.io "${CLUSTER_NAME}" -n "${NAMESPACE}" -o wide
kubectl get pods -n "${NAMESPACE}" -l cnpg.io/cluster="${CLUSTER_NAME}" -o wide