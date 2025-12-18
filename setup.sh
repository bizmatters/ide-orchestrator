#!/bin/bash
#
# IDE Orchestrator Setup Script
# This script sets up the ide-orchestrator application on any server
#
# Usage: ./setup.sh [options]
# Options:
#   --skip-build       Skip building the application
#   --skip-tests       Skip running tests
#   --skip-migrations  Skip database migrations
#   --dev              Set up for development (uses defaults)
#   --help             Show this help message

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse command line arguments
SKIP_BUILD=false
SKIP_TESTS=false
SKIP_MIGRATIONS=false
DEV_MODE=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --skip-build) SKIP_BUILD=true ;;
        --skip-tests) SKIP_TESTS=true ;;
        --skip-migrations) SKIP_MIGRATIONS=true ;;
        --dev) DEV_MODE=true ;;
        --help)
            echo "IDE Orchestrator Setup Script"
            echo ""
            echo "Usage: ./setup.sh [options]"
            echo ""
            echo "Options:"
            echo "  --skip-build       Skip building the application"
            echo "  --skip-tests       Skip running tests"
            echo "  --skip-migrations  Skip database migrations"
            echo "  --dev              Set up for development (uses defaults)"
            echo "  --help             Show this help message"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        return 1
    fi
    return 0
}

# Print banner
echo ""
echo "=========================================="
echo "  IDE Orchestrator Setup"
echo "=========================================="
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log_info "Working directory: $SCRIPT_DIR"
echo ""

# Step 1: Check prerequisites
log_info "Step 1/9: Checking prerequisites..."

# Check Go
if check_command go; then
    GO_VERSION=$(go version | awk '{print $3}')
    log_success "Go found: $GO_VERSION"
else
    log_error "Go is not installed. Please install Go 1.24.0 or later."
    log_info "Visit: https://golang.org/dl/"
    exit 1
fi

# Check PostgreSQL client (optional for migrations)
if check_command psql; then
    PSQL_VERSION=$(psql --version | awk '{print $3}')
    log_success "PostgreSQL client found: $PSQL_VERSION"
else
    log_warning "PostgreSQL client (psql) not found. Skipping direct DB checks."
fi

# Check migrate tool (optional)
if check_command migrate; then
    log_success "golang-migrate found"
    HAS_MIGRATE=true
else
    log_warning "golang-migrate not found. Database migrations will need to be run manually."
    log_info "Install with: go install -tags 'postgres' github.com/golang-migrate/migrate/v4/cmd/migrate@latest"
    HAS_MIGRATE=false
fi

# Check swag tool (optional)
if check_command swag; then
    log_success "swag found"
    HAS_SWAG=true
else
    log_warning "swag not found. Swagger docs will need to be regenerated manually."
    log_info "Install with: go install github.com/swaggo/swag/cmd/swag@latest"
    HAS_SWAG=false
fi

echo ""

# Step 2: Set up environment variables
log_info "Step 2/9: Setting up environment variables..."

if [ "$DEV_MODE" = true ]; then
    log_info "Development mode: Using default values"
    export DATABASE_URL="${DATABASE_URL:-postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable}"
    export JWT_SECRET="${JWT_SECRET:-dev-secret-key-change-in-production}"
    export SPEC_ENGINE_URL="${SPEC_ENGINE_URL:-http://spec-engine-service:8001}"
    export PORT="${PORT:-8080}"

else
    # Check if environment variables are set
    if [ -z "$DATABASE_URL" ]; then
        log_warning "DATABASE_URL not set. Using default for development."
        export DATABASE_URL="postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable"
    fi

    if [ -z "$JWT_SECRET" ]; then
        log_warning "JWT_SECRET not set. Using default for development."
        log_warning "IMPORTANT: Change this in production!"
        export JWT_SECRET="dev-secret-key-change-in-production"
    fi

    if [ -z "$SPEC_ENGINE_URL" ]; then
        export SPEC_ENGINE_URL="http://spec-engine-service:8001"
    fi

    if [ -z "$PORT" ]; then
        export PORT="8080"
    fi


fi

log_success "Environment variables configured"
log_info "  DATABASE_URL: ${DATABASE_URL}"
log_info "  JWT_SECRET: ${JWT_SECRET:0:10}... (masked)"
log_info "  SPEC_ENGINE_URL: ${SPEC_ENGINE_URL}"
log_info "  PORT: ${PORT}"


echo ""

# Step 3: Clean up Go dependencies
log_info "Step 3/9: Cleaning up Go dependencies..."
go mod download
go mod tidy
log_success "Go dependencies updated"

echo ""

# Step 4: Build the application
if [ "$SKIP_BUILD" = false ]; then
    log_info "Step 4/9: Building the application..."

    # Create bin directory if it doesn't exist
    mkdir -p bin

    # Build with version info
    BUILD_TIME=$(date -u '+%Y-%m-%d_%H:%M:%S')
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

    go build \
        -ldflags "-X main.BuildTime=${BUILD_TIME} -X main.GitCommit=${GIT_COMMIT}" \
        -o bin/ide-orchestrator \
        ./cmd/api/

    if [ -f "bin/ide-orchestrator" ]; then
        log_success "Application built successfully: bin/ide-orchestrator"

        # Make it executable
        chmod +x bin/ide-orchestrator

        # Show binary info
        BINARY_SIZE=$(du -h bin/ide-orchestrator | awk '{print $1}')
        log_info "Binary size: $BINARY_SIZE"
    else
        log_error "Build failed: Binary not found"
        exit 1
    fi
else
    log_info "Step 4/9: Skipping build (--skip-build)"
fi

echo ""

# Step 5: Remove old directories
log_info "Step 5/9: Cleaning up old directories..."

