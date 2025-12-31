"""
Refinement Approved Lifecycle Integration Test - "Happy Path"

Focus: Data integrity and state merging
Tests the complete refinement approval flow with emphasis on:
- Correct data flow from proposal to draft
- State machine transitions (processing → completed → resolved)
- Content integrity validation
- WebSocket stream processing simulation
- Runtime cleanup verification
"""

import pytest
import asyncio
from httpx import AsyncClient

from .shared.fixtures import (
    refinement_test_context,
    sample_initial_draft_content,
    sample_generated_files_approved,
    sample_refinement_request_approved
)
from .shared.database_helpers import create_test_workflow_with_draft
from .shared.mock_helpers import (
    create_mock_deepagents_client,
    patch_deepagents_client,
    simulate_proposal_completion_via_stream,
    setup_cleanup_tracking
)
from .shared.assertions import (
    assert_refinement_response_valid,
    assert_proposal_state,
    assert_content_integrity,
    assert_runtime_cleanup_called,
    assert_context_metadata_persisted,
    assert_approval_response_valid
)


@pytest.mark.asyncio
async def test_refinement_approved_lifecycle(
    test_client: AsyncClient,
    refinement_test_context,
    sample_initial_draft_content,
    sample_generated_files_approved,
    sample_refinement_request_approved
):
    """
    Test complete refinement approval lifecycle with data integrity validation.
    
    This test validates the "Happy Path" where:
    1. User initiates refinement request
    2. WebSocket streaming processes and updates proposal
    3. User approves the proposal
    4. Draft content is updated with proposal content
    5. System performs cleanup and marks proposal as resolved
    
    Focus: Data integrity and state merging
    """
    user_id, token, database_url, workflow_service, proposal_service, draft_service = refinement_test_context
    
    # Step 1: Setup workflow and draft using shared utility
    workflow_id, draft_id = await create_test_workflow_with_draft(
        user_id=user_id,
        workflow_name="Approval Test Workflow",
        draft_content=sample_initial_draft_content,
        database_url=database_url,
        draft_name="Approved Test Draft",
        draft_description="Draft for approved lifecycle testing"
    )
    
    # Step 2: Setup cleanup tracking to verify Requirement 4.5
    print(f"[DEBUG] Setting up cleanup tracking for test")
    with setup_cleanup_tracking():
        # Step 3: Trigger refinement request using real client (no mocking)
        print(f"[DEBUG] Using real DeepAgents client for approved test")
        mock_client = create_mock_deepagents_client("approved")  # Returns None
        
        print(f"[DEBUG] Making refinement request with real client")
        with patch_deepagents_client(mock_client):  # No-op context manager
            response = await test_client.post(
                f"/api/workflows/{workflow_id}/refinements",
                json=sample_refinement_request_approved,
                headers={"Authorization": f"Bearer {token}"}
            )
        
        # Validate: Response contains thread_id and proposal_id; status is processing
        print(f"[DEBUG] Refinement response: {response.status_code}")
        if response.status_code != 202:
            print(f"[DEBUG] Response content: {response.content}")
        refinement_data = assert_refinement_response_valid(response, expected_status=202)
        proposal_id = refinement_data["proposal_id"]
        thread_id = refinement_data["thread_id"]
        print(f"[DEBUG] Got proposal_id: {proposal_id}, thread_id: {thread_id}")
        
        # Step 4: Verify initial proposal state
        print(f"[DEBUG] Checking initial proposal state")
        await assert_proposal_state(
            proposal_id=proposal_id,
            expected_status="processing",
            database_url=database_url,
            has_files=False
        )
        
        # Step 5: Verify context metadata persistence (Requirement 7.1)
        print(f"[DEBUG] Verifying context metadata persistence")
        await assert_context_metadata_persisted(
            proposal_id=proposal_id,
            expected_context_file_path=sample_refinement_request_approved["context_file_path"],
            expected_context_selection=sample_refinement_request_approved["context_selection"],
            database_url=database_url
        )
        
        # Step 6: Simulate WebSocket streaming with file content updates
        # This tests the hybrid event processing (Requirement 3.1)
        print(f"[DEBUG] Simulating proposal completion via stream")
        await simulate_proposal_completion_via_stream(
            proposal_service=proposal_service,
            proposal_id=proposal_id,
            thread_id=thread_id,
            generated_files=sample_generated_files_approved
        )
        
        # Step 7: Validate proposal completion state
        print(f"[DEBUG] Validating proposal completion state")
        await assert_proposal_state(
            proposal_id=proposal_id,
            expected_status="completed",
            database_url=database_url,
            has_files=True
        )
        
        # Step 8: Approve the proposal through production API
        print(f"[DEBUG] Approving proposal through API")
        response = await test_client.post(
            f"/api/refinements/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Validate: Approval response structure
        print(f"[DEBUG] Approval response: {response.status_code}")
        if response.status_code != 200:
            print(f"[DEBUG] Approval response content: {response.content}")
        approval_data = assert_approval_response_valid(response)
        assert approval_data["proposal_id"] == proposal_id
        
        # Step 9: Validate final proposal resolution state
        print(f"[DEBUG] Validating final proposal resolution state")
        await assert_proposal_state(
            proposal_id=proposal_id,
            expected_status="resolved",
            database_url=database_url,
            has_files=True,
            expected_resolution="approved"
        )
        
        # Step 10: Critical - Validate content integrity (data merging)
        # This ensures draft content exactly matches proposal generated_files
        print(f"[DEBUG] Validating content integrity")
        await assert_content_integrity(
            proposal_id=proposal_id,
            workflow_id=workflow_id,
            database_url=database_url
        )
        
        # Step 11: Verify runtime cleanup was called (Requirement 4.5)
        print(f"[DEBUG] Verifying runtime cleanup was called for thread_id: {thread_id}")
        # Wait a bit for the async cleanup task to complete
        print(f"[DEBUG] Waiting for async cleanup task to complete...")
        await asyncio.sleep(0.5)  # Give the background task time to run
        assert_runtime_cleanup_called(thread_id)
        print(f"[DEBUG] Test completed successfully!")


@pytest.mark.asyncio
async def test_refinement_approved_state_transitions(
    test_client: AsyncClient,
    refinement_test_context,
    sample_initial_draft_content,
    sample_generated_files_approved,
    sample_refinement_request_approved
):
    """
    Test state machine transitions during approval flow.
    
    Focus: Validates proper state transitions and timestamp management
    - processing → completed (with completed_at timestamp)
    - completed → resolved (with resolved_at timestamp and resolution)
    """
    user_id, token, database_url, workflow_service, proposal_service, draft_service = refinement_test_context
    
    # Setup workflow and draft
    workflow_id, draft_id = await create_test_workflow_with_draft(
        user_id=user_id,
        workflow_name="State Transition Test Workflow",
        draft_content=sample_initial_draft_content,
        database_url=database_url
    )
    
    # Trigger refinement
    print(f"[DEBUG] Using real DeepAgents client for state transition test")
    mock_client = create_mock_deepagents_client("state_test")  # Returns None
    
    print(f"[DEBUG] Making refinement request with real client for state test")
    with patch_deepagents_client(mock_client):  # No-op context manager
        response = await test_client.post(
            f"/api/workflows/{workflow_id}/refinements",
            json=sample_refinement_request_approved,
            headers={"Authorization": f"Bearer {token}"}
        )
    
    refinement_data = assert_refinement_response_valid(response)
    proposal_id = refinement_data["proposal_id"]
    thread_id = refinement_data["thread_id"]
    
    # Validate initial state: processing
    proposal_processing = await assert_proposal_state(
        proposal_id=proposal_id,
        expected_status="processing",
        database_url=database_url
    )
    assert proposal_processing["completed_at"] is None
    assert proposal_processing["resolved_at"] is None
    assert proposal_processing["resolution"] is None
    
    # Simulate completion
    await simulate_proposal_completion_via_stream(
        proposal_service=proposal_service,
        proposal_id=proposal_id,
        thread_id=thread_id,
        generated_files=sample_generated_files_approved
    )
    
    # Validate completed state
    proposal_completed = await assert_proposal_state(
        proposal_id=proposal_id,
        expected_status="completed",
        database_url=database_url,
        has_files=True
    )
    assert proposal_completed["completed_at"] is not None
    assert proposal_completed["resolved_at"] is None
    assert proposal_completed["resolution"] is None
    
    # Approve proposal
    await test_client.post(
        f"/api/refinements/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Validate resolved state
    proposal_resolved = await assert_proposal_state(
        proposal_id=proposal_id,
        expected_status="resolved",
        database_url=database_url,
        has_files=True,
        expected_resolution="approved"
    )
    assert proposal_resolved["completed_at"] is not None
    assert proposal_resolved["resolved_at"] is not None
    assert proposal_resolved["resolved_by_user_id"] == user_id
    
    # Validate timestamp ordering
    assert proposal_resolved["completed_at"] <= proposal_resolved["resolved_at"]