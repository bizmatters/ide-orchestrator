# IDE Orchestrator - Testing Guide

This guide provides comprehensive testing procedures for the IDE Orchestrator application.

## Pre-Test Checklist

### Required Software
- [ ] Go 1.24.0+ installed
- [ ] PostgreSQL 15+ running
- [ ] git installed
- [ ] curl or wget available

### Optional Tools (for full testing)
- [ ] golang-migrate installed
- [ ] swag (Swagger generator) installed
- [ ] Docker (for container testing)
- [ ] docker-compose (for stack testing)

## Test Procedure

### Step 1: Verify Setup Files

```bash
cd /root/development/bizmatters/services/ide-orchestrator

# Verify all setup files exist
ls -la setup.sh          # Setup script
ls -la run.sh            # Will be created by setup.sh
ls -la Dockerfile        # Docker build file
ls -la docker-compose.yml # Docker compose configuration
ls -la Makefile          # Build commands
ls -la README.md         # Documentation

# Check setup.sh is executable
test -x setup.sh && echo "Executable" || chmod +x setup.sh
```

### Step 2: Run Setup Script

#### Option A: Development Mode (Recommended for Testing)

```bash
./setup.sh --dev
```

**Expected Output:**
```
==========================================
  IDE Orchestrator Setup
==========================================

[INFO] Step 1/9: Checking prerequisites...
[SUCCESS] Go found: go1.24.x
[INFO] Step 2/9: Setting up environment variables...
[SUCCESS] Environment variables configured
[INFO] Step 3/9: Cleaning up Go dependencies...
[SUCCESS] Go dependencies updated
[INFO] Step 4/9: Building the application...
[SUCCESS] Application built successfully: bin/ide-orchestrator
[INFO] Binary size: XX MB
[INFO] Step 5/9: Cleaning up old directories...
[SUCCESS] Removed internal/handlers/
[SUCCESS] Removed internal/services/
[INFO] Step 6/9: Regenerating Swagger documentation...
[SUCCESS] Swagger documentation regenerated
[INFO] Step 7/9: Testing database connection...
[INFO] Step 8/9: Applying database migrations...
[SUCCESS] Database migrations applied successfully
[INFO] Step 9/9: Running tests...
[SUCCESS] All tests passed

==========================================
  Setup Complete!
==========================================
```

#### Option B: Custom Setup

```bash
# Skip tests and migrations for faster setup
./setup.sh --skip-tests --skip-migrations

# Skip build if binary already exists
./setup.sh --skip-build

# Production setup (requires env vars set)
export DATABASE_URL="postgres://..."
export JWT_SECRET="secure-key"
./setup.sh
```

### Step 3: Verify Build Output

```bash
# Check binary was created
ls -lh bin/ide-orchestrator

# Expected: Binary file ~30-50MB
# -rwxr-xr-x  1 user  group   38M Oct 28 12:00 bin/ide-orchestrator

# Verify binary is executable
file bin/ide-orchestrator
# Expected: bin/ide-orchestrator: ELF 64-bit LSB executable

# Check binary version (if version flags implemented)
./bin/ide-orchestrator --version 2>/dev/null || echo "No version flag"
```

### Step 4: Verify Project Structure

```bash
# Check new gateway/orchestration structure exists
ls -la internal/gateway/
# Expected: handlers.go, proxy.go

ls -la internal/orchestration/
# Expected: service.go, spec_engine.go

# Check old directories were removed
test ! -d internal/handlers && echo "✓ Old handlers removed" || echo "✗ Old handlers still present"
test ! -d internal/services && echo "✓ Old services removed" || echo "✗ Old services still present"

# Check migrations exist
ls -la migrations/
# Expected: 4 migration files (000001-000004)
```

### Step 5: Database Setup (If PostgreSQL Available)

```bash
# Check if PostgreSQL is running
pg_isready

# Create database if not exists
createdb agent_builder 2>/dev/null || echo "Database exists"

# Apply migrations manually if setup skipped them
export DATABASE_URL="postgres://postgres:password@localhost:5432/agent_builder?sslmode=disable"
migrate -path ./migrations -database "$DATABASE_URL" up

# Verify migrations applied
psql $DATABASE_URL -c "SELECT version FROM schema_migrations ORDER BY version;"
# Expected: 4 rows (1, 2, 3, 4)

# Check tables created
psql $DATABASE_URL -c "\dt"
# Expected: users, workflows, drafts, proposals, etc.
```

### Step 6: Start the Application

#### Method 1: Using run.sh (Created by setup.sh)

```bash
./run.sh
```

#### Method 2: Direct Binary

