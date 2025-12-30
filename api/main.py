"""FastAPI application for IDE Orchestrator."""

import os
from fastapi import FastAPI, Depends
from fastapi.security import HTTPBearer
from contextlib import asynccontextmanager

from api.routers import auth, health, workflows, refinements, websockets
from api.dependencies import get_current_user
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

security = HTTPBearer()

# Include routers
app.include_router(health.router)
app.include_router(health.health_router)  # Root level health endpoints
app.include_router(auth.router)
app.include_router(workflows.router)
app.include_router(refinements.router)
app.include_router(websockets.router)


@app.get("/api/protected")
async def protected(current_user=Depends(get_current_user)):
    """Protected endpoint that requires authentication."""
    return {
        "user_id": current_user["user_id"],
        "email": current_user["username"],
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