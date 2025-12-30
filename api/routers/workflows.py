"""Workflow management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from models.workflow import WorkflowCreate, WorkflowResponse
from services.workflow_service import WorkflowService
from api.dependencies import get_workflow_service, get_current_user

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("", status_code=201, response_model=WorkflowResponse)
async def create_workflow(
    workflow: WorkflowCreate,
    current_user=Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
):
    """Create a new workflow."""
    result = workflow_service.create_workflow(
        name=workflow.name,
        user_id=current_user["user_id"],
        description=workflow.description,
    )
    return result


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    current_user=Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
):
    """Get a workflow by ID."""
    result = workflow_service.get_workflow(workflow_id, current_user["user_id"])
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return result