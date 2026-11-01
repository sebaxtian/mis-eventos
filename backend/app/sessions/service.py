"""Business services for the sessions domain."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from fastapi.exceptions import RequestValidationError
from redis.exceptions import RedisError
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.core.cache import CacheClient
from app.core.datetime_utils import utc_now
from app.events.models import Event, EventStatus
from app.sessions.models import Session
from app.sessions.schemas import (
    START_BEFORE_END_MESSAGE,
    SessionCreate,
    SessionListRead,
    SessionRead,
    SessionUpdate,
)
from app.users.models import User, UserRole

logger = logging.getLogger(__name__)

CAPACITY_ABOVE_EVENT_DETAIL = (
    "La capacidad de la sesión no puede superar la capacidad total del evento"
)
OUTSIDE_EVENT_WINDOW_DETAIL = (
    "La sesión debe estar dentro de la fecha UTC del evento y no puede "
    "cruzar la medianoche"
)
EVENT_NOT_FOUND_DETAIL = "Evento no encontrado"
SESSION_NOT_FOUND_DETAIL = "Sesión no encontrada"
OVERLAP_DETAIL = "La sesión se solapa con otra sesión del evento"
CANCELLED_EVENT_DETAIL = (
    "Un evento cancelado no permite modificar sus sesiones"
)
SESSION_WITH_REGISTRATIONS_DETAIL = (
    "No se puede eliminar una sesión con asistentes inscritos"
)
CAPACITY_BELOW_REGISTERED_DETAIL = (
    "No se puede reducir la capacidad de la sesión por debajo del número de "
    "inscritos actuales"
)


def _invalidate_events_cache(cache: CacheClient) -> None:
    try:
        cache.invalidate_prefix("events:")
    except RedisError as exc:
        logger.warning(
            "Redis invalidate_prefix failed for 'events:': %s", exc
        )


def _ensure_event_not_cancelled(event: Event) -> None:
    if EventStatus(event.status) == EventStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CANCELLED_EVENT_DETAIL,
        )


def _has_overlap(
    session: DBSession,
    event_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_session_id: int | None = None,
) -> bool:
    statement = select(Session.id).where(
        Session.event_id == event_id,
        Session.start_time < end_time,
        Session.end_time > start_time,
    )
    if exclude_session_id is not None:
        statement = statement.where(Session.id != exclude_session_id)
    return session.exec(statement.limit(1)).first() is not None


def _ensure_no_overlap(
    session: DBSession,
    event_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_session_id: int | None = None,
) -> None:
    if _has_overlap(
        session,
        event_id,
        start_time,
        end_time,
        exclude_session_id=exclude_session_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=OVERLAP_DETAIL,
        )


def _event_window(event: Event) -> tuple[datetime, datetime]:
    event_date = event.date
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    event_date = event_date.astimezone(timezone.utc)
    next_midnight = event_date.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ) + timedelta(days=1)
    return event_date, next_midnight


def _ensure_within_event_window(
    event: Event,
    start_time: datetime,
    end_time: datetime,
) -> None:
    window_start, window_end = _event_window(event)
    if start_time < window_start or end_time > window_end:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=OUTSIDE_EVENT_WINDOW_DETAIL,
        )


def _validation_error(field: str, message: str) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", field),
                "msg": f"Value error, {message}",
                "input": None,
                "ctx": {"error": ValueError(message)},
            }
        ]
    )


def _ensure_capacity_within_event(event: Event, capacity: int) -> None:
    if capacity > event.total_capacity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CAPACITY_ABOVE_EVENT_DETAIL,
        )


def get_session_registered_count(
    session: DBSession,
    session_id: int,
) -> int:
    """Return the number of registrations for a session.

    The ``registrations`` table belongs to a later domain; until it exists the
    count is always zero. The function is module-level so tests can
    monkeypatch it to simulate sessions with attendees.
    """

    return 0


def _can_view_event(event: Event, actor: User | None) -> bool:
    if EventStatus(event.status) == EventStatus.PUBLISHED:
        return True
    if actor is None:
        return False
    role = UserRole(actor.role)
    if role == UserRole.ADMIN:
        return True
    if role == UserRole.ORGANIZER:
        return event.organizer_id == actor.id
    return False


def get_visible_event(
    session: DBSession,
    event_id: int,
    actor: User | None,
) -> Event:
    event = session.get(Event, event_id)
    if event is None or not _can_view_event(event, actor):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EVENT_NOT_FOUND_DETAIL,
        )
    return event


def get_session_for_actor(
    session: DBSession,
    event_id: int,
    session_id: int,
    actor: User | None,
) -> SessionRead:
    event = get_visible_event(session, event_id, actor)
    session_row = session.exec(
        select(Session).where(
            Session.id == session_id,
            Session.event_id == event.id,
        )
    ).first()
    if session_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=SESSION_NOT_FOUND_DETAIL,
        )
    return to_session_read(
        session_row,
        get_session_registered_count(session, session_row.id or 0),
    )


def list_sessions(
    session: DBSession,
    event_id: int,
    actor: User | None,
) -> SessionListRead:
    event = get_visible_event(session, event_id, actor)
    rows = session.exec(
        select(Session)
        .where(Session.event_id == event.id)
        .order_by(Session.start_time.asc(), Session.id.asc())
    ).all()
    items = [
        to_session_read(
            row,
            get_session_registered_count(session, row.id or 0),
        )
        for row in rows
    ]
    return SessionListRead(items=items, total=len(items))


def to_session_read(
    session_row: Session,
    registered_count: int,
) -> SessionRead:
    return SessionRead(
        id=session_row.id or 0,
        event_id=session_row.event_id,
        title=session_row.title,
        description=session_row.description,
        speaker=session_row.speaker,
        start_time=session_row.start_time,
        end_time=session_row.end_time,
        capacity=session_row.capacity,
        registered_count=registered_count,
        available_capacity=max(0, session_row.capacity - registered_count),
        created_at=session_row.created_at,
        updated_at=session_row.updated_at,
    )


def _lock_event(session: DBSession, event_id: int) -> Event:
    statement = (
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    event = session.exec(statement).first()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EVENT_NOT_FOUND_DETAIL,
        )
    return event


def create_session(
    session: DBSession,
    event: Event,
    payload: SessionCreate,
    cache: CacheClient,
) -> SessionRead:
    try:
        locked_event = _lock_event(session, event.id or 0)
        _ensure_event_not_cancelled(locked_event)
        _ensure_within_event_window(
            locked_event,
            payload.start_time,
            payload.end_time,
        )
        _ensure_capacity_within_event(locked_event, payload.capacity)
        _ensure_no_overlap(
            session,
            locked_event.id or 0,
            payload.start_time,
            payload.end_time,
        )
        now = utc_now()
        session_row = Session(
            event_id=locked_event.id or 0,
            title=payload.title,
            speaker=payload.speaker,
            description=payload.description,
            start_time=payload.start_time,
            end_time=payload.end_time,
            capacity=payload.capacity,
            created_at=now,
            updated_at=now,
        )
        session.add(session_row)
        session.commit()
        session.refresh(session_row)
    except HTTPException:
        session.rollback()
        raise
    _invalidate_events_cache(cache)
    return to_session_read(
        session_row,
        get_session_registered_count(session, session_row.id or 0),
    )


def update_session(
    session: DBSession,
    session_row: Session,
    payload: SessionUpdate,
    cache: CacheClient,
) -> SessionRead:
    changes = payload.model_dump(exclude_unset=True)
    start_time = (
        payload.start_time
        if payload.start_time is not None
        else session_row.start_time
    )
    end_time = (
        payload.end_time
        if payload.end_time is not None
        else session_row.end_time
    )
    try:
        locked_event = _lock_event(session, session_row.event_id)
        _ensure_event_not_cancelled(locked_event)
        if start_time >= end_time:
            raise _validation_error("start_time", START_BEFORE_END_MESSAGE)
        _ensure_within_event_window(locked_event, start_time, end_time)
        if payload.capacity is not None:
            _ensure_capacity_within_event(locked_event, payload.capacity)
            if payload.capacity < get_session_registered_count(
                session,
                session_row.id or 0,
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=CAPACITY_BELOW_REGISTERED_DETAIL,
                )
        _ensure_no_overlap(
            session,
            locked_event.id or 0,
            start_time,
            end_time,
            exclude_session_id=session_row.id,
        )
        for field, value in changes.items():
            setattr(session_row, field, value)
        session_row.updated_at = utc_now()
        session.add(session_row)
        session.commit()
        session.refresh(session_row)
    except HTTPException:
        session.rollback()
        raise
    _invalidate_events_cache(cache)
    return to_session_read(
        session_row,
        get_session_registered_count(session, session_row.id or 0),
    )


def delete_session(
    session: DBSession,
    session_row: Session,
    cache: CacheClient,
) -> None:
    try:
        locked_event = _lock_event(session, session_row.event_id)
        _ensure_event_not_cancelled(locked_event)
        if get_session_registered_count(session, session_row.id or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=SESSION_WITH_REGISTRATIONS_DETAIL,
            )
        session.delete(session_row)
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    _invalidate_events_cache(cache)
