"""Business services for the events domain."""

import logging

from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.core.cache import CacheClient
from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.pagination import PaginatedResponse, build_paginated_response
from app.events.images import (
    build_image_urls,
    decode_and_clean_image,
    delete_event_image_files,
    read_and_validate_image,
    store_event_image_variants,
)
from app.events.models import Event, EventStatus
from app.events.schemas import (
    EventCreate,
    EventListParams,
    EventRead,
    EventUpdate,
)
from app.users.models import User, UserRole

logger = logging.getLogger(__name__)


def escape_like(term: str) -> str:
    return (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def resolve_cache_scope(actor: User | None) -> str:
    if actor is None or UserRole(actor.role) == UserRole.ATTENDEE:
        return "public"
    if UserRole(actor.role) == UserRole.ORGANIZER:
        return f"org:{actor.id}"
    return f"admin:{actor.id}"


def _list_cache_key(scope: str, params: EventListParams) -> str:
    search = params.search or ""
    status_value = params.status.value if params.status else ""
    return (
        f"events:list:scope={scope}:page={params.page}:size={params.size}:"
        f"search={search}:status={status_value}:mine={int(params.mine)}"
    )


def _detail_cache_key(event_id: int, scope: str) -> str:
    return f"events:detail:id={event_id}:scope={scope}"


def _cache_get(cache: CacheClient, key: str):
    try:
        return cache.get(key)
    except RedisError as exc:
        logger.warning("Redis get failed for key '%s': %s", key, exc)
        return None


def _cache_set(cache: CacheClient, key: str, payload: dict) -> None:
    try:
        cache.set(
            key,
            payload,
            ttl_seconds=settings.cache_events_ttl_seconds,
        )
    except RedisError as exc:
        logger.warning("Redis set failed for key '%s': %s", key, exc)


def _invalidate_event_cache(cache: CacheClient) -> None:
    try:
        cache.invalidate_prefix("events:")
    except RedisError as exc:
        logger.warning(
            "Redis invalidate_prefix failed for 'events:': %s", exc
        )


def get_registered_count(session: Session, event_id: int) -> int:
    """Return the number of registrations for an event.

    The ``registrations`` table belongs to a later domain; until it exists the
    count is always zero. The function is intentionally module-level so tests
    can monkeypatch it to simulate events with attendees.
    """

    return 0


def to_event_read(event: Event, registered_count: int) -> EventRead:
    return EventRead(
        id=event.id or 0,
        title=event.title,
        description=event.description,
        date=event.date,
        total_capacity=event.total_capacity,
        registered_count=registered_count,
        available_capacity=max(0, event.total_capacity - registered_count),
        status=EventStatus(event.status),
        organizer_id=event.organizer_id,
        image_urls=build_image_urls(event.image_key),
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def get_event_for_actor(
    session: Session,
    event_id: int,
    actor: User | None,
    cache: CacheClient,
) -> EventRead:
    scope = resolve_cache_scope(actor)
    cache_key = _detail_cache_key(event_id, scope)
    cached = _cache_get(cache, cache_key)
    if isinstance(cached, dict):
        try:
            return EventRead.model_validate(cached)
        except (ValidationError, ValueError, TypeError):
            logger.warning("Invalid cached event payload for '%s'", cache_key)

    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado",
        )
    if event.status != EventStatus.PUBLISHED.value:
        role = UserRole(actor.role) if actor is not None else None
        is_admin = actor is not None and role == UserRole.ADMIN
        is_owner = (
            actor is not None
            and role == UserRole.ORGANIZER
            and event.organizer_id == actor.id
        )
        if not (is_admin or is_owner):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento no encontrado",
            )
    event_read = to_event_read(
        event, get_registered_count(session, event.id or 0)
    )
    _cache_set(cache, cache_key, event_read.model_dump(mode="json"))
    return event_read


def list_events(
    session: Session,
    params: EventListParams,
    actor: User | None,
    cache: CacheClient,
) -> PaginatedResponse[EventRead]:
    role = UserRole(actor.role) if actor is not None else None
    scope = resolve_cache_scope(actor)
    if params.mine:
        if actor is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No autenticado o sesión expirada",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if role == UserRole.ATTENDEE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta acción",
            )
        conditions = [Event.organizer_id == actor.id]
        if params.status is not None:
            conditions.append(Event.status == params.status.value)
        return _list_events_query(session, params, conditions, cache, scope)
    elif role in (None, UserRole.ATTENDEE):
        conditions = [Event.status == EventStatus.PUBLISHED.value]
        if params.status is not None and params.status != EventStatus.PUBLISHED:
            conditions.append(Event.id == -1)
    elif role == UserRole.ORGANIZER:
        conditions = [
            or_(
                Event.status == EventStatus.PUBLISHED.value,
                Event.organizer_id == actor.id,
            )
        ]
        if params.status is not None:
            conditions.append(Event.status == params.status.value)
    else:
        conditions = []
        if params.status is not None:
            conditions.append(Event.status == params.status.value)

    return _list_events_query(session, params, conditions, cache, scope)


