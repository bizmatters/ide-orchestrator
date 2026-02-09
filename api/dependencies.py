"""FastAPI dependency injection functions."""

import os
from fastapi import Header, HTTPException

from services.workflow_service import WorkflowService
from services.orchestration_service import OrchestrationService


def get_database_url():
    """Get database URL from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    return database_url


def get_workflow_service():
    """Get workflow service instance."""
    return WorkflowService(get_database_url())


def get_orchestration_service():
    """Get orchestration service instance."""
    return OrchestrationService(get_database_url())


def get_current_user_id(authorization: str = Header(...)) -> str:
    """
    Extract user_id from Authorization header.
    
    For testing: Accepts "Bearer <user_id>" where user_id is a UUID string.
    TODO: Replace with proper JWT validation using SDK.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization[7:]  # Remove "Bearer " prefix
    # todo
    # For testing: token IS the user_id (UUID string)
    # In production: decode JWT and extract user_id claim
    return token
