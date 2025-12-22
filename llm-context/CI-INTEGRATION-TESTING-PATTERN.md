# CI Testing Patterns - ide-orchestrator

## Date: 2024-12-21
## Context: In-Cluster Testing Strategy for Production-Grade Go CI/CD

---

## Core Testing Patterns

### 1. **Quality Gate Pattern**
- Auto-discovers all quality workflows without manual configuration
- Prevents production deployments until all quality checks pass
- Smart filtering distinguishes quality checks from deployment workflows
- Never requires updates when adding new test workflows

### 2. **Reusable In-Cluster Testing Pattern**
- Tests run in identical infrastructure to production (Kubernetes cluster)
- Uses real service dependencies (PostgreSQL, Spec Engine services)
- GitOps-based deployment mirrors production patterns
- Tests execute as Kubernetes Jobs within the cluster

### 3. **Environment Consistency Pattern**
- CI environment replicates production networking and security
- Auto-generated secrets and credential injection
- In-cluster DNS resolution and service communication
- Environment-specific resource optimization for CI efficiency

### 4. **Go-Specific Testing Pattern**
- Built-in Go testing framework with table-driven tests
- Concurrent test execution with goroutines
- Mock external services (Spec Engine) for isolated testing
- Integration tests with real PostgreSQL database

---

## CI Stability Scripts

### Mandatory Project Structure
```
scripts/
├── ci/                           # Core CI automation scripts
│   ├── build.sh                  # Go binary building (production/CI modes)
│   ├── deploy.sh                 # GitOps service deployment automation
│   ├── in-cluster-test.sh        # Main in-cluster Go test execution script
│   ├── test-job-template.yaml    # Kubernetes Job template for Go tests
│   ├── run.sh                    # Go service runtime execution
│   ├── run-migrations.sh         # Database migration execution
│   ├── pre-deploy-diagnostics.sh # Infrastructure readiness validation
│   ├── post-deploy-diagnostics.sh# Service health verification
│   └── validate-platform-dependencies.sh # Platform dependency checks
├── helpers/                      # Service readiness utilities
│   ├── wait-for-postgres.sh      # PostgreSQL readiness validation
│   ├── wait-for-<service>.sh   # Spec Engine service readiness validation
│   ├── wait-for-externalsecret.sh# External Secrets Operator validation
│   └── wait-for-secret.sh        # Kubernetes secret availability validation
├── patches/                      # CI environment optimizations
│   ├── 00-apply-all-patches.sh   # Master patch application script
│   ├── 01-downsize-postgres.sh   # PostgreSQL resource optimization
│   ├── 02-downsize-<service>.sh# Spec Engine resource optimization
│   └── 03-downsize-application.sh# Go application resource optimization
└── local/                        # Local development utilities
    └── ci/                       # Local CI simulation scripts
```

### Core CI Scripts (`scripts/ci/`)
- **`build.sh`**: Go binary building with production and CI modes, multi-stage Docker builds
- **`deploy.sh`**: Service deployment automation using GitOps patterns
- **`in-cluster-test.sh`**: Main script for running Go test suites in Kubernetes cluster
- **`run.sh`**: Go service runtime execution script
- **`run-migrations.sh`**: Database migration execution using golang-migrate

### Infrastructure Management Scripts
- **`pre-deploy-diagnostics.sh`**: Infrastructure readiness validation before deployment
- **`post-deploy-diagnostics.sh`**: Service health verification after deployment
- **`validate-platform-dependencies.sh`**: Platform dependency validation

### Resource Optimization Scripts (`scripts/patches/`)
- **`00-apply-all-patches.sh`**: Applies all CI environment optimizations
- **`01-downsize-postgres.sh`**: PostgreSQL resource optimization for CI
- **`02-downsize-<service>.sh`**: Spec Engine service resource optimization for CI
- **`03-downsize-application.sh`**: Go application resource optimization for CI

### Service Helper Scripts (`scripts/helpers/`)
- **`wait-for-postgres.sh`**: PostgreSQL readiness validation
- **`wait-for-<service>.sh`**: Spec Engine service readiness validation
- **`wait-for-externalsecret.sh`**: External Secrets Operator validation
- **`wait-for-secret.sh`**: Kubernetes secret availability validation

### Test Infrastructure
- **`test-job-template.yaml`**: Kubernetes Job template for in-cluster Go test execution
- **`tests/integration/cluster_config.go`**: Centralized test configuration for in-cluster execution

