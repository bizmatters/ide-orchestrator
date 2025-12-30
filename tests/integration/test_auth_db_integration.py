"""
Database-specific authentication integration tests.

Tests critical auth validations that require database access.
"""

import pytest
from httpx import AsyncClient
import time


@pytest.mark.asyncio
async def test_database_user_authentication_integration(test_client: AsyncClient, test_db, jwt_manager):
    """Test that database user can access protected endpoints."""
    # Create real user in database
    user_email = f"db-auth-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    # Generate token for real user
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Test that database user can access protected endpoints
    response = await test_client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert str(data["user_id"]) == str(user_id)  # Convert both to strings for comparison
    assert data["email"] == user_email
    assert data["message"] == "Access granted"


@pytest.mark.asyncio
async def test_database_user_workflow_creation(test_client: AsyncClient, test_db, jwt_manager):
    """Test workflow creation with database user context."""
    # Create real user in database
    user_email = f"db-workflow-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    # Generate token for real user
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Create workflow to test database integration with authentication
    workflow_data = {
        "name": "Database Integration Workflow",
        "description": "Testing database integration with authentication"
    }
    
    response = await test_client.post(
        "/api/workflows",
        json=workflow_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Database Integration Workflow"
    workflow_id = data["id"]
    
    # Verify the workflow is associated with the correct user in database
    conn = test_db.connect()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT created_by_user_id FROM workflows WHERE id = %s",
            (workflow_id,)
        )
        result = cur.fetchone()
        assert str(result["created_by_user_id"]) == str(user_id)  # Convert both to strings for comparison


@pytest.mark.asyncio
async def test_database_user_access_control(test_client: AsyncClient, test_db, jwt_manager):
    """Test database-level access control between users."""
    # Create two different users in database
    user_email1 = f"user1-db-{int(time.time() * 1000000)}@example.com"
    user_id1 = test_db.create_test_user(user_email1, "hashed-password")
    
    user_email2 = f"user2-db-{int(time.time() * 1000000)}@example.com"
    user_id2 = test_db.create_test_user(user_email2, "hashed-password")
    
    # Generate tokens for both users
    token1 = await jwt_manager.generate_token(user_id1, user_email1, [], 24 * 3600)
    token2 = await jwt_manager.generate_token(user_id2, user_email2, [], 24 * 3600)
    
    # User 1 creates a workflow
    workflow_data = {
        "name": "User 1 Database Workflow",
        "description": "Testing database-level access control"
    }
    
    response = await test_client.post(
        "/api/workflows",
        json=workflow_data,
        headers={"Authorization": f"Bearer {token1}"}
    )
    
    assert response.status_code == 201
    workflow_id = response.json()["id"]
    
    # User 1 can access their own workflow
    response = await test_client.get(
        f"/api/workflows/{workflow_id}",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    
    # User 2 cannot access User 1's workflow (database-level access control)
    response = await test_client.get(
        f"/api/workflows/{workflow_id}",
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_database_login_integration(test_client: AsyncClient, test_db):
    """Test login integration with database user."""
    # Create real user in database with known password
    user_email = f"login-db-{int(time.time() * 1000000)}@example.com"
    test_password = "test-password-123"
    
    # Hash the password properly for storage
    hashed_password = test_db.hash_password(test_password)
    user_id = test_db.create_test_user(user_email, hashed_password)
    
    # Test successful login with database user
    login_data = {
        "email": user_email,
        "password": test_password
    }
    
    response = await test_client.post("/api/auth/login", json=login_data)
    
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert str(data["user_id"]) == str(user_id)  # Convert both to strings for comparison
    
    # Test the returned token works with database
    token = data["token"]
    response = await test_client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    
    # Test failed login with wrong password
    login_data["password"] = "wrong-password"
    response = await test_client.post("/api/auth/login", json=login_data)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_database_user_session_persistence(test_client: AsyncClient, test_db, jwt_manager):
    """Test that database users maintain session state correctly."""
    # Create user
    user_email = f"session-db-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    # Generate token for real user
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Make multiple requests to verify session persistence
    for _ in range(3):
        response = await test_client.get(
            "/api/protected",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify consistent user identity across requests
        assert str(data["user_id"]) == str(user_id)  # Convert both to strings for comparison
        assert data["email"] == user_email
