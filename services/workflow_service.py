"""Workflow service for database operations."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
import psycopg
from psycopg.rows import dict_row


class WorkflowService:
    """Service for workflow database operations."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
    
    def create_workflow(self, name: str, user_id: str, description: Optional[str] = None) -> dict:
        """Create a new workflow in the database."""
        workflow_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Check for workflow locking - prevent creation if user has locked workflows
                cur.execute(
                    "SELECT COUNT(*) as count FROM workflows WHERE created_by_user_id = %s AND is_locked = true",
                    (user_id,)
                )
                locked_count = cur.fetchone()["count"]
                
                if locked_count > 0:
                    raise ValueError("Cannot create workflow: user has locked workflows")
                
                cur.execute(
                    """
                    INSERT INTO workflows (id, name, description, created_by_user_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, name, description, created_by_user_id, created_at, updated_at
                    """,
                    (workflow_id, name, description, user_id, now, now)
                )
                result = cur.fetchone()
                conn.commit()
                # Convert UUID objects to strings for JSON serialization
                if result:
                    result = dict(result)
                    for key, value in result.items():
                        if hasattr(value, 'hex'):  # UUID objects have a hex attribute
                            result[key] = str(value)
                return result
    
    def get_workflow(self, workflow_id: str, user_id: str) -> Optional[dict]:
        """Get a workflow by ID, ensuring user has access."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, description, created_by_user_id, created_at, updated_at, is_locked
                    FROM workflows
                    WHERE id = %s AND created_by_user_id = %s
                    """,
                    (workflow_id, user_id)
                )
                result = cur.fetchone()
                # Convert UUID objects to strings for JSON serialization
                if result:
                    result = dict(result)
                    for key, value in result.items():
                        if hasattr(value, 'hex'):  # UUID objects have a hex attribute
                            result[key] = str(value)
                return result
    
    def get_versions(self, workflow_id: str) -> List[Dict[str, Any]]:
        """Get all versions for a workflow."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, version_number, status, created_at, updated_at
                    FROM workflow_versions
                    WHERE workflow_id = %s
                    ORDER BY version_number DESC
                    """,
                    (workflow_id,)
                )
                results = cur.fetchall()
                versions = []
                for result in results:
                    version = dict(result)
                    for key, value in version.items():
                        if hasattr(value, 'hex'):
                            version[key] = str(value)
                    versions.append(version)
                return versions
    
    def get_version(self, workflow_id: str, version_number: int) -> Optional[Dict[str, Any]]:
        """Get a specific version of a workflow."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, version_number, status, specification, created_at, updated_at
                    FROM workflow_versions
                    WHERE workflow_id = %s AND version_number = %s
                    """,
                    (workflow_id, version_number)
                )
                result = cur.fetchone()
                if result:
                    version = dict(result)
                    for key, value in version.items():
                        if hasattr(value, 'hex'):
                            version[key] = str(value)
                    return version
                return None
    
    def publish_draft(self, workflow_id: str, user_id: str) -> Dict[str, Any]:
        """Publish draft as a new version with row-level locking."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Lock the workflow to prevent concurrent modifications
                    cur.execute(
                        """
                        SELECT id, is_locked FROM workflows 
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
                    
                    # Check if draft exists
                    cur.execute(
                        "SELECT id FROM drafts WHERE workflow_id = %s",
                        (workflow_id,)
                    )
                    draft = cur.fetchone()
                    
                    if not draft:
                        raise ValueError("No draft found to publish")
                    
                    # Get next version number
                    cur.execute(
                        """
                        SELECT COALESCE(MAX(version_number), 0) + 1 as next_version
                        FROM workflow_versions WHERE workflow_id = %s
                        """,
                        (workflow_id,)
                    )
                    next_version = cur.fetchone()["next_version"]
                    
                    # Create new version
                    version_id = str(uuid.uuid4())
                    now = datetime.utcnow()
                    
                    cur.execute(
                        """
                        INSERT INTO workflow_versions 
                        (id, workflow_id, version_number, status, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, version_number
                        """,
                        (version_id, workflow_id, next_version, "published", now, now)
                    )
                    version = cur.fetchone()
                    
                    # Copy draft files to version
                    cur.execute(
                        """
                        INSERT INTO workflow_version_files (version_id, file_path, content, file_type, created_at)
                        SELECT %s, file_path, content, file_type, %s
                        FROM draft_specification_files WHERE draft_id = %s
                        """,
                        (version_id, now, draft["id"])
                    )
                    
                    # Delete draft after successful publish
                    cur.execute("DELETE FROM drafts WHERE id = %s", (draft["id"],))
                    
                    return {
                        "id": str(version["id"]),
                        "version_number": version["version_number"]
                    }
    
    def discard_draft(self, workflow_id: str, user_id: str) -> None:
        """Discard the current draft with row-level locking."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Lock the workflow
                    cur.execute(
                        """
                        SELECT id FROM workflows 
                        WHERE id = %s AND created_by_user_id = %s 
                        FOR UPDATE
                        """,
                        (workflow_id, user_id)
                    )
                    workflow = cur.fetchone()
                    
                    if not workflow:
                        raise ValueError("Workflow not found or access denied")
                    
                    # Delete draft
                    cur.execute(
                        "DELETE FROM drafts WHERE workflow_id = %s",
                        (workflow_id,)
                    )
                    
                    if cur.rowcount == 0:
                        raise ValueError("No draft found to discard")
    
    def deploy_version(self, workflow_id: str, version_number: int, user_id: str) -> Dict[str, Any]:
        """Deploy a version to production."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Validate workflow access and version exists
                    cur.execute(
                        """
                        SELECT wv.id, wv.status FROM workflow_versions wv
                        JOIN workflows w ON wv.workflow_id = w.id
                        WHERE w.id = %s AND w.created_by_user_id = %s AND wv.version_number = %s
                        FOR UPDATE
                        """,
                        (workflow_id, user_id, version_number)
                    )
                    version = cur.fetchone()
                    
                    if not version:
                        raise ValueError("Version not found or access denied")
                    
                    if version["status"] != "published":
                        raise ValueError("Only published versions can be deployed")
                    
                    # Create deployment record
                    deployment_id = str(uuid.uuid4())
                    now = datetime.utcnow()
                    
                    cur.execute(
                        """
                        INSERT INTO workflow_deployments 
                        (id, version_id, status, deployed_at, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, status
                        """,
                        (deployment_id, version["id"], "deploying", now, now)
                    )
                    deployment = cur.fetchone()
                    
                    return {
                        "id": str(deployment["id"]),
                        "status": deployment["status"]
                    }
