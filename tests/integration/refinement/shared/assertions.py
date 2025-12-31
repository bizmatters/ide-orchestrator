"""
Custom assertion helpers for refinement integration tests.

Provides specialized assertions for validating refinement workflow behavior
using production services following integration testing patterns.
"""

import json
from typing import Dict, Any, Optional
from httpx import Response

from .database_helpers import (
    get_proposal_by_id, 
    get_draft_content_by_workflow,
    verify_proposal_resolution,
    verify_context_persistence
)
from .mock_helpers import get_cleanup_tracker


def assert_refinement_response_valid(
    response: Response, 
    expected_status: int = 202
) -> Dict[str, Any]:
    """
    Validate refinement API response structure.
    
    Args:
        response: HTTP response from refinement API
        expected_status: Expected HTTP status code
        
    Returns:
        Response JSON data
        
    Raises:
        AssertionError: If response doesn't match expected structure
    """
    assert response.status_code == expected_status, f"Expected status {expected_status}, got {response.status_code}"
    
    data = response.json()
    
    # Validate required fields for refinement initiation
    if expected_status == 202:
        assert "thread_id" in data, "Response missing thread_id"
        assert "proposal_id" in data, "Response missing proposal_id"
        assert "status" in data, "Response missing status"
        assert data["status"] == "processing", f"Expected status 'processing', got {data['status']}"
        assert "websocket_url" in data, "Response missing websocket_url"
        assert "created_at" in data, "Response missing created_at"
    
    return data


