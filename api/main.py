"""FastAPI application for IDE Orchestrator."""

from fastapi import FastAPI, Depends
from fastapi.security import HTTPBearer

from api.routers import auth, health, workflows, refinements
from api.dependencies import get_current_user

app = FastAPI(title="IDE Orchestrator API")

security = HTTPBearer()

# Include routers
app.include_router(health.router)
app.include_router(health.health_router)  # Root level health endpoints
app.include_router(auth.router)
app.include_router(workflows.router)
app.include_router(refinements.router)


@app.get("/api/protected")
async def protected(current_user=Depends(get_current_user)):
    """Protected endpoint that requires authentication."""
    return {
        "user_id": current_user["user_id"],
        "email": current_user["username"],
        "message": "Access granted"
    }
