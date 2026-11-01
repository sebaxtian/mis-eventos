"""FastAPI dependencies for the registrations domain."""

from fastapi import Depends, HTTPException, Path, status
from sqlmodel import Session as DBSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.database import get_session
from app.events.models import Event
from app.registrations.models import Registration
from app.registrations.service import REGISTRATION_NOT_FOUND_DETAIL
from app.users.models import User, UserRole

require_attendee = require_roles(UserRole.ATTENDEE)
require_event_manager = require_roles(UserRole.ORGANIZER, UserRole.ADMIN)


def get_owned_event_for_organizer(
    event_id: int = Path(ge=1),
    current_user: User = Depends(require_event_manager),
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


def get_registration_for_actor(
    id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_session),
) -> Registration:
    registration = db.get(Registration, id)
    if registration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=REGISTRATION_NOT_FOUND_DETAIL,
        )
    event = db.get(Event, registration.event_id)
    role = UserRole(current_user.role)
    is_admin = role == UserRole.ADMIN
    is_event_owner = (
        role == UserRole.ORGANIZER
        and event is not None
        and event.organizer_id == current_user.id
    )
    if not (
        is_admin
        or is_event_owner
        or registration.user_id == current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=REGISTRATION_NOT_FOUND_DETAIL,
        )
    return registration
