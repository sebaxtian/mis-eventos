"""Business services for the registrations domain."""

import logging

from fastapi import HTTPException, status
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.core.cache import CacheClient
from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.pagination import build_paginated_response
from app.events.models import Event, EventStatus
from app.registrations.models import Registration, RegistrationStatus
from app.registrations.schemas import (
    RegistrationEventSummary,
    RegistrationListRead,
    RegistrationRead,
    RegistrationSessionSummary,
)
from app.sessions.models import Session
from app.users.models import User

logger = logging.getLogger(__name__)

EVENT_NOT_FOUND_DETAIL = "Evento no encontrado"
SESSION_NOT_FOUND_DETAIL = "Sesión no encontrada"
REGISTRATION_NOT_FOUND_DETAIL = "Inscripción no encontrada"
EVENT_FULL_DETAIL = "No hay cupos disponibles para este evento"
SESSION_FULL_DETAIL = "No hay cupos disponibles para esta sesión"
ALREADY_REGISTERED_EVENT_DETAIL = "Ya estás inscrito en este evento"
ALREADY_REGISTERED_SESSION_DETAIL = "Ya estás inscrito en esta sesión"
EVENT_REGISTRATION_REQUIRED_DETAIL = "Debes inscribirte primero al evento"


def count_active_event_registrations(
    db: DBSession,
    event_id: int,
) -> int:
    statement = (
        select(func.count())
        .select_from(Registration)
        .where(
            Registration.event_id == event_id,
            Registration.session_id.is_(None),
            Registration.status == RegistrationStatus.ACTIVE.value,
        )
    )
    return int(db.exec(statement).one())


def count_active_session_registrations(
    db: DBSession,
    session_id: int,
) -> int:
    statement = (
        select(func.count())
        .select_from(Registration)
        .where(
            Registration.session_id == session_id,
            Registration.status == RegistrationStatus.ACTIVE.value,
        )
    )
    return int(db.exec(statement).one())


def to_registration_read(
    registration: Registration,
    event: Event,
    session_row: Session | None,
) -> RegistrationRead:
    session_summary = None
    if session_row is not None:
        session_summary = RegistrationSessionSummary(
            id=session_row.id or 0,
            title=session_row.title,
            speaker=session_row.speaker,
            start_time=session_row.start_time,
            end_time=session_row.end_time,
        )
    return RegistrationRead(
        id=registration.id or 0,
        user_id=registration.user_id,
        event_id=registration.event_id,
        session_id=registration.session_id,
        status=RegistrationStatus(registration.status),
        event=RegistrationEventSummary(
            id=event.id or 0,
            title=event.title,
            date=event.date,
            status=EventStatus(event.status),
        ),
        session=session_summary,
        created_at=registration.created_at,
        updated_at=registration.updated_at,
    )


def _ensure_event_published(event: Event) -> None:
    if EventStatus(event.status) != EventStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EVENT_NOT_FOUND_DETAIL,
        )


def _lock_event(db: DBSession, event_id: int) -> Event:
    statement = (
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    event = db.exec(statement).first()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EVENT_NOT_FOUND_DETAIL,
        )
    return event


def _ensure_event_capacity(db: DBSession, event: Event) -> None:
    registered = count_active_event_registrations(db, event.id or 0)
    if registered >= event.total_capacity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=EVENT_FULL_DETAIL,
        )


def _lock_session(
    db: DBSession,
    event_id: int,
    session_id: int,
) -> Session:
    statement = (
        select(Session)
        .where(
            Session.id == session_id,
            Session.event_id == event_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    session_row = db.exec(statement).first()
    if session_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=SESSION_NOT_FOUND_DETAIL,
        )
    return session_row


def _ensure_session_capacity(
    db: DBSession,
    session_row: Session,
) -> None:
    registered = count_active_session_registrations(
        db,
        session_row.id or 0,
    )
    if registered >= session_row.capacity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=SESSION_FULL_DETAIL,
        )


def _find_active_event_registration(
    db: DBSession,
    user_id: int,
    event_id: int,
) -> Registration | None:
    statement = select(Registration).where(
        Registration.user_id == user_id,
        Registration.event_id == event_id,
        Registration.session_id.is_(None),
        Registration.status == RegistrationStatus.ACTIVE.value,
    )
    return db.exec(statement).first()


