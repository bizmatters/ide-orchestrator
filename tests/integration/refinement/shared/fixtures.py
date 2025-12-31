"""
Reusable test fixtures for refinement integration tests.

Provides standardized test setup, data, and context management
to ensure consistent test environments across all refinement tests.
"""

import pytest
import uuid
from typing import Dict, Any

from core.jwt_manager import JWTManager


@pytest.fixture
async def test_user_token(jwt_manager: JWTManager) -> tuple[str, str]:
    """
    Create authenticated test user following production authentication pattern.
    
    Returns:
        Tuple of (user_id, jwt_token)
    """
    # Create test user with proper UUID format
    user_id = str(uuid.uuid4())
    token = await jwt_manager.generate_token(
        user_id=user_id,
        username=f"testuser-{user_id}",
        roles=["user"],
        duration_seconds=3600
    )
    
    return user_id, token


@pytest.fixture
def sample_initial_draft_content() -> Dict[str, str]:
    """Standard initial draft content for tests - matches real deepagents workflow structure."""
    return {
        "/user_request.md": "Create a simple hello world agent that greets users",
        "/orchestrator_plan.md": "# Initial Plan\nBasic orchestrator plan for hello world agent.",
        "/guardrail_assessment.md": "# Initial Guardrail Assessment\nBasic safety assessment.",
        "/impact_assessment.md": "# Initial Impact Assessment\nBasic impact analysis.",
        "/THE_SPEC/constitution.md": "# Initial Constitution\nBasic constitutional principles.",
        "/THE_SPEC/requirements.md": "# Initial Requirements\nBasic input schema requirements.",
        "/THE_SPEC/plan.md": "# Initial Plan\nBasic execution flow.",
        "/THE_CAST/OrchestratorAgent.md": "# Initial Orchestrator\nBasic orchestrator agent.",
        "/THE_CAST/GreetingAgent.md": "# Initial Greeting Agent\nBasic greeting agent.",
        "/definition.json": '{"name": "InitialWorkflow", "version": "0.1.0"}'
    }


@pytest.fixture
def sample_generated_files_approved() -> Dict[str, Any]:
    """Standard generated files for approved proposal completion - loaded from real test data."""
    from pathlib import Path
    import json
    
    testdata_dir = Path(__file__).parent.parent.parent.parent / "testdata"
    state_path = testdata_dir / "thread_state.json"
    
    with open(state_path, 'r') as f:
        state_data = json.load(f)
    
    return state_data.get("generated_files", {})


@pytest.fixture
def sample_generated_files_rejected() -> Dict[str, Any]:
    """Standard generated files for rejected proposal completion - loaded from real test data."""
    from pathlib import Path
    import json
    
    testdata_dir = Path(__file__).parent.parent.parent.parent / "testdata"
    state_path = testdata_dir / "rejection_state.json"
    
    with open(state_path, 'r') as f:
        state_data = json.load(f)
    
    return state_data.get("generated_files", {})


@pytest.fixture
def sample_refinement_request_approved() -> Dict[str, Any]:
    """Standard refinement request for approval tests."""
    return {
        "instructions": "Add error handling and logging to the main function",
        "context_file_path": "/main.py",
        "context_selection": "Improve code quality and debugging capabilities"
    }


@pytest.fixture
def sample_refinement_request_rejected() -> Dict[str, Any]:
    """Standard refinement request for rejection tests."""
    return {
        "instructions": "Add database integration with SQLAlchemy",
        "context_file_path": "/config.json", 
        "context_selection": "Need to persist data in a database"
    }