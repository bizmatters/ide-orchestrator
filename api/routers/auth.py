"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer

from models.auth import LoginRequest, LoginResponse
from services.auth_service import AuthService
from core.jwt_manager import JWTManager
from api.dependencies import get_auth_service, get_jwt_manager

router = APIRouter(prefix="/api/auth", tags=["authentication"])
security = HTTPBearer()


@router.post("/login", response_model=LoginResponse)
async def login(
    login_request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
    jwt_manager: JWTManager = Depends(get_jwt_manager),
):
    """Login endpoint."""
    user = auth_service.authenticate_user(login_request.email, login_request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    token = await jwt_manager.generate_token(
        user_id=user["id"], username=user["email"], roles=[], duration_seconds=24 * 3600
    )

    return LoginResponse(token=token, user_id=user["id"])