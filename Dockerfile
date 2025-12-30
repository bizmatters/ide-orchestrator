# Build stage
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Copy dependency files first for better caching
COPY pyproject.toml ./

# Copy all source code
COPY api ./api
COPY core ./core
COPY models ./models
COPY services ./services
COPY tests ./tests
COPY migrations ./migrations
COPY scripts ./scripts

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]"

# Runtime stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    ca-certificates \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 app && \
    useradd -u 1000 -g app -s /bin/bash -m app

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy ALL application code and files
COPY --from=builder /build/api ./api
COPY --from=builder /build/core ./core
COPY --from=builder /build/models ./models
COPY --from=builder /build/services ./services
COPY --from=builder /build/tests ./tests
COPY --from=builder /build/migrations ./migrations
COPY --from=builder /build/scripts ./scripts
COPY --from=builder /build/pyproject.toml ./

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
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

# Use the CI run script as entrypoint
ENTRYPOINT ["./scripts/ci/run.sh"]
