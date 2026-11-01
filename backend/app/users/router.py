"""User administration HTTP endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlmodel import Session

from app.auth.dependencies import require_admin
from app.core.database import get_session
from app.core.exceptions import error_responses
from app.core.pagination import PaginatedResponse, build_paginated_response
from app.users.models import User
from app.users.schemas import AdminUserUpdateRequest, UserListParams, UserRead
from app.users.service import (
    LastActiveAdminError,
    SelfDeactivationNotAllowedError,
    SelfRoleChangeNotAllowedError,
    UserNotFoundError,
    get_user_by_id,
    list_users,
    update_user_by_admin,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get(
    "",
    response_model=PaginatedResponse[UserRead],
    responses=error_responses(401, 403, 422),
)
def read_users(
    params: UserListParams = Depends(),
    _current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PaginatedResponse[UserRead]:
    users, total = list_users(session, params)
    items = [UserRead.model_validate(u) for u in users]
    return build_paginated_response(items, total, params)


@router.get(
    "/{user_id}",
    response_model=UserRead,
    responses=error_responses(401, 403, 404, 422),
)
def read_user(
    user_id: int = Path(ge=1),
    _current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> UserRead:
    try:
        user = get_user_by_id(session, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        ) from exc
    return UserRead.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def update_user(
    payload: AdminUserUpdateRequest,
    user_id: int = Path(ge=1),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> UserRead:
    try:
        updated = update_user_by_admin(
            session,
            target_user_id=user_id,
            actor=current_user,
            payload=payload,
        )
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        ) from exc
    except SelfRoleChangeNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes cambiar tu propio rol",
        ) from exc
    except SelfDeactivationNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta",
        ) from exc
    except LastActiveAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Debe existir al menos un administrador activo",
        ) from exc
    return UserRead.model_validate(updated)
