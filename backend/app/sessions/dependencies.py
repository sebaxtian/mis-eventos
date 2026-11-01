"""FastAPI dependencies for the sessions domain."""

from fastapi import Depends, HTTPException, Path, status
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.auth.dependencies import require_roles
from app.core.database import get_session
from app.events.models import Event, EventStatus
from app.sessions.models import Session
from app.sessions.service import CANCELLED_EVENT_DETAIL
from app.users.models import User, UserRole

require_session_editor = require_roles(UserRole.ORGANIZER, UserRole.ADMIN)


def _ensure_event_not_cancelled(event: Event) -> None:
    if EventStatus(event.status) == EventStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CANCELLED_EVENT_DETAIL,
        )


def get_owned_event_for_write(
    event_id: int = Path(ge=1),
    current_user: User = Depends(require_session_editor),
    db: DBSession = Depends(get_session),
) -> Event:
    event = db.get(Event, event_id)
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


def get_owned_event_for_create(
    event: Event = Depends(get_owned_event_for_write),
) -> Event:
    _ensure_event_not_cancelled(event)
    return event


def get_session_in_event(
    event_id: int = Path(ge=1),
    session_id: int = Path(ge=1),
    event: Event = Depends(get_owned_event_for_write),
    db: DBSession = Depends(get_session),
) -> Session:
    session_row = db.exec(
        select(Session).where(
            Session.id == session_id,
            Session.event_id == event.id,
        )
    ).first()
    if session_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión no encontrada",
        )
    _ensure_event_not_cancelled(event)
    return session_row
