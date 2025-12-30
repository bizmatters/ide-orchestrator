"""Authentication models."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Login request."""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login response."""
    token: str
    user_id: str
