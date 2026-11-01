from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, inspect
from sqlalchemy.exc import OperationalError
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.auth.security import create_access_token, hash_password
from app.core.config import settings
from app.events.models import Event, EventStatus
from app.sessions.models import Session as SessionModel
from app.sessions.schemas import SessionCreate, SessionUpdate
from app.sessions.service import (
    create_session,
    delete_session,
    update_session,
)
from app.users.models import User, UserRole

EVENT_DATE = datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc)


def _utc(
    year: int,
    month: int,
    day: int,
    hour: int = 14,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


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


def _session_payload(**overrides) -> dict:
    payload = {
        "title": "Apertura y bienvenida",
        "speaker": "Ana Torres",
        "description": "Presentación del programa del día.",
        "start_time": "2026-11-15T15:00:00Z",
        "end_time": "2026-11-15T16:00:00Z",
        "capacity": 80,
    }
    payload.update(overrides)
    return payload


def test_ses_ac_25_postgres_sessions_table_constraints_indexes_and_fk_cascade(
    test_engine,
) -> None:
    inspector = inspect(test_engine)
    assert "sessions" in inspector.get_table_names()

    columns = {
        column["name"]: column
        for column in inspector.get_columns("sessions")
    }
    assert set(columns) == {
        "id",
        "event_id",
        "title",
        "speaker",
        "description",
        "start_time",
        "end_time",
        "capacity",
        "created_at",
        "updated_at",
    }
    for name in (
        "event_id",
        "title",
        "speaker",
        "start_time",
        "end_time",
        "capacity",
        "created_at",
        "updated_at",
    ):
        assert columns[name]["nullable"] is False
    assert columns["description"]["nullable"] is True
    for name in ("start_time", "end_time", "created_at", "updated_at"):
        assert columns[name]["type"].timezone is True

    foreign_keys = inspector.get_foreign_keys("sessions")
    assert len(foreign_keys) == 1
    foreign_key = foreign_keys[0]
    assert foreign_key["name"] == "fk_sessions_event_id_events"
    assert foreign_key["constrained_columns"] == ["event_id"]
    assert foreign_key["referred_table"] == "events"
    assert foreign_key["referred_columns"] == ["id"]
    assert foreign_key["options"].get("ondelete", "").upper() == "CASCADE"

    checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("sessions")
    }
    assert set(checks) == {
        "ck_sessions_time_range",
        "ck_sessions_capacity_positive",
        "ck_sessions_capacity_max",
        "ck_sessions_title_length",
        "ck_sessions_speaker_length",
        "ck_sessions_description_length",
    }
    assert "start_time < end_time" in checks["ck_sessions_time_range"]
    assert "capacity >= 1" in checks["ck_sessions_capacity_positive"]
    assert "capacity <= 100000" in checks["ck_sessions_capacity_max"]
    assert "char_length" in checks["ck_sessions_title_length"]
    assert "160" in checks["ck_sessions_title_length"]
    assert "char_length" in checks["ck_sessions_speaker_length"]
    assert "120" in checks["ck_sessions_speaker_length"]
    assert "description IS NULL" in checks["ck_sessions_description_length"]
    assert "2000" in checks["ck_sessions_description_length"]

    indexes = {
        index["name"]: index for index in inspector.get_indexes("sessions")
    }
    assert indexes["ix_sessions_event_id_start_time"]["column_names"] == [
        "event_id",
        "start_time",
    ]
    assert indexes["ix_sessions_event_id_end_time"]["column_names"] == [
        "event_id",
        "end_time",
    ]

    primary_key = inspector.get_pk_constraint("sessions")
    assert primary_key["constrained_columns"] == ["id"]


def test_ses_ac_01_owner_creates_session_with_defaults_and_capacity_fields(
    client: TestClient,
    db_session: DBSession,
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
    event = _create_event(
        db_session,
        organizer=organizer,
        total_capacity=120,
    )
    payload = _session_payload()

    created = client.post(
        f"/api/events/{event.id}/sessions",
        headers=_auth_headers(organizer),
        json=payload,
    )
    assert created.status_code == 201
    data = created.json()
    assert set(data) == {
        "id",
        "event_id",
        "title",
        "description",
        "speaker",
        "start_time",
        "end_time",
        "capacity",
        "registered_count",
        "available_capacity",
        "created_at",
        "updated_at",
    }
    assert data["event_id"] == event.id
    assert data["title"] == payload["title"]
    assert data["speaker"] == payload["speaker"]
    assert data["description"] == payload["description"]
    assert data["start_time"] == "2026-11-15T15:00:00Z"
    assert data["end_time"] == "2026-11-15T16:00:00Z"
    assert data["capacity"] == 80
    assert data["registered_count"] == 0
    assert data["available_capacity"] == 80
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")

    admin_created = client.post(
        f"/api/events/{event.id}/sessions",
        headers=_auth_headers(admin),
        json=_session_payload(
            title="Sesión creada por admin",
            start_time="2026-11-15T17:00:00Z",
            end_time="2026-11-15T18:00:00Z",
            capacity=30,
        ),
    )
    assert admin_created.status_code == 201
    admin_data = admin_created.json()
    assert admin_data["event_id"] == event.id
    assert admin_data["registered_count"] == 0
    assert admin_data["available_capacity"] == 30



def test_ses_ac_02_validates_text_lengths_normalizes_description_and_forbids_extra_fields(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    headers = _auth_headers(organizer)

    invalid_cases = (
        ({"title": "  ab  "}, "title"),
        ({"title": "x" * 161}, "title"),
        ({"speaker": "a"}, "speaker"),
        ({"speaker": "x" * 121}, "speaker"),
        ({"description": "x" * 2001}, "description"),
    )
    for overrides, field in invalid_cases:
        response = client.post(
            f"/api/events/{event.id}/sessions",
            headers=headers,
            json=_session_payload(**overrides),
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Error de validación en los datos enviados"
        field_errors = [
            error for error in data["errors"] if error["field"] == field
        ]
        assert field_errors
        assert field_errors[0]["message"]

    created = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            title="  Apertura y bienvenida  ",
            speaker="  Ana Torres  ",
            description="   ",
        ),
    )
    assert created.status_code == 201
    created_data = created.json()
    assert created_data["title"] == "Apertura y bienvenida"
    assert created_data["speaker"] == "Ana Torres"
    assert created_data["description"] is None
    session_id = created_data["id"]

    forbidden_fields = {
        "event_id": event.id,
        "id": 1,
        "registered_count": 0,
        "available_capacity": 10,
        "created_at": "2026-11-15T14:00:00Z",
        "updated_at": "2026-11-15T14:00:00Z",
        "unknown_field": "x",
    }
    for field, value in forbidden_fields.items():
        response = client.post(
            f"/api/events/{event.id}/sessions",
            headers=headers,
            json={**_session_payload(), field: value},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Error de validación en los datos enviados"
        assert {
            "field": field,
            "message": "Este campo no está permitido",
        } in data["errors"]

    patch_extra = client.patch(
        f"/api/events/{event.id}/sessions/{session_id}",
        headers=headers,
        json={"title": "Título actualizado", "event_id": event.id},
    )
    assert patch_extra.status_code == 422
    patch_data = patch_extra.json()
    assert patch_data["detail"] == "Error de validación en los datos enviados"
    assert {
        "field": "event_id",
        "message": "Este campo no está permitido",
    } in patch_data["errors"]


def test_ses_ac_03_capacity_bounds_and_event_total_capacity_conflict(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer, total_capacity=100)
    big_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento de gran capacidad",
        total_capacity=100000,
    )
    headers = _auth_headers(organizer)

    minimum = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            capacity=1,
            start_time="2026-11-15T15:00:00Z",
            end_time="2026-11-15T15:30:00Z",
        ),
    )
    assert minimum.status_code == 201
    assert minimum.json()["capacity"] == 1
    assert minimum.json()["available_capacity"] == 1

    maximum = client.post(
        f"/api/events/{big_event.id}/sessions",
        headers=headers,
        json=_session_payload(
            capacity=100000,
            start_time="2026-11-15T16:00:00Z",
            end_time="2026-11-15T17:00:00Z",
        ),
    )
    assert maximum.status_code == 201
    assert maximum.json()["capacity"] == 100000
    assert maximum.json()["available_capacity"] == 100000

    for invalid_capacity in (0, 100001, -5):
        response = client.post(
            f"/api/events/{event.id}/sessions",
            headers=headers,
            json=_session_payload(capacity=invalid_capacity),
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Error de validación en los datos enviados"
        assert any(
            error["field"] == "capacity" and error["message"]
            for error in data["errors"]
        )

    above_event = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(capacity=101),
    )
    assert above_event.status_code == 409
    assert above_event.json() == {
        "detail": (
            "La capacidad de la sesión no puede superar la capacidad total "
            "del evento"
        )
    }


