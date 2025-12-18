# IDE Orchestrator

AI-powered workflow builder API for multi-agent orchestration. The IDE Orchestrator serves as the backend gateway and orchestration layer for the Agentic IDE, managing workflows, drafts, proposals, and Spec Engine integration.

## Architecture

This service follows a clean architecture pattern with clear separation of concerns:

```
internal/
├── gateway/           # HTTP/WebSocket networking layer
│   ├── handlers.go    # Thin HTTP handlers
│   └── proxy.go       # WebSocket proxy to Spec Engine
├── orchestration/     # Pure business logic layer
│   ├── service.go     # Workflow & user operations
│   └── spec_engine.go # Spec Engine client
├── auth/             # JWT authentication
├── models/           # Domain models
├── database/         # Database utilities
├── metrics/          # Prometheus metrics
├── telemetry/        # OpenTelemetry tracing

```

### Design Principles

- **Gateway Layer**: Handles HTTP request/response, WebSocket proxying, authentication
- **Orchestration Layer**: Implements business logic, workflow management, database transactions
- **No HTTP in Business Logic**: Orchestration layer uses pure Go types, fully testable
- **Future-Proof**: Easy to split into separate microservices if needed

## Features

- **Workflow Management**: Create, version, and deploy LangGraph-based AI workflows
- **Draft System**: Iterative workflow refinement with proposal approval/rejection
- **Spec Engine Integration**: AI-powered workflow generation via Python microservice
- **Real-Time Updates**: WebSocket streaming of Spec Engine progress
- **Authentication**: JWT-based authentication
- **Observability**: OpenTelemetry tracing, structured logging, Prometheus metrics
- **Database**: PostgreSQL with pgx connection pooling

## Quick Start

### Prerequisites

