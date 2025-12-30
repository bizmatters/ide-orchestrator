"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/ready")
async def ready():
    """Readiness check endpoint."""
    return {"status": "ready"}


# Root level health endpoint for Kubernetes probes
health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_root():
    """Health check endpoint at root level."""
    return {"status": "healthy"}


@health_router.get("/ready")
async def ready_root():
    """Readiness check endpoint at root level."""
    return {"status": "ready"}