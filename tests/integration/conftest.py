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


@pytest.fixture(scope="session")
def mock_deepagents_server():
    """
    Start and provide mock deepagents-runtime server.
    
    Starts the mock server in a separate process and returns the URL.
    """
    import subprocess
    import time
    import requests
    from pathlib import Path
    
    # Check for mock URL override
    mock_url = os.getenv("MOCK_SPEC_ENGINE_URL")
    if mock_url:
        return mock_url
    
    # Start mock server
    mock_port = 8001
    mock_url = f"http://localhost:{mock_port}"
    
    # Path to mock server script
    mock_script = Path(__file__).parent.parent / "mock" / "deepagents_mock.py"
    
    # Start mock server process
    process = subprocess.Popen([
        "python", "-c", 
        f"""
import sys
sys.path.append('{Path(__file__).parent.parent}')
from mock.deepagents_mock import create_mock_server
server = create_mock_server()
server.run(host='127.0.0.1', port={mock_port})
"""
    ])
    
    # Wait for server to start
    for _ in range(30):  # Wait up to 30 seconds
        try:
            response = requests.get(f"{mock_url}/state/test", timeout=1)
            if response.status_code == 200:
                break
        except:
            time.sleep(1)
    else:
        process.terminate()
        raise RuntimeError("Mock deepagents server failed to start")
    
    yield mock_url
    
    # Cleanup
    process.terminate()
    process.wait()


@pytest.fixture(scope="function")
def jwt_manager():
    """Provide JWT manager instance for token generation/validation."""
    from core.jwt_manager import JWTManager
    import os
    
    # Set test JWT secret if not already set
    if not os.getenv("JWT_SECRET"):
        os.environ["JWT_SECRET"] = "test-secret-key-for-testing"
    
    return JWTManager()


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
