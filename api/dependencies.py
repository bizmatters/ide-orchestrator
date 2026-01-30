"""FastAPI dependency injection functions."""

import os

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
