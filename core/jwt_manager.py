"""JWT Manager for token generation and validation."""

import os
from datetime import datetime, timedelta
from typing import List, Optional

import jwt
from jwt.exceptions import InvalidTokenError


class JWTClaims:
    """JWT claims structure."""
    
    def __init__(
        self,
        user_id: str,
        username: str,
        roles: List[str],
        exp: datetime,
        iat: datetime,
        nbf: datetime,
        iss: str,
        sub: str,
        jti: str
    ):
        self.user_id = user_id
        self.username = username
        self.roles = roles
        self.exp = exp
        self.iat = iat
        self.nbf = nbf
        self.iss = iss
        self.sub = sub
        self.jti = jti


class JWTManager:
    """Manages JWT token creation and validation."""
    
    def __init__(self, signing_key: Optional[str] = None):
        """Initialize JWT manager with signing key."""
        self.signing_key = signing_key or os.getenv("JWT_SECRET")
        if not self.signing_key:
            raise ValueError("JWT_SECRET environment variable is required")
        
        self.algorithm = "HS256"
        self.key_id = "default"
    
    async def generate_token(
        self,
        user_id: str,
        username: str,
        roles: List[str],
        duration_seconds: int
    ) -> str:
        """Generate a new JWT token."""
        now = datetime.utcnow()
        exp = now + timedelta(seconds=duration_seconds)
        
        # Convert UUID to string if needed
        user_id_str = str(user_id)
        username_str = str(username)
        
        claims = {
            "user_id": user_id_str,
            "username": username_str,
            "roles": roles,
            "exp": exp,
            "iat": now,
            "nbf": now,
            "iss": "agent-ide-orchestrator",
            "sub": user_id_str,
            "jti": f"jwt-{int(now.timestamp())}"
        }
        
        token = jwt.encode(
            claims,
            self.signing_key,
            algorithm=self.algorithm,
            headers={"kid": self.key_id}
        )
        
        return token
    
    async def validate_token(self, token_string: str) -> dict:
        """Validate a JWT token and return claims as dict."""
        try:
            payload = jwt.decode(
                token_string,
                self.signing_key,
                algorithms=[self.algorithm],
                options={"verify_signature": True}
            )
            
            return payload
        except InvalidTokenError as e:
            raise ValueError(f"Invalid token: {str(e)}")
