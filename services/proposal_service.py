"""
Proposal management service for handling refinement proposals.

This module handles all proposal-related database operations,
including creation, retrieval, access control, and status updates.
"""

import uuid
import json
import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from typing import Dict, Any, Optional, Tuple


class ProposalService:
    """Service for managing refinement proposals."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
    
    def create_proposal(
        self,
        draft_id: str,
        thread_id: str,
        user_id: str,
        user_prompt: str,
        audit_trail: Dict[str, Any],
        context_file_path: Optional[str] = None,
        context_selection: Optional[str] = None
    ) -> str:
        """
        Create a new refinement proposal.
        
        Args:
            draft_id: Draft ID
            thread_id: Thread ID for deepagents-runtime
            user_id: User ID
            user_prompt: User's refinement instructions
            audit_trail: Initial audit trail
            context_file_path: Optional file path for context
            context_selection: Optional text selection for context
            
        Returns:
            Proposal ID
        """
        proposal_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Create proposal record
                cur.execute(
                    """
                    INSERT INTO proposals (
                        id, draft_id, thread_id, user_prompt, context_file_path, 
                        context_selection, status, created_by_user_id, created_at,
                        ai_generated_content
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        proposal_id, draft_id, thread_id, user_prompt,
                        context_file_path, context_selection, "processing",
                        user_id, now, json.dumps(audit_trail)
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
        
        return proposal_id
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """
        Get proposal details.
        
        Args:
            proposal_id: Proposal ID
            
        Returns:
            Proposal dictionary or None if not found
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, draft_id, thread_id, user_prompt, context_file_path,
                           context_selection, status, ai_generated_content, generated_files,
                           created_at, completed_at, created_by_user_id, resolved_by_user_id, resolved_at, resolution
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
    
    def can_access_proposal(self, proposal_id: str, user_id: str) -> bool:
        """
        Check if user can access the specified proposal.
        
        Args:
            proposal_id: Proposal ID
            user_id: User ID
            
        Returns:
            True if user can access proposal, False otherwise
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) as count FROM proposal_access WHERE proposal_id = %s AND user_id = %s",
                    (proposal_id, user_id)
                )
                result = cur.fetchone()
                return result["count"] > 0
    
    def update_proposal_results(
        self,
        proposal_id: str,
        status: str,
        audit_trail_json: str,
        generated_files: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update proposal with processing results.
        
        Args:
            proposal_id: Proposal ID
            status: New status
            audit_trail_json: Updated audit trail as JSON string
            generated_files: Generated files dictionary
        """
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
                        audit_trail_json,
                        json.dumps(generated_files) if generated_files else None,
                        datetime.utcnow() if status in ["completed", "failed"] else None,
                        proposal_id
                    )
                )
                conn.commit()
    
    def get_proposal_with_access_check(
        self,
        proposal_id: str,
        user_id: str,
        for_update: bool = False
    ) -> Dict[str, Any]:
        """
        Get proposal with access validation and optional row locking.
        
        Args:
            proposal_id: Proposal ID
            user_id: User ID
            for_update: Whether to lock the row for update
            
        Returns:
            Proposal dictionary with additional workflow info
            
        Raises:
            ValueError: If proposal not found or access denied
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                lock_clause = "FOR UPDATE" if for_update else ""
                
                cur.execute(
                    f"""
                    SELECT p.id, p.draft_id, p.status, p.generated_files, p.thread_id, 
                           p.ai_generated_content, p.resolution, d.workflow_id
                    FROM proposals p
                    JOIN proposal_access pa ON p.id = pa.proposal_id
                    JOIN drafts d ON p.draft_id = d.id
                    WHERE p.id = %s AND pa.user_id = %s
                    {lock_clause}
                    """,
                    (proposal_id, user_id)
                )
                proposal = cur.fetchone()
                
                if not proposal:
                    raise ValueError("Proposal not found")
                
                return dict(proposal)
    
    def update_proposal_status(
        self,
        proposal_id: str,
        status: str,
        user_id: str,
        audit_trail_json: str
    ) -> None:
        """
        Update proposal status with resolution details.
        
        Args:
            proposal_id: Proposal ID
            status: New status (approved, rejected)
            user_id: User ID who resolved the proposal
            audit_trail_json: Updated audit trail as JSON string
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE proposals 
                    SET status = %s, resolved_by_user_id = %s, resolved_at = %s, ai_generated_content = %s
                    WHERE id = %s
                    """,
                    (status, user_id, datetime.utcnow(), audit_trail_json, proposal_id)
                )
                conn.commit()
    
    def resolve_proposal(
        self,
        proposal_id: str,
        resolution: str,
        user_id: str,
        audit_trail_json: str
    ) -> None:
        """
        Resolve a proposal with approved or rejected outcome.
        
        Args:
            proposal_id: Proposal ID
            resolution: Resolution outcome (approved, rejected)
            user_id: User ID who resolved the proposal
            audit_trail_json: Updated audit trail as JSON string
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE proposals 
                    SET status = %s, resolution = %s, resolved_by_user_id = %s, resolved_at = %s, ai_generated_content = %s
                    WHERE id = %s
                    """,
                    ("resolved", resolution, user_id, datetime.utcnow(), audit_trail_json, proposal_id)
                )
                conn.commit()
    
    def get_proposal_by_thread_id(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get proposal by thread ID (for WebSocket processing).
        
        Args:
            thread_id: Thread ID from deepagents-runtime
            
        Returns:
            Proposal dictionary or None if not found
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, draft_id, status FROM proposals WHERE thread_id = %s",
                    (thread_id,)
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