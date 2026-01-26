"""
Orchestration service for workflow refinement operations.

This service coordinates between different services to handle the complete
workflow refinement lifecycle, from proposal creation to completion.
"""

import asyncio
import os
from typing import Optional, Dict, Any, Tuple
from opentelemetry import trace

from core.metrics import metrics
from .deepagents_client import DeepAgentsRuntimeClient
from .audit_service import AuditService
from .draft_service import DraftService
from .proposal_service import ProposalService

tracer = trace.get_tracer(__name__)


class OrchestrationService:
    """Service for orchestrating workflow refinements and deepagents-runtime integration."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        deepagents_url = os.getenv("DEEPAGENTS_RUNTIME_URL", "http://deepagents-runtime.intelligence-deepagents.svc.cluster.local:8000")
        
        # Initialize service dependencies
        self.deepagents_client = DeepAgentsRuntimeClient(deepagents_url)
        self.audit_service = AuditService()
        self.draft_service = DraftService(database_url)
        self.proposal_service = ProposalService(database_url)
    
    async def get_or_create_draft(self, workflow_id: str, user_id: str) -> str:
        """
        Get existing draft or create new one for workflow with locking logic.
        
        Args:
            workflow_id: Workflow ID
            user_id: User ID (for access validation)
            
        Returns:
            Draft ID (UUID string)
            
        Raises:
            ValueError: If workflow not found, access denied, or locked
        """
        return self.draft_service.get_or_create_draft(workflow_id, user_id)
    
    async def create_refinement_proposal(
        self,
        draft_id: str,
        user_id: str,
        user_prompt: str,
        context_file_path: Optional[str] = None,
        context_selection: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Create a refinement proposal and initiate deepagents-runtime processing.
        
        This follows the spec by:
        1. Creating a proposal in the database
        2. Calling deepagents-runtime /invoke to get a thread_id
        3. Letting the WebSocket proxy handle streaming and proposal updates
        
        Args:
            draft_id: Draft ID
            user_id: User ID
            user_prompt: User's refinement instructions
            context_file_path: Optional file path for context
            context_selection: Optional text selection for context
            
        Returns:
            Tuple of (proposal_id, thread_id)
            
        Raises:
            ValueError: If draft not found or deepagents-runtime unavailable
        """
        # Validate draft access
        draft_info = self.draft_service.validate_draft_access(draft_id, user_id)
        
        # Generate proposal ID
        proposal_id = f"proposal-{int(asyncio.get_event_loop().time() * 1000000)}"
        
        # Record metrics for job creation
        metrics.record_job_created("refinement", "created")
        
        # Create initial audit trail
        audit_trail = self.audit_service.create_initial_audit_trail(
            user_id, user_prompt, context_file_path, context_selection
        )
        
        # Get current specification from draft (empty for now)
        current_specification = {}
        
        # Prepare payload for deepagents-runtime
        payload = {
            "job_id": f"refinement-{proposal_id}",
            "trace_id": f"trace-{proposal_id}",
            "agent_definition": current_specification,
            "input_payload": {
                "messages": [{"role": "user", "content": user_prompt}],
                "instructions": user_prompt,
                "context": context_selection or "",
                "context_file_path": context_file_path
            }
        }
        
        try:
            # Call deepagents-runtime /invoke to get thread_id
            invoke_result = await self.deepagents_client.invoke_job(payload)
            thread_id = invoke_result.get("thread_id")
            
            if not thread_id:
                raise ValueError("deepagents-runtime did not return thread_id")
            
            # Create proposal in database with the thread_id from deepagents-runtime
            proposal_id = self.proposal_service.create_proposal(
                draft_id, thread_id, user_id, user_prompt, audit_trail,
                context_file_path, context_selection
            )
            
            # According to the spec, we only call /invoke and let the WebSocket proxy
            # handle streaming when the frontend connects to /api/ws/refinements/{thread_id}
            # The WebSocket proxy will update the proposal when it receives 'end' events
            
            return proposal_id, thread_id
            
        except Exception as e:
            # If deepagents-runtime is unavailable, create proposal in failed state
            thread_id = f"failed-{proposal_id}"
            proposal_id = self.proposal_service.create_proposal(
                draft_id, thread_id, user_id, user_prompt, audit_trail,
                context_file_path, context_selection
            )
            
            # Update to failed status immediately
            await self._update_proposal_results(proposal_id, "failed", str(e), {})
            
            raise ValueError(f"deepagents-runtime unavailable: {str(e)}")
    
    # Remove the old async processing method since WebSocket proxy handles it
    # async def _process_refinement_async(...) - REMOVED
    
    async def _update_proposal_results(
        self,
        proposal_id: str,
        status: str,
        result: Optional[Any] = None,
        generated_files: Optional[Dict[str, Any]] = None
    ):
        """Update proposal with processing results and audit trail."""
        # Get current proposal for audit trail
        current_proposal = self.proposal_service.get_proposal(proposal_id)
        if not current_proposal:
            return
        
        # Update audit trail
        audit_trail_json = self.audit_service.add_processing_event(
            current_proposal.get("ai_generated_content"),
            status, result, generated_files
        )
        
        # Update proposal in database
        self.proposal_service.update_proposal_results(
            proposal_id, status, audit_trail_json, generated_files
        )
    
    def can_access_proposal(self, proposal_id: str, user_id: str) -> bool:
        """Check if user can access the specified proposal."""
        return self.proposal_service.can_access_proposal(proposal_id, user_id)
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get proposal details."""
        return self.proposal_service.get_proposal(proposal_id)
    
    def get_proposal_by_thread_id(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get proposal by thread ID (for WebSocket processing)."""
        return self.proposal_service.get_proposal_by_thread_id(thread_id)
    
    def approve_proposal(self, proposal_id: str, user_id: str) -> None:
        """
        Approve a proposal and apply changes to draft with row-level locking.
        
        Args:
            proposal_id: Proposal ID
            user_id: User ID (for access validation)
            
        Raises:
            ValueError: If proposal not found, access denied, or not ready for approval
        """
        # Get proposal with locking and access validation
        proposal = self.proposal_service.get_proposal_with_access_check(
            proposal_id, user_id, for_update=True
        )
        
        if proposal["status"] != "completed":
            raise ValueError("Proposal is not ready for approval")
        
        # Apply generated files to draft
        files_applied = 0
        if proposal["generated_files"]:
            # generated_files is already a dictionary from JSONB field
            generated_files = proposal["generated_files"]
            if isinstance(generated_files, str):
                # Handle case where it might still be a JSON string
                import json
                generated_files = json.loads(generated_files)
            files_applied = self.draft_service.apply_files_to_draft(
                proposal["draft_id"], generated_files
            )
        
        # Update audit trail for approval
        audit_trail_json = self.audit_service.add_approval_event(
            proposal.get("ai_generated_content"), user_id, files_applied
        )
        
        # Update proposal status to resolved with approved resolution
        self.proposal_service.resolve_proposal(
            proposal_id, "approved", user_id, audit_trail_json
        )
        
        # Clean up deepagents-runtime checkpointer data
        if proposal["thread_id"]:
            asyncio.create_task(
                self.deepagents_client.cleanup_thread_data(proposal["thread_id"])
            )
    
    def reject_proposal(self, proposal_id: str, user_id: str) -> None:
        """
        Reject a proposal.
        
        Args:
            proposal_id: Proposal ID
            user_id: User ID (for access validation)
            
        Raises:
            ValueError: If proposal not found or access denied
        """
        # Get proposal with access validation
        proposal = self.proposal_service.get_proposal_with_access_check(
            proposal_id, user_id
        )
        
        # Update audit trail for rejection
        audit_trail_json = self.audit_service.add_rejection_event(
            proposal.get("ai_generated_content"), user_id
        )
        
        # Update proposal status to resolved with rejected resolution
        self.proposal_service.resolve_proposal(
            proposal_id, "rejected", user_id, audit_trail_json
        )
        
        # Clean up deepagents-runtime checkpointer data
        if proposal["thread_id"]:
            asyncio.create_task(
                self.deepagents_client.cleanup_thread_data(proposal["thread_id"])
            )
    
    async def update_proposal_files_from_stream(self, thread_id: str, files: Dict[str, Any]) -> None:
        """
        Update proposal with files from WebSocket streaming using thread_id.
        
        This method is called from the WebSocket proxy when files are extracted
        from streaming events. It finds the proposal by thread_id and updates it.
        
        Args:
            thread_id: Thread ID from WebSocket stream
            files: Files dictionary from streaming events
        """
        # Find proposal by thread_id
        proposal = self.get_proposal_by_thread_id(thread_id)
        if not proposal:
            raise ValueError(f"No proposal found for thread_id: {thread_id}")
        
        # Update the proposal with files
        await self._update_proposal_results(proposal["id"], "completed", None, files)
    
    async def update_proposal_status_from_stream(self, thread_id: str, status: str, error_message: str = None) -> None:
        """
        Update proposal status from WebSocket streaming using thread_id.
        
        This method is called from the WebSocket proxy when an error occurs
        during streaming. It finds the proposal by thread_id and updates its status.
        
        Args:
            thread_id: Thread ID from WebSocket stream
            status: New status (e.g., "failed")
            error_message: Optional error message
        """
        # Find proposal by thread_id
        proposal = self.get_proposal_by_thread_id(thread_id)
        if not proposal:
            raise ValueError(f"No proposal found for thread_id: {thread_id}")
        
        # Update the proposal status
        await self._update_proposal_results(proposal["id"], status, error_message, {})

    async def update_proposal_files(self, proposal_id: str, files: Dict[str, Any]) -> None:
        """
        Update proposal with files from WebSocket streaming.
        
        This method is called from the WebSocket proxy when files are extracted
        from streaming events.
        
        Args:
            proposal_id: Proposal ID
            files: Files dictionary from streaming events
        """
        await self._update_proposal_results(proposal_id, "completed", None, files)