def _find_session_registration(
    db: DBSession,
    user_id: int,
    session_id: int,
) -> Registration | None:
    statement = select(Registration).where(
        Registration.user_id == user_id,
        Registration.session_id == session_id,
    )
    return db.exec(statement).first()


def _cascade_cancel_sessions(
    db: DBSession,
    user_id: int,
    event_id: int,
    now,
) -> None:
    statement = select(Registration).where(
        Registration.user_id == user_id,
        Registration.event_id == event_id,
        Registration.session_id.is_not(None),
        Registration.status == RegistrationStatus.ACTIVE.value,
    )
    for row in db.exec(statement).all():
        row.status = RegistrationStatus.CANCELLED
        row.updated_at = now
        db.add(row)


def cancel_registration(
    db: DBSession,
    registration: Registration,
    actor: User,
    cache: CacheClient,
) -> None:
    try:
        _lock_event(db, registration.event_id)
        if registration.session_id is not None:
            _lock_session(
                db,
                registration.event_id,
                registration.session_id,
            )
        db.refresh(registration)
        if (
            RegistrationStatus(registration.status)
            == RegistrationStatus.CANCELLED
        ):
            db.commit()
            return
        now = utc_now()
        registration.status = RegistrationStatus.CANCELLED
        registration.updated_at = now
        db.add(registration)
        if registration.session_id is None:
            _cascade_cancel_sessions(
                db,
                registration.user_id,
                registration.event_id,
                now,
            )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    _invalidate_registration_cache(cache, registration.user_id)


def _invalidate_registration_cache(
    cache: CacheClient,
    user_id: int,
) -> None:
    for prefix in (f"registrations:me:{user_id}:", "events:"):
        try:
            cache.invalidate_prefix(prefix)
        except RedisError as exc:
            logger.warning(
                "Redis invalidate_prefix failed for '%s': %s",
                prefix,
                exc,
            )


def _me_cache_key(user_id: int, params) -> str:
    status_value = (
        params.status.value if params.status is not None else ""
    )
    event_value = (
        params.event_id if params.event_id is not None else ""
    )
    return (
        f"registrations:me:{user_id}:page={params.page}:size={params.size}:"
        f"status={status_value}:event={event_value}"
    )


def _cache_get(cache: CacheClient, key: str):
    try:
        return cache.get(key)
    except RedisError as exc:
        logger.warning("Redis get failed for key '%s': %s", key, exc)
        return None


def _cache_set(
    cache: CacheClient,
    key: str,
    payload: dict,
) -> None:
    try:
        cache.set(
            key,
            payload,
            ttl_seconds=settings.cache_events_ttl_seconds,
        )
    except RedisError as exc:
        logger.warning("Redis set failed for key '%s': %s", key, exc)


def _paginated_registrations(
    db: DBSession,
    conditions: list,
    params,
) -> RegistrationListRead:
    count_statement = select(func.count()).select_from(Registration)
    for condition in conditions:
        count_statement = count_statement.where(condition)
    total = int(db.exec(count_statement).one())

    statement = (
        select(Registration, Event, Session)
        .join(Event, Event.id == Registration.event_id)
        .outerjoin(Session, Session.id == Registration.session_id)
    )
    for condition in conditions:
        statement = statement.where(condition)
    statement = (
        statement.order_by(
            Registration.created_at.desc(),
            Registration.id.desc(),
        )
        .offset(params.offset)
        .limit(params.size)
    )
    rows = db.exec(statement).all()
    items = [
        to_registration_read(registration, event, session_row)
        for registration, event, session_row in rows
    ]
    base = build_paginated_response(items, total, params)
    return RegistrationListRead(
        items=base.items,
        total=base.total,
        page=base.page,
        size=base.size,
        pages=base.pages,
    )


def list_my_registrations(
    db: DBSession,
    actor: User,
    params,
    cache: CacheClient,
) -> RegistrationListRead:
    cache_key = _me_cache_key(actor.id or 0, params)
    cached = _cache_get(cache, cache_key)
    if isinstance(cached, dict):
        try:
            return RegistrationListRead.model_validate(cached)
        except (ValidationError, ValueError, TypeError):
            logger.warning(
                "Invalid cached registration list payload for '%s'",
                cache_key,
            )

    conditions = [Registration.user_id == actor.id]
    if params.status is not None:
        conditions.append(
            Registration.status == params.status.value
        )
    if params.event_id is not None:
        conditions.append(Registration.event_id == params.event_id)
    response = _paginated_registrations(db, conditions, params)
    _cache_set(cache, cache_key, response.model_dump(mode="json"))
    return response


def list_event_registrations(
    db: DBSession,
    event: Event,
    params,
) -> RegistrationListRead:
    conditions = [
        Registration.event_id == event.id,
        Registration.session_id.is_(None),
    ]
    if params.status is not None:
        conditions.append(
            Registration.status == params.status.value
        )
    return _paginated_registrations(db, conditions, params)


def get_registration_read(
    db: DBSession,
    registration: Registration,
) -> RegistrationRead:
    event = db.get(Event, registration.event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=REGISTRATION_NOT_FOUND_DETAIL,
        )
    session_row = None
    if registration.session_id is not None:
        session_row = db.get(Session, registration.session_id)
    return to_registration_read(registration, event, session_row)


def _find_event_registration(
    db: DBSession,
    user_id: int,
    event_id: int,
) -> Registration | None:
    statement = select(Registration).where(
        Registration.user_id == user_id,
        Registration.event_id == event_id,
        Registration.session_id.is_(None),
    )
    return db.exec(statement).first()


def create_event_registration(
    db: DBSession,
    event_id: int,
    actor: User,
    cache: CacheClient,
) -> tuple[RegistrationRead, bool]:
    try:
        event = _lock_event(db, event_id)
        _ensure_event_published(event)
        existing = _find_event_registration(db, actor.id or 0, event_id)
        if (
            existing is not None
            and RegistrationStatus(existing.status)
            == RegistrationStatus.ACTIVE
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ALREADY_REGISTERED_EVENT_DETAIL,
            )
        _ensure_event_capacity(db, event)
        now = utc_now()
        created = existing is None
        if existing is None:
            registration = Registration(
                user_id=actor.id,
                event_id=event_id,
                session_id=None,
                status=RegistrationStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        else:
            registration = existing
            registration.status = RegistrationStatus.ACTIVE
            registration.updated_at = now
        db.add(registration)
        db.commit()
        db.refresh(registration)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ALREADY_REGISTERED_EVENT_DETAIL,
        ) from exc
    except HTTPException:
        db.rollback()
        raise
    _invalidate_registration_cache(cache, actor.id or 0)
    return to_registration_read(registration, event, None), created


def create_session_registration(
    db: DBSession,
    event_id: int,
    session_id: int,
    actor: User,
    cache: CacheClient,
) -> tuple[RegistrationRead, bool]:
    try:
        event = _lock_event(db, event_id)
        _ensure_event_published(event)
        session_row = _lock_session(db, event_id, session_id)
        if _find_active_event_registration(
            db,
            actor.id or 0,
            event_id,
        ) is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=EVENT_REGISTRATION_REQUIRED_DETAIL,
            )
        existing = _find_session_registration(
            db,
            actor.id or 0,
            session_id,
        )
        if (
            existing is not None
            and RegistrationStatus(existing.status)
            == RegistrationStatus.ACTIVE
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ALREADY_REGISTERED_SESSION_DETAIL,
            )
        _ensure_session_capacity(db, session_row)
        now = utc_now()
        created = existing is None
        if existing is None:
            registration = Registration(
                user_id=actor.id,
                event_id=event_id,
                session_id=session_id,
                status=RegistrationStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        else:
            registration = existing
            registration.status = RegistrationStatus.ACTIVE
            registration.updated_at = now
        db.add(registration)
        db.commit()
        db.refresh(registration)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ALREADY_REGISTERED_SESSION_DETAIL,
        ) from exc
    except HTTPException:
        db.rollback()
        raise
    _invalidate_registration_cache(cache, actor.id or 0)
    return to_registration_read(registration, event, session_row), created
