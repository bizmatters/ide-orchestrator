"""
Refinement Approved Lifecycle Integration Test - "Happy Path"

Focus: Data integrity and state merging
Tests the complete refinement approval flow with emphasis on:
- Correct data flow from proposal to draft
- State machine transitions (processing → completed → resolved)
- Content integrity validation
- Production service usage
- Runtime cleanup verification
"""

import pytest
import asyncio
from httpx import AsyncClient

from .shared.fixtures import (
    test_user_token,
    sample_initial_draft_content,
    sample_generated_files_approved,
    sample_refinement_request_approved
)
from .shared.database_helpers import create_test_workflow_with_draft
from .shared.mock_helpers import (
    create_mock_deepagents_server,
    wait_for_proposal_completion_via_orchestration,
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
    test_user_token,
    sample_initial_draft_content,
    sample_generated_files_approved,
    sample_refinement_request_approved
):
    """
    Test complete refinement approval lifecycle with data integrity validation.
    
    This test validates the "Happy Path" where:
    1. User initiates refinement request
    2. Production orchestration service processes request
    3. User approves the proposal
    4. Draft content is updated with proposal content
    5. System performs cleanup and marks proposal as resolved
    
    Focus: Data integrity and state merging using production services
    """
    user_id, token = test_user_token
    
    # Setup mock server for deepagents-runtime (external dependency)
    mock_server = create_mock_deepagents_server("approved")
    await mock_server.start()
    
    try:
        # Step 1: Setup workflow and draft using production services
        workflow_id, draft_id = await create_test_workflow_with_draft(
            user_id=user_id,
            workflow_name="Approval Test Workflow",
            draft_content=sample_initial_draft_content,
            draft_name="Approved Test Draft",
            draft_description="Draft for approved lifecycle testing"
        )
        
        # Step 2: Setup cleanup tracking to verify Requirement 4.5
        print(f"[DEBUG] Setting up cleanup tracking for test")
        with setup_cleanup_tracking():
            # Step 3: Trigger refinement request through production API
            print(f"[DEBUG] Making refinement request through production API")
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
            
            # Step 4: Verify initial proposal state through production service
            print(f"[DEBUG] Checking initial proposal state")
            await assert_proposal_state(
                proposal_id=proposal_id,
                expected_status="processing",
                has_files=False
            )
            
            # Step 5: Verify context metadata persistence (Requirement 7.1)
            print(f"[DEBUG] Verifying context metadata persistence")
            await assert_context_metadata_persisted(
                proposal_id=proposal_id,
                expected_context_file_path=sample_refinement_request_approved["context_file_path"],
                expected_context_selection=sample_refinement_request_approved["context_selection"]
            )
            
            # Step 6: Wait for production orchestration service to complete processing
            print(f"[DEBUG] Waiting for production orchestration service to complete processing")
            await wait_for_proposal_completion_via_orchestration(
                proposal_service=None,  # Use production service
                proposal_id=proposal_id
            )
            
            # Step 7: Validate proposal completion state through production service
            print(f"[DEBUG] Validating proposal completion state")
            await assert_proposal_state(
                proposal_id=proposal_id,
                expected_status="completed",
                has_files=True
            )
            
            # Step 8: Approve the proposal through production API
            print(f"[DEBUG] Approving proposal through production API")
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
                has_files=True,
                expected_resolution="approved"
            )
            
            # Step 10: Critical - Validate content integrity (data merging)
            print(f"[DEBUG] Validating content integrity")
            await assert_content_integrity(
                proposal_id=proposal_id,
                workflow_id=workflow_id,
                user_id=user_id
            )
            
            # Step 11: Verify runtime cleanup was called (Requirement 4.5)
            print(f"[DEBUG] Verifying runtime cleanup was called for thread_id: {thread_id}")
            await asyncio.sleep(0.5)  # Give the background task time to run
            assert_runtime_cleanup_called(thread_id)
            print(f"[DEBUG] Test completed successfully!")
            
    finally:
        await mock_server.stop()


@pytest.mark.asyncio
async def test_refinement_approved_state_transitions(
    test_client: AsyncClient,
    test_user_token,
    sample_initial_draft_content,
    sample_generated_files_approved,
    sample_refinement_request_approved
):
    """
    Test state machine transitions during approval flow using production services.
    
    Focus: Validates proper state transitions and timestamp management
    - processing → completed (with completed_at timestamp)
    - completed → resolved (with resolved_at timestamp and resolution)
    """
    user_id, token = test_user_token
    
    # Setup mock server for deepagents-runtime (external dependency)
    mock_server = create_mock_deepagents_server("approved")
    await mock_server.start()
    
    try:
        # Setup workflow and draft through production services
        workflow_id, draft_id = await create_test_workflow_with_draft(
            user_id=user_id,
            workflow_name="State Transition Test Workflow",
            draft_content=sample_initial_draft_content
        )
        
        # Trigger refinement through production API
        print(f"[DEBUG] Making refinement request through production API")
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
            expected_status="processing"
        )
        assert proposal_processing["completed_at"] is None
        assert proposal_processing["resolved_at"] is None
        assert proposal_processing["resolution"] is None
        
        # Wait for completion through production orchestration service
        await wait_for_proposal_completion_via_orchestration(
            proposal_service=None,
            proposal_id=proposal_id
        )
        
        # Validate completed state
        proposal_completed = await assert_proposal_state(
            proposal_id=proposal_id,
            expected_status="completed",
            has_files=True
        )
        assert proposal_completed["completed_at"] is not None
        assert proposal_completed["resolved_at"] is None
        assert proposal_completed["resolution"] is None
        
        # Approve proposal through production API
        await test_client.post(
            f"/api/refinements/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Validate resolved state
        proposal_resolved = await assert_proposal_state(
            proposal_id=proposal_id,
            expected_status="resolved",
            has_files=True,
            expected_resolution="approved"
        )
        assert proposal_resolved["completed_at"] is not None
        assert proposal_resolved["resolved_at"] is not None
        assert proposal_resolved["resolved_by_user_id"] == user_id
        
        # Validate timestamp ordering
        assert proposal_resolved["completed_at"] <= proposal_resolved["resolved_at"]
        
    finally:
        await mock_server.stop()