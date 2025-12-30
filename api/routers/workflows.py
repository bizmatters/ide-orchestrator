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


@router.get("/{workflow_id}/versions")
async def get_versions(
    workflow_id: str,
    current_user=Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
):
    """Get all versions for a workflow."""
    # Validate workflow access
    workflow = workflow_service.get_workflow(workflow_id, current_user["user_id"])
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    versions = workflow_service.get_versions(workflow_id)
    return {"versions": versions}


@router.get("/{workflow_id}/versions/{version_number}")
async def get_version(
    workflow_id: str,
    version_number: int,
    current_user=Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
):
    """Get a specific version of a workflow."""
    # Validate workflow access
    workflow = workflow_service.get_workflow(workflow_id, current_user["user_id"])
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    version = workflow_service.get_version(workflow_id, version_number)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    return version


@router.post("/{workflow_id}/versions", status_code=201)
async def publish_draft(
    workflow_id: str,
    current_user=Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
):
    """Publish draft as a new version."""
    # Validate workflow access
    workflow = workflow_service.get_workflow(workflow_id, current_user["user_id"])
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    try:
        version = workflow_service.publish_draft(workflow_id, current_user["user_id"])
        return {
            "version_id": version["id"],
            "version_number": version["version_number"],
            "message": "Draft published successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{workflow_id}/draft", status_code=200)
async def discard_draft(
    workflow_id: str,
    current_user=Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
):
    """Discard the current draft."""
    # Validate workflow access
    workflow = workflow_service.get_workflow(workflow_id, current_user["user_id"])
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    try:
        workflow_service.discard_draft(workflow_id, current_user["user_id"])
        return {"message": "Draft discarded successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workflow_id}/deploy", status_code=200)
async def deploy_version(
    workflow_id: str,
    deploy_data: dict,
    current_user=Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
):
    """Deploy a version to production."""
    # Validate workflow access
    workflow = workflow_service.get_workflow(workflow_id, current_user["user_id"])
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    version_number = deploy_data.get("version_number")
    if not version_number:
        raise HTTPException(status_code=400, detail="version_number is required")
    
    try:
        deployment = workflow_service.deploy_version(
            workflow_id, version_number, current_user["user_id"]
        )
        return {
            "deployment_id": deployment["id"],
            "status": deployment["status"],
            "message": "Deployment initiated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))