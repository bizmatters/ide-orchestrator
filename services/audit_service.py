"""
Audit trail service for tracking proposal lifecycle events.

This module handles all audit trail logging and management,
providing a clean interface for tracking user actions and system events.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional


class AuditService:
    """Service for managing audit trails in proposals."""
    
    @staticmethod
    def create_initial_audit_trail(
        user_id: str,
        user_prompt: str,
        context_file_path: Optional[str] = None,
        context_selection: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create initial audit trail for a new proposal.
        
        Args:
            user_id: User who created the proposal
            user_prompt: User's refinement instructions
            context_file_path: Optional file path for context
            context_selection: Optional text selection for context
            
        Returns:
            Initial audit trail dictionary
        """
        return {
            "created": {
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": user_id,
                "action": "proposal_created",
                "user_prompt": user_prompt,
                "context_file_path": context_file_path,
                "context_selection": context_selection
            }
        }
    
    @staticmethod
    def add_processing_event(
        current_audit_trail: Optional[str],
        status: str,
        result: Optional[Any] = None,
        generated_files: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add processing completion event to audit trail.
        
        Args:
            current_audit_trail: Current audit trail as JSON string
            status: Processing status (completed, failed)
            result: Processing result
            generated_files: Generated files dictionary
            
        Returns:
            Updated audit trail as JSON string
        """
        # Parse existing audit trail
        audit_trail = {}
        if current_audit_trail:
            try:
                audit_trail = json.loads(current_audit_trail)
            except (json.JSONDecodeError, TypeError):
                audit_trail = {}
        
        # Add processing event
        audit_trail[f"processing_{status}"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,
            "result_summary": str(result)[:200] if result else None,
            "files_count": len(generated_files) if generated_files else 0
        }
        
        return json.dumps(audit_trail)
    
    @staticmethod
    def add_approval_event(
        current_audit_trail: Optional[str],
        user_id: str,
        files_applied_count: int
    ) -> str:
        """
        Add approval event to audit trail.
        
        Args:
            current_audit_trail: Current audit trail as JSON string
            user_id: User who approved the proposal
            files_applied_count: Number of files applied to draft
            
        Returns:
            Updated audit trail as JSON string
        """
        # Parse existing audit trail
        audit_trail = {}
        if current_audit_trail:
            try:
                audit_trail = json.loads(current_audit_trail)
            except (json.JSONDecodeError, TypeError):
                audit_trail = {}
        
        # Add approval event
        audit_trail["approved"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "action": "proposal_approved",
            "files_applied": files_applied_count
        }
        
        return json.dumps(audit_trail)
    
    @staticmethod
    def add_rejection_event(
        current_audit_trail: Optional[str],
        user_id: str
    ) -> str:
        """
        Add rejection event to audit trail.
        
        Args:
            current_audit_trail: Current audit trail as JSON string
            user_id: User who rejected the proposal
            
        Returns:
            Updated audit trail as JSON string
        """
        # Parse existing audit trail
        audit_trail = {}
        if current_audit_trail:
            try:
                audit_trail = json.loads(current_audit_trail)
            except (json.JSONDecodeError, TypeError):
                audit_trail = {}
        
        # Add rejection event
        audit_trail["rejected"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "action": "proposal_rejected"
        }
        
        return json.dumps(audit_trail)
    
    @staticmethod
    def get_audit_summary(audit_trail_json: Optional[str]) -> Dict[str, Any]:
        """
        Get a summary of the audit trail for API responses.
        
        Args:
            audit_trail_json: Audit trail as JSON string
            
        Returns:
            Summary dictionary with key events
        """
        if not audit_trail_json:
            return {}
        
        try:
            audit_trail = json.loads(audit_trail_json)
        except (json.JSONDecodeError, TypeError):
            return {}
        
        summary = {}
        
        # Extract key events
        if "created" in audit_trail:
            summary["created_at"] = audit_trail["created"]["timestamp"]
            summary["created_by"] = audit_trail["created"]["user_id"]
        
        if "processing_completed" in audit_trail:
            summary["completed_at"] = audit_trail["processing_completed"]["timestamp"]
            summary["files_generated"] = audit_trail["processing_completed"]["files_count"]
        
        if "processing_failed" in audit_trail:
            summary["failed_at"] = audit_trail["processing_failed"]["timestamp"]
        
        if "approved" in audit_trail:
            summary["approved_at"] = audit_trail["approved"]["timestamp"]
            summary["approved_by"] = audit_trail["approved"]["user_id"]
            summary["files_applied"] = audit_trail["approved"]["files_applied"]
        
        if "rejected" in audit_trail:
            summary["rejected_at"] = audit_trail["rejected"]["timestamp"]
            summary["rejected_by"] = audit_trail["rejected"]["user_id"]
        
        return summary