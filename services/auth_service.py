"""Authentication service for database operations."""

from typing import Optional
import psycopg
from psycopg.rows import dict_row
import bcrypt


class AuthService:
    """Service for authentication database operations."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    
    def authenticate_user(self, email: str, password: str) -> Optional[dict]:
        """Authenticate a user by email and password."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, hashed_password
                    FROM users
                    WHERE email = %s
                    """,
                    (email,)
                )
                user = cur.fetchone()
                
                if not user:
                    return None
                
                if not self.verify_password(password, user["hashed_password"]):
                    return None
                
                # Convert UUID objects to strings for JSON serialization
                result = {
                    "id": str(user["id"]),
                    "email": user["email"]
                }
                return result