```bash
# Set required environment variables
export DATABASE_URL="postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable"
export JWT_SECRET="dev-secret-key"
export SPEC_ENGINE_URL="http://spec-engine-service:8001"

# Run the binary
./bin/ide-orchestrator
```

#### Method 3: Using Make

```bash
make run
```

**Expected Startup Output:**
```
Connected to PostgreSQL database
Starting IDE Orchestrator API server on port 8080
```

### Step 7: Test API Endpoints

Open a new terminal and run these tests:

#### Health Check
```bash
curl -i http://localhost:8080/api/health

# Expected Response:
# HTTP/1.1 200 OK
# Content-Type: application/json
# {"status":"healthy"}
```

#### Swagger Documentation
```bash
# Check Swagger UI is accessible
curl -I http://localhost:8080/swagger/index.html

# Expected Response:
# HTTP/1.1 200 OK
# Content-Type: text/html

# Open in browser
xdg-open http://localhost:8080/swagger/index.html 2>/dev/null || \
open http://localhost:8080/swagger/index.html 2>/dev/null || \
echo "Visit: http://localhost:8080/swagger/index.html"
```

#### Login Endpoint (Requires User in Database)
```bash
# Test login endpoint structure (will fail without user, but endpoint should respond)
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}'

# Expected Response (without user):
# {"error":"invalid credentials"}
# This confirms endpoint is working
```

#### Protected Endpoint Test
```bash
# Test that protected endpoints require auth
curl -I http://localhost:8080/api/workflows

# Expected Response:
# HTTP/1.1 401 Unauthorized
# This confirms JWT middleware is working
```

### Step 8: Run Tests

```bash
# Run all tests
go test ./...

# Expected output:
# ?       github.com/oranger/agent-builder/ide-orchestrator/cmd/api    [no test files]
# ok      github.com/oranger/agent-builder/ide-orchestrator/internal/gateway    0.XYZs
# ok      github.com/oranger/agent-builder/ide-orchestrator/internal/orchestration    0.XYZs
# ...

# Run with verbose output
go test -v ./...

# Run with coverage
go test -cover ./...
```

### Step 9: Docker Testing (Optional)

#### Test Docker Build
```bash
# Build Docker image
docker build -t ide-orchestrator:test .

# Expected: Successfully built and tagged

# Check image size
docker images ide-orchestrator:test
# Expected: ~50-100MB (Alpine-based)

# Run container
docker run -d \
  -p 8080:8080 \
  -e DATABASE_URL="postgres://host.docker.internal:5432/agent_builder?sslmode=disable" \
  -e JWT_SECRET="test-secret" \
  --name ide-orchestrator-test \
  ide-orchestrator:test

# Test health endpoint
sleep 5
curl http://localhost:8080/api/health

# Check logs
docker logs ide-orchestrator-test

# Clean up
docker stop ide-orchestrator-test
docker rm ide-orchestrator-test
```

#### Test Docker Compose
```bash
# Start entire stack
docker-compose up -d

# Check all services are running
docker-compose ps
# Expected: postgres, ide-orchestrator, adminer all "Up"

# Check logs
docker-compose logs -f ide-orchestrator

# Test endpoints
curl http://localhost:8080/api/health

# Access Adminer (database UI)
xdg-open http://localhost:8081 || echo "Visit: http://localhost:8081"

# Clean up
docker-compose down
docker-compose down -v  # Remove volumes too
```

### Step 10: Makefile Testing

```bash
# Test various make targets

# Build
make clean
make build
ls -la bin/ide-orchestrator  # Should exist

# Format
make fmt

# Install tools (if not already installed)
make install-tools

# Regenerate swagger
make swagger

# Migration commands (requires migrate tool)
make migrate-status
make migrate-up
make migrate-down 1  # Rollback 1 migration
make migrate-up      # Reapply

# Docker commands
make docker-build
make docker-run
make docker-stop

# Help
make help  # Should show all available targets
```

### Step 11: Stress Testing (Optional)

```bash
# Test concurrent requests
for i in {1..100}; do
  curl -s http://localhost:8080/api/health > /dev/null &
done
wait

# Test with load testing tool (if available)
# Using apache bench
ab -n 1000 -c 10 http://localhost:8080/api/health

# Using wrk
wrk -t2 -c10 -d30s http://localhost:8080/api/health
```

### Step 12: Stop Application

```bash
# Find and stop the process
pkill -f ide-orchestrator

# Or if running in foreground, use Ctrl+C

# Verify stopped
curl http://localhost:8080/api/health
# Expected: Connection refused
```

## Test Results Checklist

After completing all tests, verify:

