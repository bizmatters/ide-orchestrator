"""
Comprehensive JWT validation integration tests.

Consolidates all JWT token validation tests including token generation,
validation, edge cases, and authentication flow tests.
"""

import pytest
from httpx import AsyncClient
import time
import asyncio


@pytest.mark.asyncio
async def test_basic_token_generation_and_validation(test_db, jwt_manager):
    """Test basic JWT token generation and validation."""
    user_email = f"jwt-basic-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    # Generate token
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    assert token is not None
    assert len(token) > 0
    
    # Validate token
    claims = await jwt_manager.validate_token(token)
    assert claims["user_id"] == user_id
    assert claims["username"] == user_email
    assert claims["exp"] > time.time()


@pytest.mark.asyncio
async def test_token_with_roles(test_db, jwt_manager):
    """Test JWT token with roles."""
    user_email = f"jwt-roles-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    roles = ["admin", "user", "editor"]
    token = await jwt_manager.generate_token(user_id, user_email, roles, 24 * 3600)
    
    claims = await jwt_manager.validate_token(token)
    assert claims["roles"] == roles


@pytest.mark.asyncio
async def test_empty_user_id(jwt_manager):
    """Test JWT generation with empty user ID."""
    token = await jwt_manager.generate_token("", "test@example.com", [], 24 * 3600)
    
    # Should either fail or generate token with empty user ID
    if token:
        claims = await jwt_manager.validate_token(token)
        assert claims["user_id"] == ""


@pytest.mark.asyncio
async def test_empty_username(test_db, jwt_manager):
    """Test JWT generation with empty username."""
    user_email = f"jwt-empty-username-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    token = await jwt_manager.generate_token(user_id, "", [], 24 * 3600)
    
    # Should either fail or generate token with empty username
    if token:
        claims = await jwt_manager.validate_token(token)
        assert claims["username"] == ""


@pytest.mark.asyncio
async def test_special_characters_in_claims(test_db, jwt_manager):
    """Test JWT with special characters."""
    user_email = f"jwt-special-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    special_username = "user!@#$%^&*()_+-=[]{}|;':\",./<>?"
    token = await jwt_manager.generate_token(user_id, special_username, [], 24 * 3600)
    
    claims = await jwt_manager.validate_token(token)
    assert claims["username"] == special_username


@pytest.mark.asyncio
async def test_very_long_claims(test_db, jwt_manager):
    """Test JWT with very long user ID and username (1000+ chars)."""
    user_email = f"jwt-long-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    long_username = "a" * 1000 + "@example.com"
    token = await jwt_manager.generate_token(user_id, long_username, [], 24 * 3600)
    
    claims = await jwt_manager.validate_token(token)
    assert claims["username"] == long_username


@pytest.mark.asyncio
async def test_unicode_characters_in_claims(test_db, jwt_manager):
    """Test JWT with unicode characters."""
    user_email = f"jwt-unicode-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    unicode_username = "用户名@例子.com"
    token = await jwt_manager.generate_token(user_id, unicode_username, [], 24 * 3600)
    
    claims = await jwt_manager.validate_token(token)
    assert claims["username"] == unicode_username


