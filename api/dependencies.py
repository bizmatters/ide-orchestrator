"""FastAPI dependency injection functions."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
import os

from core.jwt_manager import JWTManager
from services.auth_service import AuthService
from services.workflow_service import WorkflowService
from services.orchestration_service import OrchestrationService

security = HTTPBearer()


def get_database_url():
    """Get database URL from environment."""
    # Check for explicit DATABASE_URL first
    if database_url := os.getenv("DATABASE_URL"):
        return database_url
    
    # Build from individual environment variables
    host = os.getenv("POSTGRES_HOST", "ide-orchestrator-db-rw.intelligence-orchestrator.svc")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    dbname = os.getenv("POSTGRES_DB", "ide_orchestrator")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=prefer"


def get_jwt_manager():
    """Get JWT manager instance."""
    if not os.getenv("JWT_SECRET"):
        os.environ["JWT_SECRET"] = "test-secret-key-for-testing"
    return JWTManager()


def get_auth_service():
    """Get auth service instance."""
    return AuthService(get_database_url())


def get_workflow_service():
    """Get workflow service instance."""
    return WorkflowService(get_database_url())


def get_orchestration_service():
    """Get orchestration service instance."""
    return OrchestrationService(get_database_url())


async def get_current_user(
    credentials = Depends(security),
    jwt_manager: JWTManager = Depends(get_jwt_manager)
):
    """Dependency to get current user from JWT token."""
    try:
        token = credentials.credentials
        claims = await jwt_manager.validate_token(token)
        return claims
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )