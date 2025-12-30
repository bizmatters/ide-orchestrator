"""
Workflow lifecycle integration tests.

Tests complete workflow CRUD operations with real infrastructure.
"""

import pytest
from httpx import AsyncClient
import time
import asyncio


@pytest.mark.asyncio
async def test_complete_workflow_lifecycle(test_client: AsyncClient, test_db, jwt_manager):
    """Test complete workflow lifecycle from creation to retrieval."""
    # Create test user with unique email
    user_email = f"test-workflow-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    # Generate JWT token
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Create workflow
    workflow_data = {
        "name": "Test Workflow",
        "description": "Integration test workflow",
        "specification": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"label": "Start Node"}},
                {"id": "end", "type": "end", "data": {"label": "End Node"}}
            ],
            "edges": [
                {"id": "start-to-end", "source": "start", "target": "end"}
            ]
        }
    }
    
    response = await test_client.post(
        "/api/workflows",
        json=workflow_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 201
    create_data = response.json()
    workflow_id = create_data["id"]
    assert create_data["name"] == "Test Workflow"
    assert workflow_id is not None
    
    # Get workflow
    response = await test_client.get(
        f"/api/workflows/{workflow_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    get_data = response.json()
    assert get_data["id"] == workflow_id
    assert get_data["name"] == "Test Workflow"
    assert get_data["description"] == "Integration test workflow"
    
    # Get workflow versions
    response = await test_client.get(
        f"/api/workflows/{workflow_id}/versions",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    versions_data = response.json()
    versions = versions_data["versions"]
    assert len(versions) == 0  # No versions initially (versions created when published)


@pytest.mark.asyncio
async def test_workflow_creation_validation(test_client: AsyncClient, test_db, jwt_manager):
    """Test workflow creation validation."""
    user_email = f"test2-workflow-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Test invalid workflow (missing name)
    invalid_data = {
        "description": "Missing name",
        "specification": {
            "nodes": [],
            "edges": []
        }
    }
    
    response = await test_client.post(
        "/api/workflows",
        json=invalid_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 422
    
    # Test valid complex workflow
    complex_spec = {
        "type": "complex-workflow",
        "nodes": [
            {
                "id": "input",
                "type": "input",
                "data": {
                    "label": "User Input",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        }
                    }
                }
            },
            {
                "id": "analyzer",
                "type": "agent",
                "data": {
                    "agent_name": "Query Analyzer",
                    "prompt": "Analyze the user query and extract key information",
                    "tools": ["text_analysis", "entity_extraction"]
                }
            },
            {
                "id": "processor",
                "type": "agent",
                "data": {
                    "agent_name": "Data Processor",
                    "prompt": "Process the analyzed data and generate insights",
                    "tools": ["data_processing", "insight_generation"]
                }
            },
            {
                "id": "output",
                "type": "output",
                "data": {
                    "label": "Final Output",
                    "format": "json"
                }
            }
        ],
        "edges": [
            {"id": "input-to-analyzer", "source": "input", "target": "analyzer"},
            {"id": "analyzer-to-processor", "source": "analyzer", "target": "processor"},
            {"id": "processor-to-output", "source": "processor", "target": "output"}
        ]
    }
    
    valid_data = {
        "name": "Complex Workflow",
        "description": "A complex multi-node workflow",
        "specification": complex_spec
    }
    
    response = await test_client.post(
        "/api/workflows",
        json=valid_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Complex Workflow"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_authentication_required(test_client: AsyncClient):
    """Test that authentication is required for workflow operations."""
    workflow_data = {
        "name": "Unauthorized Workflow",
        "description": "Should fail",
        "specification": {"nodes": [], "edges": []}
    }
    
    # Test without token
    response = await test_client.post("/api/workflows", json=workflow_data)
    assert response.status_code == 401
    
    # Test with invalid token
    response = await test_client.post(
        "/api/workflows",
        json=workflow_data,
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_workflow_not_found(test_client: AsyncClient, test_db, jwt_manager):
    """Test workflow not found scenario."""
    user_email = f"test3-workflow-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Try to get non-existent workflow (use valid UUID format)
    non_existent_id = "00000000-0000-0000-0000-000000000000"
    response = await test_client.get(
        f"/api/workflows/{non_existent_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # 404 is correct - user can't access non-existent workflow
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workflow_concurrency(test_db):
    """Test concurrent workflow creation."""
    # Create user
    user_email = f"concurrent-workflow-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    # Create multiple workflows concurrently
    async def create_workflow(index: int):
        workflow_id = test_db.create_test_workflow(
            user_id,
            f"Concurrent Workflow {index}",
            f"Workflow created concurrently #{index}"
        )
        return workflow_id
    
    # Execute 10 concurrent workflow creations
    workflow_ids = await asyncio.gather(*[create_workflow(i) for i in range(10)])
    
    # Verify all workflows were created
    assert len(workflow_ids) == 10
    
    # Verify all IDs are unique
    unique_ids = set(workflow_ids)
    assert len(unique_ids) == 10
