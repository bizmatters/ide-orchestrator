"""
Pytest configuration and fixtures for IDE Orchestrator integration tests.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
import os
from pathlib import Path

# Import test helpers
from tests.helpers.database import TestDatabase
from tests.integration.cluster_config import setup_in_cluster_environment
from tests.mock.deepagents_mock import create_mock_server


@pytest.fixture(scope="session")
def cluster_config():
    """Setup in-cluster environment configuration."""
    config = setup_in_cluster_environment()
    print(f"\nUsing infrastructure - Database: {config.database_url}, SpecEngine: {config.spec_engine_url}")
    return config


@pytest.fixture(scope="function")
def test_db():
    """
    Provide test database instance with automatic cleanup.
    
    Uses transaction-based isolation for test data.
    """
    db = TestDatabase()
    yield db
    db.close()


@pytest_asyncio.fixture(scope="function")
async def test_client(app):
    """
    Provide async HTTP test client.
    
    Args:
        app: FastAPI application instance
        
    Yields:
        AsyncClient for making HTTP requests
    """
    from httpx import ASGITransport
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def mock_deepagents_server():
    """
    Start and provide in-process mock deepagents-runtime server.
    
    This follows the integration testing pattern by providing HTTP endpoints
    that the production WebSocket proxy connects to.
    """
    from tests.integration.refinement.shared.mock_helpers import create_mock_deepagents_server
    
    # Create and start mock server
    mock_server = create_mock_deepagents_server("approved")
    await mock_server.start()
    
    yield f"http://127.0.0.1:{mock_server.http_port}"
    
    # Cleanup
    await mock_server.stop()


@pytest.fixture(scope="function")
def app():
    """Provide FastAPI application instance."""
    from api.main import app
    return app


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