def test_ses_ac_04_rejects_start_time_not_before_end_time(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    headers = _auth_headers(organizer)
    expected_message = "La hora de inicio debe ser anterior a la hora de fin"

    invalid_ranges = (
        ("2026-11-15T16:00:00Z", "2026-11-15T16:00:00Z"),
        ("2026-11-15T17:00:00Z", "2026-11-15T16:00:00Z"),
    )
    for start_time, end_time in invalid_ranges:
        response = client.post(
            f"/api/events/{event.id}/sessions",
            headers=headers,
            json=_session_payload(start_time=start_time, end_time=end_time),
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Error de validación en los datos enviados"
        assert any(
            error["message"] == expected_message for error in data["errors"]
        )

    created = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(),
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    invalid_patches = (
        {
            "start_time": "2026-11-15T17:00:00Z",
            "end_time": "2026-11-15T16:00:00Z",
        },
        {"start_time": "2026-11-15T16:00:00Z"},
        {"end_time": "2026-11-15T15:00:00Z"},
    )
    for body in invalid_patches:
        response = client.patch(
            f"/api/events/{event.id}/sessions/{session_id}",
            headers=headers,
            json=body,
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Error de validación en los datos enviados"
        assert any(
            error["message"] == expected_message for error in data["errors"]
        )


def test_ses_ac_05_rejects_naive_datetimes_and_normalizes_offsets_to_utc(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    headers = _auth_headers(organizer)
    naive_message = "La fecha y hora debe incluir zona horaria (por ejemplo, Z)"

    naive_cases = (
        ("start_time", "2026-11-15T15:00:00"),
        ("end_time", "2026-11-15T16:00:00"),
    )
    for field, value in naive_cases:
        response = client.post(
            f"/api/events/{event.id}/sessions",
            headers=headers,
            json=_session_payload(**{field: value}),
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Error de validación en los datos enviados"
        assert any(
            error["field"] == field and error["message"] == naive_message
            for error in data["errors"]
        )

    created = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T10:00:00-05:00",
            end_time="2026-11-15T11:00:00-05:00",
        ),
    )
    assert created.status_code == 201
    created_data = created.json()
    assert created_data["start_time"] == "2026-11-15T15:00:00Z"
    assert created_data["end_time"] == "2026-11-15T16:00:00Z"
    session_id = created_data["id"]

    naive_patch = client.patch(
        f"/api/events/{event.id}/sessions/{session_id}",
        headers=headers,
        json={"end_time": "2026-11-15T16:30:00"},
    )
    assert naive_patch.status_code == 422
    patch_data = naive_patch.json()
    assert patch_data["detail"] == "Error de validación en los datos enviados"
    assert any(
        error["field"] == "end_time" and error["message"] == naive_message
        for error in patch_data["errors"]
    )

    offset_patch = client.patch(
        f"/api/events/{event.id}/sessions/{session_id}",
        headers=headers,
        json={"end_time": "2026-11-15T11:30:00-05:00"},
    )
    assert offset_patch.status_code == 200
    assert offset_patch.json()["end_time"] == "2026-11-15T16:30:00Z"


def test_ses_ac_06_enforces_event_utc_window_and_rejects_midnight_crossing(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    headers = _auth_headers(organizer)
    window_message = (
        "La sesión debe estar dentro de la fecha UTC del evento y no puede "
        "cruzar la medianoche"
    )

    before_event_date = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T13:00:00Z",
            end_time="2026-11-15T14:00:00Z",
        ),
    )
    assert before_event_date.status_code == 409
    assert before_event_date.json() == {"detail": window_message}

    crossing_midnight = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T23:00:00Z",
            end_time="2026-11-16T00:00:01Z",
        ),
    )
    assert crossing_midnight.status_code == 409
    assert crossing_midnight.json() == {"detail": window_message}

    exact_midnight = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T23:00:00Z",
            end_time="2026-11-16T00:00:00Z",
        ),
    )
    assert exact_midnight.status_code == 201
    assert exact_midnight.json()["end_time"] == "2026-11-16T00:00:00Z"

    created = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(),
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    for body in (
        {"end_time": "2026-11-16T00:00:01Z"},
        {"start_time": "2026-11-15T13:00:00Z"},
    ):
        response = client.patch(
            f"/api/events/{event.id}/sessions/{session_id}",
            headers=headers,
            json=body,
        )
        assert response.status_code == 409
        assert response.json() == {"detail": window_message}

    offset_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento con fecha desplazada",
        date=datetime(
            2026,
            11,
            15,
            23,
            0,
            tzinfo=timezone(timedelta(hours=-5)),
        ),
    )
    offset_valid = client.post(
        f"/api/events/{offset_event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-16T05:00:00Z",
            end_time="2026-11-16T06:00:00Z",
        ),
    )
    assert offset_valid.status_code == 201

    offset_invalid = client.post(
        f"/api/events/{offset_event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T10:00:00Z",
            end_time="2026-11-15T11:00:00Z",
        ),
    )
    assert offset_invalid.status_code == 409
    assert offset_invalid.json() == {"detail": window_message}


def test_ses_ac_07_allows_past_datetimes_inside_event_window(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    past_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento del pasado",
        date=_utc(2000, 1, 1, 0, 0),
        total_capacity=50,
    )
    headers = _auth_headers(organizer)

    created = client.post(
        f"/api/events/{past_event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2000-01-01T01:00:00Z",
            end_time="2000-01-01T02:00:00Z",
            capacity=20,
        ),
    )
    assert created.status_code == 201
    created_data = created.json()
    assert created_data["start_time"] == "2000-01-01T01:00:00Z"
    assert created_data["end_time"] == "2000-01-01T02:00:00Z"
    session_id = created_data["id"]

    patched = client.patch(
        f"/api/events/{past_event.id}/sessions/{session_id}",
        headers=headers,
        json={
            "start_time": "2000-01-01T03:00:00Z",
            "end_time": "2000-01-01T04:00:00Z",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["start_time"] == "2000-01-01T03:00:00Z"
    assert patched.json()["end_time"] == "2000-01-01T04:00:00Z"


def test_ses_ac_08_rejects_overlaps_and_allows_consecutive_sessions(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    other_event = _create_event(
        db_session,
        organizer=organizer,
        title="Otro evento",
    )
    headers = _auth_headers(organizer)
    overlap_message = "La sesión se solapa con otra sesión del evento"

    base = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T15:00:00Z",
            end_time="2026-11-15T16:00:00Z",
        ),
    )
    assert base.status_code == 201

    overlapping_cases = (
        ("2026-11-15T15:00:00Z", "2026-11-15T16:00:00Z"),
        ("2026-11-15T15:30:00Z", "2026-11-15T16:30:00Z"),
        ("2026-11-15T14:30:00Z", "2026-11-15T15:30:00Z"),
        ("2026-11-15T14:00:00Z", "2026-11-15T17:00:00Z"),
    )
    for start_time, end_time in overlapping_cases:
        response = client.post(
            f"/api/events/{event.id}/sessions",
            headers=headers,
            json=_session_payload(
                start_time=start_time,
                end_time=end_time,
            ),
        )
        assert response.status_code == 409
        assert response.json() == {"detail": overlap_message}

    consecutive_after = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T16:00:00Z",
            end_time="2026-11-15T17:00:00Z",
        ),
    )
    assert consecutive_after.status_code == 201

    consecutive_before = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T14:00:00Z",
            end_time="2026-11-15T15:00:00Z",
        ),
    )
    assert consecutive_before.status_code == 201

    same_schedule_other_event = client.post(
        f"/api/events/{other_event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T15:00:00Z",
            end_time="2026-11-15T16:00:00Z",
        ),
    )
    assert same_schedule_other_event.status_code == 201


