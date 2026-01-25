## Cluster commands for debugging
kubectl get pods -n intelligence-orchestrator
kubectl logs -n intelligence-orchestrator deployment/ide-orchestrator --tail=20
kubectl delete pod -n intelligence-orchestrator -l app=ide-orchestrator
kubectl get deployment ide-orchestrator -n intelligence-orchestrator -o yaml | grep -A 10 -B 5 envFrom
kubectl get secrets -n intelligence-orchestrator | grep ide-orchestrator

## Check cluster memory usage
docker stats zerotouch-preview-control-plane --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

## AWS SSM Parameter Store
aws ssm put-parameter --name "/zerotouch/prod/ide-orchestrator/database_url" --value "postgresql://neondb_owner:npg_lhaL8SJCzD9v@ep-flat-feather-aekziod9-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require" --type "SecureString" --overwrite
aws ssm get-parameter --name "/zerotouch/prod/ide-orchestrator/database_url" --with-decryption

## INTEGRATION TESTING
docker build -t ide-orchestrator:ci-test .
kind load docker-image ide-orchestrator:ci-test --name zerotouch-preview

### Use this command when all env.var in-cluster ES already exists

kubectl run integration-test-orchestrator --image=ide-orchestrator:ci-test --rm -i --restart=Never -n intelligence-orchestrator --overrides='
{
  "spec": {
    "containers": [
      {
        "name": "integration-test-orchestrator",
        "image": "ide-orchestrator:ci-test",
        "command": ["python", "-m", "pytest", "tests/integration/", "-v"],
        "envFrom": [
          {"secretRef": {"name": "ide-orchestrator-db-conn", "optional": true}},
          {"secretRef": {"name": "ide-orchestrator-jwt-keys", "optional": true}},
          {"secretRef": {"name": "ide-orchestrator-app-secrets", "optional": true}}
        ]
      }
    ]
  }
}'

### Use this command when all env.var in-cluster ES do not exist and you want to pass them as env vars

kubectl run integration-test-orchestrator --image=ide-orchestrator:ci-test --rm -i --restart=Never -n intelligence-orchestrator --overrides='
{
  "spec": {
    "containers": [
      {
        "name": "integration-test-orchestrator",
        "image": "ide-orchestrator:ci-test",
        "command": ["python", "-m", "pytest", "tests/integration/", "-v"],
        "env": [
          {"name": "DATABASE_URL", "value": "postgresql://neondb_owner:npg_lhaL8SJCzD9v@ep-flat-feather-aekziod9-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require"},
          {"name": "JWT_SECRET", "value": "test-secret-key-for-testing"},
          {"name": "SPEC_ENGINE_URL", "value": "http://spec-engine.intelligence-orchestrator.svc.cluster.local:8080"},
          {"name": "ENVIRONMENT", "value": "test"}
        ]
      }
    ]
  }
}'

## Testing in-cluster service
kubectl port-forward -n intelligence-orchestrator svc/ide-orchestrator 8080:8080 &

curl -s http://localhost:8080/health
curl -s http://localhost:8080/api/workflows
curl -s http://localhost:8080/api/auth/login -X POST -H "Content-Type: application/json" -d '{"email":"test@example.com","password":"testpass"}'