"""
Orchestration service for workflow refinement operations.

This service handles the business logic for workflow refinements,
including draft management, proposal creation, and deepagents-runtime integration.
Based on the Go implementation patterns from archived/internal/orchestration/service.go
"""

import uuid
import json
import httpx
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import psycopg
from psycopg.rows import dict_row
import os
import pybreaker
from opentelemetry import trace
from opentelemetry.propagate import inject

# Circuit breaker for deepagents-runtime calls
deepagents_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    exclude=[httpx.HTTPStatusError]  # Don't break on HTTP errors, only on connection issues
)

tracer = trace.get_tracer(__name__)


class OrchestrationService:
    """Service for orchestrating workflow refinements and deepagents-runtime integration."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.deepagents_url = os.getenv("DEEPAGENTS_RUNTIME_URL", "http://deepagents-runtime:8000")
    
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
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Lock workflow and validate access
                    cur.execute(
                        """
                        SELECT id, name, is_locked FROM workflows 
                        WHERE id = %s AND created_by_user_id = %s 
                        FOR UPDATE
                        """,
                        (workflow_id, user_id)
                    )
                    workflow = cur.fetchone()
                    
                    if not workflow:
                        raise ValueError("Workflow not found or access denied")
                    
                    if workflow["is_locked"]:
                        raise ValueError("Workflow is locked by another operation")
                    
                    # Check for existing draft
                    cur.execute(
                        "SELECT id FROM drafts WHERE workflow_id = %s ORDER BY created_at DESC LIMIT 1",
                        (workflow_id,)
                    )
                    existing_draft = cur.fetchone()
                    
                    if existing_draft:
                        return str(existing_draft["id"])
                    
                    # Create new draft
                    draft_id = str(uuid.uuid4())
                    now = datetime.utcnow()
                    
                    cur.execute(
                        """
                        INSERT INTO drafts (id, workflow_id, name, description, created_by_user_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (draft_id, workflow_id, f"Draft for {workflow['name']}", "Work in progress", user_id, now, now)
                    )
                    result = cur.fetchone()
                    return str(result["id"])
    
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
        proposal_id = str(uuid.uuid4())
        thread_id = f"refinement-{proposal_id}"
        now = datetime.utcnow()
        
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Validate draft exists and get workflow info
                cur.execute(
                    """
                    SELECT d.workflow_id, w.created_by_user_id, w.name
                    FROM drafts d
                    JOIN workflows w ON d.workflow_id = w.id
                    WHERE d.id = %s
                    """,
                    (draft_id,)
                )
                draft_info = cur.fetchone()
                
                if not draft_info:
                    raise ValueError("Draft not found")
                
                if str(draft_info["created_by_user_id"]) != user_id:
                    raise ValueError("Access denied to draft")
                
                # Create proposal record
                cur.execute(
                    """
                    INSERT INTO proposals (
                        id, draft_id, thread_id, user_prompt, context_file_path, 
                        context_selection, status, created_by_user_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        proposal_id, draft_id, thread_id, user_prompt,
                        context_file_path, context_selection, "processing",
                        user_id, now
                    )
                )
                
                # Create proposal access record for user
                cur.execute(
                    """
                    INSERT INTO proposal_access (proposal_id, user_id, granted_at)
                    VALUES (%s, %s, %s)
                    """,
                    (proposal_id, user_id, now)
                )
                
                conn.commit()
        
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
            
            try:
                # Prepare payload for deepagents-runtime
                payload = {
                    "job_id": f"refinement-{proposal_id}",
                    "trace_id": f"trace-{proposal_id}",
                    "agent_definition": current_specification,
                    "input_payload": {
                        "instructions": user_prompt,
                        "context": context_selection or "",
                        "context_file_path": context_file_path
                    }
                }
                
                # Call deepagents-runtime with circuit breaker and trace propagation
                await self._call_deepagents_with_circuit_breaker(payload, proposal_id, thread_id)
                
            except pybreaker.CircuitBreakerError:
                span.record_exception(Exception("Circuit breaker open"))
                await self._update_proposal_results(proposal_id, "failed", "AI service temporarily unavailable", {})
            except Exception as e:
                span.record_exception(e)
                await self._update_proposal_results(proposal_id, "failed", str(e), {})
    
    @deepagents_breaker
    async def _call_deepagents_with_circuit_breaker(self, payload: dict, proposal_id: str, thread_id: str):
        """Call deepagents-runtime with circuit breaker protection and trace propagation."""
        headers = {}
        # Inject OpenTelemetry trace context
        inject(headers)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.deepagents_url}/invoke",
                json=payload,
                headers=headers
            )
            
            if response.status_code != 200:
                raise Exception(f"Deepagents-runtime invoke failed: {response.status_code}")
            
            invoke_result = response.json()
            runtime_thread_id = invoke_result.get("thread_id", thread_id)
            
            # Poll for completion (in real implementation, this would use WebSocket)
            await asyncio.sleep(2)  # Give it time to process
            
            # Get final state with trace propagation
            state_response = await client.get(
                f"{self.deepagents_url}/state/{runtime_thread_id}",
                headers=headers
            )
            
            if state_response.status_code == 200:
                state_data = state_response.json()
                
                # Update proposal with results
                await self._update_proposal_results(
                    proposal_id,
                    "completed",
                    state_data.get("result"),
                    state_data.get("generated_files", {})
                )
            else:
                await self._update_proposal_results(proposal_id, "failed", None, {})
    
    async def _update_proposal_results(
        self,
        proposal_id: str,
        status: str,
        result: Optional[Any] = None,
        generated_files: Optional[Dict[str, Any]] = None
    ):
        """Update proposal with processing results."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE proposals 
                    SET status = %s, ai_generated_content = %s, generated_files = %s, completed_at = %s
                    WHERE id = %s
                    """,
                    (
                        status,
                        json.dumps(result) if result else None,
                        json.dumps(generated_files) if generated_files else None,
                        datetime.utcnow() if status in ["completed", "failed"] else None,
                        proposal_id
                    )
                )
                conn.commit()
    
    def can_access_proposal(self, proposal_id: str, user_id: str) -> bool:
        """Check if user can access the specified proposal."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) as count FROM proposal_access WHERE proposal_id = %s AND user_id = %s",
                    (proposal_id, user_id)
                )
                result = cur.fetchone()
                return result["count"] > 0
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get proposal details."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, draft_id, thread_id, user_prompt, context_file_path,
                           context_selection, status, ai_generated_content, generated_files,
                           created_at, completed_at
                    FROM proposals
                    WHERE id = %s
                    """,
                    (proposal_id,)
                )
                result = cur.fetchone()
                if result:
                    result = dict(result)
                    # Convert UUID objects to strings
                    for key, value in result.items():
                        if hasattr(value, 'hex'):
                            result[key] = str(value)
                    return result
                return None
    
    def approve_proposal(self, proposal_id: str, user_id: str) -> None:
        """
        Approve a proposal and apply changes to draft with row-level locking.
        
        Args:
            proposal_id: Proposal ID
            user_id: User ID (for access validation)
            
        Raises:
            ValueError: If proposal not found, access denied, or not ready for approval
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Get proposal details with row-level locking and validate access
                    cur.execute(
                        """
                        SELECT p.id, p.draft_id, p.status, p.generated_files, d.workflow_id
                        FROM proposals p
                        JOIN proposal_access pa ON p.id = pa.proposal_id
                        JOIN drafts d ON p.draft_id = d.id
                        WHERE p.id = %s AND pa.user_id = %s
                        FOR UPDATE
                        """,
                        (proposal_id, user_id)
                    )
                    proposal = cur.fetchone()
                    
                    if not proposal:
                        raise ValueError("Proposal not found")
                    
                    if proposal["status"] != "completed":
                        raise ValueError("Proposal is not ready for approval")
                    
                    # Lock the workflow to prevent concurrent modifications
                    cur.execute(
                        """
                        SELECT id, is_locked FROM workflows 
                        WHERE id = %s 
                        FOR UPDATE
                        """,
                        (proposal["workflow_id"],)
                    )
                    workflow = cur.fetchone()
                    
                    if workflow and workflow["is_locked"]:
                        raise ValueError("Workflow is locked by another operation")
                    
                    # Apply generated files to draft using UPSERT logic
                    if proposal["generated_files"]:
                        self._apply_files_to_draft(cur, proposal["draft_id"], proposal["generated_files"])
                    
                    # Update proposal status
                    cur.execute(
                        """
                        UPDATE proposals 
                        SET status = %s, resolved_by_user_id = %s, resolved_at = %s
                        WHERE id = %s
                        """,
                        ("approved", user_id, datetime.utcnow(), proposal_id)
                    )
    
    def _apply_files_to_draft(self, cursor, draft_id: str, generated_files: dict) -> None:
        """
        Apply generated files to draft using UPSERT (INSERT ... ON CONFLICT) logic.
        
        This handles the complex logic of updating existing files or inserting new ones.
        """
        if not generated_files:
            return
        
        now = datetime.utcnow()
        
        for file_path, file_data in generated_files.items():
            if not isinstance(file_data, dict) or "content" not in file_data:
                continue
            
            content = file_data["content"]
            file_type = file_data.get("type", "markdown")
            
            # Convert content list to string if needed
            if isinstance(content, list):
                content = "\n".join(str(line) for line in content)
            elif not isinstance(content, str):
                content = str(content)
            
            # UPSERT: Insert or Update on Conflict
            cursor.execute(
                """
                INSERT INTO draft_specification_files 
                (id, draft_id, file_path, content, file_type, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (draft_id, file_path) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    file_type = EXCLUDED.file_type,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    str(uuid.uuid4()),
                    draft_id,
                    file_path,
                    content,
                    file_type,
                    now,
                    now
                )
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
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Validate access
                cur.execute(
                    """
                    SELECT p.id
                    FROM proposals p
                    JOIN proposal_access pa ON p.id = pa.proposal_id
                    WHERE p.id = %s AND pa.user_id = %s
                    """,
                    (proposal_id, user_id)
                )
                
                if not cur.fetchone():
                    raise ValueError("Proposal not found")
                
                # Update proposal status
                cur.execute(
                    """
                    UPDATE proposals 
                    SET status = %s, resolved_by_user_id = %s, resolved_at = %s
                    WHERE id = %s
                    """,
                    ("rejected", user_id, datetime.utcnow(), proposal_id)
                )
                
                conn.commit()