async def assert_proposal_state(
    proposal_id: str,
    expected_status: str,
    has_files: Optional[bool] = None,
    expected_resolution: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate proposal database state using production service.
    
    Args:
        proposal_id: Proposal ID to check
        expected_status: Expected proposal status
        has_files: Whether proposal should have generated_files (None = don't check)
        expected_resolution: Expected resolution value (None = don't check)
        
    Returns:
        Proposal data
        
    Raises:
        AssertionError: If proposal state doesn't match expectations
    """
    proposal = await get_proposal_by_id(proposal_id)
    assert proposal is not None, f"Proposal {proposal_id} not found"
    
    assert proposal["status"] == expected_status, \
        f"Expected status '{expected_status}', got '{proposal['status']}'"
    
    if has_files is not None:
        if has_files:
            assert proposal["generated_files"] is not None, "Expected proposal to have generated_files"
            assert len(proposal["generated_files"]) > 0, "Expected non-empty generated_files"
        else:
            assert proposal["generated_files"] is None or len(proposal["generated_files"]) == 0, \
                "Expected proposal to have no generated_files"
    
    if expected_resolution is not None:
        assert proposal["resolution"] == expected_resolution, \
            f"Expected resolution '{expected_resolution}', got '{proposal['resolution']}'"
    
    # Validate timestamp consistency
    if expected_status == "completed":
        assert proposal["completed_at"] is not None, "Completed proposal should have completed_at timestamp"
    
    if expected_status == "resolved":
        assert proposal["resolved_at"] is not None, "Resolved proposal should have resolved_at timestamp"
        assert proposal["resolved_by_user_id"] is not None, "Resolved proposal should have resolved_by_user_id"
    
    return proposal


async def assert_content_integrity(
    proposal_id: str,
    workflow_id: str,
    user_id: str
):
    """
    Validate exact content match between proposal and draft using production services.
    
    This ensures that when a proposal is approved, the draft content
    exactly matches the proposal's generated_files content.
    
    Args:
        proposal_id: Proposal ID
        workflow_id: Workflow ID
        user_id: User ID for access control
        
    Raises:
        AssertionError: If content doesn't match exactly
    """
    # Get proposal generated files through production service
    proposal = await get_proposal_by_id(proposal_id)
    assert proposal is not None, f"Proposal {proposal_id} not found"
    assert proposal["generated_files"] is not None, "Proposal has no generated_files"
    
    generated_files = proposal["generated_files"]
    if isinstance(generated_files, str):
        generated_files = json.loads(generated_files)
    
    # Extract content from generated files
    expected_draft_content = {}
    for file_path, file_data in generated_files.items():
        if isinstance(file_data, dict) and "content" in file_data:
            # Handle content as array of lines (join them)
            if isinstance(file_data["content"], list):
                expected_draft_content[file_path] = "\n".join(file_data["content"])
            else:
                expected_draft_content[file_path] = file_data["content"]
        else:
            expected_draft_content[file_path] = str(file_data)
    
    # Get actual draft content through production service
    actual_draft_content = await get_draft_content_by_workflow(workflow_id, user_id)
    
    print(f"[DEBUG] Expected draft content keys: {list(expected_draft_content.keys())}")
    print(f"[DEBUG] Actual draft content keys: {list(actual_draft_content.keys())}")
    
    # Compare content
    if actual_draft_content != expected_draft_content:
        print(f"[DEBUG] Content mismatch details:")
        for file_path in set(list(expected_draft_content.keys()) + list(actual_draft_content.keys())):
            expected = expected_draft_content.get(file_path, "<MISSING>")
            actual = actual_draft_content.get(file_path, "<MISSING>")
            if expected != actual:
                print(f"[DEBUG] File {file_path}:")
                print(f"[DEBUG]   Expected: {expected[:100]}...")
                print(f"[DEBUG]   Actual: {actual[:100]}...")
    
    assert actual_draft_content == expected_draft_content, \
        f"Content integrity violation.\nProposal files: {list(expected_draft_content.keys())}\nDraft files: {list(actual_draft_content.keys())}"


async def assert_draft_content_unchanged(
    workflow_id: str,
    baseline_content: Dict[str, str],
    user_id: str
):
    """
    Validate that draft content remains unchanged from baseline using production service.
    
    This is used in rejection tests to ensure no data leakage occurs.
    
    Args:
        workflow_id: Workflow ID
        baseline_content: Baseline content to compare against
        user_id: User ID for access control
        
    Raises:
        AssertionError: If draft content has changed from baseline
    """
    current_content = await get_draft_content_by_workflow(workflow_id, user_id)
    
    assert current_content == baseline_content, \
        f"Draft content changed unexpectedly.\nBaseline: {baseline_content}\nCurrent: {current_content}"


def assert_runtime_cleanup_called(thread_id: str):
    """
    Ensure that deepagents-runtime cleanup was called for thread_id.
    
    This validates Requirement 4.5: cleanup removes checkpoint data
    upon proposal resolution (approve/reject).
    
    Args:
        thread_id: Thread ID that should have been cleaned up
        
    Raises:
        AssertionError: If cleanup was not called for thread_id
    """
    cleanup_tracker = get_cleanup_tracker()
    
    print(f"[DEBUG] Checking cleanup tracker for thread_id: {thread_id}")
    print(f"[DEBUG] All cleanup calls: {cleanup_tracker.cleanup_calls}")
    print(f"[DEBUG] was_cleanup_called result: {cleanup_tracker.was_cleanup_called(thread_id)}")
    
    assert cleanup_tracker.was_cleanup_called(thread_id), \
        f"Runtime cleanup was not called for thread_id: {thread_id}"
    
    # Verify cleanup was successful
    cleanup_calls = cleanup_tracker.get_cleanup_calls_for_thread(thread_id)
    successful_calls = [call for call in cleanup_calls if call["success"]]
    
    assert len(successful_calls) > 0, \
        f"Runtime cleanup was called but failed for thread_id: {thread_id}"


async def assert_context_metadata_persisted(
    proposal_id: str,
    expected_context_file_path: Optional[str],
    expected_context_selection: Optional[str]
):
    """
    Validate that context metadata is correctly persisted using production service.
    
    This validates Requirement 7.1: context_file_path and context_selection
    are correctly stored during refinement request.
    
    Args:
        proposal_id: Proposal ID
        expected_context_file_path: Expected context file path
        expected_context_selection: Expected context selection
        
    Raises:
        AssertionError: If context metadata doesn't match expected values
    """
    is_persisted = await verify_context_persistence(
        proposal_id, expected_context_file_path, expected_context_selection
    )
    
    assert is_persisted, \
        f"Context metadata not persisted correctly for proposal {proposal_id}. " \
        f"Expected file_path: {expected_context_file_path}, selection: {expected_context_selection}"


def assert_approval_response_valid(response: Response) -> Dict[str, Any]:
    """
    Validate proposal approval response structure.
    
    Args:
        response: HTTP response from approval API
        
    Returns:
        Response JSON data
        
    Raises:
        AssertionError: If response doesn't match expected structure
    """
    assert response.status_code == 200, f"Expected status 200, got {response.status_code}"
    
    data = response.json()
    
    assert "proposal_id" in data, "Approval response missing proposal_id"
    assert "approved_at" in data, "Approval response missing approved_at"
    assert "message" in data, "Approval response missing message"
    
    return data


def assert_rejection_response_valid(response: Response) -> Dict[str, Any]:
    """
    Validate proposal rejection response structure.
    
    Args:
        response: HTTP response from rejection API
        
    Returns:
        Response JSON data
        
    Raises:
        AssertionError: If response doesn't match expected structure
    """
    assert response.status_code == 200, f"Expected status 200, got {response.status_code}"
    
    data = response.json()
    
    assert "proposal_id" in data, "Rejection response missing proposal_id"
    assert "message" in data, "Rejection response missing message"
    
    return data