- **Go 1.24.0+** ([Download](https://golang.org/dl/))
- **PostgreSQL 15+** ([Download](https://www.postgresql.org/download/))
- **golang-migrate** (optional): `go install -tags 'postgres' github.com/golang-migrate/migrate/v4/cmd/migrate@latest`
- **swag** (optional): `go install github.com/swaggo/swag/cmd/swag@latest`

### Installation

1. **Clone the repository:**
   ```bash
   cd /path/to/bizmatters/services/ide-orchestrator
   ```

2. **Run the setup script:**
   ```bash
   ./setup.sh
   ```

   Or for development with defaults:
   ```bash
   ./setup.sh --dev
   ```

3. **Start the application:**
   ```bash
   ./run.sh
   ```

   Or manually:
   ```bash
   export DATABASE_URL="postgres://postgres:password@localhost:5432/agent_builder?sslmode=disable"
   export JWT_SECRET="your-secret-key"
   export SPEC_ENGINE_URL="http://spec-engine-service:8000"
   ./bin/ide-orchestrator
   ```

### Setup Options

```bash
./setup.sh [options]

Options:
  --skip-build       Skip building the application
  --skip-tests       Skip running tests
  --skip-migrations  Skip database migrations
  --dev              Set up for development (uses defaults)
  --help             Show help message
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable` |
| `JWT_SECRET` | Secret key for JWT signing | `dev-secret-key-change-in-production` |
| `SPEC_ENGINE_URL` | Spec Engine service URL | `http://spec-engine-service:8000` |
| `PORT` | HTTP server port | `8080` |


### Database Setup

1. **Create the database:**
   ```bash
   createdb agent_builder
   ```

2. **Apply migrations:**
   ```bash
   migrate -path ./migrations -database "$DATABASE_URL" up
   ```

   Migrations include:
   - `000001`: Users table
   - `000002`: Workflow tables
   - `000003`: Draft and proposal tables
   - `000004`: Spec Engine integration (thread_id, execution_trace)

## API Documentation

### Swagger UI

Access interactive API documentation at:
```
http://localhost:8080/swagger/index.html
```

### Key Endpoints

**Authentication:**
- `POST /api/auth/login` - User login (returns JWT token)

**Workflows:**
- `POST /api/workflows` - Create new workflow
- `GET /api/workflows/:id` - Get workflow by ID
- `GET /api/workflows/:id/versions` - List workflow versions
- `POST /api/workflows/:id/deploy` - Deploy workflow version

**Drafts & Refinements:**
- `POST /api/refinements` - Create refinement (invokes Spec Engine)
- `GET /api/ws/refinements/:thread_id` - WebSocket stream of Spec Engine progress
- `POST /api/proposals/:id/approve` - Approve AI-generated proposal
- `POST /api/proposals/:id/reject` - Reject proposal
- `DELETE /api/drafts/:id` - Discard draft

**Health:**
- `GET /api/health` - Health check endpoint

## Development

### Project Structure

```
ide-orchestrator/
├── cmd/
│   └── api/
│       └── main.go           # Application entry point
├── internal/
│   ├── gateway/              # HTTP/WebSocket layer
│   ├── orchestration/        # Business logic layer
│   ├── auth/                 # Authentication
│   ├── models/               # Domain models
│   └── ...                   # Supporting packages
├── migrations/               # Database migrations
├── docs/                     # Swagger documentation
├── bin/                      # Compiled binaries
├── setup.sh                  # Setup script
├── run.sh                    # Convenience run script
├── Makefile                  # Build commands
└── README.md                 # This file
```

### Building

```bash
# Build
make build

# Build and run
make run

# Run tests
make test

# Clean build artifacts
make clean

# Install dependencies
make deps

# Regenerate Swagger docs
make swagger
```

### Testing

```bash
# Run all tests
go test ./...

# Run tests with coverage
go test -cover ./...

# Run tests with verbose output
go test -v ./...

# Test specific package
go test ./internal/orchestration/...
```

### Adding New Endpoints

1. **Add handler in `internal/gateway/handlers.go`:**
   ```go
   func (h *Handler) YourEndpoint(c *gin.Context) {
       // Parse request
       var req YourRequest
       if err := c.ShouldBindJSON(&req); err != nil {
           c.JSON(400, gin.H{"error": err.Error()})
           return
       }

       // Call orchestration layer
       result, err := h.orch.YourBusinessLogic(c.Request.Context(), req.Data)
       if err != nil {
           c.JSON(500, gin.H{"error": err.Error()})
           return
       }

       c.JSON(200, result)
   }
   ```

2. **Add business logic in `internal/orchestration/service.go`:**
   ```go
   func (s *Service) YourBusinessLogic(ctx context.Context, data string) (*Result, error) {
       // Pure business logic - no HTTP dependencies
       // ...
       return result, nil
   }
   ```

3. **Register route in `cmd/api/main.go`:**
   ```go
   protected.POST("/your-endpoint", handler.YourEndpoint)
   ```

4. **Regenerate Swagger:**
   ```bash
   swag init -g cmd/api/main.go -o ./docs --parseDependency --parseInternal
   ```

## Architecture Decisions

### Why Gateway + Orchestration?

**Gateway Layer** (Thin):
- Handles HTTP/WebSocket protocol concerns
- Request parsing and validation
- Response formatting
- Authentication middleware
- 5-30 lines per handler

**Orchestration Layer** (Thick):
- Pure business logic
- No HTTP dependencies
- Database transactions
- Spec Engine communication
- Fully unit testable

**Benefits:**
- Clear separation of concerns
- Easy to test business logic
- Future-proof for microservices split
- No mixing of networking and business logic

### Spec Engine Integration

The IDE Orchestrator integrates with the Spec Engine (Python/LangGraph microservice) via:

1. **REST API** for invocation:
   - `POST /spec-engine/invoke` - Start workflow generation
   - `GET /spec-engine/state/:thread_id` - Get final state

2. **WebSocket** for real-time updates:
   - `WS /spec-engine/stream/:thread_id` - Stream progress
   - Proxied through IDE Orchestrator with JWT auth

3. **State Management**:
   - LangGraph checkpointer stores execution state
   - IDE Orchestrator cleans up checkpointer data after proposal resolution

## Deployment

### Docker

```bash
# Build image
docker build -t ide-orchestrator:latest .

# Run container
docker run -d \
  -p 8080:8080 \
  -e DATABASE_URL="postgres://..." \
  -e JWT_SECRET="..." \
  -e SPEC_ENGINE_URL="http://spec-engine-service:8000" \
  ide-orchestrator:latest
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ide-orchestrator
spec:
  replicas: 2
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
        image: bizmatters/ide-orchestrator:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ide-orchestrator-secrets
              key: database-url
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: ide-orchestrator-secrets
              key: jwt-secret
        - name: SPEC_ENGINE_URL
          value: "http://spec-engine-service:8001"
```

## Troubleshooting

### Database Connection Failed

**Error:** `Failed to connect to database`

**Solution:**
- Ensure PostgreSQL is running: `pg_isready`
- Check DATABASE_URL is correct
- Verify database exists: `psql -d agent_builder -c "SELECT 1;"`

### Migration Errors

**Error:** `Dirty database version`

**Solution:**
```bash
# Force version (use with caution)
migrate -path ./migrations -database "$DATABASE_URL" force VERSION

# Or manually fix via SQL
psql "$DATABASE_URL" -c "UPDATE schema_migrations SET dirty = false WHERE version = VERSION;"
```

### Spec Engine Unreachable

**Error:** `Failed to invoke Spec Engine: connection refused`

**Solution:**
- Verify Spec Engine is running
- Check SPEC_ENGINE_URL is correct
- Ensure network connectivity (same Kubernetes cluster/network)

### JWT Token Invalid

**Error:** `Invalid token`

**Solution:**
- Check JWT_SECRET is set correctly
- Ensure token hasn't expired (24h default)
- Verify Authorization header format: `Bearer <token>`

## Contributing

### Code Style

- Follow standard Go conventions
- Use `gofmt` for formatting
- Add Swagger comments for all endpoints
- Write tests for business logic
- Keep gateway handlers thin (< 30 lines)

### Commit Messages

Follow conventional commits:
```
feat: Add new endpoint for workflow export
fix: Fix race condition in draft locking
docs: Update API documentation
refactor: Separate gateway and orchestration layers
```

## License

MIT License - See LICENSE file for details

## Support

For issues and questions:
- GitHub Issues: [bizmatters/ide-orchestrator](https://github.com/oranger/bizmatters)
- Email: support@bizmatters.dev

## Related Services

- **Spec Engine**: Python/LangGraph microservice for AI-powered workflow generation
- **Agentic IDE**: Next.js frontend application
- **PostgreSQL**: Primary data store


---

**Version**: 1.0.0
**Last Updated**: 2025-10-28
**Architecture**: Gateway + Orchestration Pattern
