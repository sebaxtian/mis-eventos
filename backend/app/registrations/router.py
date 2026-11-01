"""HTTP endpoints for the registrations domain."""

from fastapi import APIRouter, Depends, Path, Response, status
from sqlmodel import Session as DBSession

from app.auth.dependencies import get_current_user
from app.core.cache import CacheClient, get_cache_client
from app.core.database import get_session
from app.core.exceptions import error_responses
from app.events.models import Event
from app.registrations.dependencies import (
    get_owned_event_for_organizer,
    get_registration_for_actor,
    require_attendee,
)
from app.registrations.models import Registration
from app.registrations.schemas import (
    EventRegistrationListParams,
    RegistrationListParams,
    RegistrationListRead,
    RegistrationRead,
)
from app.registrations.service import (
    cancel_registration,
    create_event_registration,
    create_session_registration,
    get_registration_read,
    list_event_registrations,
    list_my_registrations,
)
from app.users.models import User

router = APIRouter(prefix="/api", tags=["registrations"])
events_router = APIRouter(prefix="/api/events", tags=["registrations"])


@events_router.post(
    "/{event_id}/registrations",
    response_model=RegistrationRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        **error_responses(401, 403, 404, 409, 422),
        200: {
            "model": RegistrationRead,
            "description": "Inscripción reactivada",
        },
    },
)
def create_event_registration_endpoint(
    response: Response,
    event_id: int = Path(ge=1),
    current_user: User = Depends(require_attendee),
    db: DBSession = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> RegistrationRead:
    registration, created = create_event_registration(
        db,
        event_id,
        current_user,
        cache,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return registration


@events_router.get(
    "/{event_id}/registrations",
    response_model=RegistrationListRead,
    responses=error_responses(401, 403, 404, 409, 422),
)
def read_event_registrations(
    params: EventRegistrationListParams = Depends(),
    event: Event = Depends(get_owned_event_for_organizer),
    db: DBSession = Depends(get_session),
) -> RegistrationListRead:
    return list_event_registrations(db, event, params)


@router.get(
    "/registrations/me",
    response_model=RegistrationListRead,
    responses=error_responses(401, 403, 404, 409, 422),
)
def read_my_registrations(
    params: RegistrationListParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> RegistrationListRead:
    return list_my_registrations(db, current_user, params, cache)


@router.get(
    "/registrations/{id}",
    response_model=RegistrationRead,
    responses=error_responses(401, 403, 404, 409, 422),
)
def read_registration(
    registration: Registration = Depends(get_registration_for_actor),
    db: DBSession = Depends(get_session),
) -> RegistrationRead:
    return get_registration_read(db, registration)


@router.delete(
    "/registrations/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_registration_endpoint(
    registration: Registration = Depends(get_registration_for_actor),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> Response:
    cancel_registration(db, registration, current_user, cache)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@events_router.post(
    "/{event_id}/sessions/{session_id}/registrations",
    response_model=RegistrationRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        **error_responses(401, 403, 404, 409, 422),
        200: {
            "model": RegistrationRead,
            "description": "Inscripción reactivada",
        },
    },
)
def create_session_registration_endpoint(
    response: Response,
    event_id: int = Path(ge=1),
    session_id: int = Path(ge=1),
    current_user: User = Depends(require_attendee),
    db: DBSession = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> RegistrationRead:
    registration, created = create_session_registration(
        db,
        event_id,
        session_id,
        current_user,
        cache,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return registration
