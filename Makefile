.PHONY: build test run clean deps lint swagger docker-build docker-run migrate-up migrate-down migrate-create help

# Variables
BINARY_NAME=ide-orchestrator
DOCKER_IMAGE=bizmatters/ide-orchestrator
VERSION?=latest
DATABASE_URL?=postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable

# Build the application
build:
	@echo "Building $(BINARY_NAME)..."
	@mkdir -p bin
	@go build -ldflags="-X main.BuildTime=$$(date -u '+%Y-%m-%d_%H:%M:%S') -X main.GitCommit=$$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" -o bin/$(BINARY_NAME) ./cmd/api
	@echo "Build complete: bin/$(BINARY_NAME)"

# Run tests
test:
	@echo "Running tests..."
	@go test -v ./...

# Run tests with coverage
test-coverage:
	@echo "Running tests with coverage..."
	@go test -cover -coverprofile=coverage.out ./...
	@go tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report: coverage.html"

# Run the application
run:
	@echo "Running $(BINARY_NAME)..."
	@go run ./cmd/api

# Start the application (requires build first)
start:
	@echo "Starting $(BINARY_NAME)..."
	@./bin/$(BINARY_NAME)

# Clean build artifacts
clean:
	@echo "Cleaning..."
	@rm -rf bin/
	@rm -f coverage.out coverage.html
	@echo "Clean complete"

# Install dependencies
deps:
	@echo "Installing dependencies..."
	@go mod download
	@go mod tidy
	@echo "Dependencies installed"

# Lint code (requires golangci-lint)
lint:
	@echo "Linting code..."
	@golangci-lint run

# Format code
fmt:
	@echo "Formatting code..."
	@go fmt ./...
	@gofmt -s -w .

# Regenerate Swagger documentation (requires swag)
swagger:
	@echo "Regenerating Swagger docs..."
	@swag init -g cmd/api/main.go -o ./docs --parseDependency --parseInternal --parseDepth 3
	@echo "Swagger docs regenerated"

# Install development tools
install-tools:
	@echo "Installing development tools..."
	@go install github.com/swaggo/swag/cmd/swag@latest
	@go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
	@go install -tags 'postgres' github.com/golang-migrate/migrate/v4/cmd/migrate@latest
	@go install github.com/air-verse/air@latest
	@echo "Tools installed"

# Docker build
docker-build:
	@echo "Building Docker image..."
	@docker build -t $(DOCKER_IMAGE):$(VERSION) .
	@docker tag $(DOCKER_IMAGE):$(VERSION) $(DOCKER_IMAGE):latest
	@echo "Docker image built: $(DOCKER_IMAGE):$(VERSION)"

# Docker run
docker-run:
	@echo "Running Docker container..."
	@docker run -d \
		-p 8080:8080 \
		-e DATABASE_URL="$(DATABASE_URL)" \
		-e JWT_SECRET="dev-secret-key" \
		-e SPEC_ENGINE_URL="http://spec-engine-service:8000" \
		--name $(BINARY_NAME) \
		$(DOCKER_IMAGE):latest

# Docker stop
docker-stop:
	@docker stop $(BINARY_NAME) || true
	@docker rm $(BINARY_NAME) || true

# Run database migrations up
migrate-up:
	@echo "Running migrations up..."
	@migrate -path ./migrations -database "$(DATABASE_URL)" up
	@echo "Migrations complete"

# Run database migrations down
migrate-down:
	@echo "Running migrations down..."
	@migrate -path ./migrations -database "$(DATABASE_URL)" down
	@echo "Migrations rolled back"

# Create new migration
migrate-create:
	@read -p "Enter migration name: " name; \
	migrate create -ext sql -dir ./migrations -seq $$name
	@echo "Migration files created in ./migrations/"

# Check migration status
migrate-status:
	@echo "Migration status:"
	@migrate -path ./migrations -database "$(DATABASE_URL)" version

# Development with hot reload (requires air)
dev:
	@echo "Starting development mode with hot reload..."
	@air

# Run setup script
setup:
	@echo "Running setup script..."
	@./setup.sh --dev

# Show help
help:
	@echo "Available targets:"
	@echo "  build           - Build the application"
	@echo "  test            - Run tests"
	@echo "  test-coverage   - Run tests with coverage report"
	@echo "  run             - Run the application (development)"
	@echo "  start           - Start the built binary"
	@echo "  clean           - Clean build artifacts"
	@echo "  deps            - Install dependencies"
	@echo "  lint            - Lint code (requires golangci-lint)"
	@echo "  fmt             - Format code"
	@echo "  swagger         - Regenerate Swagger docs (requires swag)"
	@echo "  install-tools   - Install development tools"
	@echo "  docker-build    - Build Docker image"
	@echo "  docker-run      - Run Docker container"
	@echo "  docker-stop     - Stop Docker container"
	@echo "  migrate-up      - Run database migrations"
	@echo "  migrate-down    - Rollback database migrations"
	@echo "  migrate-create  - Create new migration"
	@echo "  migrate-status  - Check migration status"
	@echo "  dev             - Run with hot reload (requires air)"
	@echo "  setup           - Run setup script"
	@echo "  help            - Show this help message"
