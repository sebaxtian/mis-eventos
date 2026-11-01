"""TDD tests for the registrations domain (REG-AC-01..34)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.auth.security import create_access_token, hash_password
from app.core.cache import get_cache_client
from app.core.config import settings
from app.events.models import Event, EventStatus
from app.main import app
from app.registrations.models import Registration, RegistrationStatus
from app.registrations.service import (
    count_active_event_registrations,
    count_active_session_registrations,
    create_event_registration,
    create_session_registration,
)
from app.sessions.models import Session as SessionModel
from app.users.models import User, UserRole

EVENT_DATE = datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc)


class _NoCache:
    """Cache stub that never stores anything, so reads hit PostgreSQL."""

    def get(self, key: str):
        return None

    def set(self, key: str, value, ttl_seconds: int = 60) -> bool:
        return True

    def invalidate_prefix(self, prefix: str) -> bool:
        return True


@pytest.fixture()
def client_no_cache(client: TestClient):
    app.dependency_overrides[get_cache_client] = lambda: _NoCache()
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_cache_client, None)


def _create_user(
    session: DBSession,
    *,
    email: str,
    full_name: str = "Usuario Test",
    role: UserRole = UserRole.ATTENDEE,
    is_active: bool = True,
    password: str = "Test1234!",
) -> User:
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token, _ = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _create_event(
    session: DBSession,
    *,
    organizer: User,
    title: str = "Evento de prueba",
    description: str = "Descripción suficientemente larga.",
    date: datetime | None = None,
    total_capacity: int = 100,
    status: EventStatus = EventStatus.PUBLISHED,
) -> Event:
    event = Event(
        organizer_id=organizer.id,
        title=title,
        description=description,
        date=date or EVENT_DATE,
        total_capacity=total_capacity,
        status=status,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _create_session_row(
    session: DBSession,
    *,
    event: Event,
    title: str = "Apertura y bienvenida",
    speaker: str = "Ana Torres",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    capacity: int = 20,
) -> SessionModel:
    session_row = SessionModel(
        event_id=event.id,
        title=title,
        speaker=speaker,
        description=None,
        start_time=start_time or datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc),
        end_time=end_time or datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc),
        capacity=capacity,
    )
    session.add(session_row)
    session.commit()
    session.refresh(session_row)
    return session_row


def _create_registration(
    session: DBSession,
    *,
    user: User,
    event: Event,
    session_row: SessionModel | None = None,
    status: RegistrationStatus = RegistrationStatus.ACTIVE,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Registration:
    registration = Registration(
        user_id=user.id,
        event_id=event.id,
        session_id=session_row.id if session_row is not None else None,
        status=status,
        created_at=created_at or datetime.now(timezone.utc),
        updated_at=updated_at or created_at or datetime.now(timezone.utc),
    )
    session.add(registration)
    session.commit()
    session.refresh(registration)
    return registration


def _count_active_event(session: DBSession, event_id: int) -> int:
    statement = (
        select(func.count())
        .select_from(Registration)
        .where(
            Registration.event_id == event_id,
            Registration.session_id.is_(None),
            Registration.status == RegistrationStatus.ACTIVE.value,
        )
    )
    return int(session.exec(statement).one())


def _count_active_session(session: DBSession, session_id: int) -> int:
    statement = (
        select(func.count())
        .select_from(Registration)
        .where(
            Registration.session_id == session_id,
            Registration.status == RegistrationStatus.ACTIVE.value,
        )
    )
    return int(session.exec(statement).one())


def _count_rows(session: DBSession) -> int:
    return int(
        session.exec(
            select(func.count()).select_from(Registration)
        ).one()
    )


def test_reg_ac_32_migration_creates_registrations_table_with_constraints_and_indexes(
    test_engine,
) -> None:
    inspector = inspect(test_engine)
    assert "registrations" in inspector.get_table_names()

    columns = {
        column["name"]: column
        for column in inspector.get_columns("registrations")
    }
    assert set(columns) == {
        "id",
        "user_id",
        "event_id",
        "session_id",
        "status",
        "created_at",
        "updated_at",
    }
    for name in (
        "user_id",
        "event_id",
        "status",
        "created_at",
        "updated_at",
    ):
        assert columns[name]["nullable"] is False
    assert columns["session_id"]["nullable"] is True
    for name in ("created_at", "updated_at"):
        assert columns[name]["type"].timezone is True
    assert columns["status"]["type"].length == 20

    primary_key = inspector.get_pk_constraint("registrations")
    assert primary_key["constrained_columns"] == ["id"]

    foreign_keys = {
        foreign_key["name"]: foreign_key
        for foreign_key in inspector.get_foreign_keys("registrations")
    }
    assert set(foreign_keys) == {
        "fk_registrations_user_id_users",
        "fk_registrations_event_id_events",
        "fk_registrations_session_id_sessions",
    }
    user_fk = foreign_keys["fk_registrations_user_id_users"]
    assert user_fk["constrained_columns"] == ["user_id"]
    assert user_fk["referred_table"] == "users"
    assert user_fk["referred_columns"] == ["id"]
    assert user_fk["options"].get("ondelete", "").upper() == "RESTRICT"

    event_fk = foreign_keys["fk_registrations_event_id_events"]
    assert event_fk["constrained_columns"] == ["event_id"]
    assert event_fk["referred_table"] == "events"
    assert event_fk["referred_columns"] == ["id"]
    assert event_fk["options"].get("ondelete", "").upper() == "CASCADE"

    session_fk = foreign_keys["fk_registrations_session_id_sessions"]
    assert session_fk["constrained_columns"] == ["session_id"]
    assert session_fk["referred_table"] == "sessions"
    assert session_fk["referred_columns"] == ["id"]
    assert session_fk["options"].get("ondelete", "").upper() == "CASCADE"

    checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("registrations")
    }
    assert "ck_registrations_status" in checks
    assert "status" in checks["ck_registrations_status"]
    assert "ACTIVE" in checks["ck_registrations_status"]
    assert "CANCELLED" in checks["ck_registrations_status"]

    indexes = {
        index["name"]: index
        for index in inspector.get_indexes("registrations")
    }
    assert indexes["ix_registrations_event_id_status"]["column_names"] == [
        "event_id",
        "status",
    ]
    assert indexes["ix_registrations_session_id_status"]["column_names"] == [
        "session_id",
        "status",
    ]
    assert indexes[
        "ix_registrations_user_id_status_created_at"
    ]["column_names"] == ["user_id", "status", "created_at"]

    with test_engine.connect() as connection:
        partial_indexes = {
            row[0]: row[1]
            for row in connection.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'registrations'"
                )
            ).all()
        }
    active_event_index = partial_indexes["uq_registrations_active_event"]
    assert "UNIQUE INDEX" in active_event_index
    assert "user_id" in active_event_index
    assert "event_id" in active_event_index
    assert "status" in active_event_index
    assert "ACTIVE" in active_event_index
    assert "session_id IS NULL" in active_event_index

    active_session_index = partial_indexes["uq_registrations_active_session"]
    assert "UNIQUE INDEX" in active_session_index
    assert "user_id" in active_session_index
    assert "session_id" in active_session_index
    assert "status" in active_session_index
    assert "ACTIVE" in active_session_index
    assert "session_id IS NOT NULL" in active_session_index


def test_reg_ac_32_deleting_user_with_registration_is_restricted_by_fk(
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer)
    registration = _create_registration(
        db_session,
        user=attendee,
        event=event,
    )
    attendee_id = attendee.id
    registration_id = registration.id

    db_session.delete(attendee)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.get(User, attendee_id) is not None
    persisted = db_session.get(Registration, registration_id)
    assert persisted is not None
    assert persisted.user_id == attendee_id
    assert (
        db_session.exec(
            select(func.count()).select_from(Registration)
        ).one()
        == 1
    )


def test_reg_ac_01_attendee_creates_event_registration_and_receives_201(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(
        db_session,
        email="attendee@example.com",
    )
    event = _create_event(db_session, organizer=organizer, total_capacity=100)

    response = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert response.status_code == 201
    data = response.json()
    assert set(data) == {
        "id",
        "user_id",
        "event_id",
        "session_id",
        "status",
        "event",
        "session",
        "created_at",
        "updated_at",
    }
    assert data["user_id"] == attendee.id
    assert data["event_id"] == event.id
    assert data["session_id"] is None
    assert data["status"] == "ACTIVE"
    assert data["event"] == {
        "id": event.id,
        "title": "Evento de prueba",
        "date": "2026-11-15T14:00:00Z",
        "status": "PUBLISHED",
    }
    assert data["session"] is None
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")

    row = db_session.get(Registration, data["id"])
    assert row is not None
    assert row.user_id == attendee.id
    assert row.event_id == event.id
    assert row.session_id is None
    assert RegistrationStatus(row.status) == RegistrationStatus.ACTIVE
    assert _count_active_event(db_session, event.id) == 1

    event_read = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=_auth_headers(attendee),
    )
    assert event_read.status_code == 200
    assert event_read.json()["registered_count"] == 1
    assert event_read.json()["available_capacity"] == 99


def test_reg_ac_02_event_capacity_allows_exact_limit(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer, total_capacity=2)
    first = _create_user(db_session, email="first@example.com")
    second = _create_user(db_session, email="second@example.com")

    first_response = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(first),
    )
    assert first_response.status_code == 201

    second_response = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(second),
    )
    assert second_response.status_code == 201
    assert _count_active_event(db_session, event.id) == 2

    event_read = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert event_read.json()["registered_count"] == 2
    assert event_read.json()["available_capacity"] == 0


def test_reg_ac_03_event_capacity_overflow_returns_409_without_creating_rows(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer, total_capacity=1)
    first = _create_user(db_session, email="first@example.com")
    second = _create_user(db_session, email="second@example.com")

    assert client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(first),
    ).status_code == 201

    overflow = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(second),
    )
    assert overflow.status_code == 409
    assert overflow.json() == {
        "detail": "No hay cupos disponibles para este evento"
    }
    assert _count_active_event(db_session, event.id) == 1
    assert _count_rows(db_session) == 1

    event_read = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert event_read.json()["registered_count"] == 1


class _NullCache:
    def get(self, key: str):
        return None

    def set(self, key: str, value, ttl_seconds: int = 60) -> bool:
        return True

    def invalidate_prefix(self, prefix: str) -> bool:
        return True


class ConcurrentRegistrationRunner:
    """Runs registration writes on independent PostgreSQL connections."""

    def __init__(self, engine) -> None:
        self.engine = engine

    def seed_users(self, count: int) -> list[int]:
        with self.engine.begin() as connection:
            db = DBSession(bind=connection)
            user_ids: list[int] = []
            for _ in range(count):
                user = User(
                    email=f"conc-{uuid4().hex[:12]}@example.com",
                    password_hash=hash_password("Test1234!"),
                    full_name="Concurrente",
                    role=UserRole.ATTENDEE,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                user_ids.append(int(user.id))
            db.close()
        return user_ids

    def seed_event(self, *, total_capacity: int = 1) -> int:
        with self.engine.begin() as connection:
            db = DBSession(bind=connection)
            organizer = User(
                email=f"org-{uuid4().hex[:12]}@example.com",
                password_hash=hash_password("Test1234!"),
                full_name="Organizador",
                role=UserRole.ORGANIZER,
            )
            db.add(organizer)
            db.commit()
            db.refresh(organizer)
            event = Event(
                organizer_id=organizer.id,
                title="Evento concurrente",
                description="Descripción suficientemente larga.",
                date=EVENT_DATE,
                total_capacity=total_capacity,
                status=EventStatus.PUBLISHED.value,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            event_id = int(event.id)
            db.close()
        return event_id

    def seed_session(
        self,
        event_id: int,
        *,
        capacity: int = 1,
    ) -> int:
        with self.engine.begin() as connection:
            db = DBSession(bind=connection)
            session_row = SessionModel(
                event_id=event_id,
                title="Sesión concurrente",
                speaker="Ana Torres",
                description=None,
                start_time=datetime(
                    2026, 11, 15, 14, 0, tzinfo=timezone.utc
                ),
                end_time=datetime(
                    2026, 11, 15, 15, 0, tzinfo=timezone.utc
                ),
                capacity=capacity,
            )
            db.add(session_row)
            db.commit()
            db.refresh(session_row)
            session_id = int(session_row.id)
            db.close()
        return session_id

    def seed_event_registrations(
        self,
        event_id: int,
        user_ids: list[int],
    ) -> None:
        with self.engine.begin() as connection:
            db = DBSession(bind=connection)
            now = datetime.now(timezone.utc)
            for user_id in user_ids:
                db.add(
                    Registration(
                        user_id=user_id,
                        event_id=event_id,
                        session_id=None,
                        status=RegistrationStatus.ACTIVE,
                        created_at=now,
                        updated_at=now,
                    )
                )
            db.commit()
            db.close()

    def run_event(
        self,
        event_id: int,
        user_ids: list[int],
    ) -> list[tuple[str, object]]:
        barrier = Barrier(len(user_ids))
        outcomes: list[tuple[str, object]] = []

        def worker(user_id: int) -> None:
            connection = self.engine.connect()
            db = DBSession(bind=connection)
            try:
                actor = db.get(User, user_id)
                barrier.wait(timeout=15)
                try:
                    dto, created = create_event_registration(
                        db,
                        event_id,
                        actor,
                        _NullCache(),
                    )
                    outcomes.append(
                        ("created" if created else "reactivated", dto)
                    )
                except HTTPException as exc:
                    db.rollback()
                    outcomes.append(("conflict", exc))
            finally:
                db.close()
                connection.close()

        with ThreadPoolExecutor(max_workers=len(user_ids)) as pool:
            list(pool.map(worker, user_ids))
        return outcomes

    def run_session(
        self,
        event_id: int,
        session_id: int,
        user_ids: list[int],
    ) -> list[tuple[str, object]]:
        barrier = Barrier(len(user_ids))
        outcomes: list[tuple[str, object]] = []

        def worker(user_id: int) -> None:
            connection = self.engine.connect()
            db = DBSession(bind=connection)
            try:
                actor = db.get(User, user_id)
                barrier.wait(timeout=15)
                try:
                    dto, created = create_session_registration(
                        db,
                        event_id,
                        session_id,
                        actor,
                        _NullCache(),
                    )
                    outcomes.append(
                        ("created" if created else "reactivated", dto)
                    )
                except HTTPException as exc:
                    db.rollback()
                    outcomes.append(("conflict", exc))
            finally:
                db.close()
                connection.close()

        with ThreadPoolExecutor(max_workers=len(user_ids)) as pool:
            list(pool.map(worker, user_ids))
        return outcomes

    def count_active_event(self, event_id: int) -> int:
        with self.engine.connect() as connection:
            db = DBSession(bind=connection)
            try:
                return count_active_event_registrations(db, event_id)
            finally:
                db.close()

    def count_active_session(self, session_id: int) -> int:
        with self.engine.connect() as connection:
            db = DBSession(bind=connection)
            try:
                return count_active_session_registrations(db, session_id)
            finally:
                db.close()


@pytest.fixture()
def concurrent_registrations(test_engine):
    return ConcurrentRegistrationRunner(test_engine)


def test_reg_ac_04_concurrent_event_registrations_serialize_last_seat_with_for_update(
    concurrent_registrations: ConcurrentRegistrationRunner,
    db_truncate,
) -> None:
    db_truncate()
    for _ in range(3):
        event_id = concurrent_registrations.seed_event(total_capacity=1)
        user_ids = concurrent_registrations.seed_users(2)

        outcomes = concurrent_registrations.run_event(event_id, user_ids)

        assert sorted(kind for kind, _ in outcomes) == [
            "conflict",
            "created",
        ]
        conflict = next(
            value for kind, value in outcomes if kind == "conflict"
        )
        assert conflict.status_code == 409
        assert conflict.detail == "No hay cupos disponibles para este evento"
        created = next(
            value for kind, value in outcomes if kind == "created"
        )
        assert created.event_id == event_id
        assert concurrent_registrations.count_active_event(event_id) == 1


def test_reg_ac_05_duplicate_active_event_registration_returns_409(
    client_no_cache: TestClient,
    db_session: DBSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer)

    first = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert first.status_code == 201

    duplicate = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Ya estás inscrito en este evento"
    }
    assert _count_active_event(db_session, event.id) == 1
    assert _count_rows(db_session) == 1

    # Safety net: a partial unique index violation is still a 409, never a 500.
    monkeypatch.setattr(
        "app.registrations.service._find_event_registration",
        lambda db, user_id, event_id: None,
    )
    safety_net = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert safety_net.status_code == 409
    assert safety_net.json() == {
        "detail": "Ya estás inscrito en este evento"
    }
    assert _count_rows(db_session) == 1


def test_reg_ac_06_cancelled_event_registration_is_reactivated_with_200(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=5)
    created_at = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    cancelled = _create_registration(
        db_session,
        user=attendee,
        event=event,
        status=RegistrationStatus.CANCELLED,
        created_at=created_at,
    )
    assert _count_active_event(db_session, event.id) == 0

    response = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == cancelled.id
    assert data["status"] == "ACTIVE"
    assert data["created_at"] == "2026-10-01T09:00:00Z"
    assert data["updated_at"] != "2026-10-01T09:00:00Z"
    assert data["updated_at"].endswith("Z")
    assert _count_active_event(db_session, event.id) == 1
    assert _count_rows(db_session) == 1

    event_read = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert event_read.json()["registered_count"] == 1


def test_reg_ac_07_reactivation_without_capacity_returns_409_and_keeps_cancelled(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    other = _create_user(db_session, email="other@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=1)
    cancelled = _create_registration(
        db_session,
        user=attendee,
        event=event,
        status=RegistrationStatus.CANCELLED,
    )
    _create_registration(db_session, user=other, event=event)

    response = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": "No hay cupos disponibles para este evento"
    }
    db_session.refresh(cancelled)
    assert RegistrationStatus(cancelled.status) == RegistrationStatus.CANCELLED
    assert _count_active_event(db_session, event.id) == 1


def test_reg_ac_08_reactivation_on_non_published_event_returns_404_and_keeps_cancelled(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")

    for event_status in (EventStatus.CANCELLED, EventStatus.DRAFT):
        event = _create_event(
            db_session,
            organizer=organizer,
            title=f"Evento {event_status.value}",
            status=event_status,
        )
        cancelled = _create_registration(
            db_session,
            user=attendee,
            event=event,
            status=RegistrationStatus.CANCELLED,
        )

        response = client_no_cache.post(
            f"/api/events/{event.id}/registrations",
            headers=_auth_headers(attendee),
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Evento no encontrado"}
        db_session.refresh(cancelled)
        assert (
            RegistrationStatus(cancelled.status)
            == RegistrationStatus.CANCELLED
        )
        assert _count_active_event(db_session, event.id) == 0


def test_reg_ac_09_draft_and_cancelled_events_are_not_registerable(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    headers = _auth_headers(attendee)

    for event_status in (EventStatus.DRAFT, EventStatus.CANCELLED):
        event = _create_event(
            db_session,
            organizer=organizer,
            title=f"Evento {event_status.value}",
            status=event_status,
        )
        session_row = _create_session_row(db_session, event=event)

        event_response = client_no_cache.post(
            f"/api/events/{event.id}/registrations",
            headers=headers,
        )
        assert event_response.status_code == 404
        assert event_response.json() == {
            "detail": "Evento no encontrado"
        }

        session_response = client_no_cache.post(
            f"/api/events/{event.id}/sessions/{session_row.id}/registrations",
            headers=headers,
        )
        assert session_response.status_code == 404
        assert session_response.json() == {
            "detail": "Evento no encontrado"
        }

        assert _count_rows(db_session) == 0


def test_reg_ac_10_cancelling_event_keeps_registrations_and_counters(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=10)

    created = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert created.status_code == 201
    registration_id = created.json()["id"]
    registration = db_session.get(Registration, registration_id)
    original_updated_at = registration.updated_at

    cancelled = client_no_cache.patch(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
        json={"status": "CANCELLED"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    db_session.refresh(registration)
    assert RegistrationStatus(registration.status) == RegistrationStatus.ACTIVE
    assert registration.updated_at == original_updated_at

    event_read = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert event_read.status_code == 200
    assert event_read.json()["registered_count"] == 1
    assert event_read.json()["available_capacity"] == 9
    assert _count_active_event(db_session, event.id) == 1


def test_reg_ac_11_registration_requires_attendee_role(
    client_no_cache: TestClient,
    db_session: DBSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(db_session, event=event)
    path = f"/api/events/{event.id}/registrations"
    session_path = (
        f"/api/events/{event.id}/sessions/{session_row.id}/registrations"
    )

    anonymous = client_no_cache.post(path)
    assert anonymous.status_code == 401
    assert anonymous.json() == {
        "detail": "No autenticado o sesión expirada"
    }
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"

    invalid_token = client_no_cache.post(
        path,
        headers={"Authorization": "Bearer token-invalido"},
    )
    assert invalid_token.status_code == 401
    assert invalid_token.json() == {
        "detail": "No autenticado o sesión expirada"
    }

    monkeypatch.setattr(settings, "jwt_expire_minutes", -1)
    expired_headers = _auth_headers(attendee)
    monkeypatch.setattr(settings, "jwt_expire_minutes", 480)
    expired = client_no_cache.post(path, headers=expired_headers)
    assert expired.status_code == 401
    assert expired.headers["WWW-Authenticate"] == "Bearer"

    inactive = _create_user(
        db_session,
        email="inactive@example.com",
        is_active=False,
    )
    inactive_response = client_no_cache.post(
        path,
        headers=_auth_headers(inactive),
    )
    assert inactive_response.status_code == 401

    for headers in (_auth_headers(organizer), _auth_headers(admin)):
        forbidden = client_no_cache.post(path, headers=headers)
        assert forbidden.status_code == 403
        assert forbidden.json() == {
            "detail": "No tienes permisos para realizar esta acción"
        }

    anonymous_session = client_no_cache.post(session_path)
    assert anonymous_session.status_code == 401
    assert anonymous_session.json() == {
        "detail": "No autenticado o sesión expirada"
    }
    assert anonymous_session.headers["WWW-Authenticate"] == "Bearer"

    for headers in (_auth_headers(organizer), _auth_headers(admin)):
        forbidden_session = client_no_cache.post(
            session_path,
            headers=headers,
        )
        assert forbidden_session.status_code == 403
        assert forbidden_session.json() == {
            "detail": "No tienes permisos para realizar esta acción"
        }

    assert _count_rows(db_session) == 0


def test_reg_ac_12_attendee_registers_session_without_consuming_event_seat(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=10)
    session_row = _create_session_row(
        db_session,
        event=event,
        title="Apertura y bienvenida",
        speaker="Ana Torres",
        capacity=40,
    )
    headers = _auth_headers(attendee)

    event_registration = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=headers,
    )
    assert event_registration.status_code == 201

    session_registration = client_no_cache.post(
        f"/api/events/{event.id}/sessions/{session_row.id}/registrations",
        headers=headers,
    )
    assert session_registration.status_code == 201
    data = session_registration.json()
    assert data["user_id"] == attendee.id
    assert data["event_id"] == event.id
    assert data["session_id"] == session_row.id
    assert data["status"] == "ACTIVE"
    assert data["session"] == {
        "id": session_row.id,
        "title": "Apertura y bienvenida",
        "speaker": "Ana Torres",
        "start_time": "2026-11-15T14:00:00Z",
        "end_time": "2026-11-15T15:00:00Z",
    }
    assert data["event"]["id"] == event.id

    assert _count_active_session(db_session, session_row.id) == 1
    assert _count_active_event(db_session, event.id) == 1

    sessions_list = client_no_cache.get(
        f"/api/events/{event.id}/sessions",
        headers=headers,
    )
    assert sessions_list.status_code == 200
    listed = sessions_list.json()["items"][0]
    assert listed["registered_count"] == 1
    assert listed["available_capacity"] == 39

    event_read = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=headers,
    )
    assert event_read.json()["registered_count"] == 1


def test_reg_ac_13_session_registration_requires_active_event_registration(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(db_session, event=event)
    headers = _auth_headers(attendee)
    path = f"/api/events/{event.id}/sessions/{session_row.id}/registrations"

    without_registration = client_no_cache.post(path, headers=headers)
    assert without_registration.status_code == 409
    assert without_registration.json() == {
        "detail": "Debes inscribirte primero al evento"
    }
    assert _count_rows(db_session) == 0

    _create_registration(
        db_session,
        user=attendee,
        event=event,
        status=RegistrationStatus.CANCELLED,
    )

    cancelled_registration = client_no_cache.post(path, headers=headers)
    assert cancelled_registration.status_code == 409
    assert cancelled_registration.json() == {
        "detail": "Debes inscribirte primero al evento"
    }
    assert _count_rows(db_session) == 1
    assert _count_active_session(db_session, session_row.id) == 0


def test_reg_ac_14_session_from_another_event_returns_404(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer)
    other_event = _create_event(
        db_session,
        organizer=organizer,
        title="Otro evento",
    )
    foreign_session = _create_session_row(db_session, event=other_event)
    headers = _auth_headers(attendee)

    client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=headers,
    )

    foreign = client_no_cache.post(
        f"/api/events/{event.id}/sessions/{foreign_session.id}/registrations",
        headers=headers,
    )
    assert foreign.status_code == 404
    assert foreign.json() == {"detail": "Sesión no encontrada"}

    missing = client_no_cache.post(
        f"/api/events/{event.id}/sessions/999999/registrations",
        headers=headers,
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Sesión no encontrada"}

    assert _count_active_session(db_session, foreign_session.id) == 0
    assert _count_rows(db_session) == 1


def test_reg_ac_15_session_capacity_exact_limit_and_overflow(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer, total_capacity=10)
    session_row = _create_session_row(db_session, event=event, capacity=2)
    attendees = [
        _create_user(db_session, email=f"attendee{index}@example.com")
        for index in range(3)
    ]
    for attendee in attendees:
        response = client_no_cache.post(
            f"/api/events/{event.id}/registrations",
            headers=_auth_headers(attendee),
        )
        assert response.status_code == 201

    for attendee in attendees[:2]:
        response = client_no_cache.post(
            f"/api/events/{event.id}/sessions/{session_row.id}/registrations",
            headers=_auth_headers(attendee),
        )
        assert response.status_code == 201
    assert _count_active_session(db_session, session_row.id) == 2

    overflow = client_no_cache.post(
        f"/api/events/{event.id}/sessions/{session_row.id}/registrations",
        headers=_auth_headers(attendees[2]),
    )
    assert overflow.status_code == 409
    assert overflow.json() == {
        "detail": "No hay cupos disponibles para esta sesión"
    }
    assert _count_active_session(db_session, session_row.id) == 2
    assert _count_active_event(db_session, event.id) == 3

    sessions_list = client_no_cache.get(
        f"/api/events/{event.id}/sessions",
        headers=_auth_headers(organizer),
    )
    listed = sessions_list.json()["items"][0]
    assert listed["registered_count"] == 2
    assert listed["available_capacity"] == 0


def test_reg_ac_16_concurrent_session_registrations_serialize_last_seat(
    concurrent_registrations: ConcurrentRegistrationRunner,
    db_truncate,
) -> None:
    db_truncate()
    for _ in range(3):
        event_id = concurrent_registrations.seed_event(total_capacity=10)
        session_id = concurrent_registrations.seed_session(
            event_id,
            capacity=1,
        )
        user_ids = concurrent_registrations.seed_users(2)
        concurrent_registrations.seed_event_registrations(
            event_id,
            user_ids,
        )

        outcomes = concurrent_registrations.run_session(
            event_id,
            session_id,
            user_ids,
        )

        assert sorted(kind for kind, _ in outcomes) == [
            "conflict",
            "created",
        ]
        conflict = next(
            value for kind, value in outcomes if kind == "conflict"
        )
        assert conflict.status_code == 409
        assert conflict.detail == "No hay cupos disponibles para esta sesión"
        created = next(
            value for kind, value in outcomes if kind == "created"
        )
        assert created.session_id == session_id
        assert (
            concurrent_registrations.count_active_session(session_id) == 1
        )


def test_reg_ac_17_duplicate_and_reactivation_of_session_registration(
    client_no_cache: TestClient,
    db_session: DBSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(db_session, event=event, capacity=5)
    headers = _auth_headers(attendee)
    path = f"/api/events/{event.id}/sessions/{session_row.id}/registrations"

    client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=headers,
    )
    first = client_no_cache.post(path, headers=headers)
    assert first.status_code == 201

    duplicate = client_no_cache.post(path, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Ya estás inscrito en esta sesión"
    }
    assert _count_active_session(db_session, session_row.id) == 1

    session_registration = db_session.get(
        Registration,
        first.json()["id"],
    )
    session_registration.status = RegistrationStatus.CANCELLED
    db_session.add(session_registration)
    db_session.commit()

    reactivated = client_no_cache.post(path, headers=headers)
    assert reactivated.status_code == 200
    reactivated_data = reactivated.json()
    assert reactivated_data["id"] == session_registration.id
    assert reactivated_data["status"] == "ACTIVE"
    assert reactivated_data["session_id"] == session_row.id

    # Safety net: the session partial unique index is also translated to 409.
    monkeypatch.setattr(
        "app.registrations.service._find_session_registration",
        lambda db, user_id, session_id: None,
    )
    safety_net = client_no_cache.post(path, headers=headers)
    assert safety_net.status_code == 409
    assert safety_net.json() == {
        "detail": "Ya estás inscrito en esta sesión"
    }
    monkeypatch.undo()

    session_registration.status = RegistrationStatus.CANCELLED
    db_session.add(session_registration)
    event_registration = db_session.exec(
        select(Registration).where(
            Registration.user_id == attendee.id,
            Registration.event_id == event.id,
            Registration.session_id.is_(None),
        )
    ).first()
    event_registration.status = RegistrationStatus.CANCELLED
    db_session.add(event_registration)
    db_session.commit()

    blocked = client_no_cache.post(path, headers=headers)
    assert blocked.status_code == 409
    assert blocked.json() == {
        "detail": "Debes inscribirte primero al evento"
    }
    db_session.refresh(session_registration)
    assert (
        RegistrationStatus(session_registration.status)
        == RegistrationStatus.CANCELLED
    )


def test_reg_ac_18_owner_cancels_registration_and_releases_capacity(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    other = _create_user(db_session, email="other@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=10)
    first_session = _create_session_row(
        db_session,
        event=event,
        title="Sesión uno",
        start_time=datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc),
    )
    second_session = _create_session_row(
        db_session,
        event=event,
        title="Sesión dos",
        start_time=datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc),
    )

    event_registration = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert event_registration.status_code == 201
    registration_id = event_registration.json()["id"]
    registration = db_session.get(Registration, registration_id)
    original_updated_at = registration.updated_at

    deleted = client_no_cache.delete(
        f"/api/registrations/{registration_id}",
        headers=_auth_headers(attendee),
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    db_session.refresh(registration)
    assert RegistrationStatus(registration.status) == RegistrationStatus.CANCELLED
    assert registration.updated_at != original_updated_at
    assert _count_active_event(db_session, event.id) == 0

    event_read = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert event_read.json()["registered_count"] == 0
    assert event_read.json()["available_capacity"] == 10

    # A session registration only releases its own seat.
    other_headers = _auth_headers(other)
    assert client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=other_headers,
    ).status_code == 201
    first_session_registration = client_no_cache.post(
        f"/api/events/{event.id}/sessions/{first_session.id}/registrations",
        headers=other_headers,
    )
    assert first_session_registration.status_code == 201
    second_session_registration = client_no_cache.post(
        f"/api/events/{event.id}/sessions/{second_session.id}/registrations",
        headers=other_headers,
    )
    assert second_session_registration.status_code == 201

    cancelled_session = client_no_cache.delete(
        f"/api/registrations/{first_session_registration.json()['id']}",
        headers=other_headers,
    )
    assert cancelled_session.status_code == 204
    assert _count_active_session(db_session, first_session.id) == 0
    assert _count_active_session(db_session, second_session.id) == 1
    assert _count_active_event(db_session, event.id) == 1
    event_registration_row = db_session.exec(
        select(Registration).where(
            Registration.user_id == other.id,
            Registration.event_id == event.id,
            Registration.session_id.is_(None),
        )
    ).first()
    assert (
        RegistrationStatus(event_registration_row.status)
        == RegistrationStatus.ACTIVE
    )


def test_reg_ac_19_repeated_delete_is_idempotent_and_keeps_row(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=10)
    created = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(attendee),
    )
    assert created.status_code == 201
    registration_id = created.json()["id"]

    first = client_no_cache.delete(
        f"/api/registrations/{registration_id}",
        headers=_auth_headers(attendee),
    )
    assert first.status_code == 204
    registration = db_session.get(Registration, registration_id)
    first_updated_at = registration.updated_at

    second = client_no_cache.delete(
        f"/api/registrations/{registration_id}",
        headers=_auth_headers(attendee),
    )
    assert second.status_code == 204
    assert second.content == b""
    db_session.refresh(registration)
    assert registration.updated_at == first_updated_at
    assert RegistrationStatus(registration.status) == RegistrationStatus.CANCELLED
    assert _count_rows(db_session) == 1
    assert _count_active_event(db_session, event.id) == 0


def test_reg_ac_20_cancelling_event_registration_cascades_session_registrations(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    other = _create_user(db_session, email="other@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=10)
    first_session = _create_session_row(
        db_session,
        event=event,
        title="Sesión uno",
        start_time=datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc),
    )
    second_session = _create_session_row(
        db_session,
        event=event,
        title="Sesión dos",
        start_time=datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc),
    )
    headers = _auth_headers(attendee)
    other_headers = _auth_headers(other)

    event_registration = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=headers,
    )
    assert event_registration.status_code == 201
    for session_row in (first_session, second_session):
        assert client_no_cache.post(
            f"/api/events/{event.id}/sessions/{session_row.id}/registrations",
            headers=headers,
        ).status_code == 201

    assert client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=other_headers,
    ).status_code == 201
    other_session_registration = client_no_cache.post(
        f"/api/events/{event.id}/sessions/{first_session.id}/registrations",
        headers=other_headers,
    )
    assert other_session_registration.status_code == 201

    assert _count_active_session(db_session, first_session.id) == 2
    assert _count_active_session(db_session, second_session.id) == 1

    cancelled = client_no_cache.delete(
        f"/api/registrations/{event_registration.json()['id']}",
        headers=headers,
    )
    assert cancelled.status_code == 204

    attendee_sessions = db_session.exec(
        select(Registration).where(
            Registration.user_id == attendee.id,
            Registration.session_id.is_not(None),
        )
    ).all()
    assert len(attendee_sessions) == 2
    for row in attendee_sessions:
        assert RegistrationStatus(row.status) == RegistrationStatus.CANCELLED

    assert _count_active_session(db_session, first_session.id) == 1
    assert _count_active_session(db_session, second_session.id) == 0
    assert _count_active_event(db_session, event.id) == 1

    other_row = db_session.get(
        Registration,
        other_session_registration.json()["id"],
    )
    assert RegistrationStatus(other_row.status) == RegistrationStatus.ACTIVE

    # Cancelling a session registration does not touch the event registration.
    other_event_registration = client_no_cache.delete(
        f"/api/registrations/{other_session_registration.json()['id']}",
        headers=other_headers,
    )
    assert other_event_registration.status_code == 204
    other_event_row = db_session.exec(
        select(Registration).where(
            Registration.user_id == other.id,
            Registration.event_id == event.id,
            Registration.session_id.is_(None),
        )
    ).first()
    assert (
        RegistrationStatus(other_event_row.status)
        == RegistrationStatus.ACTIVE
    )
    assert _count_active_event(db_session, event.id) == 1
    assert _count_active_session(db_session, first_session.id) == 0


def test_reg_ac_21_cancellation_permissions_and_not_found(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    other_organizer = _create_user(
        db_session,
        email="other-organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    stranger = _create_user(db_session, email="stranger@example.com")
    event = _create_event(db_session, organizer=organizer)

    registrations = []
    for user in (attendee, stranger):
        response = client_no_cache.post(
            f"/api/events/{event.id}/registrations",
            headers=_auth_headers(user),
        )
        assert response.status_code == 201
        registrations.append(response.json()["id"])

    owner_registration_id = registrations[0]
    stranger_registration_id = registrations[1]

    not_visible = client_no_cache.delete(
        f"/api/registrations/{owner_registration_id}",
        headers=_auth_headers(stranger),
    )
    assert not_visible.status_code == 404
    assert not_visible.json() == {
        "detail": "Inscripción no encontrada"
    }

    foreign_organizer = client_no_cache.delete(
        f"/api/registrations/{owner_registration_id}",
        headers=_auth_headers(other_organizer),
    )
    assert foreign_organizer.status_code == 404
    assert foreign_organizer.json() == {
        "detail": "Inscripción no encontrada"
    }

    missing = client_no_cache.delete(
        "/api/registrations/999999",
        headers=_auth_headers(attendee),
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Inscripción no encontrada"}

    owner_row = db_session.get(Registration, owner_registration_id)
    assert RegistrationStatus(owner_row.status) == RegistrationStatus.ACTIVE

    owner_cancel = client_no_cache.delete(
        f"/api/registrations/{owner_registration_id}",
        headers=_auth_headers(attendee),
    )
    assert owner_cancel.status_code == 204

    organizer_cancel = client_no_cache.delete(
        f"/api/registrations/{stranger_registration_id}",
        headers=_auth_headers(organizer),
    )
    assert organizer_cancel.status_code == 204

    admin_registration = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(stranger),
    )
    assert admin_registration.status_code == 200
    admin_cancel = client_no_cache.delete(
        f"/api/registrations/{admin_registration.json()['id']}",
        headers=_auth_headers(admin),
    )
    assert admin_cancel.status_code == 204


def test_reg_ac_22_my_registrations_are_paginated_and_ordered_desc(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    empty_user = _create_user(db_session, email="empty@example.com")
    event = _create_event(db_session, organizer=organizer)
    second_event = _create_event(
        db_session,
        organizer=organizer,
        title="Segundo evento",
    )
    session_row = _create_session_row(db_session, event=event)

    oldest = _create_registration(
        db_session,
        user=attendee,
        event=event,
        created_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    )
    middle = _create_registration(
        db_session,
        user=attendee,
        event=event,
        session_row=session_row,
        created_at=datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc),
    )
    newest = _create_registration(
        db_session,
        user=attendee,
        event=event,
        status=RegistrationStatus.CANCELLED,
        created_at=datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc),
    )
    same_instant = _create_registration(
        db_session,
        user=attendee,
        event=second_event,
        created_at=datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc),
    )

    response = client_no_cache.get(
        "/api/registrations/me",
        headers=_auth_headers(attendee),
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"items", "total", "page", "size", "pages"}
    assert data["total"] == 4
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["pages"] == 1
    assert [item["id"] for item in data["items"]] == [
        newest.id,
        same_instant.id,
        middle.id,
        oldest.id,
    ]
    statuses = {item["status"] for item in data["items"]}
    assert statuses == {"ACTIVE", "CANCELLED"}
    assert any(item["session_id"] is None for item in data["items"])
    assert any(item["session_id"] == session_row.id for item in data["items"])
    first_item = data["items"][0]
    assert first_item["event"]["id"] == event.id
    assert first_item["event"]["title"] == "Evento de prueba"
    assert first_item["created_at"] == "2026-10-03T08:00:00Z"

    second_page = client_no_cache.get(
        "/api/registrations/me?page=2&size=2",
        headers=_auth_headers(attendee),
    )
    assert second_page.status_code == 200
    second_data = second_page.json()
    assert second_data["page"] == 2
    assert second_data["size"] == 2
    assert second_data["pages"] == 2
    assert [item["id"] for item in second_data["items"]] == [
        middle.id,
        oldest.id,
    ]

    empty_response = client_no_cache.get(
        "/api/registrations/me",
        headers=_auth_headers(empty_user),
    )
    assert empty_response.status_code == 200
    assert empty_response.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "size": 10,
        "pages": 0,
    }


def test_reg_ac_23_my_registrations_filters_and_invalid_values(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    first_event = _create_event(db_session, organizer=organizer)
    second_event = _create_event(
        db_session,
        organizer=organizer,
        title="Segundo evento",
    )
    active_first = _create_registration(
        db_session,
        user=attendee,
        event=first_event,
        created_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    )
    cancelled_first = _create_registration(
        db_session,
        user=attendee,
        event=first_event,
        status=RegistrationStatus.CANCELLED,
        created_at=datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc),
    )
    active_second = _create_registration(
        db_session,
        user=attendee,
        event=second_event,
        created_at=datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc),
    )
    headers = _auth_headers(attendee)

    active_response = client_no_cache.get(
        "/api/registrations/me?status=ACTIVE",
        headers=headers,
    )
    assert active_response.status_code == 200
    assert [item["id"] for item in active_response.json()["items"]] == [
        active_second.id,
        active_first.id,
    ]

    cancelled_response = client_no_cache.get(
        "/api/registrations/me?status=CANCELLED",
        headers=headers,
    )
    assert cancelled_response.status_code == 200
    assert [
        item["id"] for item in cancelled_response.json()["items"]
    ] == [cancelled_first.id]

    event_response = client_no_cache.get(
        f"/api/registrations/me?event_id={first_event.id}",
        headers=headers,
    )
    assert event_response.status_code == 200
    assert [item["id"] for item in event_response.json()["items"]] == [
        cancelled_first.id,
        active_first.id,
    ]

    unknown_event = client_no_cache.get(
        "/api/registrations/me?event_id=999999",
        headers=headers,
    )
    assert unknown_event.status_code == 200
    assert unknown_event.json()["items"] == []
    assert unknown_event.json()["total"] == 0

    invalid_cases = (
        "/api/registrations/me?status=UNKNOWN",
        "/api/registrations/me?page=0",
        "/api/registrations/me?size=51",
        "/api/registrations/me?event_id=0",
    )
    for path in invalid_cases:
        response = client_no_cache.get(path, headers=headers)
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == (
            "Error de validación en los datos enviados"
        )
        assert data["errors"]
        for error in data["errors"]:
            assert set(error) == {"field", "message"}
            assert error["message"]

    invalid_status = client_no_cache.get(
        "/api/registrations/me?status=UNKNOWN",
        headers=headers,
    )
    assert any(
        error["field"] == "status"
        and "Valor no permitido" in error["message"]
        for error in invalid_status.json()["errors"]
    )

    invalid_page = client_no_cache.get(
        "/api/registrations/me?page=0",
        headers=headers,
    )
    assert any(
        error["field"] == "page"
        and "mayor o igual a 1" in error["message"]
        for error in invalid_page.json()["errors"]
    )


def test_reg_ac_24_my_registrations_only_returns_own_rows(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    first = _create_user(db_session, email="first@example.com")
    second = _create_user(db_session, email="second@example.com")
    event = _create_event(db_session, organizer=organizer)
    first_registration = _create_registration(
        db_session,
        user=first,
        event=event,
        created_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    )
    second_registration = _create_registration(
        db_session,
        user=second,
        event=event,
        created_at=datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc),
    )

    first_response = client_no_cache.get(
        "/api/registrations/me",
        headers=_auth_headers(first),
    )
    assert first_response.status_code == 200
    assert [item["id"] for item in first_response.json()["items"]] == [
        first_registration.id
    ]
    assert all(
        item["user_id"] == first.id
        for item in first_response.json()["items"]
    )

    second_response = client_no_cache.get(
        "/api/registrations/me",
        headers=_auth_headers(second),
    )
    assert second_response.status_code == 200
    assert [item["id"] for item in second_response.json()["items"]] == [
        second_registration.id
    ]

    spoofed = client_no_cache.get(
        f"/api/registrations/me?user_id={second.id}",
        headers=_auth_headers(first),
    )
    assert spoofed.status_code == 200
    assert [item["id"] for item in spoofed.json()["items"]] == [
        first_registration.id
    ]


def test_reg_ac_25_event_registrations_list_exposes_no_personal_data(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        full_name="Organizador Propietario",
        role=UserRole.ORGANIZER,
    )
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    attendee = _create_user(
        db_session,
        email="attendee@example.com",
        full_name="Asistente Uno",
    )
    other = _create_user(
        db_session,
        email="other@example.com",
        full_name="Asistente Dos",
    )
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(db_session, event=event)

    event_registration = _create_registration(
        db_session,
        user=attendee,
        event=event,
        created_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    )
    _create_registration(
        db_session,
        user=attendee,
        event=event,
        session_row=session_row,
        created_at=datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc),
    )
    cancelled_registration = _create_registration(
        db_session,
        user=other,
        event=event,
        status=RegistrationStatus.CANCELLED,
        created_at=datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc),
    )

    response = client_no_cache.get(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(organizer),
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"items", "total", "page", "size", "pages"}
    assert data["total"] == 2
    assert [item["id"] for item in data["items"]] == [
        cancelled_registration.id,
        event_registration.id,
    ]
    assert all(
        item["session_id"] is None for item in data["items"]
    )
    assert all(
        item["user_id"] in {attendee.id, other.id}
        for item in data["items"]
    )
    raw = response.text
    assert "full_name" not in raw
    assert "email" not in raw
    assert "password_hash" not in raw
    assert "Asistente Uno" not in raw

    active_only = client_no_cache.get(
        f"/api/events/{event.id}/registrations?status=ACTIVE",
        headers=_auth_headers(organizer),
    )
    assert active_only.status_code == 200
    assert active_only.json()["total"] == 1
    assert [item["id"] for item in active_only.json()["items"]] == [
        event_registration.id
    ]

    admin_response = client_no_cache.get(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(admin),
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["total"] == 2

    session_only_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento con inscritos solo a sesiones",
    )
    session_only = _create_session_row(
        db_session,
        event=session_only_event,
    )
    _create_registration(
        db_session,
        user=attendee,
        event=session_only_event,
        session_row=session_only,
    )
    empty_response = client_no_cache.get(
        f"/api/events/{session_only_event.id}/registrations",
        headers=_auth_headers(organizer),
    )
    assert empty_response.status_code == 200
    assert empty_response.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "size": 10,
        "pages": 0,
    }


def test_reg_ac_26_event_registrations_list_permissions_and_empty_page(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    other_organizer = _create_user(
        db_session,
        email="other-organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer)
    path = f"/api/events/{event.id}/registrations"

    for headers in (_auth_headers(attendee), _auth_headers(other_organizer)):
        forbidden = client_no_cache.get(path, headers=headers)
        assert forbidden.status_code == 403
        assert forbidden.json() == {
            "detail": "No tienes permisos para realizar esta acción"
        }

    missing = client_no_cache.get(
        "/api/events/999999/registrations",
        headers=_auth_headers(organizer),
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Evento no encontrado"}

    foreign_admin = client_no_cache.get(path, headers=_auth_headers(admin))
    assert foreign_admin.status_code == 200
    assert foreign_admin.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "size": 10,
        "pages": 0,
    }


def test_reg_ac_27_registration_detail_visibility_returns_404_for_strangers(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    other_organizer = _create_user(
        db_session,
        email="other-organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    attendee = _create_user(
        db_session,
        email="attendee@example.com",
        full_name="Asistente Privado",
    )
    stranger = _create_user(db_session, email="stranger@example.com")
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(db_session, event=event)
    registration = _create_registration(
        db_session,
        user=attendee,
        event=event,
        session_row=session_row,
    )
    path = f"/api/registrations/{registration.id}"

    for headers in (
        _auth_headers(attendee),
        _auth_headers(organizer),
        _auth_headers(admin),
    ):
        detail = client_no_cache.get(path, headers=headers)
        assert detail.status_code == 200
        data = detail.json()
        assert data["id"] == registration.id
        assert data["user_id"] == attendee.id
        assert data["session_id"] == session_row.id
        assert data["session"]["id"] == session_row.id
        assert set(data) == {
            "id",
            "user_id",
            "event_id",
            "session_id",
            "status",
            "event",
            "session",
            "created_at",
            "updated_at",
        }
        assert "full_name" not in detail.text
        assert "email" not in detail.text
        assert "Asistente Privado" not in detail.text

    for headers in (
        _auth_headers(stranger),
        _auth_headers(other_organizer),
    ):
        hidden = client_no_cache.get(path, headers=headers)
        assert hidden.status_code == 404
        assert hidden.json() == {
            "detail": "Inscripción no encontrada"
        }

    missing = client_no_cache.get(
        "/api/registrations/999999",
        headers=_auth_headers(attendee),
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Inscripción no encontrada"}


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, object] = {}
        self.set_calls: list[tuple[str, int]] = []
        self.invalidated: list[str] = []

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value, ttl_seconds: int = 60) -> bool:
        self.set_calls.append((key, ttl_seconds))
        self.store[key] = value
        return True

    def invalidate_prefix(self, prefix: str) -> bool:
        self.invalidated.append(prefix)
        for key in list(self.store):
            if key.startswith(prefix):
                del self.store[key]
        return True


def test_reg_ac_28_my_registrations_cache_keys_and_invalidation(
    client: TestClient,
    db_session: DBSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    other = _create_user(db_session, email="other@example.com")
    event = _create_event(db_session, organizer=organizer)
    second_event = _create_event(
        db_session,
        organizer=organizer,
        title="Segundo evento",
    )
    fake_cache = FakeCache()
    app.dependency_overrides[get_cache_client] = lambda: fake_cache
    try:
        created = client.post(
            f"/api/events/{event.id}/registrations",
            headers=_auth_headers(attendee),
        )
        assert created.status_code == 201
        assert f"registrations:me:{attendee.id}:" in fake_cache.invalidated
        assert "events:" in fake_cache.invalidated

        listing = client.get(
            "/api/registrations/me",
            headers=_auth_headers(attendee),
        )
        assert listing.status_code == 200
        expected_key = (
            f"registrations:me:{attendee.id}:"
            "page=1:size=10:status=:event="
        )
        assert fake_cache.set_calls[-1] == (
            expected_key,
            settings.cache_events_ttl_seconds,
        )
        assert fake_cache.set_calls[-1][1] == 60
        assert listing.json()["total"] == 1

        # A direct write bypasses invalidation: the cached payload is served.
        _create_registration(db_session, user=attendee, event=second_event)
        cached_listing = client.get(
            "/api/registrations/me",
            headers=_auth_headers(attendee),
        )
        assert cached_listing.status_code == 200
        assert cached_listing.json()["total"] == 1

        # A corrupted cached payload is discarded and PostgreSQL is used.
        import logging

        fake_cache.store[expected_key] = {"items": "not-a-list"}
        with caplog.at_level(
            logging.WARNING,
            logger="app.registrations.service",
        ):
            fallback_listing = client.get(
                "/api/registrations/me",
                headers=_auth_headers(attendee),
            )
        assert fallback_listing.status_code == 200
        assert fallback_listing.json()["total"] == 2
        assert any(
            "Invalid cached registration list payload" in record.getMessage()
            for record in caplog.records
        )

        filtered = client.get(
            "/api/registrations/me?status=ACTIVE&event_id="
            f"{second_event.id}&page=2&size=5",
            headers=_auth_headers(attendee),
        )
        assert filtered.status_code == 200
        filtered_key = (
            f"registrations:me:{attendee.id}:"
            f"page=2:size=5:status=ACTIVE:event={second_event.id}"
        )
        assert fake_cache.set_calls[-1][0] == filtered_key

        other_listing = client.get(
            "/api/registrations/me",
            headers=_auth_headers(other),
        )
        assert other_listing.status_code == 200
        assert other_listing.json()["total"] == 0
        other_keys = [
            key
            for key, _ in fake_cache.set_calls
            if key.startswith(f"registrations:me:{other.id}:")
        ]
        assert other_keys
        assert not any(
            key.startswith(f"registrations:me:{attendee.id}:")
            for key in other_keys
        )

        registration_id = created.json()["id"]
        fake_cache.invalidated.clear()
        cancelled = client.delete(
            f"/api/registrations/{registration_id}",
            headers=_auth_headers(organizer),
        )
        assert cancelled.status_code == 204
        assert f"registrations:me:{attendee.id}:" in fake_cache.invalidated
        assert "events:" in fake_cache.invalidated

        fake_cache.invalidated.clear()
        reactivated = client.post(
            f"/api/events/{event.id}/registrations",
            headers=_auth_headers(attendee),
        )
        assert reactivated.status_code == 200
        assert f"registrations:me:{attendee.id}:" in fake_cache.invalidated
        assert "events:" in fake_cache.invalidated
    finally:
        app.dependency_overrides.pop(get_cache_client, None)


def test_reg_ac_28_session_registration_invalidates_cache_and_does_not_cache_event_listing(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(
        db_session,
        organizer=organizer,
        total_capacity=10,
    )
    session_row = _create_session_row(
        db_session,
        event=event,
        capacity=5,
    )
    _create_registration(db_session, user=attendee, event=event)

    fake_cache = FakeCache()
    app.dependency_overrides[get_cache_client] = lambda: fake_cache
    try:
        response = client.post(
            f"/api/events/{event.id}/sessions/{session_row.id}/registrations",
            headers=_auth_headers(attendee),
        )
        assert response.status_code == 201
        assert f"registrations:me:{attendee.id}:" in fake_cache.invalidated
        assert "events:" in fake_cache.invalidated

        # The management listing is not cached: it never writes to the cache.
        fake_cache.set_calls.clear()
        listing = client.get(
            f"/api/events/{event.id}/registrations",
            headers=_auth_headers(organizer),
        )
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert fake_cache.set_calls == []
        assert not any(
            "registrations" in key and f"event={event.id}" in key
            for key in fake_cache.store
        )
    finally:
        app.dependency_overrides.pop(get_cache_client, None)


def test_reg_ac_29_redis_failure_degrades_to_postgresql(
    client: TestClient,
    db_session: DBSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from redis.exceptions import RedisError

    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(db_session, event=event)

    class BrokenCache:
        def get(self, key: str):
            raise RedisError("redis no disponible")

        def set(self, key: str, value, ttl_seconds: int = 60) -> bool:
            raise RedisError("redis no disponible")

        def invalidate_prefix(self, prefix: str) -> bool:
            raise RedisError("redis no disponible")

    app.dependency_overrides[get_cache_client] = lambda: BrokenCache()
    try:
        with caplog.at_level(
            logging.WARNING,
            logger="app.registrations.service",
        ):
            listing = client.get(
                "/api/registrations/me",
                headers=_auth_headers(attendee),
            )
            assert listing.status_code == 200
            assert listing.json()["items"] == []

            created = client.post(
                f"/api/events/{event.id}/registrations",
                headers=_auth_headers(attendee),
            )
            assert created.status_code == 201

            session_created = client.post(
                f"/api/events/{event.id}/sessions/{session_row.id}/registrations",
                headers=_auth_headers(attendee),
            )
            assert session_created.status_code == 201

            cancelled = client.delete(
                f"/api/registrations/{created.json()['id']}",
                headers=_auth_headers(attendee),
            )
            assert cancelled.status_code == 204

            after = client.get(
                "/api/registrations/me",
                headers=_auth_headers(attendee),
            )
            assert after.status_code == 200
            assert after.json()["total"] == 2
    finally:
        app.dependency_overrides.pop(get_cache_client, None)

    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    assert warnings
    assert any("Redis" in message for message in warnings)
    assert any("invalidat" in message for message in warnings)


def test_reg_ac_30_errors_use_spanish_detail_and_never_400(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    other = _create_user(db_session, email="other@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=1)
    attendee_headers = _auth_headers(attendee)

    unauthorized = client_no_cache.post(
        f"/api/events/{event.id}/registrations"
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json() == {
        "detail": "No autenticado o sesión expirada"
    }
    assert unauthorized.headers["WWW-Authenticate"] == "Bearer"

    forbidden = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(organizer),
    )
    assert forbidden.status_code == 403
    assert forbidden.json() == {
        "detail": "No tienes permisos para realizar esta acción"
    }

    missing_event = client_no_cache.post(
        "/api/events/999999/registrations",
        headers=attendee_headers,
    )
    assert missing_event.status_code == 404
    assert missing_event.json() == {"detail": "Evento no encontrado"}

    created = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=attendee_headers,
    )
    assert created.status_code == 201
    duplicate = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=attendee_headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Ya estás inscrito en este evento"
    }

    full = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=_auth_headers(other),
    )
    assert full.status_code == 409
    assert full.json() == {
        "detail": "No hay cupos disponibles para este evento"
    }

    invalid_path = client_no_cache.post(
        "/api/events/0/registrations",
        headers=attendee_headers,
    )
    assert invalid_path.status_code == 422
    invalid_path_data = invalid_path.json()
    assert invalid_path_data["detail"] == (
        "Error de validación en los datos enviados"
    )
    assert set(invalid_path_data) == {"detail", "errors"}
    assert any(
        error["field"] == "event_id"
        and "mayor o igual a 1" in error["message"]
        for error in invalid_path_data["errors"]
    )

    invalid_query = client_no_cache.get(
        "/api/registrations/me?status=WRONG&size=99",
        headers=attendee_headers,
    )
    assert invalid_query.status_code == 422
    invalid_query_data = invalid_query.json()
    assert invalid_query_data["detail"] == (
        "Error de validación en los datos enviados"
    )
    assert {error["field"] for error in invalid_query_data["errors"]} == {
        "status",
        "size",
    }
    for error in invalid_query_data["errors"]:
        assert error["message"]
        assert error["message"] != "Valor inválido para este campo"

    missing_registration = client_no_cache.delete(
        "/api/registrations/999999",
        headers=attendee_headers,
    )
    assert missing_registration.status_code == 404
    assert missing_registration.json() == {
        "detail": "Inscripción no encontrada"
    }

    observed_codes = {
        unauthorized.status_code,
        forbidden.status_code,
        missing_event.status_code,
        created.status_code,
        duplicate.status_code,
        full.status_code,
        invalid_path.status_code,
        invalid_query.status_code,
        missing_registration.status_code,
    }
    assert 400 not in observed_codes


def test_reg_ac_31_openapi_declares_registration_routes_schemas_and_codes(
    client: TestClient,
) -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = spec["paths"]

    event_collection = "/api/events/{event_id}/registrations"
    session_collection = (
        "/api/events/{event_id}/sessions/{session_id}/registrations"
    )
    my_collection = "/api/registrations/me"
    detail = "/api/registrations/{id}"

    operations = (
        paths[event_collection]["post"],
        paths[session_collection]["post"],
        paths[event_collection]["get"],
        paths[my_collection]["get"],
        paths[detail]["get"],
        paths[detail]["delete"],
    )
    for operation in operations:
        assert operation["tags"] == ["registrations"]
        response_codes = set(operation["responses"])
        assert {"401", "403", "404", "409", "422"} <= response_codes
        assert "400" not in response_codes

    assert "201" in paths[event_collection]["post"]["responses"]
    assert "200" in paths[event_collection]["post"]["responses"]
    assert "201" in paths[session_collection]["post"]["responses"]
    assert "200" in paths[session_collection]["post"]["responses"]
    assert "204" in paths[detail]["delete"]["responses"]

    for operation in (
        paths[event_collection]["post"],
        paths[session_collection]["post"],
    ):
        assert "requestBody" not in operation

    parameters = paths[event_collection]["post"]["parameters"]
    event_parameter = next(
        parameter
        for parameter in parameters
        if parameter["name"] == "event_id"
    )
    assert event_parameter["schema"]["minimum"] == 1
    assert event_parameter["schema"]["type"] == "integer"

    session_parameters = {
        parameter["name"]: parameter
        for parameter in paths[session_collection]["post"]["parameters"]
    }
    assert session_parameters["event_id"]["schema"]["minimum"] == 1
    assert session_parameters["session_id"]["schema"]["minimum"] == 1
    assert (
        paths[detail]["delete"]["parameters"][0]["schema"]["minimum"] == 1
    )

    schemas = spec["components"]["schemas"]
    for schema_name in (
        "RegistrationRead",
        "RegistrationListRead",
        "RegistrationEventSummary",
        "RegistrationSessionSummary",
    ):
        assert schema_name in schemas
    assert "RegistrationCreate" not in schemas
    assert set(schemas["RegistrationRead"]["properties"]) == {
        "id",
        "user_id",
        "event_id",
        "session_id",
        "status",
        "event",
        "session",
        "created_at",
        "updated_at",
    }
    assert set(schemas["RegistrationListRead"]["properties"]) == {
        "items",
        "total",
        "page",
        "size",
        "pages",
    }
    for personal_field in ("full_name", "email", "password_hash"):
        assert personal_field not in schemas["RegistrationRead"]["properties"]


def test_reg_ac_33_hooks_count_active_rows_without_signature_change(
    client_no_cache: TestClient,
    db_session: DBSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import inspect

    from app.events.service import get_registered_count
    from app.sessions.service import get_session_registered_count

    assert list(inspect.signature(get_registered_count).parameters) == [
        "session",
        "event_id",
    ]
    assert list(
        inspect.signature(get_session_registered_count).parameters
    ) == ["session", "session_id"]

    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    first = _create_user(db_session, email="first@example.com")
    second = _create_user(db_session, email="second@example.com")
    event = _create_event(db_session, organizer=organizer, total_capacity=10)
    first_session = _create_session_row(
        db_session,
        event=event,
        title="Sesión uno",
        start_time=datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc),
        capacity=5,
    )
    second_session = _create_session_row(
        db_session,
        event=event,
        title="Sesión dos",
        start_time=datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc),
        capacity=3,
    )

    _create_registration(db_session, user=first, event=event)
    _create_registration(
        db_session,
        user=first,
        event=event,
        session_row=first_session,
    )
    _create_registration(db_session, user=second, event=event)
    _create_registration(
        db_session,
        user=second,
        event=event,
        session_row=first_session,
    )
    _create_registration(
        db_session,
        user=second,
        event=event,
        session_row=second_session,
    )

    assert get_registered_count(db_session, event.id) == 2
    assert get_session_registered_count(db_session, first_session.id) == 2
    assert get_session_registered_count(db_session, second_session.id) == 1

    event_read = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert event_read.status_code == 200
    assert event_read.json()["registered_count"] == 2
    assert event_read.json()["available_capacity"] == 8

    sessions_read = client_no_cache.get(
        f"/api/events/{event.id}/sessions",
        headers=_auth_headers(organizer),
    )
    assert sessions_read.status_code == 200
    sessions_by_id = {
        item["id"]: item for item in sessions_read.json()["items"]
    }
    assert sessions_by_id[first_session.id]["registered_count"] == 2
    assert sessions_by_id[first_session.id]["available_capacity"] == 3
    assert sessions_by_id[second_session.id]["registered_count"] == 1
    assert sessions_by_id[second_session.id]["available_capacity"] == 2

    overbooked_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento sobrevendido",
        total_capacity=1,
    )
    _create_registration(db_session, user=first, event=overbooked_event)
    _create_registration(db_session, user=second, event=overbooked_event)
    overbooked = client_no_cache.get(
        f"/api/events/{overbooked_event.id}",
        headers=_auth_headers(organizer),
    )
    assert overbooked.json()["registered_count"] == 2
    assert overbooked.json()["available_capacity"] == 0

    monkeypatch.setattr(
        "app.events.service.get_registered_count",
        lambda session, event_id: 3,
    )
    monkeypatched_event = client_no_cache.get(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert monkeypatched_event.json()["registered_count"] == 3
    assert monkeypatched_event.json()["available_capacity"] == 7

    monkeypatch.setattr(
        "app.sessions.service.get_session_registered_count",
        lambda session, session_id: 4,
    )
    monkeypatched_sessions = client_no_cache.get(
        f"/api/events/{event.id}/sessions",
        headers=_auth_headers(organizer),
    )
    monkeypatched_item = next(
        item
        for item in monkeypatched_sessions.json()["items"]
        if item["id"] == first_session.id
    )
    assert monkeypatched_item["registered_count"] == 4
    assert monkeypatched_item["available_capacity"] == 1


def test_reg_ac_34_deleting_event_or_session_cascades_registrations(
    client_no_cache: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(db_session, email="attendee@example.com")
    headers = _auth_headers(attendee)

    # Event with only CANCELLED history: cascade removes every row.
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(db_session, event=event)
    event_registration = client_no_cache.post(
        f"/api/events/{event.id}/registrations",
        headers=headers,
    )
    assert event_registration.status_code == 201
    assert client_no_cache.post(
        f"/api/events/{event.id}/sessions/{session_row.id}/registrations",
        headers=headers,
    ).status_code == 201
    assert client_no_cache.delete(
        f"/api/registrations/{event_registration.json()['id']}",
        headers=headers,
    ).status_code == 204
    assert _count_rows(db_session) == 2

    deleted_event = client_no_cache.delete(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert deleted_event.status_code == 204
    assert _count_rows(db_session) == 0
    assert db_session.exec(
        select(SessionModel.id).where(SessionModel.event_id == event.id)
    ).first() is None

    # Session with only CANCELLED history: cascade removes its rows only.
    second_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento con sesión borrable",
    )
    second_session = _create_session_row(db_session, event=second_event)
    event_registration = client_no_cache.post(
        f"/api/events/{second_event.id}/registrations",
        headers=headers,
    )
    assert event_registration.status_code == 201
    session_registration = client_no_cache.post(
        f"/api/events/{second_event.id}/sessions/{second_session.id}/registrations",
        headers=headers,
    )
    assert session_registration.status_code == 201
    assert client_no_cache.delete(
        f"/api/registrations/{session_registration.json()['id']}",
        headers=headers,
    ).status_code == 204

    deleted_session = client_no_cache.delete(
        f"/api/events/{second_event.id}/sessions/{second_session.id}",
        headers=_auth_headers(organizer),
    )
    assert deleted_session.status_code == 204
    assert db_session.exec(
        select(Registration).where(
            Registration.session_id == second_session.id
        )
    ).first() is None
    remaining = db_session.exec(
        select(Registration).where(
            Registration.event_id == second_event.id
        )
    ).all()
    assert len(remaining) == 1
    assert remaining[0].session_id is None
    assert (
        RegistrationStatus(remaining[0].status)
        == RegistrationStatus.ACTIVE
    )

    # ACTIVE registrations keep the parent-delete guards working.
    protected_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento protegido",
    )
    protected_session = _create_session_row(
        db_session,
        event=protected_event,
    )
    protected_registration = client_no_cache.post(
        f"/api/events/{protected_event.id}/registrations",
        headers=headers,
    )
    assert protected_registration.status_code == 201
    protected_session_registration = client_no_cache.post(
        f"/api/events/{protected_event.id}/sessions/"
        f"{protected_session.id}/registrations",
        headers=headers,
    )
    assert protected_session_registration.status_code == 201

    blocked_event = client_no_cache.delete(
        f"/api/events/{protected_event.id}",
        headers=_auth_headers(organizer),
    )
    assert blocked_event.status_code == 409
    assert blocked_event.json() == {
        "detail": (
            "No se puede eliminar un evento con asistentes inscritos; "
            "cancélalo en su lugar"
        )
    }
    blocked_session = client_no_cache.delete(
        f"/api/events/{protected_event.id}/sessions/{protected_session.id}",
        headers=_auth_headers(organizer),
    )
    assert blocked_session.status_code == 409
    assert blocked_session.json() == {
        "detail": "No se puede eliminar una sesión con asistentes inscritos"
    }
    assert db_session.get(
        Registration,
        protected_registration.json()["id"],
    ) is not None
    assert db_session.get(
        Registration,
        protected_session_registration.json()["id"],
    ) is not None

    # The database-level cascade works without any purge logic in services.
    direct_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento borrado con SQL",
    )
    direct_registration = _create_registration(
        db_session,
        user=attendee,
        event=direct_event,
        status=RegistrationStatus.CANCELLED,
    )
    direct_registration_id = direct_registration.id
    db_session.execute(
        text("DELETE FROM events WHERE id = :event_id"),
        {"event_id": direct_event.id},
    )
    db_session.commit()
    assert db_session.exec(
        select(Registration.id).where(
            Registration.id == direct_registration_id
        )
    ).first() is None
