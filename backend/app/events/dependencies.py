"""FastAPI dependencies for the events domain."""

from fastapi import Depends, HTTPException, Path, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel import Session

from app.auth.dependencies import bearer_scheme, require_roles
from app.auth.security import InvalidAccessTokenError, decode_access_token
from app.core.database import get_session
from app.events.models import Event
from app.users.models import User, UserRole

require_event_creator = require_roles(UserRole.ORGANIZER, UserRole.ADMIN)


def _unauthorized_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado o sesión expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User | None:
    if credentials is None:
        if request.headers.get("Authorization"):
            raise _unauthorized_exception()
        return None

    if credentials.scheme.lower() != "bearer" or not credentials.credentials:
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


def get_owned_or_admin_event(
    event_id: int = Path(ge=1),
    current_user: User = Depends(require_event_creator),
    session: Session = Depends(get_session),
) -> Event:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado",
        )
    if (
        UserRole(current_user.role) != UserRole.ADMIN
        and event.organizer_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para realizar esta acción",
        )
    return event
