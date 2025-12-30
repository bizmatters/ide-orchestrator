# Build stage
FROM golang:1.24-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git ca-certificates tzdata

# Install golang-migrate tool
RUN go install -tags 'postgres' github.com/golang-migrate/migrate/v4/cmd/migrate@latest

# Set working directory
WORKDIR /build

# Copy go mod files
COPY go.mod go.sum ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-w -s -X main.BuildTime=$(date -u '+%Y-%m-%d_%H:%M:%S') -X main.GitCommit=$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
    -o ide-orchestrator \
    ./cmd/api/

# Runtime stage
FROM alpine:latest

# Install runtime dependencies
RUN apk add --no-cache ca-certificates tzdata bash postgresql-client

# Create non-root user
RUN addgroup -g 1000 app && \
    adduser -D -u 1000 -G app app

# Set working directory
WORKDIR /app

# Copy binary, migrations, and scripts from builder
COPY --from=builder /build/ide-orchestrator ./bin/ide-orchestrator
COPY --from=builder /build/migrations ./migrations
COPY --from=builder /build/scripts ./scripts
COPY --from=builder /go/bin/migrate /usr/local/bin/migrate

# Copy tests and source for in-cluster execution
COPY --from=builder /build/tests ./tests
COPY --from=builder /build/internal ./internal
COPY --from=builder /build/cmd ./cmd
COPY --from=builder /build/pkg ./pkg
COPY --from=builder /build/go.mod /build/go.sum ./

# Make scripts executable
RUN chmod +x ./scripts/ci/*.sh

# Set ownership
RUN chown -R app:app /app

# Switch to non-root user
USER app

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/api/health || exit 1

# Run the application using the runtime bootstrapper
CMD ["./scripts/ci/run.sh"]