def test_ses_ac_09_patch_combines_times_excludes_self_and_detects_overlap(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer, total_capacity=100)
    headers = _auth_headers(organizer)
    overlap_message = "La sesión se solapa con otra sesión del evento"
    window_message = (
        "La sesión debe estar dentro de la fecha UTC del evento y no puede "
        "cruzar la medianoche"
    )
    capacity_message = (
        "La capacidad de la sesión no puede superar la capacidad total del "
        "evento"
    )

    first = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T15:00:00Z",
            end_time="2026-11-15T16:00:00Z",
        ),
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            title="Segunda sesión",
            start_time="2026-11-15T17:00:00Z",
            end_time="2026-11-15T18:00:00Z",
        ),
    )
    assert second.status_code == 201
    second_id = second.json()["id"]

    only_start = client.patch(
        f"/api/events/{event.id}/sessions/{first_id}",
        headers=headers,
        json={"start_time": "2026-11-15T15:30:00Z"},
    )
    assert only_start.status_code == 200
    assert only_start.json()["start_time"] == "2026-11-15T15:30:00Z"
    assert only_start.json()["end_time"] == "2026-11-15T16:00:00Z"

    only_end = client.patch(
        f"/api/events/{event.id}/sessions/{first_id}",
        headers=headers,
        json={"end_time": "2026-11-15T16:30:00Z"},
    )
    assert only_end.status_code == 200
    assert only_end.json()["start_time"] == "2026-11-15T15:30:00Z"
    assert only_end.json()["end_time"] == "2026-11-15T16:30:00Z"

    same_schedule = client.patch(
        f"/api/events/{event.id}/sessions/{first_id}",
        headers=headers,
        json={
            "start_time": "2026-11-15T15:30:00Z",
            "end_time": "2026-11-15T16:30:00Z",
        },
    )
    assert same_schedule.status_code == 200

    overlap_from_first = client.patch(
        f"/api/events/{event.id}/sessions/{first_id}",
        headers=headers,
        json={"end_time": "2026-11-15T17:30:00Z"},
    )
    assert overlap_from_first.status_code == 409
    assert overlap_from_first.json() == {"detail": overlap_message}

    overlap_from_second = client.patch(
        f"/api/events/{event.id}/sessions/{second_id}",
        headers=headers,
        json={"start_time": "2026-11-15T16:00:00Z"},
    )
    assert overlap_from_second.status_code == 409
    assert overlap_from_second.json() == {"detail": overlap_message}

    outside_window = client.patch(
        f"/api/events/{event.id}/sessions/{first_id}",
        headers=headers,
        json={"start_time": "2026-11-15T13:00:00Z"},
    )
    assert outside_window.status_code == 409
    assert outside_window.json() == {"detail": window_message}

    above_event_capacity = client.patch(
        f"/api/events/{event.id}/sessions/{first_id}",
        headers=headers,
        json={"capacity": 101},
    )
    assert above_event_capacity.status_code == 409
    assert above_event_capacity.json() == {"detail": capacity_message}


class _NullCache:
    def invalidate_prefix(self, prefix: str) -> bool:
        return True


class ConcurrentSessionRunner:
    """Runs session writes on independent PostgreSQL connections."""

    def __init__(self, engine) -> None:
        self.engine = engine

    def seed_event(
        self,
        *,
        event_date: datetime,
        total_capacity: int = 100,
    ) -> int:
        with self.engine.begin() as connection:
            db = DBSession(bind=connection)
            organizer = User(
                email=f"conc-{uuid4().hex[:12]}@example.com",
                password_hash=hash_password("Test1234!"),
                full_name="Concurrente",
                role=UserRole.ORGANIZER,
            )
            db.add(organizer)
            db.commit()
            db.refresh(organizer)
            event = Event(
                organizer_id=organizer.id,
                title="Evento concurrente",
                description="Descripción suficientemente larga.",
                date=event_date,
                total_capacity=total_capacity,
                status=EventStatus.PUBLISHED.value,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            event_id = event.id
            db.close()
        return int(event_id)

    def run(
        self,
        event_id: int,
        payloads: list[SessionCreate],
    ) -> list[tuple[str, object]]:
        barrier = Barrier(len(payloads))
        outcomes: list[tuple[str, object]] = []

        def worker(payload: SessionCreate) -> None:
            connection = self.engine.connect()
            db = DBSession(bind=connection)
            try:
                event = db.get(Event, event_id)
                barrier.wait(timeout=15)
                try:
                    created = create_session(db, event, payload, _NullCache())
                    outcomes.append(("created", created))
                except HTTPException as exc:
                    db.rollback()
                    outcomes.append(("conflict", exc))
            finally:
                db.close()
                connection.close()

        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            list(pool.map(worker, payloads))
        return outcomes

    def count_sessions(self, event_id: int) -> int:
        with self.engine.connect() as connection:
            db = DBSession(bind=connection)
            try:
                statement = (
                    select(func.count())
                    .select_from(SessionModel)
                    .where(SessionModel.event_id == event_id)
                )
                return int(db.exec(statement).one())
            finally:
                db.close()


    def seed_session(
        self,
        event_id: int,
        *,
        start_time: datetime,
        end_time: datetime,
        title: str = "Sesión concurrente",
        capacity: int = 10,
    ) -> int:
        with self.engine.begin() as connection:
            db = DBSession(bind=connection)
            session_row = SessionModel(
                event_id=event_id,
                title=title,
                speaker="Ana Torres",
                description=None,
                start_time=start_time,
                end_time=end_time,
                capacity=capacity,
            )
            db.add(session_row)
            db.commit()
            db.refresh(session_row)
            session_id = session_row.id
            db.close()
        return int(session_id)

    def run_delete_and_create(
        self,
        event_id: int,
        session_id: int,
        payload: SessionCreate,
    ) -> list[tuple[str, object]]:
        barrier = Barrier(2)
        outcomes: list[tuple[str, object]] = []

        def delete_worker() -> None:
            connection = self.engine.connect()
            db = DBSession(bind=connection)
            try:
                session_row = db.get(SessionModel, session_id)
                barrier.wait(timeout=15)
                try:
                    delete_session(db, session_row, _NullCache())
                    outcomes.append(("deleted", None))
                except HTTPException as exc:
                    db.rollback()
                    outcomes.append(("delete_conflict", exc))
            finally:
                db.close()
                connection.close()

        def create_worker() -> None:
            connection = self.engine.connect()
            db = DBSession(bind=connection)
            try:
                event = db.get(Event, event_id)
                barrier.wait(timeout=15)
                try:
                    created = create_session(db, event, payload, _NullCache())
                    outcomes.append(("created", created))
                except HTTPException as exc:
                    db.rollback()
                    outcomes.append(("conflict", exc))
            finally:
                db.close()
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(delete_worker), pool.submit(create_worker)]
            for future in futures:
                future.result()
        return outcomes

    def run_delete_and_update(
        self,
        event_id: int,
        deleted_session_id: int,
        updated_session_id: int,
        payload: SessionUpdate,
    ) -> list[tuple[str, object]]:
        barrier = Barrier(2)
        outcomes: list[tuple[str, object]] = []

        def delete_worker() -> None:
            connection = self.engine.connect()
            db = DBSession(bind=connection)
            try:
                session_row = db.get(SessionModel, deleted_session_id)
                barrier.wait(timeout=15)
                try:
                    delete_session(db, session_row, _NullCache())
                    outcomes.append(("deleted", None))
                except HTTPException as exc:
                    db.rollback()
                    outcomes.append(("delete_conflict", exc))
            finally:
                db.close()
                connection.close()

        def update_worker() -> None:
            connection = self.engine.connect()
            db = DBSession(bind=connection)
            try:
                session_row = db.get(SessionModel, updated_session_id)
                barrier.wait(timeout=15)
                try:
                    updated = update_session(
                        db,
                        session_row,
                        payload,
                        _NullCache(),
                    )
                    outcomes.append(("updated", updated))
                except HTTPException as exc:
                    db.rollback()
                    outcomes.append(("conflict", exc))
            finally:
                db.close()
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(delete_worker), pool.submit(update_worker)]
            for future in futures:
                future.result()
        return outcomes

    def list_sessions(
        self,
        event_id: int,
    ) -> list[tuple[int, datetime, datetime]]:
        with self.engine.connect() as connection:
            db = DBSession(bind=connection)
            try:
                rows = db.exec(
                    select(SessionModel)
                    .where(SessionModel.event_id == event_id)
                    .order_by(SessionModel.id.asc())
                ).all()
                return [
                    (int(row.id or 0), row.start_time, row.end_time)
                    for row in rows
                ]
            finally:
                db.close()


