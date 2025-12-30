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
        deepagents_url = os.getenv("DEEPAGENTS_RUNTIME_URL", "http://deepagents-runtime:8000")
        
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
        
        # Generate IDs
        proposal_id = f"proposal-{asyncio.get_event_loop().time()}"
        thread_id = f"refinement-{proposal_id}"
        
        # Record metrics for job creation
        metrics.record_job_created("refinement", "created")
        
        # Create initial audit trail
        audit_trail = self.audit_service.create_initial_audit_trail(
            user_id, user_prompt, context_file_path, context_selection
        )
        
        # Create proposal in database
        proposal_id = self.proposal_service.create_proposal(
            draft_id, thread_id, user_id, user_prompt, audit_trail,
            context_file_path, context_selection
        )
        
        # Start async processing with deepagents-runtime
        asyncio.create_task(self._process_refinement_async(
            proposal_id, thread_id, user_prompt, {},  # Empty specification for now
            context_file_path, context_selection
        ))
        
        return proposal_id, thread_id
    
    async def _process_refinement_async(
        self,
        proposal_id: str,
        thread_id: str,
        user_prompt: str,
        current_specification: Dict[str, Any],
        context_file_path: Optional[str] = None,
        context_selection: Optional[str] = None
    ):
        """
        Async processing of refinement with deepagents-runtime using circuit breaker.
        
        This method runs in the background to call deepagents-runtime
        and update the proposal with results.
        """
        with tracer.start_as_current_span("process_refinement_async") as span:
            span.set_attributes({
                "proposal_id": proposal_id,
                "thread_id": thread_id,
                "user_prompt": user_prompt[:100] + "..." if len(user_prompt) > 100 else user_prompt
            })
            
            # Use metrics context manager for timing
            with metrics.time_refinement():
                try:
                    # Process refinement job through deepagents client
                    state_data = await self.deepagents_client.process_refinement_job(
                        proposal_id, thread_id, user_prompt, current_specification,
                        context_file_path, context_selection
                    )
                    
                    # Update proposal with results
                    await self._update_proposal_results(
                        proposal_id, "completed", 
                        state_data.get("result"),
                        state_data.get("generated_files", {})
                    )
                    
                except Exception as e:
                    span.record_exception(e)
                    await self._update_proposal_results(proposal_id, "failed", str(e), {})
    
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