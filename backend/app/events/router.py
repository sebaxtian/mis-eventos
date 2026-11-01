"""HTTP endpoints for the events domain."""

from fastapi import (
    APIRouter,
    Depends,
    File,
    Path,
    Response,
    UploadFile,
    status,
)
from sqlmodel import Session

from app.core.cache import CacheClient, get_cache_client
from app.core.database import get_session
from app.core.exceptions import error_responses
from app.core.pagination import PaginatedResponse
from app.events.dependencies import (
    get_optional_current_user,
    get_owned_or_admin_event,
    require_event_creator,
)
from app.events.models import Event
from app.events.schemas import (
    EventCreate,
    EventListParams,
    EventRead,
    EventUpdate,
)
from app.events.service import (
    create_event,
    delete_event,
    get_event_for_actor,
    list_events,
    update_event,
    upload_event_image,
)
from app.users.models import User

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get(
    "",
    response_model=PaginatedResponse[EventRead],
    responses=error_responses(401, 403, 422),
)
def read_events(
    params: EventListParams = Depends(),
    actor: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> PaginatedResponse[EventRead]:
    return list_events(session, params, actor, cache)


@router.post(
    "",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 422),
)
def create_event_endpoint(
    payload: EventCreate,
    current_user: User = Depends(require_event_creator),
    session: Session = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> EventRead:
    return create_event(session, payload, current_user, cache)


@router.get(
    "/{event_id}",
    response_model=EventRead,
    responses=error_responses(401, 404, 422),
)
def read_event(
    event_id: int = Path(ge=1),
    actor: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> EventRead:
    return get_event_for_actor(session, event_id, actor, cache)


@router.patch(
    "/{event_id}",
    response_model=EventRead,
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_event_endpoint(
    payload: EventUpdate,
    event: Event = Depends(get_owned_or_admin_event),
    session: Session = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> EventRead:
    return update_event(session, event, payload, cache)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
)
def delete_event_endpoint(
    event: Event = Depends(get_owned_or_admin_event),
    session: Session = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> Response:
    delete_event(session, event, cache)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{event_id}/image",
    response_model=EventRead,
    responses=error_responses(400, 401, 403, 404, 409, 413, 422),
)
async def upload_event_image_endpoint(
    event: Event = Depends(get_owned_or_admin_event),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> EventRead:
    return await upload_event_image(session, event, file, cache)
