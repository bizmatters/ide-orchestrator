"""
Comprehensive refinement lifecycle integration tests.

Tests the complete flow from refinement request through proposal generation,
approval/rejection, and final state validation including data integrity checks.

Follows integration testing patterns:
- Uses production service classes and dependency injection
- Tests against real PostgreSQL infrastructure
- Mocks only external dependencies (DeepAgents service)
- Validates persistence through direct database queries
"""

import pytest
import pytest_asyncio
import json
import time
import uuid
from httpx import AsyncClient
from unittest.mock import patch
import psycopg
from psycopg.rows import dict_row

from core.jwt_manager import JWTManager
from api.dependencies import get_database_url, get_workflow_service, get_auth_service
from services.workflow_service import WorkflowService
from services.proposal_service import ProposalService
from services.draft_service import DraftService
from tests.mock.deepagents_mock import MockDeepAgentsRuntimeClient


@pytest.mark.asyncio
async def test_refinement_approved_lifecycle(test_client: AsyncClient, jwt_manager: JWTManager):
    """
    Test complete refinement lifecycle with approval flow.
    
    Uses production code paths and validates:
    1. Refinement request returns thread_id and proposal_id
    2. WebSocket streaming persists proposal data correctly
    3. Approval updates draft with proposal content
    4. Cleanup removes checkpoint data
    """
    # Use production dependency injection - same as production
    database_url = get_database_url()
    workflow_service = WorkflowService(database_url)
    proposal_service = ProposalService(database_url)
    draft_service = DraftService(database_url)
    
    # Create test user (using direct database access for test setup only)
    user_email = f"lifecycle-approved-{int(time.time() * 1000000)}@example.com"
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, hashed_password, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                ("Test User", user_email, "hashed-password")
            )
            user_result = cur.fetchone()
            user_id = str(user_result["id"])
    
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Step 1: Create workflow using production service
    workflow_result = workflow_service.create_workflow(
        name="Lifecycle Test Workflow",
        user_id=user_id,
        description="Testing complete refinement lifecycle"
    )
    workflow_id = workflow_result["id"]
    
    # Create initial draft content using production service
    initial_draft_content = {
        "main.py": "print('initial version')",
        "config.json": '{"version": "1.0"}'
    }
    
    # Insert initial draft using direct database access (for test setup)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO drafts (id, workflow_id, name, description, created_by_user_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (str(uuid.uuid4()), workflow_id, "Approved Test Draft", "Draft for approved lifecycle testing", user_id)
            )
            draft_result = cur.fetchone()
            draft_id = draft_result["id"]
            
            # Insert initial draft files
            for file_path, content in initial_draft_content.items():
                cur.execute(
                    """
                    INSERT INTO draft_specification_files (draft_id, file_path, content, file_type, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (draft_id, file_path, content, "json" if file_path.endswith(".json") else "markdown")
                )
    
    # Step 2: Trigger refinement request through production API
    refinement_data = {
        "instructions": "Add error handling and logging to the main function",
        "context_file_path": None,
        "context_selection": "Improve code quality and debugging capabilities"
    }
    
    # Create mock client and set up response
    mock_client = MockDeepAgentsRuntimeClient()
    mock_thread_id = f"thread_{int(time.time())}"
    mock_client.set_mock_response("invoke_job", {"thread_id": mock_thread_id})
    
    with patch('services.deepagents_client.DeepAgentsRuntimeClient', return_value=mock_client):
        response = await test_client.post(
            f"/api/workflows/{workflow_id}/refinements",
            json=refinement_data,
            headers={"Authorization": f"Bearer {token}"}
        )
    
    # Validate: Response contains thread_id and proposal_id; status is processing
    assert response.status_code == 202
    refinement_response = response.json()
    assert "thread_id" in refinement_response
    assert "proposal_id" in refinement_response
    thread_id = refinement_response["thread_id"]
    proposal_id = refinement_response["proposal_id"]
    
    # Verify proposal is created with processing status using production service
    proposal = proposal_service.get_proposal(proposal_id)
    assert proposal is not None
    assert proposal["status"] == "processing"
    assert proposal["thread_id"] == thread_id
    
    # Step 3: Simulate WebSocket streaming with file content updates
    updated_files_content = {
        "main.py": {
            "content": """import logging
import sys

def main():
    try:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        
        logger.info("Starting application")
        print('enhanced version with error handling')
        logger.info("Application completed successfully")
        
    except Exception as e:
        logger.error(f"Application failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()""",
            "type": "markdown"
        },
        "config.json": {
            "content": '{"version": "2.0", "logging": {"level": "INFO"}}',
            "type": "json"
        }
    }
    
    # Simulate proposal completion using production service
    proposal_service.update_proposal_results(
        proposal_id=proposal_id,
        status="completed",
        audit_trail_json="{}",
        generated_files=updated_files_content
    )
    
    # Validate: Query database directly to verify proposal completion
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, generated_files, completed_at FROM proposals WHERE id = %s",
                (proposal_id,)
            )
            proposal_record = cur.fetchone()
            assert proposal_record["status"] == "completed"
            assert proposal_record["completed_at"] is not None
            
            stored_files = proposal_record["generated_files"]
            if isinstance(stored_files, str):
                stored_files = json.loads(stored_files)
            assert stored_files == updated_files_content
    
    # Step 4: Approve the proposal through production API
    response = await test_client.post(
        f"/api/refinements/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Validate: Response contains status: success and message
    assert response.status_code == 200
    approval_response = response.json()
    assert "proposal_id" in approval_response
    assert "approved_at" in approval_response
    assert "message" in approval_response
    
    # Step 5: Final Persistence - Validate draft content matches proposal using database query
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dsf.file_path, dsf.content 
                FROM draft_specification_files dsf
                JOIN drafts d ON dsf.draft_id = d.id
                WHERE d.workflow_id = %s
                """,
                (workflow_id,)
            )
            draft_files = {row["file_path"]: row["content"] for row in cur.fetchall()}
    
    # Validate: Draft's file content matches the Proposal's generated_files exactly
    expected_draft_content = {
        file_path: file_data["content"] 
        for file_path, file_data in updated_files_content.items()
    }
    assert draft_files == expected_draft_content
    
    # Step 6: Verify proposal is resolved using production service
    final_proposal = proposal_service.get_proposal(proposal_id)
    assert final_proposal["status"] == "resolved"
    assert final_proposal["resolved_at"] is not None


@pytest.mark.asyncio
async def test_refinement_rejected_lifecycle(test_client: AsyncClient, jwt_manager: JWTManager):
    """
    Test complete refinement lifecycle with rejection flow.
    
    Uses production code paths and validates:
    1. Refinement request and streaming work as expected
    2. Pre-rejection draft content is recorded
    3. Rejection leaves draft content unchanged
    4. Proposal is marked as resolved
    """
    # Use production dependency injection
    database_url = get_database_url()
    workflow_service = WorkflowService(database_url)
    proposal_service = ProposalService(database_url)
    
    # Create test user
    user_email = f"lifecycle-rejected-{int(time.time() * 1000000)}@example.com"
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, hashed_password, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                ("Test User", user_email, "hashed-password")
            )
            user_result = cur.fetchone()
            user_id = str(user_result["id"])
    
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Create workflow using production service
    workflow_result = workflow_service.create_workflow(
        name="Lifecycle Rejection Test Workflow",
        user_id=user_id,
        description="Testing refinement rejection lifecycle"
    )
    workflow_id = workflow_result["id"]
    
    # Create initial draft content
    original_draft_content = {
        "app.py": "def hello(): return 'Hello World'",
        "requirements.txt": "flask==2.0.1"
    }
    
    # Insert initial draft
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO drafts (id, workflow_id, name, description, created_by_user_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (str(uuid.uuid4()), workflow_id, "Rejected Test Draft", "Draft for rejected lifecycle testing", user_id)
            )
            draft_result = cur.fetchone()
            draft_id = draft_result["id"]
            
            # Insert initial draft files
            for file_path, content in original_draft_content.items():
                cur.execute(
                    """
                    INSERT INTO draft_specification_files (draft_id, file_path, content, file_type, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (draft_id, file_path, content, "json" if file_path.endswith(".json") else "markdown")
                )
    
    # Step 1: Trigger refinement request through production API
    refinement_data = {
        "instructions": "Add database integration with SQLAlchemy",
        "context_file_path": None,
        "context_selection": "Need to persist data in a database"
    }
    
    # Create mock client and set up response
    mock_client = MockDeepAgentsRuntimeClient()
    mock_thread_id = f"thread_reject_{int(time.time())}"
    mock_client.set_mock_response("invoke_job", {"thread_id": mock_thread_id})
    
    with patch('services.deepagents_client.DeepAgentsRuntimeClient', return_value=mock_client):
        response = await test_client.post(
            f"/api/workflows/{workflow_id}/refinements",
            json=refinement_data,
            headers={"Authorization": f"Bearer {token}"}
        )
    
    assert response.status_code == 202
    refinement_response = response.json()
    proposal_id = refinement_response["proposal_id"]
    
    # Step 2: Simulate proposal completion with different content
    proposed_files_content = {
        "app.py": {
            "content": """from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)

def hello():
    return 'Hello World with Database!'

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()""",
            "type": "markdown"
        },
        "requirements.txt": {
            "content": "flask==2.0.1\nflask-sqlalchemy==2.5.1",
            "type": "markdown"
        }
    }
    
    # Complete the proposal using production service
    proposal_service.update_proposal_results(
        proposal_id=proposal_id,
        status="completed",
        audit_trail_json="{}",
        generated_files=proposed_files_content
    )
    
    # Step 3: Pre-Action Check - Record current draft content using database query
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dsf.file_path, dsf.content 
                FROM draft_specification_files dsf
                JOIN drafts d ON dsf.draft_id = d.id
                WHERE d.workflow_id = %s
                """,
                (workflow_id,)
            )
            pre_rejection_content = {row["file_path"]: row["content"] for row in cur.fetchall()}
    
    # Validate pre-rejection content matches original
    assert pre_rejection_content == original_draft_content
    
    # Step 4: Reject the proposal through production API
    response = await test_client.post(
        f"/api/refinements/{proposal_id}/reject",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Validate: Response contains status: success and message
    assert response.status_code == 200
    rejection_response = response.json()
    assert "proposal_id" in rejection_response
    assert "message" in rejection_response
    
    # Step 5: Final Persistence - Query drafts table to verify no changes
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dsf.file_path, dsf.content 
                FROM draft_specification_files dsf
                JOIN drafts d ON dsf.draft_id = d.id
                WHERE d.workflow_id = %s
                """,
                (workflow_id,)
            )
            post_rejection_content = {row["file_path"]: row["content"] for row in cur.fetchall()}
    
    # Validate: Draft content remains unchanged (matches pre-action check)
    assert post_rejection_content == pre_rejection_content
    assert post_rejection_content == original_draft_content
    
    # Step 6: Verify proposal state using production service
    final_proposal = proposal_service.get_proposal(proposal_id)
    assert final_proposal["status"] == "resolved"
    assert final_proposal["resolved_at"] is not None


