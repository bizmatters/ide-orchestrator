"""Refinement workflow endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime

from services.workflow_service import WorkflowService
from services.orchestration_service import OrchestrationService
from api.dependencies import get_workflow_service, get_orchestration_service, get_current_user

router = APIRouter(prefix="/api", tags=["refinements"])


@router.post("/workflows/{workflow_id}/refinements", status_code=202)
async def create_refinement(
    workflow_id: str,
    refinement_data: dict,
    current_user=Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
):
    """Create a refinement for a workflow."""
    # Validate workflow access
    workflow = workflow_service.get_workflow(workflow_id, current_user["user_id"])
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Validate required fields - match Go test expectations
    if "instructions" not in refinement_data:
        raise HTTPException(status_code=400, detail="Invalid request")
    
    try:
        # Get or create draft
        draft_id = await orchestration_service.get_or_create_draft(
            workflow_id, current_user["user_id"]
        )
        
        # Create refinement proposal
        proposal_id, thread_id = await orchestration_service.create_refinement_proposal(
            draft_id=draft_id,
            user_id=current_user["user_id"],
            user_prompt=refinement_data["instructions"],
            context_file_path=refinement_data.get("context_file_path"),
            context_selection=refinement_data.get("context_selection")
        )
        
        # Return response matching Go implementation format
        return {
            "proposal_id": proposal_id,
            "thread_id": thread_id,
            "status": "processing",
            "websocket_url": f"/api/ws/refinements/{thread_id}",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        elif "access denied" in str(e).lower():
            raise HTTPException(status_code=403, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "deepagents-runtime unavailable" in str(e):
            raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
        else:
            raise HTTPException(status_code=500, detail="Failed to create refinement proposal")


@router.post("/refinements/{proposal_id}/approve", status_code=200)
async def approve_proposal(
    proposal_id: str,
    current_user=Depends(get_current_user),
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
):
    """Approve a refinement proposal."""
    try:
        orchestration_service.approve_proposal(proposal_id, current_user["user_id"])
        
        return {
            "proposal_id": proposal_id,
            "approved_at": datetime.utcnow().isoformat() + "Z",
            "message": "Proposal approved and changes applied to draft"
        }
        
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Proposal not found")
        elif "not ready" in str(e).lower():
            raise HTTPException(status_code=400, detail="Proposal is not ready for approval")
        else:
            raise HTTPException(status_code=500, detail="Failed to approve proposal")


@router.post("/refinements/{proposal_id}/reject", status_code=200)
async def reject_proposal(
    proposal_id: str,
    current_user=Depends(get_current_user),
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
):
    """Reject a refinement proposal."""
    try:
        orchestration_service.reject_proposal(proposal_id, current_user["user_id"])
        
        return {
            "proposal_id": proposal_id,
            "message": "Proposal rejected and discarded"
        }
        
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Proposal not found")
        else:
            raise HTTPException(status_code=500, detail="Failed to reject proposal")


@router.get("/proposals/{proposal_id}", status_code=200)
async def get_proposal(
    proposal_id: str,
    current_user=Depends(get_current_user),
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
):
    """Get proposal details and generated files."""
    # Validate access
    if not orchestration_service.can_access_proposal(proposal_id, current_user["user_id"]):
        raise HTTPException(status_code=403, detail="Access denied to proposal")
    
    proposal = orchestration_service.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    return proposal