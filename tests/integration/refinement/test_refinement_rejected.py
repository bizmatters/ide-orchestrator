"""
Refinement Rejected Lifecycle Integration Test - "Undo Path"

Focus: No data leakage and draft state preservation
Tests the complete refinement rejection flow with emphasis on:
- Draft content remains completely unchanged after rejection
- No data leakage from proposal to draft
- State machine transitions (processing → completed → resolved)
- Runtime cleanup verification
- Isolation between proposal and draft data
"""

import pytest
import asyncio
from httpx import AsyncClient
from fastapi.testclient import TestClient

from .shared.fixtures import (
    test_user_token,
    sample_initial_draft_content,
    sample_generated_files_rejected,
    sample_refinement_request_rejected
)
from .shared.database_helpers import (
    create_test_workflow_with_draft,
    get_draft_content_by_workflow
)
from .shared.mock_helpers import (
    create_mock_deepagents_server,
    wait_for_proposal_completion_via_orchestration,
    setup_cleanup_tracking
)
from .shared.assertions import (
    assert_refinement_response_valid,
    assert_proposal_state,
    assert_draft_content_unchanged,
    assert_runtime_cleanup_called,
    assert_context_metadata_persisted,
    assert_rejection_response_valid
)


@pytest.mark.asyncio
async def test_refinement_rejected_lifecycle(
    test_client: AsyncClient,
    test_user_token,
    sample_initial_draft_content,
    sample_generated_files_rejected,
    sample_refinement_request_rejected,
    app
):
    """
    Test complete refinement rejection lifecycle with data isolation validation.
    
    This test validates the "Undo Path" where:
    1. User initiates refinement request
    2. Production orchestration service processes request
    3. User rejects the proposal
    4. Draft content remains completely unchanged
    5. System performs cleanup and marks proposal as resolved
    
    Focus: No data leakage and draft state preservation using production services
    """
    user_id, token = test_user_token
    
    # Setup mock server for deepagents-runtime (external dependency)
    mock_server = create_mock_deepagents_server("rejected", http_port=8000, ws_port=8001)
    await mock_server.start()
    
    try:
        # Step 1: Setup workflow and draft using production services
        workflow_id, draft_id = await create_test_workflow_with_draft(
            user_id=user_id,
            workflow_name="Rejection Test Workflow",
            draft_content=sample_initial_draft_content,
            draft_name="Rejected Test Draft",
            draft_description="Draft for rejected lifecycle testing"
        )
        
        # Step 2: Capture baseline draft content for comparison
        baseline_draft_content = await get_draft_content_by_workflow(workflow_id, user_id)
        assert baseline_draft_content == sample_initial_draft_content, "Baseline content mismatch"
        
        # Step 3: Setup cleanup tracking to verify Requirement 4.5
        print(f"[DEBUG] Setting up cleanup tracking for rejected test")
        with setup_cleanup_tracking():
            # Step 4: Trigger refinement request through production API
            print(f"[DEBUG] Making refinement request through production API")
            response = await test_client.post(
                f"/api/workflows/{workflow_id}/refinements",
                json=sample_refinement_request_rejected,
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
            
            # Step 5: Verify initial proposal state through production service
            print(f"[DEBUG] Checking initial proposal state")
            await assert_proposal_state(
                proposal_id=proposal_id,
                expected_status="processing",
                has_files=False
            )
            
            # Step 6: Verify context metadata persistence (Requirement 7.1)
            print(f"[DEBUG] Verifying context metadata persistence")
            await assert_context_metadata_persisted(
                proposal_id=proposal_id,
                expected_context_file_path=sample_refinement_request_rejected["context_file_path"],
                expected_context_selection=sample_refinement_request_rejected["context_selection"]
            )
            
            # Step 6.5: Drive WebSocket execution to trigger backend processing
            print(f"[DEBUG] Connecting to WebSocket to drive execution for thread: {thread_id}")
            with TestClient(app) as client:
                with client.websocket_connect(f"/api/ws/refinements/{thread_id}?token={token}") as websocket:
                    while True:
                        try:
                            data = websocket.receive_json()
                            if data.get("event_type") == "end":
                                break
                        except Exception:
                            break
            
            # Step 7: Wait for production orchestration service to complete processing
            print(f"[DEBUG] Waiting for production orchestration service to complete processing")
            await wait_for_proposal_completion_via_orchestration(
                proposal_service=None,  # Use production service
                proposal_id=proposal_id
            )
            
            # Step 8: Validate proposal completion state (has different content)
            print(f"[DEBUG] Validating proposal completion state")
            await assert_proposal_state(
                proposal_id=proposal_id,
                expected_status="completed",
                has_files=True
            )
            
            # Step 9: Critical - Verify draft content is still unchanged
            print(f"[DEBUG] Verifying draft content is still unchanged")
            await assert_draft_content_unchanged(
                workflow_id=workflow_id,
                baseline_content=baseline_draft_content,
                user_id=user_id
            )
            
            # Step 10: Reject the proposal through production API
            print(f"[DEBUG] Rejecting proposal through production API")
            response = await test_client.post(
                f"/api/refinements/{proposal_id}/reject",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Validate: Rejection response structure
            print(f"[DEBUG] Rejection response: {response.status_code}")
            if response.status_code != 200:
                print(f"[DEBUG] Rejection response content: {response.content}")
            rejection_data = assert_rejection_response_valid(response)
            assert rejection_data["proposal_id"] == proposal_id
            
            # Step 11: Validate final proposal resolution state
            print(f"[DEBUG] Validating final proposal resolution state")
            await assert_proposal_state(
                proposal_id=proposal_id,
                expected_status="resolved",
                has_files=True,
                expected_resolution="rejected"
            )
            
            # Step 12: Critical - Verify draft content is STILL unchanged (no data leakage)
            print(f"[DEBUG] Verifying draft content is STILL unchanged (no data leakage)")
            await assert_draft_content_unchanged(
                workflow_id=workflow_id,
                baseline_content=baseline_draft_content,
                user_id=user_id
            )
            
            # Step 13: Verify runtime cleanup was called (Requirement 4.5)
            print(f"[DEBUG] Verifying runtime cleanup was called for thread_id: {thread_id}")
            await asyncio.sleep(0.5)  # Give the background task time to run
            assert_runtime_cleanup_called(thread_id)
            print(f"[DEBUG] Rejected test completed successfully!")
            
    finally:
        await mock_server.stop()


@pytest.mark.asyncio
async def test_refinement_rejected_data_isolation(
    test_client: AsyncClient,
    test_user_token,
    sample_initial_draft_content,
    sample_generated_files_rejected,
    sample_refinement_request_rejected,
    app
):
    """
    Test data isolation between proposal and draft during rejection using production services.
    
    Focus: Validates that proposal content never leaks into draft
    - Proposal can have completely different content
    - Draft remains isolated throughout the entire process
    - Multiple rejection cycles don't cause data corruption
    """
    user_id, token = test_user_token
    
    # Setup mock server for deepagents-runtime (external dependency)
    mock_server = create_mock_deepagents_server("rejected", http_port=8002, ws_port=8003)
    await mock_server.start()
    
    try:
        # Setup workflow and draft through production services
        workflow_id, draft_id = await create_test_workflow_with_draft(
            user_id=user_id,
            workflow_name="Data Isolation Test Workflow",
            draft_content=sample_initial_draft_content
        )
        
        # Capture original content
        original_content = await get_draft_content_by_workflow(workflow_id, user_id)
        
        # Create first proposal with different content
        print(f"[DEBUG] Creating first proposal for data isolation test")
        response = await test_client.post(
            f"/api/workflows/{workflow_id}/refinements",
            json=sample_refinement_request_rejected,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        print(f"[DEBUG] First refinement response: {response.status_code}")
        refinement_data_1 = assert_refinement_response_valid(response)
        proposal_id_1 = refinement_data_1["proposal_id"]
        thread_id_1 = refinement_data_1["thread_id"]
        print(f"[DEBUG] Got first proposal_id: {proposal_id_1}, thread_id: {thread_id_1}")
        
        # Drive WebSocket execution for first proposal
        print(f"[DEBUG] Driving WebSocket execution for first proposal: {thread_id_1}")
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/refinements/{thread_id_1}?token={token}") as websocket:
                while True:
                    try:
                        data = websocket.receive_json()
                        if data.get("event_type") == "end":
                            break
                    except Exception:
                        break
        
        # Complete first proposal through production orchestration service
        print(f"[DEBUG] Waiting for first proposal to complete via production orchestration service")
        await wait_for_proposal_completion_via_orchestration(
            proposal_service=None,
            proposal_id=proposal_id_1
        )
        
        # Verify draft is still unchanged
        print(f"[DEBUG] Verifying draft is still unchanged after first proposal")
        await assert_draft_content_unchanged(
            workflow_id=workflow_id,
            baseline_content=original_content,
            user_id=user_id
        )
        
        # Reject first proposal through production API
        print(f"[DEBUG] Rejecting first proposal")
        await test_client.post(
            f"/api/refinements/{proposal_id_1}/reject",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Verify draft is STILL unchanged after rejection
        print(f"[DEBUG] Verifying draft is STILL unchanged after first rejection")
        await assert_draft_content_unchanged(
            workflow_id=workflow_id,
            baseline_content=original_content,
            user_id=user_id
        )
        
        # Create second proposal with even more different content
        print(f"[DEBUG] Creating second proposal for data isolation test")
        response = await test_client.post(
            f"/api/workflows/{workflow_id}/refinements",
            json=sample_refinement_request_rejected,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        print(f"[DEBUG] Second refinement response: {response.status_code}")
        refinement_data_2 = assert_refinement_response_valid(response)
        proposal_id_2 = refinement_data_2["proposal_id"]
        thread_id_2 = refinement_data_2["thread_id"]
        print(f"[DEBUG] Got second proposal_id: {proposal_id_2}, thread_id: {thread_id_2}")
        
        # Drive WebSocket execution for second proposal
        print(f"[DEBUG] Driving WebSocket execution for second proposal: {thread_id_2}")
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/refinements/{thread_id_2}?token={token}") as websocket:
                while True:
                    try:
                        data = websocket.receive_json()
                        if data.get("event_type") == "end":
                            break
                    except Exception:
                        break
        
        # Complete second proposal through production orchestration service
        print(f"[DEBUG] Waiting for second proposal to complete via production orchestration service")
        await wait_for_proposal_completion_via_orchestration(
            proposal_service=None,
            proposal_id=proposal_id_2
        )
        
        # Verify draft is STILL unchanged after second proposal
        print(f"[DEBUG] Verifying draft is STILL unchanged after second proposal")
        await assert_draft_content_unchanged(
            workflow_id=workflow_id,
            baseline_content=original_content,
            user_id=user_id
        )
        
        # Reject second proposal through production API
        print(f"[DEBUG] Rejecting second proposal")
        await test_client.post(
            f"/api/refinements/{proposal_id_2}/reject",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Final verification: draft content is completely unchanged
        print(f"[DEBUG] Final verification: draft content is completely unchanged")
        await assert_draft_content_unchanged(
            workflow_id=workflow_id,
            baseline_content=original_content,
            user_id=user_id
        )
        
        # Verify both proposals are resolved as rejected through production service
        print(f"[DEBUG] Verifying both proposals are resolved as rejected")
        await assert_proposal_state(
            proposal_id=proposal_id_1,
            expected_status="resolved",
            expected_resolution="rejected"
        )
        
        await assert_proposal_state(
            proposal_id=proposal_id_2,
            expected_status="resolved",
            expected_resolution="rejected"
        )
        print(f"[DEBUG] Data isolation test completed successfully!")
        
    finally:
        await mock_server.stop()