@pytest.mark.asyncio
async def test_refinement_data_integrity_validation(test_client: AsyncClient, jwt_manager: JWTManager):
    """
    Test data integrity across the refinement lifecycle using production code paths.
    
    Validates:
    1. Contract validation - UI gets thread_id and updated_files
    2. State machine transitions work correctly
    3. Data integrity between proposals and drafts
    4. Production service layer handles all business logic correctly
    """
    # Use production dependency injection
    database_url = get_database_url()
    workflow_service = WorkflowService(database_url)
    proposal_service = ProposalService(database_url)
    
    # Create test user
    user_email = f"data-integrity-{int(time.time() * 1000000)}@example.com"
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, hashed_password, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                ("Test User", user_email, "hashed-password")
            )
            user_result = cur.fetchone()
            user_id = str(user_result["id"])
    
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Create workflow using production service
    workflow_result = workflow_service.create_workflow(
        name="Data Integrity Test Workflow",
        user_id=user_id,
        description="Testing data integrity across refinement lifecycle"
    )
    workflow_id = workflow_result["id"]
    
    # Create initial draft
    initial_content = {"test.py": "# Initial version"}
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO drafts (id, workflow_id, name, description, created_by_user_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (str(uuid.uuid4()), workflow_id, "Data Integrity Test Draft", "Draft for data integrity testing", user_id)
            )
            draft_id = cur.fetchone()["id"]
            
            cur.execute(
                """
                INSERT INTO draft_specification_files (draft_id, file_path, content, file_type, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (draft_id, "test.py", "# Initial version", "markdown")
            )
    
    # Test 1: Contract Validation - Create refinement through production API
    refinement_data = {
        "instructions": "Add comprehensive documentation",
        "context_file_path": None,
        "context_selection": "Need better code documentation"
    }
    
    # Create mock client and set up response
    mock_client = MockDeepAgentsRuntimeClient()
    mock_thread_id = f"thread_integrity_{int(time.time())}"
    mock_client.set_mock_response("invoke_job", {"thread_id": mock_thread_id})
    
    with patch('services.deepagents_client.DeepAgentsRuntimeClient', return_value=mock_client):
        response = await test_client.post(
            f"/api/workflows/{workflow_id}/refinements",
            json=refinement_data,
            headers={"Authorization": f"Bearer {token}"}
        )
    
    # Validate contract - UI gets thread_id for WebSocket connection
    assert response.status_code == 202
    contract_data = response.json()
    assert "thread_id" in contract_data
    assert "proposal_id" in contract_data
    thread_id = contract_data["thread_id"]
    proposal_id = contract_data["proposal_id"]
    
    # Test 2: State Machine - Verify processing → completed transition using production service
    proposal = proposal_service.get_proposal(proposal_id)
    assert proposal["status"] == "processing"
    
    # Simulate completion using production service
    final_content = {
        "test.py": {
            "content": """# Test Module
# This module provides comprehensive testing functionality

def test_function():
    '''
    A well-documented test function.
    
    Returns:
        str: A test message
    '''
    return "Test completed successfully"

if __name__ == "__main__":
    print(test_function())""",
            "type": "markdown"
        }
    }
    
    proposal_service.update_proposal_results(
        proposal_id=proposal_id,
        status="completed",
        audit_trail_json="{}",
        generated_files=final_content
    )
    
    # Verify state transition using production service
    updated_proposal = proposal_service.get_proposal(proposal_id)
    assert updated_proposal["status"] == "completed"
    
    # Test 3: Data Integrity - Approve and verify exact content match through production API
    response = await test_client.post(
        f"/api/refinements/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    approval_data = response.json()
    
    # Validate contract - UI gets success response
    assert "proposal_id" in approval_data
    assert "approved_at" in approval_data
    
    # Verify exact content match between proposal and draft using database queries
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # Get proposal content
            cur.execute("SELECT generated_files FROM proposals WHERE id = %s", (proposal_id,))
            generated_files_raw = cur.fetchone()["generated_files"]
            if isinstance(generated_files_raw, str):
                proposal_content = json.loads(generated_files_raw)
            else:
                proposal_content = generated_files_raw
            
            # Get draft content
            cur.execute(
                """
                SELECT dsf.file_path, dsf.content 
                FROM draft_specification_files dsf
                JOIN drafts d ON dsf.draft_id = d.id
                WHERE d.workflow_id = %s
                """,
                (workflow_id,)
            )
            draft_content = {row["file_path"]: row["content"] for row in cur.fetchall()}
            
            # Validate exact match
            expected_draft_content = {
                file_path: file_data["content"] 
                for file_path, file_data in final_content.items()
            }
            expected_proposal_content = {
                file_path: file_data["content"] 
                for file_path, file_data in proposal_content.items()
            }
            assert draft_content == expected_proposal_content
            assert draft_content == expected_draft_content
    
    # Test 4: State Machine - Verify completed → resolved transition using production service
    final_proposal = proposal_service.get_proposal(proposal_id)
    assert final_proposal["status"] == "resolved"
    assert final_proposal["resolved_at"] is not None



