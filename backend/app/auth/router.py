"""Authentication HTTP endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.auth.security import create_access_token
from app.auth.service import (
    EmailAlreadyExistsError,
    authenticate_user,
    register_user,
)
from app.core.database import get_session
from app.core.exceptions import error_responses
from app.users.models import User
from app.users.schemas import UpdateMeRequest, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(409, 422),
)
def register(
    payload: RegisterRequest,
    session: Session = Depends(get_session),
) -> UserRead:
    try:
        user = register_user(session, payload)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo electrónico",
        ) from exc
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=error_responses(401, 422),
)
def login(
    payload: LoginRequest,
    session: Session = Depends(get_session),
) -> TokenResponse:
    user = authenticate_user(session, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token, expires_in = create_access_token(user)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserRead.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserRead,
    responses=error_responses(401),
)
def read_me(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    return UserRead.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserRead,
    responses=error_responses(401, 422),
)
def update_me(
    payload: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserRead:
    assert payload.full_name is not None
    current_user.full_name = payload.full_name
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return UserRead.model_validate(current_user)