@pytest.fixture()
def concurrent_sessions(test_engine):
    return ConcurrentSessionRunner(test_engine)


def test_ses_ac_10_concurrent_overlapping_creates_serialize_with_for_update(
    concurrent_sessions: ConcurrentSessionRunner,
    db_truncate,
) -> None:
    event_id = concurrent_sessions.seed_event(event_date=EVENT_DATE)
    payloads = [
        SessionCreate.model_validate(
            _session_payload(
                start_time="2026-11-15T15:00:00Z",
                end_time="2026-11-15T16:00:00Z",
            )
        ),
        SessionCreate.model_validate(
            _session_payload(
                start_time="2026-11-15T15:30:00Z",
                end_time="2026-11-15T16:30:00Z",
            )
        ),
    ]

    outcomes = concurrent_sessions.run(event_id, payloads)

    assert sorted(kind for kind, _ in outcomes) == ["conflict", "created"]
    conflict = next(
        value for kind, value in outcomes if kind == "conflict"
    )
    assert conflict.status_code == 409
    assert conflict.detail == (
        "La sesión se solapa con otra sesión del evento"
    )
    created = next(value for kind, value in outcomes if kind == "created")
    assert created.event_id == event_id
    assert concurrent_sessions.count_sessions(event_id) == 1


def _create_session_row(
    session: DBSession,
    *,
    event: Event,
    title: str = "Sesión base",
    speaker: str = "Ana Torres",
    description: str | None = None,
    start_time: datetime,
    end_time: datetime,
    capacity: int = 20,
) -> SessionModel:
    session_row = SessionModel(
        event_id=event.id,
        title=title,
        speaker=speaker,
        description=description,
        start_time=start_time,
        end_time=end_time,
        capacity=capacity,
    )
    session.add(session_row)
    session.commit()
    session.refresh(session_row)
    return session_row


def test_ses_ac_11_lists_sessions_ordered_by_start_time_and_id_without_pagination(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    empty_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento sin sesiones",
    )
    headers = _auth_headers(organizer)

    empty_listing = client.get(f"/api/events/{empty_event.id}/sessions")
    assert empty_listing.status_code == 200
    assert empty_listing.json() == {"items": [], "total": 0}

    same_start_first = _create_session_row(
        db_session,
        event=event,
        title="Mismo inicio A",
        start_time=_utc(2026, 11, 15, 16, 0),
        end_time=_utc(2026, 11, 15, 16, 15),
    )
    same_start_second = _create_session_row(
        db_session,
        event=event,
        title="Mismo inicio B",
        start_time=_utc(2026, 11, 15, 16, 0),
        end_time=_utc(2026, 11, 15, 16, 45),
    )

    late = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            title="Sesion tardia",
            start_time="2026-11-15T17:00:00Z",
            end_time="2026-11-15T18:00:00Z",
        ),
    )
    assert late.status_code == 201

    early = client.post(
        f"/api/events/{event.id}/sessions",
        headers=headers,
        json=_session_payload(
            title="Sesion temprana",
            start_time="2026-11-15T15:00:00Z",
            end_time="2026-11-15T15:30:00Z",
        ),
    )
    assert early.status_code == 201

    listing = client.get(
        f"/api/events/{event.id}/sessions?page=2&size=1",
        headers=headers,
    )
    assert listing.status_code == 200
    data = listing.json()
    assert set(data) == {"items", "total"}
    assert data["total"] == 4
    assert [item["id"] for item in data["items"]] == [
        early.json()["id"],
        same_start_first.id,
        same_start_second.id,
        late.json()["id"],
    ]
    assert [item["title"] for item in data["items"]] == [
        "Sesion temprana",
        "Mismo inicio A",
        "Mismo inicio B",
        "Sesion tardia",
    ]
    first_item = data["items"][0]
    assert first_item["registered_count"] == 0
    assert first_item["available_capacity"] == first_item["capacity"]
    assert first_item["start_time"].endswith("Z")


