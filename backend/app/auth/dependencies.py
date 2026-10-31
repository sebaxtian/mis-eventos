"""FastAPI authentication and authorization dependency chain."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.auth.security import InvalidAccessTokenError, decode_access_token
from app.core.database import get_session
from app.users.models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")


def _unauthorized_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado o sesión expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise _unauthorized_exception()

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (InvalidAccessTokenError, KeyError, TypeError, ValueError) as exc:
        raise _unauthorized_exception() from exc

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized_exception()
    user.role = UserRole(user.role)
    return user


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    allowed_roles = set(roles)

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if UserRole(current_user.role) not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta acción",
            )
        return current_user

    return _dependency


require_admin = require_roles(UserRole.ADMIN)
