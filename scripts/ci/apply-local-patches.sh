#!/bin/bash
set -euo pipefail

# ==============================================================================
# Apply Local Patches Script
# ==============================================================================
# Applies minimal infrastructure for local testing
# Creates simple PostgreSQL and DeepAgents Runtime mocks
# ==============================================================================

NAMESPACE="${1:-intelligence-deepagents}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

main() {
    log_info "Applying minimal patches for local testing..."
    
    # Create namespace if it doesn't exist
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    # Create a simple PostgreSQL deployment for testing
    log_info "Creating PostgreSQL deployment..."
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        env:
        - name: POSTGRES_DB
          value: "ide-orchestrator-db"
        - name: POSTGRES_USER
          value: "postgres"
        - name: POSTGRES_PASSWORD
          value: "test-password"
        ports:
        - containerPort: 5432
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: ide-orchestrator-db-rw
  namespace: $NAMESPACE
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
---
apiVersion: v1
kind: Secret
metadata:
  name: ide-orchestrator-db-conn
  namespace: $NAMESPACE
type: Opaque
stringData:
  POSTGRES_HOST: "ide-orchestrator-db-rw"
  POSTGRES_PORT: "5432"
  POSTGRES_DB: "ide-orchestrator-db"
  POSTGRES_USER: "postgres"
  POSTGRES_PASSWORD: "test-password"
EOF

    # Create a simple DeepAgents Runtime mock for testing
    log_info "Creating DeepAgents Runtime mock..."
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deepagents-runtime
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: deepagents-runtime
  template:
    metadata:
      labels:
        app: deepagents-runtime
    spec:
      containers:
      - name: deepagents-runtime
        image: nginx:alpine
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
---
apiVersion: v1
kind: Service
metadata:
  name: deepagents-runtime
  namespace: $NAMESPACE
spec:
  selector:
    app: deepagents-runtime
  ports:
  - port: 8080
    targetPort: 80
EOF

    # Wait for deployments to be ready
    log_info "Waiting for PostgreSQL to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/postgres -n $NAMESPACE
    
    log_info "Waiting for DeepAgents Runtime to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/deepagents-runtime -n $NAMESPACE
    
    log_success "Local patches applied successfully"
}

main "$@"