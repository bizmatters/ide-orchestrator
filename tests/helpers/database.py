"""
Database helper utilities for testing.

Provides database connection management, test data creation,
and transaction-based test isolation.
"""

import os
from contextlib import contextmanager
from typing import Optional, Dict, Any
import psycopg
from psycopg.rows import dict_row
import bcrypt


def build_database_url() -> str:
    """Use DATABASE_URL from environment variables."""
    return os.getenv("DATABASE_URL")


class TestDatabase:
    """Test database utilities with transaction-based isolation."""
    
    def __init__(self):
        """Initialize test database connection."""
        self.database_url = build_database_url()
        self.conn: Optional[psycopg.Connection] = None
    
    def connect(self) -> psycopg.Connection:
        """Create database connection."""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(self.database_url, row_factory=dict_row)
        return self.conn
    
    def close(self):
        """Close database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()
    
    @contextmanager
    def transaction(self):
        """
        Context manager for transaction-based test isolation.
        
        Usage:
            with test_db.transaction():
                # Test operations here
                # Automatically rolled back after test
        """
        conn = self.connect()
        with conn.transaction():
            try:
                yield conn
            finally:
                # Transaction automatically rolled back on context exit
                pass
    
    def create_test_user(self, email: str, password: str) -> str:
        """
        Create a test user and return user ID.
        
        Args:
            email: User email
            password: User password (will be hashed)
            
        Returns:
            User ID (UUID string)
        """
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, hashed_password, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                ("Test User", email, password)
            )
            result = cur.fetchone()
            conn.commit()
            # Convert UUID to string for consistent test comparisons
            return str(result["id"])
    
    def create_test_workflow(self, user_id: str, name: str, description: str) -> str:
        """
        Create a test workflow and return workflow ID.
        
        Args:
            user_id: User ID who owns the workflow
            name: Workflow name
            description: Workflow description
            
        Returns:
            Workflow ID (UUID string)
        """
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflows (created_by_user_id, name, description, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (user_id, name, description)
            )
            result = cur.fetchone()
            conn.commit()
            # Convert UUID to string for consistent test comparisons
            return str(result["id"])
    
    def create_test_draft(self, workflow_id: str, specification: str) -> str:
        """
        Create a test draft and return draft ID.
        
        Args:
            workflow_id: Workflow ID
            specification: Draft specification (JSON string)
            
        Returns:
            Draft ID (UUID string)
        """
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO drafts (workflow_id, specification, created_at, updated_at)
                VALUES (%s, %s, NOW(), NOW())
                RETURNING id
                """,
                (workflow_id, specification)
            )
            result = cur.fetchone()
            conn.commit()
            # Convert UUID to string for consistent test comparisons
            return str(result["id"])
    
    def get_workflow_count(self) -> int:
        """Get total number of workflows."""
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM workflows")
            result = cur.fetchone()
            return result["count"]
    
    def get_user_count(self) -> int:
        """Get total number of users."""
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM users")
            result = cur.fetchone()
            return result["count"]
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password string
        """
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        return hashed.decode('utf-8')


def wait_for_database(max_attempts: int = 10) -> bool:
    """
    Wait for database to be ready.
    
    Args:
        max_attempts: Maximum connection attempts
        
    Returns:
        True if database is ready, False otherwise
    """
    import time
    
    for attempt in range(max_attempts):
        try:
            conn = psycopg.connect(build_database_url(), connect_timeout=5)
            conn.close()
            return True
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(1)
    
    return False
