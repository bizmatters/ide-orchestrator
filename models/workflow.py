"""Workflow models."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class WorkflowCreate(BaseModel):
    """Workflow creation request."""
    name: str
    description: Optional[str] = None


class WorkflowResponse(BaseModel):
    """Workflow response."""
    id: str
    name: str
    description: Optional[str] = None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime
