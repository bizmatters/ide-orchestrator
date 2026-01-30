"""
Authentication normalization tests for IDE Orchestrator.

These tests verify that the service correctly handles missing authorization
and allows public endpoints without authentication.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_missing_authorization_header(test_client: AsyncClient):
    """Test missing authorization header."""
    response = await test_client.get("/api/protected")
    
    assert response.status_code == 401
    data = response.json()
    assert "Not authenticated" in data["detail"] or "authorization" in data["detail"].lower()


@pytest.mark.asyncio
async def test_public_endpoints_no_auth_required(test_client: AsyncClient):
    """Test public endpoints don't require authentication."""
    response = await test_client.get("/api/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