- [ ] setup.sh completes without errors
- [ ] Binary created in bin/ide-orchestrator
- [ ] New structure (gateway/, orchestration/) exists
- [ ] Old structure (handlers/, services/) removed
- [ ] run.sh created and works
- [ ] Application starts successfully
- [ ] Health endpoint responds (200 OK)
- [ ] Swagger UI accessible
- [ ] Login endpoint responds (even if auth fails)
- [ ] Protected endpoints require JWT (401)
- [ ] Tests pass (go test ./...)
- [ ] Docker build succeeds
- [ ] Docker container runs
- [ ] Docker Compose stack works
- [ ] Makefile targets execute
- [ ] Application handles concurrent requests
- [ ] Application shuts down gracefully

## Common Issues and Solutions

### Issue 1: Go Version Too Old
**Error:** `go: directive requires go 1.24.0`
**Solution:**
```bash
# Update Go to 1.24.0 or later
wget https://go.dev/dl/go1.24.9.linux-amd64.tar.gz
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go1.24.9.linux-amd64.tar.gz
go version
```

### Issue 2: Database Connection Failed
**Error:** `Failed to connect to database`
**Solution:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql
# or
pg_isready

# Start if not running
sudo systemctl start postgresql

# Create database
createdb agent_builder

# Test connection
psql -d agent_builder -c "SELECT 1;"
```

### Issue 3: Port Already in Use
**Error:** `bind: address already in use`
**Solution:**
```bash
# Find process using port 8080
lsof -i :8080
# or
netstat -tulpn | grep 8080

# Kill the process or use different port
export PORT=8081
./bin/ide-orchestrator
```

### Issue 4: Module Import Errors
**Error:** `cannot find module`
**Solution:**
```bash
# Clean and reinstall dependencies
go clean -modcache
go mod download
go mod tidy
go build ./cmd/api/
```

### Issue 5: Swagger Not Found
**Error:** `404 on /swagger/index.html`
**Solution:**
```bash
# Regenerate swagger docs
swag init -g cmd/api/main.go -o ./docs --parseDependency --parseInternal

# Rebuild application
make build
```

### Issue 6: Migration Dirty State
**Error:** `Dirty database version`
**Solution:**
```bash
# Check current version
migrate -path ./migrations -database "$DATABASE_URL" version

# Force to clean state (use with caution)
migrate -path ./migrations -database "$DATABASE_URL" force VERSION

# Or fix manually
psql $DATABASE_URL -c "UPDATE schema_migrations SET dirty = false;"
```

## Performance Benchmarks

Expected performance metrics:

- **Startup Time**: < 2 seconds
- **Health Check Response**: < 10ms
- **Login Request**: < 100ms
- **Memory Usage**: ~50-100MB
- **Concurrent Requests**: 100+ req/sec on modern hardware

## Security Checklist

- [ ] JWT_SECRET not using default in production
- [ ] DATABASE_URL not exposed in logs
- [ ] HTTPS configured in production

- [ ] CORS properly configured
- [ ] Rate limiting configured (if needed)
- [ ] Database credentials rotated regularly
- [ ] Logs don't contain sensitive data

## Next Steps After Successful Testing

1. **Configure Production Environment**
   - Set strong JWT_SECRET
   - Configure production DATABASE_URL

   - Configure TLS/HTTPS

2. **Set Up Monitoring**
   - Configure Prometheus metrics endpoint
   - Set up Grafana dashboards
   - Configure alerting

3. **Set Up Logging**
   - Configure centralized logging (ELK, Loki)
   - Set appropriate log levels
   - Configure log rotation

4. **Deploy to Production**
   - Use Docker or Kubernetes
   - Configure load balancer
   - Set up health checks
   - Configure auto-scaling

5. **Create Runbooks**
   - Deployment procedures
   - Rollback procedures
   - Incident response
   - Backup and restore

---

**Test Status Template:**

```
=== IDE Orchestrator Test Report ===

Date: _______________
Tester: _____________
Environment: ________

Setup:
[ ] setup.sh completed successfully
[ ] Binary created
[ ] Structure verified

Functionality:
[ ] Application starts
[ ] Health endpoint works
[ ] Swagger UI accessible
[ ] Authentication enforced

Testing:
[ ] Unit tests pass
[ ] Integration tests pass
[ ] Docker build works
[ ] Docker Compose works

Performance:
[ ] Handles concurrent requests
[ ] Memory usage acceptable
[ ] Response times acceptable

Security:
[ ] JWT authentication works
[ ] Protected endpoints secure
[ ] Environment variables set
[ ] No secrets in logs

Status: [ ] PASS  [ ] FAIL

Notes:
________________________________
________________________________
```

---

**Last Updated:** 2025-10-28
**Version:** 1.0.0
