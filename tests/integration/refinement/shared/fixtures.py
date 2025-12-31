"""
Reusable test fixtures for refinement integration tests.

Provides standardized test setup, data, and context management
to ensure consistent test environments across all refinement tests.
"""

import pytest
import time
import uuid
import psycopg
from psycopg.rows import dict_row
from typing import Dict, Any, Tuple, NamedTuple

from api.dependencies import get_database_url
from services.workflow_service import WorkflowService
from services.proposal_service import ProposalService
from services.draft_service import DraftService
from core.jwt_manager import JWTManager


class RefinementTestContext(NamedTuple):
    """Complete test context for refinement tests."""
    user_id: str
    token: str
    database_url: str
    workflow_service: WorkflowService
    proposal_service: ProposalService
    draft_service: DraftService


@pytest.fixture
async def refinement_test_context(jwt_manager: JWTManager, mock_deepagents_server) -> RefinementTestContext:
    """
    Complete test context with user, services, and token.
    
    Creates a test user and initializes all production services
    using the same dependency injection as production code.
    """
    # Set the mock deepagents server URL for this test
    import os
    os.environ["DEEPAGENTS_RUNTIME_URL"] = mock_deepagents_server
    print(f"[DEBUG] Set DEEPAGENTS_RUNTIME_URL to: {mock_deepagents_server}")
    
    # Use production dependency injection
    database_url = get_database_url()
    workflow_service = WorkflowService(database_url)
    proposal_service = ProposalService(database_url)
    draft_service = DraftService(database_url)
    
    # Create test user with unique email
    user_email = f"refinement-test-{int(time.time() * 1000000)}@example.com"
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, hashed_password, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                ("Refinement Test User", user_email, "hashed-password")
            )
            user_result = cur.fetchone()
            user_id = str(user_result["id"])
    
    # Generate JWT token
    token = await jwt_manager.generate_token(user_id, user_email, [], 24 * 3600)
    
    return RefinementTestContext(
        user_id=user_id,
        token=token,
        database_url=database_url,
        workflow_service=workflow_service,
        proposal_service=proposal_service,
        draft_service=draft_service
    )


@pytest.fixture
def sample_initial_draft_content() -> Dict[str, str]:
    """Standard initial draft content for tests."""
    return {
        "main.py": "print('initial version')",
        "config.json": '{"version": "1.0", "debug": false}'
    }


@pytest.fixture
def sample_enhanced_draft_content() -> Dict[str, str]:
    """Enhanced draft content for approval tests."""
    return {
        "main.py": """import logging
import sys

def main():
    try:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        
        logger.info("Starting application")
        print('enhanced version with error handling')
        logger.info("Application completed successfully")
        
    except Exception as e:
        logger.error(f"Application failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()""",
        "config.json": '{"version": "2.0", "debug": false, "logging": {"level": "INFO"}}'
    }


@pytest.fixture
def sample_generated_files_approved() -> Dict[str, Any]:
    """Standard generated files for approved proposal completion."""
    return {
        "main.py": {
            "content": """import logging
import sys

def main():
    try:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        
        logger.info("Starting application")
        print('enhanced version with error handling')
        logger.info("Application completed successfully")
        
    except Exception as e:
        logger.error(f"Application failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()""",
            "type": "markdown"
        },
        "config.json": {
            "content": '{"version": "2.0", "debug": false, "logging": {"level": "INFO"}}',
            "type": "json"
        }
    }


@pytest.fixture
def sample_generated_files_rejected() -> Dict[str, Any]:
    """Standard generated files for rejected proposal completion."""
    return {
        "main.py": {
            "content": """from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)

def main():
    print('Hello World with Database!')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()""",
            "type": "markdown"
        },
        "config.json": {
            "content": '{"version": "2.0", "database": {"uri": "sqlite:///app.db"}}',
            "type": "json"
        }
    }


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