def _list_events_query(
    session: Session,
    params: EventListParams,
    conditions: list,
    cache: CacheClient,
    scope: str,
) -> PaginatedResponse[EventRead]:
    cache_key = _list_cache_key(scope, params)
    cached = _cache_get(cache, cache_key)
    if isinstance(cached, dict):
        try:
            return PaginatedResponse[EventRead].model_validate(cached)
        except (ValidationError, ValueError, TypeError):
            logger.warning("Invalid cached list payload for '%s'", cache_key)

    if params.search:
        conditions.append(
            Event.title.ilike(
                f"%{escape_like(params.search)}%",
                escape="\\",
            )
        )

    stmt = select(Event)
    count_stmt = select(func.count()).select_from(Event)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = int(session.exec(count_stmt).one())
    events = list(
        session.exec(
            stmt.order_by(Event.date.asc(), Event.id.asc())
            .offset(params.offset)
            .limit(params.size)
        ).all()
    )
    items = [
        to_event_read(event, get_registered_count(session, event.id or 0))
        for event in events
    ]
    response = build_paginated_response(items, total, params)
    _cache_set(cache, cache_key, response.model_dump(mode="json"))
    return response


def delete_event(
    session: Session,
    event: Event,
    cache: CacheClient,
) -> None:
    if get_registered_count(session, event.id or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se puede eliminar un evento con asistentes inscritos; "
                "cancélalo en su lugar"
            ),
        )
    image_key = event.image_key
    session.delete(event)
    session.commit()
    if image_key:
        delete_event_image_files(image_key)
    _invalidate_event_cache(cache)


def _ensure_not_cancelled(event: Event) -> None:
    if event.status == EventStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un evento cancelado no puede cambiar de estado ni editarse",
        )


async def upload_event_image(
    session: Session,
    event: Event,
    upload: UploadFile,
    cache: CacheClient,
) -> EventRead:
    _ensure_not_cancelled(event)
    old_key = event.image_key
    raw = await read_and_validate_image(upload)
    clean = decode_and_clean_image(raw)
    new_key = store_event_image_variants(clean)
    event.image_key = new_key
    event.updated_at = utc_now()
    session.add(event)
    session.commit()
    session.refresh(event)
    if old_key:
        delete_event_image_files(old_key)
    _invalidate_event_cache(cache)
    return to_event_read(
        event, get_registered_count(session, event.id or 0)
    )


def update_event(
    session: Session,
    event: Event,
    payload: EventUpdate,
    cache: CacheClient,
) -> EventRead:
    _ensure_not_cancelled(event)
    changes = payload.model_dump(exclude_unset=True)
    new_status: EventStatus | None = None
    if payload.status is not None:
        new_status = EventStatus(payload.status)
        if (
            event.status == EventStatus.PUBLISHED
            and new_status == EventStatus.DRAFT
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede regresar un evento publicado a borrador",
            )
    registered_count = get_registered_count(session, event.id or 0)
    if (
        payload.total_capacity is not None
        and payload.total_capacity < registered_count
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se puede reducir la capacidad total por debajo del "
                "número de inscritos actuales"
            ),
        )
    for field, value in changes.items():
        if field == "status":
            continue
        setattr(event, field, value)
    if new_status is not None:
        event.status = new_status
    event.updated_at = utc_now()
    session.add(event)
    session.commit()
    session.refresh(event)
    _invalidate_event_cache(cache)
    return to_event_read(event, registered_count)


def create_event(
    session: Session,
    payload: EventCreate,
    actor: User,
    cache: CacheClient,
) -> EventRead:
    event = Event(
        organizer_id=actor.id,
        title=payload.title,
        description=payload.description,
        date=payload.date,
        total_capacity=payload.total_capacity,
        status=EventStatus(payload.status),
        updated_at=utc_now(),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    _invalidate_event_cache(cache)
    return to_event_read(event, get_registered_count(session, event.id or 0))
