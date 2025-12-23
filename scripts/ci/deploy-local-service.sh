#!/bin/bash
set -euo pipefail

# ==============================================================================
# Local Service Deployment Script
# ==============================================================================
# Deploys IDE Orchestrator service for local testing
# Creates a simple deployment with test configuration
# ==============================================================================

NAMESPACE="${1:-intelligence-deepagents}"
IMAGE_TAG="${2:-ci-test}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

main() {
    log_info "Deploying IDE Orchestrator service for local testing..."
    
    # Create a simple deployment for ide-orchestrator
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ide-orchestrator
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ide-orchestrator
  template:
    metadata:
      labels:
        app: ide-orchestrator
    spec:
      containers:
      - name: ide-orchestrator
        image: ide-orchestrator:$IMAGE_TAG
        env:
        - name: POSTGRES_HOST
          valueFrom:
            secretKeyRef:
              name: ide-orchestrator-db-conn
              key: POSTGRES_HOST
        - name: POSTGRES_PORT
          valueFrom:
            secretKeyRef:
              name: ide-orchestrator-db-conn
              key: POSTGRES_PORT
        - name: POSTGRES_DB
          valueFrom:
            secretKeyRef:
              name: ide-orchestrator-db-conn
              key: POSTGRES_DB
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: ide-orchestrator-db-conn
              key: POSTGRES_USER
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ide-orchestrator-db-conn
              key: POSTGRES_PASSWORD
        - name: JWT_SECRET
          value: "test-secret-key-for-local-testing"
        - name: SPEC_ENGINE_URL
          value: "http://deepagents-runtime.${NAMESPACE}.svc:8080"
        ports:
        - containerPort: 8080
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
  name: ide-orchestrator
  namespace: $NAMESPACE
spec:
  selector:
    app: ide-orchestrator
  ports:
  - port: 8080
    targetPort: 8080
EOF

    # Wait for pod to be created and start running
    log_info "Waiting for IDE Orchestrator pod to start..."
    
    ELAPSED=0
    TIMEOUT=120
    POLL_INTERVAL=5
    
    while [ $ELAPSED -lt $TIMEOUT ]; do
        # Get pod name
        POD_NAME=$(kubectl get pods -n $NAMESPACE -l app=ide-orchestrator -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        
        if [ -n "$POD_NAME" ]; then
            POD_PHASE=$(kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
            
            if [ "$POD_PHASE" = "Running" ] || [ "$POD_PHASE" = "Succeeded" ]; then
                log_success "IDE Orchestrator pod is running: $POD_NAME ($POD_PHASE)"
                break
            elif [ "$POD_PHASE" = "Failed" ]; then
                log_error "IDE Orchestrator pod failed"
                kubectl logs $POD_NAME -n $NAMESPACE || true
                return 1
            else
                log_info "Pod status: $POD_PHASE, waiting... (${ELAPSED}s elapsed)"
            fi
        else
            log_info "Waiting for pod to be created... (${ELAPSED}s elapsed)"
        fi
        
        sleep $POLL_INTERVAL
        ELAPSED=$((ELAPSED + POLL_INTERVAL))
    done
    
    if [ $ELAPSED -ge $TIMEOUT ]; then
        log_error "Timeout waiting for IDE Orchestrator pod to start"
        return 1
    fi
    
    log_success "Service deployed and pod started"
}

main "$@"