def test_ses_ac_12_nested_detail_returns_session_or_404_for_foreign_session(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    other_event = _create_event(
        db_session,
        organizer=organizer,
        title="Otro evento publicado",
    )
    draft_event = _create_event(
        db_session,
        organizer=organizer,
        title="Borrador",
        status=EventStatus.DRAFT,
    )
    session_row = _create_session_row(
        db_session,
        event=event,
        title="Sesión publicada",
        description="Descripción de la sesión.",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    foreign_row = _create_session_row(
        db_session,
        event=other_event,
        title="Sesión de otro evento",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    draft_row = _create_session_row(
        db_session,
        event=draft_event,
        title="Sesión de borrador",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )

    detail = client.get(
        f"/api/events/{event.id}/sessions/{session_row.id}"
    )
    assert detail.status_code == 200
    data = detail.json()
    assert data["id"] == session_row.id
    assert data["event_id"] == event.id
    assert data["title"] == "Sesión publicada"
    assert data["description"] == "Descripción de la sesión."
    assert data["speaker"] == "Ana Torres"
    assert data["start_time"] == "2026-11-15T15:00:00Z"
    assert data["end_time"] == "2026-11-15T16:00:00Z"
    assert data["capacity"] == 20
    assert data["registered_count"] == 0
    assert data["available_capacity"] == 20
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")

    foreign = client.get(
        f"/api/events/{event.id}/sessions/{foreign_row.id}"
    )
    assert foreign.status_code == 404
    assert foreign.json() == {"detail": "Sesión no encontrada"}

    missing_session = client.get(
        f"/api/events/{event.id}/sessions/999999"
    )
    assert missing_session.status_code == 404
    assert missing_session.json() == {"detail": "Sesión no encontrada"}

    missing_event = client.get(f"/api/events/999999/sessions/1")
    assert missing_event.status_code == 404
    assert missing_event.json() == {"detail": "Evento no encontrado"}

    hidden_draft = client.get(
        f"/api/events/{draft_event.id}/sessions/{draft_row.id}"
    )
    assert hidden_draft.status_code == 404
    assert hidden_draft.json() == {"detail": "Evento no encontrado"}

    invalid_session_id = client.get(
        f"/api/events/{event.id}/sessions/0"
    )
    assert invalid_session_id.status_code == 422
    assert any(
        error["field"] == "session_id"
        for error in invalid_session_id.json()["errors"]
    )

    invalid_event_id = client.get("/api/events/0/sessions/1")
    assert invalid_event_id.status_code == 422
    assert any(
        error["field"] == "event_id"
        for error in invalid_event_id.json()["errors"]
    )


def test_ses_ac_13_anonymous_and_attendee_read_only_published_event_sessions(
    client: TestClient,
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
        role=UserRole.ATTENDEE,
    )
    events = {
        "PUBLISHED": _create_event(
            db_session,
            organizer=organizer,
            title="Evento publicado",
            status=EventStatus.PUBLISHED,
        ),
        "DRAFT": _create_event(
            db_session,
            organizer=organizer,
            title="Evento borrador",
            status=EventStatus.DRAFT,
        ),
        "CANCELLED": _create_event(
            db_session,
            organizer=organizer,
            title="Evento cancelado",
            status=EventStatus.CANCELLED,
        ),
    }
    sessions = {
        status: _create_session_row(
            db_session,
            event=event,
            title=f"Sesión {status}",
            start_time=_utc(2026, 11, 15, 15, 0),
            end_time=_utc(2026, 11, 15, 16, 0),
        )
        for status, event in events.items()
    }

    for headers in ({}, _auth_headers(attendee)):
        published_list = client.get(
            f"/api/events/{events['PUBLISHED'].id}/sessions",
            headers=headers,
        )
        assert published_list.status_code == 200
        listing = published_list.json()
        assert listing["total"] == 1
        assert [item["id"] for item in listing["items"]] == [
            sessions["PUBLISHED"].id
        ]

        published_detail = client.get(
            f"/api/events/{events['PUBLISHED'].id}/sessions/"
            f"{sessions['PUBLISHED'].id}",
            headers=headers,
        )
        assert published_detail.status_code == 200
        assert published_detail.json()["id"] == sessions["PUBLISHED"].id

        for hidden_status in ("DRAFT", "CANCELLED"):
            hidden_event = events[hidden_status]
            hidden_session = sessions[hidden_status]
            hidden_list = client.get(
                f"/api/events/{hidden_event.id}/sessions",
                headers=headers,
            )
            assert hidden_list.status_code == 404
            assert hidden_list.json() == {"detail": "Evento no encontrado"}

            hidden_detail = client.get(
                f"/api/events/{hidden_event.id}/sessions/{hidden_session.id}",
                headers=headers,
            )
            assert hidden_detail.status_code == 404
            assert hidden_detail.json() == {"detail": "Evento no encontrado"}

    invalid_token = {"Authorization": "Bearer token-invalido"}
    invalid_list = client.get(
        f"/api/events/{events['PUBLISHED'].id}/sessions",
        headers=invalid_token,
    )
    assert invalid_list.status_code == 401
    assert invalid_list.json() == {
        "detail": "No autenticado o sesión expirada"
    }
    assert invalid_list.headers["WWW-Authenticate"] == "Bearer"

    invalid_detail = client.get(
        f"/api/events/{events['PUBLISHED'].id}/sessions/"
        f"{sessions['PUBLISHED'].id}",
        headers=invalid_token,
    )
    assert invalid_detail.status_code == 401
    assert invalid_detail.json() == {
        "detail": "No autenticado o sesión expirada"
    }


def test_ses_ac_14_organizer_reads_published_plus_own_event_sessions(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    other_organizer = _create_user(
        db_session,
        email="other@example.com",
        role=UserRole.ORGANIZER,
    )
    events = {
        ("own", "DRAFT"): _create_event(
            db_session,
            organizer=organizer,
            title="Borrador propio",
            status=EventStatus.DRAFT,
        ),
        ("own", "CANCELLED"): _create_event(
            db_session,
            organizer=organizer,
            title="Cancelado propio",
            status=EventStatus.CANCELLED,
        ),
        ("own", "PUBLISHED"): _create_event(
            db_session,
            organizer=organizer,
            title="Publicado propio",
            status=EventStatus.PUBLISHED,
        ),
        ("other", "DRAFT"): _create_event(
            db_session,
            organizer=other_organizer,
            title="Borrador ajeno",
            status=EventStatus.DRAFT,
        ),
        ("other", "CANCELLED"): _create_event(
            db_session,
            organizer=other_organizer,
            title="Cancelado ajeno",
            status=EventStatus.CANCELLED,
        ),
        ("other", "PUBLISHED"): _create_event(
            db_session,
            organizer=other_organizer,
            title="Publicado ajeno",
            status=EventStatus.PUBLISHED,
        ),
    }
    sessions = {
        key: _create_session_row(
            db_session,
            event=event,
            title=f"Sesión {key[0]} {key[1]}",
            start_time=_utc(2026, 11, 15, 15, 0),
            end_time=_utc(2026, 11, 15, 16, 0),
        )
        for key, event in events.items()
    }
    headers = _auth_headers(organizer)

    for key in (
        ("own", "DRAFT"),
        ("own", "CANCELLED"),
        ("own", "PUBLISHED"),
        ("other", "PUBLISHED"),
    ):
        listing = client.get(
            f"/api/events/{events[key].id}/sessions",
            headers=headers,
        )
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()["items"]] == [
            sessions[key].id
        ]

        detail = client.get(
            f"/api/events/{events[key].id}/sessions/{sessions[key].id}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["id"] == sessions[key].id

    for key in (("other", "DRAFT"), ("other", "CANCELLED")):
        hidden_list = client.get(
            f"/api/events/{events[key].id}/sessions",
            headers=headers,
        )
        assert hidden_list.status_code == 404
        assert hidden_list.json() == {"detail": "Evento no encontrado"}

        hidden_detail = client.get(
            f"/api/events/{events[key].id}/sessions/{sessions[key].id}",
            headers=headers,
        )
        assert hidden_detail.status_code == 404
        assert hidden_detail.json() == {"detail": "Evento no encontrado"}


def test_ses_ac_15_admin_reads_sessions_of_any_event_state(
    client: TestClient,
    db_session: DBSession,
) -> None:
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    events = {
        status: _create_event(
            db_session,
            organizer=organizer,
            title=f"Evento {status}",
            status=status,
        )
        for status in (
            EventStatus.DRAFT,
            EventStatus.PUBLISHED,
            EventStatus.CANCELLED,
        )
    }
    sessions = {
        status: _create_session_row(
            db_session,
            event=event,
            title=f"Sesión {status.value}",
            start_time=_utc(2026, 11, 15, 15, 0),
            end_time=_utc(2026, 11, 15, 16, 0),
        )
        for status, event in events.items()
    }
    headers = _auth_headers(admin)

    for status, event in events.items():
        listing = client.get(
            f"/api/events/{event.id}/sessions",
            headers=headers,
        )
        assert listing.status_code == 200
        listing_data = listing.json()
        assert listing_data["total"] == 1
        assert [item["id"] for item in listing_data["items"]] == [
            sessions[status].id
        ]

        detail = client.get(
            f"/api/events/{event.id}/sessions/{sessions[status].id}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["id"] == sessions[status].id
        assert detail.json()["event_id"] == event.id


def test_ses_ac_16_writes_require_valid_token_and_owner_or_admin(
    client: TestClient,
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
        role=UserRole.ATTENDEE,
    )
    other_organizer = _create_user(
        db_session,
        email="other@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(
        db_session,
        event=event,
        title="Sesión protegida",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    base = f"/api/events/{event.id}/sessions"
    detail = f"{base}/{session_row.id}"
    payload = _session_payload(
        title="Sesión nueva",
        start_time="2026-11-15T17:00:00Z",
        end_time="2026-11-15T18:00:00Z",
    )

    unauthenticated_calls = (
        client.post(base, json=payload),
        client.patch(detail, json={"title": "Intento sin token"}),
        client.delete(detail),
    )
    for response in unauthenticated_calls:
        assert response.status_code == 401
        assert response.json() == {
            "detail": "No autenticado o sesión expirada"
        }
        assert response.headers["WWW-Authenticate"] == "Bearer"

    invalid_token_calls = (
        client.post(
            base,
            headers={"Authorization": "Bearer token-invalido"},
            json=payload,
        ),
        client.patch(
            detail,
            headers={"Authorization": "Bearer token-invalido"},
            json={"title": "Intento inválido"},
        ),
        client.delete(
            detail,
            headers={"Authorization": "Bearer token-invalido"},
        ),
    )
    for response in invalid_token_calls:
        assert response.status_code == 401
        assert response.json() == {
            "detail": "No autenticado o sesión expirada"
        }

    for headers in (_auth_headers(attendee), _auth_headers(other_organizer)):
        forbidden_calls = (
            client.post(base, headers=headers, json=payload),
            client.patch(detail, headers=headers, json={"title": "Ajeno"}),
            client.delete(detail, headers=headers),
        )
        for response in forbidden_calls:
            assert response.status_code == 403
            assert response.json() == {
                "detail": "No tienes permisos para realizar esta acción"
            }

    db_session.refresh(session_row)
    assert session_row.title == "Sesión protegida"


def test_ses_ac_17_allows_writes_on_draft_and_published_events(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    headers = _auth_headers(organizer)

    for status in (EventStatus.DRAFT, EventStatus.PUBLISHED):
        event = _create_event(
            db_session,
            organizer=organizer,
            title=f"Evento {status.value}",
            status=status,
        )
        base = f"/api/events/{event.id}/sessions"

        created = client.post(
            base,
            headers=headers,
            json=_session_payload(
                title=f"Sesión en {status.value}",
                start_time="2026-11-15T15:00:00Z",
                end_time="2026-11-15T16:00:00Z",
            ),
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        patched = client.patch(
            f"{base}/{session_id}",
            headers=headers,
            json={"title": "Título editado"},
        )
        assert patched.status_code == 200
        assert patched.json()["title"] == "Título editado"

        deleted = client.delete(f"{base}/{session_id}", headers=headers)
        assert deleted.status_code == 204
        assert deleted.content == b""


def test_ses_ac_18_cancelled_event_blocks_all_session_writes_with_409(
    client: TestClient,
    db_session: DBSession,
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
    other_organizer = _create_user(
        db_session,
        email="other@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento cancelado",
        status=EventStatus.CANCELLED,
    )
    session_row = _create_session_row(
        db_session,
        event=event,
        title="Sesión cancelada",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    base = f"/api/events/{event.id}/sessions"
    detail = f"{base}/{session_row.id}"
    cancelled_message = (
        "Un evento cancelado no permite modificar sus sesiones"
    )

    for headers in (_auth_headers(organizer), _auth_headers(admin)):
        post_response = client.post(
            base,
            headers=headers,
            json=_session_payload(
                title="Nueva sesión",
                start_time="2026-11-15T17:00:00Z",
                end_time="2026-11-15T18:00:00Z",
            ),
        )
        assert post_response.status_code == 409
        assert post_response.json() == {"detail": cancelled_message}

        patch_response = client.patch(
            detail,
            headers=headers,
            json={"title": "Intento de edición"},
        )
        assert patch_response.status_code == 409
        assert patch_response.json() == {"detail": cancelled_message}

        delete_response = client.delete(detail, headers=headers)
        assert delete_response.status_code == 409
        assert delete_response.json() == {"detail": cancelled_message}

    empty_patch = client.patch(
        detail,
        headers=_auth_headers(organizer),
        json={},
    )
    assert empty_patch.status_code == 409
    assert empty_patch.json() == {"detail": cancelled_message}

    owner_listing = client.get(base, headers=_auth_headers(organizer))
    assert owner_listing.status_code == 200
    assert owner_listing.json()["total"] == 1

    db_session.refresh(session_row)
    assert session_row.title == "Sesión cancelada"

    foreign_headers = _auth_headers(other_organizer)
    foreign_post = client.post(
        base,
        headers=foreign_headers,
        json=_session_payload(),
    )
    assert foreign_post.status_code == 403
    assert foreign_post.json() == {
        "detail": "No tienes permisos para realizar esta acción"
    }
    foreign_patch = client.patch(
        detail,
        headers=foreign_headers,
        json={"title": "Ajeno"},
    )
    assert foreign_patch.status_code == 403
    foreign_delete = client.delete(detail, headers=foreign_headers)
    assert foreign_delete.status_code == 403


def test_ses_ac_19_delete_session_returns_204_and_removes_row(
    client: TestClient,
    db_session: DBSession,
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
    event = _create_event(db_session, organizer=organizer)
    first = _create_session_row(
        db_session,
        event=event,
        title="Sesión a borrar",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    second = _create_session_row(
        db_session,
        event=event,
        title="Sesión borrada por admin",
        start_time=_utc(2026, 11, 15, 17, 0),
        end_time=_utc(2026, 11, 15, 18, 0),
    )
    base = f"/api/events/{event.id}/sessions"

    deleted = client.delete(
        f"{base}/{first.id}",
        headers=_auth_headers(organizer),
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert db_session.get(SessionModel, first.id) is None

    detail = client.get(f"{base}/{first.id}")
    assert detail.status_code == 404
    assert detail.json() == {"detail": "Sesión no encontrada"}

    admin_deleted = client.delete(
        f"{base}/{second.id}",
        headers=_auth_headers(admin),
    )
    assert admin_deleted.status_code == 204
    assert db_session.get(SessionModel, second.id) is None


def test_ses_ac_19_delete_session_with_registrations_is_conflict_and_hook_defaults_to_zero(
    client: TestClient,
    db_session: DBSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    deletable = _create_session_row(
        db_session,
        event=event,
        title="Sesión sin inscritos",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    protected = _create_session_row(
        db_session,
        event=event,
        title="Sesión con inscritos",
        start_time=_utc(2026, 11, 15, 17, 0),
        end_time=_utc(2026, 11, 15, 18, 0),
        capacity=20,
    )
    base = f"/api/events/{event.id}/sessions"
    headers = _auth_headers(organizer)

    from app.sessions.service import get_session_registered_count

    assert get_session_registered_count(db_session, protected.id) == 0

    default_delete = client.delete(
        f"{base}/{deletable.id}",
        headers=headers,
    )
    assert default_delete.status_code == 204
    assert db_session.get(SessionModel, deletable.id) is None

    monkeypatch.setattr(
        "app.sessions.service.get_session_registered_count",
        lambda session, session_id: 3,
    )

    with_registrations = client.delete(
        f"{base}/{protected.id}",
        headers=headers,
    )
    assert with_registrations.status_code == 409
    assert with_registrations.json() == {
        "detail": "No se puede eliminar una sesión con asistentes inscritos"
    }
    assert db_session.get(SessionModel, protected.id) is not None

    reduction = client.patch(
        f"{base}/{protected.id}",
        headers=headers,
        json={"capacity": 2},
    )
    assert reduction.status_code == 409
    assert reduction.json() == {
        "detail": (
            "No se puede reducir la capacidad de la sesión por debajo del "
            "número de inscritos actuales"
        )
    }

    detail = client.get(f"{base}/{protected.id}")
    assert detail.status_code == 200
    detail_data = detail.json()
    assert detail_data["registered_count"] == 3
    assert detail_data["available_capacity"] == 17

    listing = client.get(base)
    assert listing.status_code == 200
    listed = listing.json()["items"][0]
    assert listed["registered_count"] == 3
    assert listed["available_capacity"] == 17


def test_ses_ac_21_timestamps_are_utc_and_event_id_is_immutable(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    other_event = _create_event(
        db_session,
        organizer=organizer,
        title="Otro evento",
    )
    headers = _auth_headers(organizer)
    old_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)

    session_row = SessionModel(
        event_id=event.id,
        title="Sesión base",
        speaker="Ana Torres",
        description=None,
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
        capacity=20,
        created_at=old_timestamp,
        updated_at=old_timestamp,
    )
    db_session.add(session_row)
    db_session.commit()
    db_session.refresh(session_row)

    patched = client.patch(
        f"/api/events/{event.id}/sessions/{session_row.id}",
        headers=headers,
        json={"title": "Sesión base"},
    )
    assert patched.status_code == 200
    data = patched.json()
    assert data["event_id"] == event.id
    assert data["created_at"] == "2026-01-01T00:00:00Z"
    assert data["updated_at"] != "2026-01-01T00:00:00Z"
    assert data["updated_at"].endswith("Z")
    assert data["created_at"].endswith("Z")

    forbidden_event_id = client.patch(
        f"/api/events/{event.id}/sessions/{session_row.id}",
        headers=headers,
        json={"event_id": other_event.id},
    )
    assert forbidden_event_id.status_code == 422
    assert forbidden_event_id.json()["detail"] == (
        "Error de validación en los datos enviados"
    )
    assert {
        "field": "event_id",
        "message": "Este campo no está permitido",
    } in forbidden_event_id.json()["errors"]

    created = client.post(
        f"/api/events/{other_event.id}/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T15:00:00Z",
            end_time="2026-11-15T16:00:00Z",
        ),
    )
    assert created.status_code == 201
    created_data = created.json()
    assert created_data["event_id"] == other_event.id
    assert created_data["created_at"].endswith("Z")
    assert created_data["updated_at"].endswith("Z")

    detail = client.get(
        f"/api/events/{event.id}/sessions/{session_row.id}"
    )
    assert detail.status_code == 200
    assert detail.json()["event_id"] == event.id
    assert detail.json()["created_at"] == "2026-01-01T00:00:00Z"


def test_ses_ac_22_validation_errors_use_spanish_detail_and_empty_patch_message(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    headers = _auth_headers(organizer)
    session_row = _create_session_row(
        db_session,
        event=event,
        title="Sesión con descripción",
        description="Descripción inicial",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    base = f"/api/events/{event.id}/sessions"
    detail = f"{base}/{session_row.id}"
    validation_detail = "Error de validación en los datos enviados"

    empty_patch = client.patch(detail, headers=headers, json={})
    assert empty_patch.status_code == 422
    empty_data = empty_patch.json()
    assert empty_data["detail"] == validation_detail
    assert set(empty_data) == {"detail", "errors"}
    assert {
        "field": "body",
        "message": "Debes indicar al menos un campo para actualizar",
    } in empty_data["errors"]

    for field in ("title", "speaker", "start_time", "end_time", "capacity"):
        null_patch = client.patch(
            detail,
            headers=headers,
            json={field: None},
        )
        assert null_patch.status_code == 422
        assert null_patch.json()["detail"] == validation_detail

    clear_description = client.patch(
        detail,
        headers=headers,
        json={"description": None},
    )
    assert clear_description.status_code == 200
    assert clear_description.json()["description"] is None

    missing_session = client.get(f"{base}/999999")
    assert missing_session.status_code == 404
    assert missing_session.json() == {"detail": "Sesión no encontrada"}
    assert set(missing_session.json()) == {"detail"}

    overlap = client.post(
        base,
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T15:30:00Z",
            end_time="2026-11-15T16:30:00Z",
        ),
    )
    assert overlap.status_code == 409
    assert overlap.json() == {
        "detail": "La sesión se solapa con otra sesión del evento"
    }
    assert set(overlap.json()) == {"detail"}

    invalid_body = client.post(
        base,
        headers=headers,
        json={**_session_payload(), "event_id": event.id},
    )
    assert invalid_body.status_code == 422
    assert invalid_body.json()["detail"] == validation_detail
    assert set(invalid_body.json()) == {"detail", "errors"}
    for error in invalid_body.json()["errors"]:
        assert set(error) == {"field", "message"}

    unauthorized = client.post(base, json=_session_payload())
    assert unauthorized.status_code == 401
    assert set(unauthorized.json()) == {"detail"}

    observed_codes = {
        empty_patch.status_code,
        missing_session.status_code,
        overlap.status_code,
        invalid_body.status_code,
        unauthorized.status_code,
    }
    assert 400 not in observed_codes


def test_ses_ac_23_openapi_declares_sessions_routes_schemas_and_error_codes(
    client: TestClient,
) -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = spec["paths"]

    collection = "/api/events/{event_id}/sessions"
    detail = "/api/events/{event_id}/sessions/{session_id}"
    assert "get" in paths[collection]
    assert "post" in paths[collection]
    assert "get" in paths[detail]
    assert "patch" in paths[detail]
    assert "delete" in paths[detail]

    operations = (
        paths[collection]["get"],
        paths[collection]["post"],
        paths[detail]["get"],
        paths[detail]["patch"],
        paths[detail]["delete"],
    )
    for operation in operations:
        assert "sessions" in operation["tags"]
        response_codes = set(operation["responses"])
        assert {"401", "403", "404", "409", "422"} <= response_codes
        assert "400" not in response_codes

    assert "204" in paths[detail]["delete"]["responses"]

    schemas = spec["components"]["schemas"]
    for schema_name in (
        "SessionCreate",
        "SessionUpdate",
        "SessionRead",
        "SessionListRead",
    ):
        assert schema_name in schemas

    assert set(schemas["SessionRead"]["properties"]) == {
        "id",
        "event_id",
        "title",
        "description",
        "speaker",
        "start_time",
        "end_time",
        "capacity",
        "registered_count",
        "available_capacity",
        "created_at",
        "updated_at",
    }
    assert set(schemas["SessionListRead"]["properties"]) == {
        "items",
        "total",
    }


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


def test_ses_ac_24_session_writes_invalidate_events_cache_and_tolerate_redis_failure(
    client: TestClient,
    db_session: DBSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from redis.exceptions import RedisError

    from app.core.cache import get_cache_client
    from app.main import app

    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    headers = _auth_headers(organizer)
    base = f"/api/events/{event.id}/sessions"

    fake_cache = FakeCache()
    app.dependency_overrides[get_cache_client] = lambda: fake_cache
    try:
        listing = client.get(base)
        assert listing.status_code == 200
        assert fake_cache.set_calls == []

        created = client.post(
            base,
            headers=headers,
            json=_session_payload(
                start_time="2026-11-15T15:00:00Z",
                end_time="2026-11-15T16:00:00Z",
            ),
        )
        assert created.status_code == 201
        assert "events:" in fake_cache.invalidated
        session_id = created.json()["id"]

        invalidations_before_patch = len(fake_cache.invalidated)
        patched = client.patch(
            f"{base}/{session_id}",
            headers=headers,
            json={"title": "Título con caché"},
        )
        assert patched.status_code == 200
        assert len(fake_cache.invalidated) == invalidations_before_patch + 1
        assert fake_cache.invalidated[-1] == "events:"

        invalidations_before_delete = len(fake_cache.invalidated)
        deleted = client.delete(f"{base}/{session_id}", headers=headers)
        assert deleted.status_code == 204
        assert len(fake_cache.invalidated) == invalidations_before_delete + 1
        assert fake_cache.invalidated[-1] == "events:"
        assert fake_cache.set_calls == []
    finally:
        app.dependency_overrides.pop(get_cache_client, None)

    class BrokenCache:
        def get(self, key: str):
            return None

        def set(self, key: str, value, ttl_seconds: int = 60) -> bool:
            return False

        def invalidate_prefix(self, prefix: str) -> bool:
            raise RedisError("redis no disponible")

    broken_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento con Redis caído",
    )
    broken_base = f"/api/events/{broken_event.id}/sessions"
    app.dependency_overrides[get_cache_client] = lambda: BrokenCache()
    try:
        with caplog.at_level(
            logging.WARNING,
            logger="app.sessions.service",
        ):
            created = client.post(
                broken_base,
                headers=headers,
                json=_session_payload(
                    start_time="2026-11-15T15:00:00Z",
                    end_time="2026-11-15T16:00:00Z",
                ),
            )
            assert created.status_code == 201
            session_id = created.json()["id"]

            patched = client.patch(
                f"{broken_base}/{session_id}",
                headers=headers,
                json={"title": "Sin Redis"},
            )
            assert patched.status_code == 200

            deleted = client.delete(
                f"{broken_base}/{session_id}",
                headers=headers,
            )
            assert deleted.status_code == 204
    finally:
        app.dependency_overrides.pop(get_cache_client, None)

    assert any(
        "invalidate_prefix" in record.getMessage()
        for record in caplog.records
    )


def test_ses_ac_20_deleting_event_cascades_sessions(
    client: TestClient,
    db_session: DBSession,
) -> None:
    from sqlalchemy import text

    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    first = _create_session_row(
        db_session,
        event=event,
        title="Sesión cascada A",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    second = _create_session_row(
        db_session,
        event=event,
        title="Sesión cascada B",
        start_time=_utc(2026, 11, 15, 17, 0),
        end_time=_utc(2026, 11, 15, 18, 0),
    )

    def count_sessions(event_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.event_id == event_id)
        )
        return int(db_session.exec(statement).one())

    event_id = event.id
    first_id = first.id
    second_id = second.id

    assert count_sessions(event_id) == 2

    deleted = client.delete(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
    )
    assert deleted.status_code == 204
    assert count_sessions(event_id) == 0
    assert db_session.exec(
        select(SessionModel.id).where(SessionModel.id == first_id)
    ).first() is None
    assert db_session.exec(
        select(SessionModel.id).where(SessionModel.id == second_id)
    ).first() is None

    direct_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento borrado con SQL",
    )
    direct_session = _create_session_row(
        db_session,
        event=direct_event,
        title="Sesión borrada con SQL",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    direct_event_id = direct_event.id
    direct_session_id = direct_session.id
    db_session.execute(
        text("DELETE FROM events WHERE id = :event_id"),
        {"event_id": direct_event_id},
    )
    db_session.commit()
    assert count_sessions(direct_event_id) == 0
    assert db_session.exec(
        select(SessionModel.id).where(
            SessionModel.id == direct_session_id
        )
    ).first() is None


def test_ses_ac_29_patch_and_delete_return_404_for_foreign_or_missing_session(
    client: TestClient,
    db_session: DBSession,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    other_event = _create_event(
        db_session,
        organizer=organizer,
        title="Otro evento",
    )
    own_session = _create_session_row(
        db_session,
        event=event,
        title="Sesión propia",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    foreign_session = _create_session_row(
        db_session,
        event=other_event,
        title="Sesión ajena",
        start_time=_utc(2026, 11, 15, 17, 0),
        end_time=_utc(2026, 11, 15, 18, 0),
    )
    own_updated_at = own_session.updated_at
    foreign_updated_at = foreign_session.updated_at
    headers = _auth_headers(organizer)
    base = f"/api/events/{event.id}/sessions"

    foreign_patch = client.patch(
        f"{base}/{foreign_session.id}",
        headers=headers,
        json={"title": "Intento sobre sesión ajena"},
    )
    assert foreign_patch.status_code == 404
    assert foreign_patch.json() == {"detail": "Sesión no encontrada"}

    foreign_delete = client.delete(
        f"{base}/{foreign_session.id}",
        headers=headers,
    )
    assert foreign_delete.status_code == 404
    assert foreign_delete.json() == {"detail": "Sesión no encontrada"}

    missing_patch = client.patch(
        f"{base}/999999",
        headers=headers,
        json={"title": "Sesión inexistente"},
    )
    assert missing_patch.status_code == 404
    assert missing_patch.json() == {"detail": "Sesión no encontrada"}

    missing_delete = client.delete(f"{base}/999999", headers=headers)
    assert missing_delete.status_code == 404
    assert missing_delete.json() == {"detail": "Sesión no encontrada"}

    missing_event_patch = client.patch(
        f"/api/events/999999/sessions/{own_session.id}",
        headers=headers,
        json={"title": "Evento inexistente"},
    )
    assert missing_event_patch.status_code == 404
    assert missing_event_patch.json() == {"detail": "Evento no encontrado"}

    missing_event_delete = client.delete(
        f"/api/events/999999/sessions/{own_session.id}",
        headers=headers,
    )
    assert missing_event_delete.status_code == 404
    assert missing_event_delete.json() == {
        "detail": "Evento no encontrado"
    }

    missing_event_post = client.post(
        "/api/events/999999/sessions",
        headers=headers,
        json=_session_payload(
            start_time="2026-11-15T17:00:00Z",
            end_time="2026-11-15T18:00:00Z",
        ),
    )
    assert missing_event_post.status_code == 404
    assert missing_event_post.json() == {"detail": "Evento no encontrado"}

    db_session.refresh(own_session)
    db_session.refresh(foreign_session)
    assert own_session.title == "Sesión propia"
    assert foreign_session.title == "Sesión ajena"
    assert own_session.updated_at == own_updated_at
    assert foreign_session.updated_at == foreign_updated_at
    assert (
        db_session.exec(
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.event_id == event.id)
        ).one()
        == 1
    )
    assert (
        db_session.exec(
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.event_id == other_event.id)
        ).one()
        == 1
    )


def test_ses_ac_30_delete_serializes_with_concurrent_create_on_same_event(
    concurrent_sessions: ConcurrentSessionRunner,
    db_truncate,
    test_engine,
) -> None:
    # 1) DELETE waits for the event row lock before touching the session.
    lock_event_id = concurrent_sessions.seed_event(event_date=EVENT_DATE)
    lock_session_id = concurrent_sessions.seed_session(
        lock_event_id,
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    holder = test_engine.connect()
    holder_tx = holder.begin()
    holder.execute(
        select(Event).where(Event.id == lock_event_id).with_for_update()
    )
    contender = test_engine.connect()
    contender.exec_driver_sql("SET lock_timeout = '250ms'")
    contender_db = DBSession(bind=contender)
    try:
        with pytest.raises(OperationalError):
            delete_session(
                contender_db,
                contender_db.get(SessionModel, lock_session_id),
                _NullCache(),
            )
    finally:
        contender_db.rollback()
        contender_db.close()
        contender.close()
        holder_tx.rollback()
        holder.close()
    assert concurrent_sessions.count_sessions(lock_event_id) == 1

    # 2) Three concurrent DELETE + POST rounds on the same event.
    for _ in range(3):
        event_id = concurrent_sessions.seed_event(event_date=EVENT_DATE)
        old_session_id = concurrent_sessions.seed_session(
            event_id,
            start_time=_utc(2026, 11, 15, 15, 0),
            end_time=_utc(2026, 11, 15, 16, 0),
        )
        create_payload = SessionCreate.model_validate(
            _session_payload(
                start_time="2026-11-15T15:30:00Z",
                end_time="2026-11-15T16:30:00Z",
            )
        )
        outcomes = concurrent_sessions.run_delete_and_create(
            event_id,
            old_session_id,
            create_payload,
        )
        kinds = sorted(kind for kind, _ in outcomes)
        assert "deleted" in kinds
        assert set(kinds) <= {"deleted", "created", "conflict"}

        rows = concurrent_sessions.list_sessions(event_id)
        assert all(row_id != old_session_id for row_id, _, _ in rows)
        if "created" in kinds:
            assert len(rows) == 1
        else:
            assert rows == []
            conflict = next(
                value for kind, value in outcomes if kind == "conflict"
            )
            assert conflict.status_code == 409
            assert conflict.detail == (
                "La sesión se solapa con otra sesión del evento"
            )
        for index, (_, start_a, end_a) in enumerate(rows):
            for _, start_b, end_b in rows[index + 1 :]:
                assert not (start_a < end_b and end_a > start_b)

    # 3) Three concurrent DELETE + PATCH rounds on the same event.
    for _ in range(3):
        event_id = concurrent_sessions.seed_event(event_date=EVENT_DATE)
        deleted_id = concurrent_sessions.seed_session(
            event_id,
            start_time=_utc(2026, 11, 15, 15, 0),
            end_time=_utc(2026, 11, 15, 16, 0),
        )
        updated_id = concurrent_sessions.seed_session(
            event_id,
            start_time=_utc(2026, 11, 15, 17, 0),
            end_time=_utc(2026, 11, 15, 18, 0),
            title="Sesión a editar",
        )
        update_payload = SessionUpdate.model_validate(
            {
                "start_time": "2026-11-15T15:30:00Z",
                "end_time": "2026-11-15T16:30:00Z",
            }
        )
        outcomes = concurrent_sessions.run_delete_and_update(
            event_id,
            deleted_id,
            updated_id,
            update_payload,
        )
        kinds = sorted(kind for kind, _ in outcomes)
        assert "deleted" in kinds
        assert set(kinds) <= {"deleted", "updated", "conflict"}

        rows = concurrent_sessions.list_sessions(event_id)
        assert all(row_id != deleted_id for row_id, _, _ in rows)
        assert len(rows) == 1
        row_id, start_time, end_time = rows[0]
        assert row_id == updated_id
        if "updated" in kinds:
            assert start_time == _utc(2026, 11, 15, 15, 30)
            assert end_time == _utc(2026, 11, 15, 16, 30)
        else:
            conflict = next(
                value for kind, value in outcomes if kind == "conflict"
            )
            assert conflict.status_code == 409
            assert start_time == _utc(2026, 11, 15, 17, 0)
            assert end_time == _utc(2026, 11, 15, 18, 0)


def test_ses_ac_16_expired_tokens_and_inactive_users_get_401_on_all_writes(
    client: TestClient,
    db_session: DBSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(db_session, organizer=organizer)
    session_row = _create_session_row(
        db_session,
        event=event,
        title="Sesión protegida",
        start_time=_utc(2026, 11, 15, 15, 0),
        end_time=_utc(2026, 11, 15, 16, 0),
    )
    base = f"/api/events/{event.id}/sessions"
    detail = f"{base}/{session_row.id}"
    payload = _session_payload(
        start_time="2026-11-15T17:00:00Z",
        end_time="2026-11-15T18:00:00Z",
    )

    monkeypatch.setattr(settings, "jwt_expire_minutes", -1)
    expired_headers = _auth_headers(organizer)
    monkeypatch.setattr(settings, "jwt_expire_minutes", 480)

    expired_calls = (
        client.post(base, headers=expired_headers, json=payload),
        client.patch(
            detail,
            headers=expired_headers,
            json={"title": "Token expirado"},
        ),
        client.delete(detail, headers=expired_headers),
    )
    for response in expired_calls:
        assert response.status_code == 401
        assert response.json() == {
            "detail": "No autenticado o sesión expirada"
        }
        assert response.headers["WWW-Authenticate"] == "Bearer"

    inactive = _create_user(
        db_session,
        email="inactive@example.com",
        role=UserRole.ORGANIZER,
        is_active=False,
    )
    inactive_headers = _auth_headers(inactive)
    inactive_calls = (
        client.post(base, headers=inactive_headers, json=payload),
        client.patch(
            detail,
            headers=inactive_headers,
            json={"title": "Usuario inactivo"},
        ),
        client.delete(detail, headers=inactive_headers),
    )
    for response in inactive_calls:
        assert response.status_code == 401
        assert response.json() == {
            "detail": "No autenticado o sesión expirada"
        }
        assert response.headers["WWW-Authenticate"] == "Bearer"

    db_session.refresh(session_row)
    assert session_row.title == "Sesión protegida"