@pytest.mark.asyncio
async def test_expired_token_handling(test_client: AsyncClient, test_db, jwt_manager):
    """Test expired token handling."""
    user_email = f"jwt-expired-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    # Generate token with very short expiration (1 millisecond)
    token = await jwt_manager.generate_token(user_id, user_email, [], 0.001)
    
    # Wait for token to expire
    await asyncio.sleep(0.01)
    
    # Try to use expired token
    response = await test_client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Should be rejected due to expiration
    assert response.status_code == 401
    data = response.json()
    assert "token" in data["detail"].lower() or "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_token_near_expiration(test_client: AsyncClient, test_db, jwt_manager):
    """Test token near expiration."""
    user_email = f"jwt-near-expiry-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    # Generate token with 5 second expiration (enough time to make request)
    token = await jwt_manager.generate_token(user_id, user_email, [], 5)
    
    # Use token immediately - should work
    response = await test_client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [
    "invalid-token",
    "Bearer ",
    "Bearer invalid.jwt.token",
    "NotBearer token",
    "Bearer",
    "Bearer Bearer token",
    "bearer valid-token",
    "Bearer  token",
    "Bearer\ttoken",
    "",
    "   ",
    "Bearer YWJjZGVm",
    "Bearer header.payload",
    "Bearer a.b.c.d",
])
async def test_malformed_token_formats(test_client: AsyncClient, header: str):
    """Test various malformed token formats."""
    headers = {}
    if header:
        headers["Authorization"] = header
    
    response = await test_client.get("/api/protected", headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_authorization_header(test_client: AsyncClient):
    """Test missing authorization header."""
    response = await test_client.get("/api/protected")
    
    assert response.status_code == 401
    data = response.json()
    assert "Missing authorization header" in data["detail"] or "authorization" in data["detail"].lower()


@pytest.mark.asyncio
async def test_public_endpoints_no_auth_required(test_client: AsyncClient):
    """Test public endpoints don't require authentication."""
    response = await test_client.get("/api/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_valid_token_access(test_client: AsyncClient, test_db, jwt_manager):
    """Test valid token access."""
    user_email = f"jwt-valid-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    response = await test_client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["email"] == user_email
    assert data["message"] == "Access granted"


@pytest.mark.asyncio
async def test_token_reuse_validation(test_client: AsyncClient, test_db, jwt_manager):
    """Test token reuse validation - JWT is stateless so should work multiple times."""
    user_email = f"jwt-reuse-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Use the same token multiple times - should work (JWT is stateless)
    for _ in range(5):
        response = await test_client.get(
            "/api/protected",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        assert data["email"] == user_email


@pytest.mark.asyncio
async def test_concurrent_token_usage(test_client: AsyncClient, test_db, jwt_manager):
    """Test concurrent token usage."""
    user_email = f"jwt-concurrent-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    # Make concurrent requests
    async def make_request():
        response = await test_client.get(
            "/api/protected",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.status_code, response.json()
    
    # Execute 10 concurrent requests
    results = await asyncio.gather(*[make_request() for _ in range(10)])
    
    # All should succeed
    for status_code, data in results:
        assert status_code == 200
        assert data["user_id"] == user_id


@pytest.mark.asyncio
async def test_token_claims_extraction_with_workflow_creation(
    test_client: AsyncClient, test_db, jwt_manager
):
    """Test token claims extraction with workflow creation."""
    user_email = f"jwt-claims-{int(time.time() * 1000000)}@example.com"
    user_id = test_db.create_test_user(user_email, "hashed-password")
    
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    workflow_data = {
        "name": "JWT Claims Test Workflow",
        "description": "Testing claims extraction"
    }
    
    response = await test_client.post(
        "/api/workflows",
        json=workflow_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "JWT Claims Test Workflow"
    workflow_id = data["id"]
    
    # Verify workflow is associated with correct user
    conn = test_db.connect()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT created_by_user_id FROM workflows WHERE id = %s",
            (workflow_id,)
        )
        result = cur.fetchone()
        assert str(result["created_by_user_id"]) == user_id


@pytest.mark.asyncio
async def test_user_access_control_own_resources_only(
    test_client: AsyncClient, test_db, jwt_manager
):
    """Test user access control - own resources only."""
    user_email1 = f"jwt-user1-{int(time.time() * 1000000)}@example.com"
    user_id1 = test_db.create_test_user(user_email1, "hashed-password")
    
    user_email2 = f"jwt-user2-{int(time.time() * 1000000)}@example.com"
    user_id2 = test_db.create_test_user(user_email2, "hashed-password")
    
    token1 = await jwt_manager.generate_token(user_id1, user_email1, [], 24 * 3600)
    token2 = await jwt_manager.generate_token(user_id2, user_email2, [], 24 * 3600)
    
    # User 1 creates a workflow
    workflow_data = {
        "name": "User 1 Workflow",
        "description": "Testing access control"
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
    
    # User 2 cannot access User 1's workflow
    response = await test_client.get(
        f"/api/workflows/{workflow_id}",
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_login_integration_with_database(test_client: AsyncClient, test_db):
    """Test login integration with database."""
    user_email = f"jwt-login-{int(time.time() * 1000000)}@example.com"
    test_password = "test-password-123"
    
    hashed_password = test_db.hash_password(test_password)
    user_id = test_db.create_test_user(user_email, hashed_password)
    
    # Test successful login
    login_data = {
        "email": user_email,
        "password": test_password
    }
    
    response = await test_client.post("/api/auth/login", json=login_data)
    
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["user_id"] == user_id
    
    # Test the returned token works
    token = data["token"]
    response = await test_client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_with_wrong_password(test_client: AsyncClient, test_db):
    """Test login with wrong password."""
    user_email = f"jwt-login-fail-{int(time.time() * 1000000)}@example.com"
    test_password = "correct-password"
    
    hashed_password = test_db.hash_password(test_password)
    test_db.create_test_user(user_email, hashed_password)
    
    login_data = {
        "email": user_email,
        "password": "wrong-password"
    }
    
    response = await test_client.post("/api/auth/login", json=login_data)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_with_non_existent_user(test_client: AsyncClient):
    """Test login with non-existent user."""
    login_data = {
        "email": "nonexistent@example.com",
        "password": "any-password"
    }
    
    response = await test_client.post("/api/auth/login", json=login_data)
    assert response.status_code == 401
