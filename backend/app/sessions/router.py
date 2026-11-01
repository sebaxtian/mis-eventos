"""HTTP endpoints for the sessions domain."""

from fastapi import APIRouter, Depends, Path, Response, status
from sqlmodel import Session as DBSession

from app.core.cache import CacheClient, get_cache_client
from app.core.database import get_session
from app.core.exceptions import error_responses
from app.events.dependencies import get_optional_current_user
from app.events.models import Event
from app.sessions.dependencies import (
    get_owned_event_for_create,
    get_session_in_event,
)
from app.sessions.models import Session
from app.sessions.schemas import (
    SessionCreate,
    SessionListRead,
    SessionRead,
    SessionUpdate,
)
from app.sessions.service import (
    create_session,
    delete_session,
    get_session_for_actor,
    list_sessions,
    update_session,
)
from app.users.models import User

router = APIRouter(prefix="/api/events", tags=["sessions"])


@router.get(
    "/{event_id}/sessions",
    response_model=SessionListRead,
    responses=error_responses(401, 403, 404, 409, 422),
)
def read_sessions(
    event_id: int = Path(ge=1),
    actor: User | None = Depends(get_optional_current_user),
    db: DBSession = Depends(get_session),
) -> SessionListRead:
    return list_sessions(db, event_id, actor)


@router.get(
    "/{event_id}/sessions/{session_id}",
    response_model=SessionRead,
    responses=error_responses(401, 403, 404, 409, 422),
)
def read_session(
    event_id: int = Path(ge=1),
    session_id: int = Path(ge=1),
    actor: User | None = Depends(get_optional_current_user),
    db: DBSession = Depends(get_session),
) -> SessionRead:
    return get_session_for_actor(db, event_id, session_id, actor)


@router.post(
    "/{event_id}/sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_session_endpoint(
    payload: SessionCreate,
    event: Event = Depends(get_owned_event_for_create),
    db: DBSession = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> SessionRead:
    return create_session(db, event, payload, cache)


@router.patch(
    "/{event_id}/sessions/{session_id}",
    response_model=SessionRead,
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_session_endpoint(
    payload: SessionUpdate,
    session_row: Session = Depends(get_session_in_event),
    db: DBSession = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> SessionRead:
    return update_session(db, session_row, payload, cache)


@router.delete(
    "/{event_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422),
)
def delete_session_endpoint(
    session_row: Session = Depends(get_session_in_event),
    db: DBSession = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> Response:
    delete_session(db, session_row, cache)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