### **MANDATORY: Template Reuse Requirement**
**ALL CI workflows MUST reuse the standard templates:**
- **`.github/workflows/in-cluster-test.yml`**: Reusable workflow template - MUST be used by all test workflows
- **`scripts/ci/test-job-template.yaml`**: Kubernetes Job template - MUST be used for all in-cluster test execution
- **No custom workflow implementations** - ensures consistency, maintainability, and reliability across all services
- **Template parameters** provide customization while maintaining standardized infrastructure patterns

---

## Go-Specific Testing Adaptations

### 1. **Test Execution Pattern**
- **Unit Tests**: `go test ./internal/...` - Co-located with source code
- **Integration Tests**: `go test ./tests/integration/...` - Centralized test directory
- **Table-Driven Tests**: Standard Go testing pattern for comprehensive coverage
- **Concurrent Execution**: Leverage Go's goroutines for parallel test execution

### 2. **Database Integration**
- **pgx Connection Pooling**: Real PostgreSQL connections in tests
- **Transaction Rollback**: Clean test isolation using database transactions
- **Migration Testing**: Validate database schema changes
- **Connection Management**: Proper cleanup and resource management

### 3. **HTTP API Testing**
- **httptest Package**: Standard Go HTTP testing utilities
- **Gin Test Mode**: Framework-specific testing configurations
- **WebSocket Testing**: gorilla/websocket test patterns
- **JWT Authentication**: Token generation and validation testing

### 4. **Mock Service Integration**
- **Mock Spec Engine**: Complete HTTP/WebSocket mock implementation
- **Interface Mocking**: Go interface-based mocking patterns
- **Dependency Injection**: Testable service architecture
- **External Service Simulation**: Realistic mock responses

---

## Testing Flow

1. **Code Change Trigger**: Path-based triggering for Go source files and tests
2. **Parallel Test Execution**: Multiple Go test suites run simultaneously
3. **Infrastructure Provisioning**: Automated cluster and service setup
4. **In-Cluster Test Jobs**: Go tests execute within Kubernetes environment
5. **Quality Gate Validation**: Auto-discovery of all workflow results
6. **Production Build**: Triggered only after all quality checks pass

---

## Go Test Categories

### 1. **Unit Tests** (`*_test.go` files)
- **Gateway Layer**: HTTP handler testing with httptest
- **Orchestration Layer**: Business logic testing with mocks
- **Auth Package**: JWT generation and validation
- **Models Package**: Data structure validation

### 2. **Integration Tests** (`tests/integration/`)
- **Workflow Integration**: Complete workflow lifecycle testing
- **Authentication Integration**: End-to-end auth flow testing
- **Refinement Integration**: Spec Engine integration with WebSocket streaming
- **Database Integration**: Real PostgreSQL operations

### 3. **Performance Tests**
- **Concurrent Request Handling**: Load testing with goroutines
- **Database Connection Pooling**: Connection management under load
- **Memory Usage**: Go runtime memory profiling
- **Response Time**: API endpoint performance validation

---

## Key Benefits

- **High Confidence**: Tests against real infrastructure eliminate environment-specific issues
- **Go-Native Patterns**: Leverages Go's built-in testing framework and concurrency
- **Type Safety**: Compile-time validation ensures robust test code
- **Fast Execution**: Go's fast compilation and execution speeds up CI cycles
- **Resource Efficient**: Go's low memory footprint optimizes CI resource usage
- **Observable**: Comprehensive diagnostics enable quick issue resolution

---

## Best Practices

### DO
- Use real infrastructure components for integration testing
- Leverage Go's built-in testing framework and patterns
- Implement table-driven tests for comprehensive coverage
- Use interface-based mocking for external dependencies
- Auto-inject credentials from Kubernetes secrets
- Mirror production deployment patterns in CI
- Use smart resource optimization for CI environments
- Implement proper test cleanup and resource management

### DON'T
- Mock infrastructure components in integration tests
- Hardcode credentials or connection strings
- Skip comprehensive failure diagnostics
- Use different deployment patterns between CI and production
- Ignore resource constraints and cleanup procedures
- Mix unit and integration test concerns
- Create custom workflow implementations outside templates

-----

This Go-specific CI testing pattern maintains consistency with the Python deepagents-runtime approach while leveraging Go's unique strengths and testing ecosystem.