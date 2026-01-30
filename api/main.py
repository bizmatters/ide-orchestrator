"""FastAPI application for IDE Orchestrator."""

import os
from fastapi import FastAPI, Header, HTTPException
from typing import Optional
from contextlib import asynccontextmanager

from api.routers import health, workflows, refinements, websockets
from core.metrics import metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    metrics_port = int(os.getenv("METRICS_PORT", "8090"))
    metrics.start_metrics_server(metrics_port)
    print(f"🔢 Prometheus metrics server started on port {metrics_port}")
    
    yield
    
    # Shutdown
    print("🔄 Application shutting down...")


app = FastAPI(
    title="IDE Orchestrator API",
    lifespan=lifespan
)

# Include routers
app.include_router(health.router)
app.include_router(health.health_router)  # Root level health endpoints
app.include_router(workflows.router)
app.include_router(refinements.router)
app.include_router(websockets.router)


@app.get("/api/protected")
async def protected(authorization: Optional[str] = Header(None)):
    """
    Protected endpoint that requires authentication.
    
    Note: Authentication will be handled by SDK middleware in future implementation.
    This endpoint is kept for integration tests.
    """
    # Temporary check for Authorization header until SDK middleware is integrated
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # TODO: Replace with SDK-based authentication
    return {
        "user_id": "pending-sdk-integration",
        "email": "pending-sdk-integration",
        "message": "Access granted"
    }


def main():
    """Main entry point for the application."""
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    
    print(f"🚀 Starting IDE Orchestrator on {host}:{port}")
    
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=os.getenv("ENVIRONMENT") == "development"
    )


if __name__ == "__main__":
    main()