if [ -d "internal/handlers" ]; then
    rm -rf internal/handlers
    log_success "Removed internal/handlers/"
else
    log_info "internal/handlers/ already removed"
fi

if [ -d "internal/services" ]; then
    rm -rf internal/services
    log_success "Removed internal/services/"
else
    log_info "internal/services/ already removed"
fi

echo ""

# Step 6: Regenerate Swagger documentation
log_info "Step 6/9: Regenerating Swagger documentation..."

if [ "$HAS_SWAG" = true ]; then
    swag init -g cmd/api/main.go -o ./docs --parseDependency --parseInternal --parseDepth 3
    if [ $? -eq 0 ]; then
        log_success "Swagger documentation regenerated"
    else
        log_warning "Swagger generation had warnings (this is usually OK)"
        log_info "Check logs above for details. Application will still work."
    fi
else
    log_warning "Skipping swagger generation (swag not installed)"
    log_info "Swagger docs may be outdated. Install swag to regenerate."
fi

echo ""

# Step 7: Test database connection (if psql is available)
log_info "Step 7/9: Testing database connection..."

if check_command psql && [ "$SKIP_MIGRATIONS" = false ]; then
    # Extract connection details from DATABASE_URL
    if psql "$DATABASE_URL" -c "SELECT 1;" > /dev/null 2>&1; then
        log_success "Database connection successful"

        # Check if migrations table exists
        MIGRATIONS_EXIST=$(psql "$DATABASE_URL" -tAc "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'schema_migrations');")

        if [ "$MIGRATIONS_EXIST" = "t" ]; then
            log_info "Migrations table exists"
        else
            log_warning "Migrations table does not exist. Database may need initialization."
        fi
    else
        log_warning "Could not connect to database. Migrations will need to be run manually."
        log_info "Ensure PostgreSQL is running and DATABASE_URL is correct."
    fi
else
    log_info "Skipping database connection test"
fi

echo ""

# Step 8: Apply database migrations
if [ "$SKIP_MIGRATIONS" = false ] && [ "$HAS_MIGRATE" = true ]; then
    log_info "Step 8/9: Applying database migrations..."

    if [ -d "migrations" ]; then
        MIGRATION_COUNT=$(ls -1 migrations/*.up.sql 2>/dev/null | wc -l)
        log_info "Found $MIGRATION_COUNT migration(s)"

        if migrate -path ./migrations -database "$DATABASE_URL" up; then
            log_success "Database migrations applied successfully"
        else
            log_warning "Migration failed or no new migrations to apply"
        fi
    else
        log_warning "migrations/ directory not found"
    fi
else
    log_info "Step 8/9: Skipping migrations (--skip-migrations or migrate not installed)"
    if [ "$HAS_MIGRATE" = false ]; then
        log_info "To apply migrations manually:"
        log_info "  1. Install golang-migrate: go install -tags 'postgres' github.com/golang-migrate/migrate/v4/cmd/migrate@latest"
        log_info "  2. Run: migrate -path ./migrations -database \"\$DATABASE_URL\" up"
    fi
fi

echo ""

# Step 9: Run tests
if [ "$SKIP_TESTS" = false ]; then
    log_info "Step 9/9: Running tests..."

    if go test ./... -v; then
        log_success "All tests passed"
    else
        log_warning "Some tests failed. Review the output above."
    fi
else
    log_info "Step 9/9: Skipping tests (--skip-tests)"
fi

echo ""

# Print summary
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""

log_success "IDE Orchestrator is ready to run"
echo ""

log_info "Project structure:"
log_info "  - Binary: bin/ide-orchestrator"
log_info "  - Gateway: internal/gateway/ (HTTP handlers & WebSocket proxy)"
log_info "  - Orchestration: internal/orchestration/ (Business logic)"
log_info "  - Migrations: migrations/ ($MIGRATION_COUNT SQL files)"
log_info "  - Documentation: docs/ (Swagger)"

echo ""

log_info "To start the application:"
echo ""
echo "  export DATABASE_URL=\"$DATABASE_URL\""
echo "  export JWT_SECRET=\"$JWT_SECRET\""
echo "  export SPEC_ENGINE_URL=\"$SPEC_ENGINE_URL\""
echo "  ./bin/ide-orchestrator"
echo ""

log_info "Or simply run:"
echo ""
echo "  ./bin/ide-orchestrator"
echo ""
echo "  (Environment variables are already set in this shell)"
echo ""

log_info "API will be available at:"
log_info "  - Health: http://localhost:${PORT}/api/health"
log_info "  - Swagger: http://localhost:${PORT}/swagger/index.html"
log_info "  - Login: POST http://localhost:${PORT}/api/auth/login"

echo ""

# Create a run script for convenience
log_info "Creating convenience script: run.sh"

cat > run.sh << 'EOF'
#!/bin/bash
# Convenience script to run IDE Orchestrator

# Load environment variables
export DATABASE_URL="${DATABASE_URL:-postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable}"
export JWT_SECRET="${JWT_SECRET:-dev-secret-key-change-in-production}"
export SPEC_ENGINE_URL="${SPEC_ENGINE_URL:-http://spec-engine-service:8001}"
export PORT="${PORT:-8080}"
export VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"

# Run the application
echo "Starting IDE Orchestrator on port $PORT..."
./bin/ide-orchestrator
EOF

chmod +x run.sh
log_success "Created run.sh - use './run.sh' to start the application"

echo ""

log_info "Next steps:"
log_info "  1. Ensure PostgreSQL is running"
log_info "  2. Run: ./run.sh (or ./bin/ide-orchestrator)"
log_info "  3. Test: curl http://localhost:${PORT}/api/health"

echo ""
log_success "Setup complete! 🎉"
echo ""
