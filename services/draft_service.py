"""
Draft management service for handling workflow drafts and file operations.

This module handles all draft-related operations including creation,
file management, and UPSERT operations for draft specification files.
"""

import uuid
import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from typing import Dict, Any, Optional


class DraftService:
    """Service for managing workflow drafts and their files."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
    
    def get_or_create_draft(self, workflow_id: str, user_id: str) -> str:
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
    
    def apply_files_to_draft(self, draft_id: str, generated_files: Dict[str, Any]) -> int:
        """
        Apply generated files to draft using UPSERT (INSERT ... ON CONFLICT) logic.
        
        Args:
            draft_id: Draft ID
            generated_files: Dictionary of file paths to file data
            
        Returns:
            Number of files applied
            
        Raises:
            ValueError: If draft not found
        """
        if not generated_files:
            return 0
        
        files_applied = 0
        now = datetime.utcnow()
        
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Validate draft exists
                cur.execute("SELECT id FROM drafts WHERE id = %s", (draft_id,))
                if not cur.fetchone():
                    raise ValueError("Draft not found")
                
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
                    cur.execute(
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
                    files_applied += 1
                
                conn.commit()
        
        return files_applied
    
    def get_draft_files(self, draft_id: str) -> Dict[str, Any]:
        """
        Get all files for a draft.
        
        Args:
            draft_id: Draft ID
            
        Returns:
            Dictionary of file paths to file data
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT file_path, content, file_type, created_at, updated_at
                    FROM draft_specification_files
                    WHERE draft_id = %s
                    ORDER BY file_path
                    """,
                    (draft_id,)
                )
                
                files = {}
                for row in cur.fetchall():
                    files[row["file_path"]] = {
                        "content": row["content"],
                        "type": row["file_type"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                    }
                
                return files
    
    def validate_draft_access(self, draft_id: str, user_id: str) -> Dict[str, Any]:
        """
        Validate user access to draft and return draft info.
        
        Args:
            draft_id: Draft ID
            user_id: User ID
            
        Returns:
            Draft information dictionary
            
        Raises:
            ValueError: If draft not found or access denied
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
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
                
                return dict(draft_info)