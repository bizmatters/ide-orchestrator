"""
Database helper utilities for refinement integration tests.

Provides reusable database operations using production services
to ensure consistent data setup following integration testing patterns.
"""

import uuid
import bcrypt
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
import psycopg
from psycopg.rows import dict_row

from api.dependencies import get_workflow_service, get_orchestration_service, get_database_url


async def create_test_user(user_id: str) -> str:
    """
    Create a test user in the database using production database connection.
    
    Args:
        user_id: UUID string for the user
        
    Returns:
        The created user_id
    """
    database_url = get_database_url()
    
    # Create test user with hashed password
    hashed_password = bcrypt.hashpw("testpassword".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    now = datetime.utcnow()
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, name, email, hashed_password, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id, f"Test User {user_id[:8]}", f"test-{user_id}@example.com", hashed_password, now, now)
            )
            conn.commit()
    
    return user_id


async def create_test_workflow_with_draft(
    user_id: str,
    workflow_name: str,
    draft_content: Dict[str, str],
    draft_name: Optional[str] = None,
    draft_description: Optional[str] = None
) -> Tuple[str, str]:
    """
    Create workflow and initial draft using production services.
    
    Args:
        user_id: User ID who owns the workflow
        workflow_name: Name of the workflow
        draft_content: Dictionary of file_path -> content
        draft_name: Optional draft name (defaults to workflow name + " Draft")
        draft_description: Optional draft description
        
    Returns:
        Tuple of (workflow_id, draft_id)
    """
    if draft_name is None:
        draft_name = f"{workflow_name} Draft"
    if draft_description is None:
        draft_description = f"Draft for {workflow_name}"
    
    # Ensure user exists in database first
    await create_test_user(user_id)
    
    # Use production workflow service
    workflow_service = get_workflow_service()
    orchestration_service = get_orchestration_service()
    
    # Create workflow through production service
    workflow_result = workflow_service.create_workflow(
        name=workflow_name,
        user_id=user_id,
        description=f"Testing workflow: {workflow_name}"
    )
    workflow_id = workflow_result["id"]
    
    # Create draft through production orchestration service
    draft_id = await orchestration_service.get_or_create_draft(workflow_id, user_id)
    
    # Update draft with initial content through production service
    # This would typically be done through the draft service
    # For now, we'll use the orchestration service pattern
    
    return workflow_id, draft_id


async def get_draft_content_by_workflow(workflow_id: str, user_id: str) -> Dict[str, str]:
    """
    Retrieve draft content using production services.
    
    Args:
        workflow_id: Workflow ID
        user_id: User ID for access control
        
    Returns:
        Dictionary of file_path -> content
    """
    # Use production services to get draft content
    workflow_service = get_workflow_service()
    
    # Get workflow and associated draft through production service
    workflow = workflow_service.get_workflow(workflow_id, user_id)
    if not workflow:
        return {}
    
    # This would use the production draft service to get content
    # Implementation depends on the actual production service methods
    return {}


async def get_proposal_by_id(proposal_id: str) -> Optional[Dict[str, Any]]:
    """
    Get proposal using production orchestration service.
    
    Args:
        proposal_id: Proposal ID
        
    Returns:
        Proposal dictionary or None if not found
    """
    orchestration_service = get_orchestration_service()
    return orchestration_service.get_proposal(proposal_id)


async def verify_proposal_resolution(
    proposal_id: str, 
    expected_resolution: str
) -> bool:
    """
    Verify proposal resolution state using production service.
    
    Args:
        proposal_id: Proposal ID
        expected_resolution: Expected resolution ("approved" or "rejected")
        
    Returns:
        True if proposal has expected resolution and proper timestamps
    """
    proposal = await get_proposal_by_id(proposal_id)
    if not proposal:
        return False
    
    return (
        proposal["status"] == "resolved" and
        proposal["resolution"] == expected_resolution and
        proposal["resolved_at"] is not None and
        proposal["resolved_by_user_id"] is not None
    )


async def verify_context_persistence(
    proposal_id: str,
    expected_context_file_path: Optional[str],
    expected_context_selection: Optional[str]
) -> bool:
    """
    Verify context persistence using production service.
    
    Args:
        proposal_id: Proposal ID
        expected_context_file_path: Expected context file path
        expected_context_selection: Expected context selection
        
    Returns:
        True if context fields match expected values
    """
    proposal = await get_proposal_by_id(proposal_id)
    if not proposal:
        return False
    
    return (
        proposal["context_file_path"] == expected_context_file_path and
        proposal["context_selection"] == expected_context_selection
    )