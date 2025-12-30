"""Workflow service for database operations."""

import uuid
from datetime import datetime
from typing import Optional
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
                    SELECT id, name, description, created_by_user_id, created_at, updated_at
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
