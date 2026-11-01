from collections.abc import Iterator
from datetime import datetime, timezone
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import inspect, text
from sqlmodel import Session
import pytest

from app.auth.security import create_access_token, hash_password
from app.events.models import Event, EventStatus
from app.users.models import User, UserRole


def _utc(year: int, month: int, day: int, hour: int = 14) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _create_user(
    session: Session,
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


def _image_bytes(
    *,
    size: tuple[int, int] = (1600, 900),
    image_format: str = "JPEG",
    mode: str = "RGB",
    color=(200, 50, 50),
    exif_orientation: int | None = None,
) -> bytes:
    image = Image.new(mode, size, color)
    buffer = BytesIO()
    save_kwargs = {}
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[274] = exif_orientation
        save_kwargs["exif"] = exif
    image.save(buffer, format=image_format, **save_kwargs)
    return buffer.getvalue()


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, object] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, int]] = []
        self.invalidated: list[str] = []

    def get(self, key: str):
        self.get_calls.append(key)
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


def _upload_image(
    client: TestClient,
    *,
    event_id: int,
    headers: dict[str, str],
    data: bytes,
    filename: str = "foto.jpg",
    content_type: str = "image/jpeg",
):
    return client.post(
        f"/api/events/{event_id}/image",
        headers=headers,
        files={"file": (filename, data, content_type)},
    )


def _create_event(
    session: Session,
    *,
    organizer: User,
    title: str = "Evento de prueba",
    description: str = "Descripción suficientemente larga.",
    date: datetime | None = None,
    total_capacity: int = 10,
    status: EventStatus = EventStatus.DRAFT,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Event:
    event = Event(
        organizer_id=organizer.id,
        title=title,
        description=description,
        date=date or _utc(2026, 11, 15),
        total_capacity=total_capacity,
        status=status,
    )
    if created_at is not None:
        event.created_at = created_at
    if updated_at is not None:
        event.updated_at = updated_at
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@pytest.fixture()
def media_root(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_event_cache() -> Iterator[None]:
    from app.core.cache import cache_client

    cache_client.invalidate_prefix("events:")
    yield
    cache_client.invalidate_prefix("events:")


def test_evt_ac_01_organizer_and_admin_create_event_with_defaults_and_published(
    client: TestClient,
    db_session: Session,
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
    payload = {
        "title": "Conferencia Python Colombia",
        "description": "Encuentro anual de desarrollo con FastAPI y Vue.",
        "date": "2026-11-15T14:00:00Z",
        "total_capacity": 120,
    }

    created = client.post(
        "/api/events",
        headers=_auth_headers(organizer),
        json=payload,
    )
    assert created.status_code == 201
    data = created.json()
    assert set(data) == {
        "id",
        "title",
        "description",
        "date",
        "total_capacity",
        "registered_count",
        "available_capacity",
        "status",
        "organizer_id",
        "image_urls",
        "created_at",
        "updated_at",
    }
    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["date"] == "2026-11-15T14:00:00Z"
    assert data["total_capacity"] == 120
    assert data["registered_count"] == 0
    assert data["available_capacity"] == 120
    assert data["status"] == "DRAFT"
    assert data["organizer_id"] == organizer.id
    assert data["image_urls"] is None
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")

    published = client.post(
        "/api/events",
        headers=_auth_headers(admin),
        json={**payload, "status": "PUBLISHED"},
    )
    assert published.status_code == 201
    published_data = published.json()
    assert published_data["status"] == "PUBLISHED"
    assert published_data["organizer_id"] == admin.id
    assert published_data["registered_count"] == 0
    assert published_data["available_capacity"] == 120


def test_evt_ac_02_write_endpoints_reject_unauthenticated_401_and_attendee_403(
    client: TestClient,
    db_session: Session,
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
    payload = {
        "title": "Evento de prueba",
        "description": "Descripción suficientemente larga.",
        "date": "2026-11-15T14:00:00Z",
        "total_capacity": 10,
    }
    created = client.post(
        "/api/events",
        headers=_auth_headers(organizer),
        json=payload,
    )
    assert created.status_code == 201
    event_id = created.json()["id"]

    unauthenticated_calls = (
        client.post("/api/events", json=payload),
        client.patch(f"/api/events/{event_id}", json={"title": "Otro título"}),
        client.delete(f"/api/events/{event_id}"),
        client.post(
            f"/api/events/{event_id}/image",
            files={"file": ("foto.jpg", b"not-an-image", "image/jpeg")},
        ),
    )
    for response in unauthenticated_calls:
        assert response.status_code == 401
        assert response.json() == {"detail": "No autenticado o sesión expirada"}
        assert response.headers["WWW-Authenticate"] == "Bearer"

    attendee_headers = _auth_headers(attendee)
    forbidden_calls = (
        client.post("/api/events", headers=attendee_headers, json=payload),
        client.patch(
            f"/api/events/{event_id}",
            headers=attendee_headers,
            json={"title": "Otro título"},
        ),
        client.delete(f"/api/events/{event_id}", headers=attendee_headers),
        client.post(
            f"/api/events/{event_id}/image",
            headers=attendee_headers,
            files={"file": ("foto.jpg", b"not-an-image", "image/jpeg")},
        ),
    )
    for response in forbidden_calls:
        assert response.status_code == 403
        assert response.json() == {
            "detail": "No tienes permisos para realizar esta acción"
        }


def test_evt_ac_03_create_and_patch_forbid_extra_fields_and_initial_cancelled_status(
    client: TestClient,
    db_session: Session,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    headers = _auth_headers(organizer)
    payload = {
        "title": "Evento de prueba",
        "description": "Descripción suficientemente larga.",
        "date": "2026-11-15T14:00:00Z",
        "total_capacity": 10,
    }

    forbidden_fields = {
        "organizer_id": organizer.id,
        "registered_count": 0,
        "available_capacity": 10,
        "image_urls": None,
        "image_key": "abc",
        "unknown_field": "x",
    }
    for field, value in forbidden_fields.items():
        response = client.post(
            "/api/events",
            headers=headers,
            json={**payload, field: value},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Error de validación en los datos enviados"
        assert {
            "field": field,
            "message": "Este campo no está permitido",
        } in data["errors"]

    cancelled = client.post(
        "/api/events",
        headers=headers,
        json={**payload, "status": "CANCELLED"},
    )
    assert cancelled.status_code == 422
    cancelled_data = cancelled.json()
    assert (
        cancelled_data["detail"]
        == "Error de validación en los datos enviados"
    )
    status_errors = [
        err for err in cancelled_data["errors"] if err["field"] == "status"
    ]
    assert status_errors
    assert status_errors[0]["message"]

    created = client.post("/api/events", headers=headers, json=payload)
    assert created.status_code == 201
    event_id = created.json()["id"]

    patch_extra = client.patch(
        f"/api/events/{event_id}",
        headers=headers,
        json={"title": "Título actualizado", "organizer_id": organizer.id},
    )
    assert patch_extra.status_code == 422
    patch_data = patch_extra.json()
    assert patch_data["detail"] == "Error de validación en los datos enviados"
    assert {
        "field": "organizer_id",
        "message": "Este campo no está permitido",
    } in patch_data["errors"]


def test_evt_ac_04_validates_title_description_capacity_bounds_and_empty_patch_body(
    client: TestClient,
    db_session: Session,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    headers = _auth_headers(organizer)
    payload = {
        "title": "Evento de prueba",
        "description": "Descripción suficientemente larga.",
        "date": "2026-11-15T14:00:00Z",
        "total_capacity": 10,
    }

    invalid_payloads = (
        ({**payload, "title": "  ab  "}, "title"),
        ({**payload, "title": "x" * 161}, "title"),
        ({**payload, "description": "  corta  "}, "description"),
        ({**payload, "description": "x" * 5001}, "description"),
        ({**payload, "total_capacity": 0}, "total_capacity"),
        ({**payload, "total_capacity": 100001}, "total_capacity"),
    )
    for body, field in invalid_payloads:
        response = client.post("/api/events", headers=headers, json=body)
        assert response.status_code == 422
        data = response.json()
        assert data["detail"] == "Error de validación en los datos enviados"
        field_errors = [
            err for err in data["errors"] if err["field"] == field
        ]
        assert field_errors
        assert field_errors[0]["message"]

    created = client.post(
        "/api/events",
        headers=headers,
        json={**payload, "title": "  Evento con espacios  "},
    )
    assert created.status_code == 201
    assert created.json()["title"] == "Evento con espacios"
    event_id = created.json()["id"]

    for empty_body in ({}, {"title": None}):
        empty_patch = client.patch(
            f"/api/events/{event_id}",
            headers=headers,
            json=empty_body,
        )
        assert empty_patch.status_code == 422
        empty_data = empty_patch.json()
        assert (
            empty_data["detail"]
            == "Error de validación en los datos enviados"
        )
        assert any(
            err["message"]
            == "Debes indicar al menos un campo para actualizar"
            for err in empty_data["errors"]
        )

    invalid_patch = client.patch(
        f"/api/events/{event_id}",
        headers=headers,
        json={"total_capacity": 0},
    )
    assert invalid_patch.status_code == 422
    patch_data = invalid_patch.json()
    assert patch_data["detail"] == "Error de validación en los datos enviados"
    assert any(
        err["field"] == "total_capacity" and err["message"]
        for err in patch_data["errors"]
    )


def test_evt_ac_05_anonymous_and_attendee_list_only_published_ordered_by_date_and_id(
    client: TestClient,
    db_session: Session,
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

    late = _create_event(
        db_session,
        organizer=organizer,
        title="Evento tardío",
        date=_utc(2026, 12, 1),
        status=EventStatus.PUBLISHED,
    )
    early = _create_event(
        db_session,
        organizer=organizer,
        title="Evento temprano",
        date=_utc(2026, 11, 1),
        status=EventStatus.PUBLISHED,
    )
    same_date = _create_event(
        db_session,
        organizer=organizer,
        title="Evento misma fecha",
        date=_utc(2026, 11, 1),
        status=EventStatus.PUBLISHED,
    )
    _create_event(
        db_session,
        organizer=organizer,
        title="Borrador oculto",
        date=_utc(2026, 11, 5),
        status=EventStatus.DRAFT,
    )
    _create_event(
        db_session,
        organizer=organizer,
        title="Cancelado oculto",
        date=_utc(2026, 11, 6),
        status=EventStatus.CANCELLED,
    )

    for headers in ({}, _auth_headers(attendee)):
        response = client.get("/api/events?page=1&size=10", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["pages"] == 1
        assert [item["id"] for item in data["items"]] == [
            early.id,
            same_date.id,
            late.id,
        ]
        assert all(item["status"] == "PUBLISHED" for item in data["items"])

    for headers in ({}, _auth_headers(attendee)):
        for hidden_status in ("DRAFT", "CANCELLED"):
            response = client.get(
                f"/api/events?status={hidden_status}",
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json() == {
                "items": [],
                "total": 0,
                "page": 1,
                "size": 10,
                "pages": 0,
            }

    paged = client.get("/api/events?page=2&size=2")
    assert paged.status_code == 200
    paged_data = paged.json()
    assert paged_data["total"] == 3
    assert paged_data["pages"] == 2
    assert [item["id"] for item in paged_data["items"]] == [late.id]


def test_evt_ac_06_detail_hides_draft_and_cancelled_from_public_attendee_and_other_org(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = _create_user(
        db_session,
        email="owner@example.com",
        role=UserRole.ORGANIZER,
    )
    other_organizer = _create_user(
        db_session,
        email="other@example.com",
        role=UserRole.ORGANIZER,
    )
    attendee = _create_user(
        db_session,
        email="attendee@example.com",
        role=UserRole.ATTENDEE,
    )
    published = _create_event(
        db_session,
        organizer=owner,
        title="Evento publicado",
        status=EventStatus.PUBLISHED,
    )
    draft = _create_event(
        db_session,
        organizer=owner,
        title="Borrador privado",
        status=EventStatus.DRAFT,
    )
    cancelled = _create_event(
        db_session,
        organizer=owner,
        title="Evento cancelado",
        status=EventStatus.CANCELLED,
    )

    public_response = client.get(f"/api/events/{published.id}")
    assert public_response.status_code == 200
    assert public_response.json()["id"] == published.id

    for hidden in (draft, cancelled):
        for headers in (
            {},
            _auth_headers(attendee),
            _auth_headers(other_organizer),
        ):
            response = client.get(f"/api/events/{hidden.id}", headers=headers)
            assert response.status_code == 404
            assert response.json() == {"detail": "Evento no encontrado"}

    missing = client.get("/api/events/999999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Evento no encontrado"}


def test_evt_ac_07_organizer_views_published_plus_own_events_and_filters_with_mine(
    client: TestClient,
    db_session: Session,
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
    draft_own = _create_event(
        db_session,
        organizer=organizer,
        title="Borrador propio",
        date=_utc(2026, 11, 1),
        status=EventStatus.DRAFT,
    )
    cancelled_own = _create_event(
        db_session,
        organizer=organizer,
        title="Cancelado propio",
        date=_utc(2026, 11, 2),
        status=EventStatus.CANCELLED,
    )
    published_own = _create_event(
        db_session,
        organizer=organizer,
        title="Publicado propio",
        date=_utc(2026, 11, 4),
        status=EventStatus.PUBLISHED,
    )
    draft_other = _create_event(
        db_session,
        organizer=other_organizer,
        title="Borrador ajeno",
        date=_utc(2026, 11, 3),
        status=EventStatus.DRAFT,
    )
    published_other = _create_event(
        db_session,
        organizer=other_organizer,
        title="Publicado ajeno",
        date=_utc(2026, 11, 10),
        status=EventStatus.PUBLISHED,
    )
    headers = _auth_headers(organizer)

    listing = client.get("/api/events?size=50", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [
        draft_own.id,
        cancelled_own.id,
        published_own.id,
        published_other.id,
    ]

    mine = client.get("/api/events?mine=true&size=50", headers=headers)
    assert mine.status_code == 200
    mine_data = mine.json()
    assert mine_data["total"] == 3
    assert [item["id"] for item in mine_data["items"]] == [
        draft_own.id,
        cancelled_own.id,
        published_own.id,
    ]
    assert all(
        item["organizer_id"] == organizer.id for item in mine_data["items"]
    )

    mine_draft = client.get(
        "/api/events?mine=true&status=DRAFT", headers=headers
    )
    assert mine_draft.status_code == 200
    assert [item["id"] for item in mine_draft.json()["items"]] == [
        draft_own.id
    ]

    cancelled_only = client.get("/api/events?status=CANCELLED", headers=headers)
    assert cancelled_only.status_code == 200
    assert [item["id"] for item in cancelled_only.json()["items"]] == [
        cancelled_own.id
    ]

    published_only = client.get("/api/events?status=PUBLISHED", headers=headers)
    assert published_only.status_code == 200
    assert [item["id"] for item in published_only.json()["items"]] == [
        published_own.id,
        published_other.id,
    ]

    for own_event in (draft_own, cancelled_own, published_own):
        response = client.get(f"/api/events/{own_event.id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == own_event.id

    foreign_draft = client.get(
        f"/api/events/{draft_other.id}", headers=headers
    )
    assert foreign_draft.status_code == 404
    assert foreign_draft.json() == {"detail": "Evento no encontrado"}


def test_evt_ac_08_mine_filter_returns_401_for_anonymous_and_403_for_attendee(
    client: TestClient,
    db_session: Session,
) -> None:
    attendee = _create_user(
        db_session,
        email="attendee@example.com",
        role=UserRole.ATTENDEE,
    )

    anonymous = client.get("/api/events?mine=true")
    assert anonymous.status_code == 401
    assert anonymous.json() == {
        "detail": "No autenticado o sesión expirada"
    }
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"

    forbidden = client.get(
        "/api/events?mine=true",
        headers=_auth_headers(attendee),
    )
    assert forbidden.status_code == 403
    assert forbidden.json() == {
        "detail": "No tienes permisos para realizar esta acción"
    }

    invalid_token = client.get(
        "/api/events",
        headers={"Authorization": "Bearer token-invalido"},
    )
    assert invalid_token.status_code == 401
    assert invalid_token.json() == {
        "detail": "No autenticado o sesión expirada"
    }
    assert invalid_token.headers["WWW-Authenticate"] == "Bearer"


def test_evt_ac_09_admin_views_all_events_in_any_status_in_list_and_detail(
    client: TestClient,
    db_session: Session,
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
    other_organizer = _create_user(
        db_session,
        email="other@example.com",
        role=UserRole.ORGANIZER,
    )
    draft = _create_event(
        db_session,
        organizer=organizer,
        title="Borrador",
        date=_utc(2026, 11, 1),
        status=EventStatus.DRAFT,
    )
    cancelled = _create_event(
        db_session,
        organizer=organizer,
        title="Cancelado",
        date=_utc(2026, 11, 2),
        status=EventStatus.CANCELLED,
    )
    published = _create_event(
        db_session,
        organizer=organizer,
        title="Publicado",
        date=_utc(2026, 11, 3),
        status=EventStatus.PUBLISHED,
    )
    other_draft = _create_event(
        db_session,
        organizer=other_organizer,
        title="Borrador ajeno",
        date=_utc(2026, 11, 4),
        status=EventStatus.DRAFT,
    )
    admin_event = _create_event(
        db_session,
        organizer=admin,
        title="Evento del admin",
        date=_utc(2026, 11, 5),
        status=EventStatus.PUBLISHED,
    )
    headers = _auth_headers(admin)

    listing = client.get("/api/events?size=50", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [
        draft.id,
        cancelled.id,
        published.id,
        other_draft.id,
        admin_event.id,
    ]

    drafts = client.get("/api/events?status=DRAFT&size=50", headers=headers)
    assert drafts.status_code == 200
    assert [item["id"] for item in drafts.json()["items"]] == [
        draft.id,
        other_draft.id,
    ]

    mine = client.get("/api/events?mine=true&size=50", headers=headers)
    assert mine.status_code == 200
    assert [item["id"] for item in mine.json()["items"]] == [admin_event.id]

    for event in (draft, cancelled, other_draft):
        response = client.get(f"/api/events/{event.id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == event.id


def test_evt_ac_10_owner_and_admin_patch_event_preserving_original_organizer_id(
    client: TestClient,
    db_session: Session,
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
    old_updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Título original",
        description="Descripción original del evento.",
        date=_utc(2026, 11, 15),
        total_capacity=10,
        updated_at=old_updated_at,
    )

    owner_patch = client.patch(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
        json={
            "title": "  Título actualizado  ",
            "description": "  Descripción actualizada del evento.  ",
            "date": "2026-12-01T09:30:00-05:00",
            "total_capacity": 25,
        },
    )
    assert owner_patch.status_code == 200
    patched = owner_patch.json()
    assert patched["title"] == "Título actualizado"
    assert patched["description"] == "Descripción actualizada del evento."
    assert patched["date"] == "2026-12-01T14:30:00Z"
    assert patched["total_capacity"] == 25
    assert patched["organizer_id"] == organizer.id
    assert patched["updated_at"] != old_updated_at.isoformat().replace(
        "+00:00", "Z"
    )
    assert patched["updated_at"].endswith("Z")

    admin_patch = client.patch(
        f"/api/events/{event.id}",
        headers=_auth_headers(admin),
        json={"title": "Título editado por admin"},
    )
    assert admin_patch.status_code == 200
    admin_data = admin_patch.json()
    assert admin_data["title"] == "Título editado por admin"
    assert admin_data["organizer_id"] == organizer.id

    db_session.refresh(event)
    assert event.organizer_id == organizer.id


def test_evt_ac_11_non_owner_organizer_gets_403_on_patch_delete_and_image_upload(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = _create_user(
        db_session,
        email="owner@example.com",
        role=UserRole.ORGANIZER,
    )
    intruder = _create_user(
        db_session,
        email="intruder@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=owner,
        title="Evento privado del dueño",
    )
    headers = _auth_headers(intruder)

    patch_response = client.patch(
        f"/api/events/{event.id}",
        headers=headers,
        json={"title": "Intento de edición"},
    )
    assert patch_response.status_code == 403
    assert patch_response.json() == {
        "detail": "No tienes permisos para realizar esta acción"
    }

    delete_response = client.delete(
        f"/api/events/{event.id}", headers=headers
    )
    assert delete_response.status_code == 403
    assert delete_response.json() == {
        "detail": "No tienes permisos para realizar esta acción"
    }

    image_response = client.post(
        f"/api/events/{event.id}/image",
        headers=headers,
        files={"file": ("foto.jpg", b"not-an-image", "image/jpeg")},
    )
    assert image_response.status_code == 403
    assert image_response.json() == {
        "detail": "No tienes permisos para realizar esta acción"
    }

    missing = client.patch(
        "/api/events/999999",
        headers=headers,
        json={"title": "Inexistente"},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Evento no encontrado"}

    db_session.refresh(event)
    assert event.title == "Evento privado del dueño"


def test_evt_ac_12_valid_state_transitions_draft_to_published_and_to_cancelled(
    client: TestClient,
    db_session: Session,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    headers = _auth_headers(organizer)
    draft_to_published = _create_event(
        db_session,
        organizer=organizer,
        title="Borrador a publicar",
        status=EventStatus.DRAFT,
    )
    draft_to_cancelled = _create_event(
        db_session,
        organizer=organizer,
        title="Borrador a cancelar",
        status=EventStatus.DRAFT,
    )
    published_to_cancelled = _create_event(
        db_session,
        organizer=organizer,
        title="Publicado a cancelar",
        status=EventStatus.PUBLISHED,
    )
    draft_idempotent = _create_event(
        db_session,
        organizer=organizer,
        title="Borrador idempotente",
        status=EventStatus.DRAFT,
    )
    published_idempotent = _create_event(
        db_session,
        organizer=organizer,
        title="Publicado idempotente",
        status=EventStatus.PUBLISHED,
    )

    transitions = (
        (draft_to_published, "PUBLISHED"),
        (draft_to_cancelled, "CANCELLED"),
        (published_to_cancelled, "CANCELLED"),
        (draft_idempotent, "DRAFT"),
        (published_idempotent, "PUBLISHED"),
    )
    for event, new_status in transitions:
        response = client.patch(
            f"/api/events/{event.id}",
            headers=headers,
            json={"status": new_status},
        )
        assert response.status_code == 200
        assert response.json()["status"] == new_status


def test_evt_ac_13_transition_from_published_to_draft_returns_409_conflict(
    client: TestClient,
    db_session: Session,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento publicado",
        status=EventStatus.PUBLISHED,
    )

    response = client.patch(
        f"/api/events/{event.id}",
        headers=_auth_headers(organizer),
        json={"status": "DRAFT"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": "No se puede regresar un evento publicado a borrador"
    }

    db_session.refresh(event)
    assert event.status == EventStatus.PUBLISHED.value


def test_evt_ac_14_cancelled_event_is_immutable_for_patch_and_image_upload_with_409(
    client: TestClient,
    db_session: Session,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento cancelado",
        status=EventStatus.CANCELLED,
    )
    headers = _auth_headers(organizer)

    patch_field = client.patch(
        f"/api/events/{event.id}",
        headers=headers,
        json={"title": "Intento de edición"},
    )
    assert patch_field.status_code == 409
    assert patch_field.json() == {
        "detail": "Un evento cancelado no puede cambiar de estado ni editarse"
    }

    patch_status = client.patch(
        f"/api/events/{event.id}",
        headers=headers,
        json={"status": "PUBLISHED"},
    )
    assert patch_status.status_code == 409
    assert patch_status.json() == {
        "detail": "Un evento cancelado no puede cambiar de estado ni editarse"
    }

    image = client.post(
        f"/api/events/{event.id}/image",
        headers=headers,
        files={"file": ("foto.jpg", b"not-an-image", "image/jpeg")},
    )
    assert image.status_code == 409
    assert image.json() == {
        "detail": "Un evento cancelado no puede cambiar de estado ni editarse"
    }

    db_session.refresh(event)
    assert event.title == "Evento cancelado"
    assert event.status == EventStatus.CANCELLED.value


def test_evt_ac_15_exposes_backend_capacity_fields_and_rejects_reduction_below_registered(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento con inscritos",
        total_capacity=10,
        status=EventStatus.PUBLISHED,
    )
    monkeypatch.setattr(
        "app.events.service.get_registered_count",
        lambda session, event_id: 5,
    )
    headers = _auth_headers(organizer)

    detail = client.get(f"/api/events/{event.id}", headers=headers)
    assert detail.status_code == 200
    detail_data = detail.json()
    assert detail_data["total_capacity"] == 10
    assert detail_data["registered_count"] == 5
    assert detail_data["available_capacity"] == 5

    listing = client.get("/api/events?size=50", headers=headers)
    assert listing.status_code == 200
    listed = next(
        item for item in listing.json()["items"] if item["id"] == event.id
    )
    assert listed["registered_count"] == 5
    assert listed["available_capacity"] == 5

    rejected = client.patch(
        f"/api/events/{event.id}",
        headers=headers,
        json={"total_capacity": 4},
    )
    assert rejected.status_code == 409
    assert rejected.json() == {
        "detail": (
            "No se puede reducir la capacidad total por debajo del "
            "número de inscritos actuales"
        )
    }

    allowed = client.patch(
        f"/api/events/{event.id}",
        headers=headers,
        json={"total_capacity": 5},
    )
    assert allowed.status_code == 200
    assert allowed.json()["total_capacity"] == 5
    assert allowed.json()["registered_count"] == 5
    assert allowed.json()["available_capacity"] == 0


def test_evt_ac_16_normalizes_event_dates_to_utc_iso_z_and_allows_deterministic_dates(
    client: TestClient,
    db_session: Session,
    test_engine,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    headers = _auth_headers(organizer)
    payload = {
        "title": "Evento con zona horaria",
        "description": "Descripción suficientemente larga.",
        "date": "2026-11-15T14:00:00-05:00",
        "total_capacity": 10,
        "status": "PUBLISHED",
    }

    created = client.post("/api/events", headers=headers, json=payload)
    assert created.status_code == 201
    data = created.json()
    assert data["date"] == "2026-11-15T19:00:00Z"
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")
    event_id = data["id"]

    past = client.post(
        "/api/events",
        headers=headers,
        json={
            **payload,
            "title": "Evento en el pasado",
            "date": "2000-01-01T00:00:00Z",
        },
    )
    assert past.status_code == 201
    assert past.json()["date"] == "2000-01-01T00:00:00Z"

    detail = client.get(f"/api/events/{event_id}")
    assert detail.status_code == 200
    assert detail.json()["date"] == "2026-11-15T19:00:00Z"
    assert detail.json()["created_at"].endswith("Z")
    assert detail.json()["updated_at"].endswith("Z")

    listing = client.get("/api/events?size=50")
    assert listing.status_code == 200
    listed = next(
        item for item in listing.json()["items"] if item["id"] == event_id
    )
    assert listed["date"] == "2026-11-15T19:00:00Z"
    assert listed["created_at"].endswith("Z")
    assert listed["updated_at"].endswith("Z")

    columns = {
        column["name"]: column
        for column in inspect(test_engine).get_columns("events")
    }
    for column_name in ("date", "created_at", "updated_at"):
        assert columns[column_name]["type"].timezone is True


def test_evt_ac_17_search_trgm_ilike_partial_case_insensitive_escapes_wildcards_and_max(
    client: TestClient,
    db_session: Session,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    conference = _create_event(
        db_session,
        organizer=organizer,
        title="Conferencia Python Colombia",
        date=_utc(2026, 11, 1),
        status=EventStatus.PUBLISHED,
    )
    advanced = _create_event(
        db_session,
        organizer=organizer,
        title="Python avanzado",
        date=_utc(2026, 11, 2),
        status=EventStatus.PUBLISHED,
    )
    _create_event(
        db_session,
        organizer=organizer,
        title="Taller de Vue",
        date=_utc(2026, 11, 3),
        status=EventStatus.PUBLISHED,
    )
    percent = _create_event(
        db_session,
        organizer=organizer,
        title="100% Real",
        date=_utc(2026, 11, 4),
        status=EventStatus.PUBLISHED,
    )
    _create_event(
        db_session,
        organizer=organizer,
        title="100X Real",
        date=_utc(2026, 11, 5),
        status=EventStatus.PUBLISHED,
    )
    underscore = _create_event(
        db_session,
        organizer=organizer,
        title="a_b test",
        date=_utc(2026, 11, 6),
        status=EventStatus.PUBLISHED,
    )
    _create_event(
        db_session,
        organizer=organizer,
        title="axb test",
        date=_utc(2026, 11, 7),
        status=EventStatus.PUBLISHED,
    )
    backslash = _create_event(
        db_session,
        organizer=organizer,
        title="Ruta \\ Windows",
        date=_utc(2026, 11, 8),
        status=EventStatus.PUBLISHED,
    )

    def search_ids(term: str) -> list[int]:
        response = client.get("/api/events", params={"search": term, "size": 50})
        assert response.status_code == 200
        return [item["id"] for item in response.json()["items"]]

    assert search_ids("python") == [conference.id, advanced.id]
    assert search_ids("  python  ") == [conference.id, advanced.id]
    assert search_ids("PYTHON") == [conference.id, advanced.id]
    assert search_ids("100%") == [percent.id]
    assert search_ids("a_b") == [underscore.id]
    assert search_ids("\\") == [backslash.id]
    assert len(search_ids("   ")) == 8

    too_long = client.get("/api/events", params={"search": "x" * 101})
    assert too_long.status_code == 422
    too_long_data = too_long.json()
    assert (
        too_long_data["detail"]
        == "Error de validación en los datos enviados"
    )
    assert any(
        err["field"] == "search" and err["message"]
        for err in too_long_data["errors"]
    )


def test_evt_ac_18_delete_event_without_registrations_removes_row_and_webp_files_204(
    client: TestClient,
    db_session: Session,
    media_root,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento con imagen",
    )
    event_id = event.id
    image_key = "a" * 32
    event.image_key = image_key
    db_session.add(event)
    db_session.commit()

    events_dir = media_root / "events"
    events_dir.mkdir(parents=True)
    variant_files = [
        events_dir / f"{image_key}_{width}w.webp"
        for width in (400, 800, 1200)
    ]
    for variant_file in variant_files:
        variant_file.write_bytes(b"fake-webp")

    response = client.delete(
        f"/api/events/{event_id}",
        headers=_auth_headers(organizer),
    )
    assert response.status_code == 204
    assert response.content == b""
    assert all(not variant_file.exists() for variant_file in variant_files)
    assert db_session.get(Event, event_id) is None

    detail = client.get(
        f"/api/events/{event_id}",
        headers=_auth_headers(organizer),
    )
    assert detail.status_code == 404
    assert detail.json() == {"detail": "Evento no encontrado"}

    plain_event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento sin imagen",
    )
    plain_id = plain_event.id
    plain_delete = client.delete(
        f"/api/events/{plain_id}",
        headers=_auth_headers(organizer),
    )
    assert plain_delete.status_code == 204
    assert db_session.get(Event, plain_id) is None


def test_evt_ac_19_delete_event_with_registrations_returns_409_conflict(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento con asistentes",
        status=EventStatus.PUBLISHED,
    )
    event_id = event.id
    monkeypatch.setattr(
        "app.events.service.get_registered_count",
        lambda session, event_id: 3,
    )

    response = client.delete(
        f"/api/events/{event_id}",
        headers=_auth_headers(organizer),
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "No se puede eliminar un evento con asistentes inscritos; "
            "cancélalo en su lugar"
        )
    }

    assert db_session.get(Event, event_id) is not None
    detail = client.get(
        f"/api/events/{event_id}",
        headers=_auth_headers(organizer),
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == event_id


def test_evt_ac_20_upload_image_converts_to_3_webp_variants_strips_exif_no_upscale(
    client: TestClient,
    db_session: Session,
    media_root,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    headers = _auth_headers(organizer)

    def assert_variants(
        payload: dict,
        expected_sizes: dict[int, tuple[int, int]],
    ) -> None:
        urls = payload["image_urls"]
        assert urls is not None
        assert set(urls) == {"w400", "w800", "w1200"}
        key = urls["w400"].rsplit("/", 1)[-1].removesuffix("_400w.webp")
        assert len(key) == 32
        for width, expected_size in expected_sizes.items():
            assert (
                urls[f"w{width}"]
                == f"/api/media/events/{key}_{width}w.webp"
            )
            variant_path = media_root / "events" / f"{key}_{width}w.webp"
            assert variant_path.exists()
            with Image.open(variant_path) as variant:
                assert variant.format == "WEBP"
                assert variant.size == expected_size
                assert len(variant.getexif()) == 0
                assert "exif" not in variant.info
                assert "icc_profile" not in variant.info
                assert "xmp" not in variant.info

    large_event = _create_event(
        db_session, organizer=organizer, title="Evento imagen grande"
    )
    large = _upload_image(
        client,
        event_id=large_event.id,
        headers=headers,
        data=_image_bytes(size=(1600, 900), image_format="JPEG"),
    )
    assert large.status_code == 200
    assert_variants(
        large.json(),
        {400: (400, 225), 800: (800, 450), 1200: (1200, 675)},
    )

    small_event = _create_event(
        db_session, organizer=organizer, title="Evento imagen pequeña"
    )
    small = _upload_image(
        client,
        event_id=small_event.id,
        headers=headers,
        data=_image_bytes(
            size=(300, 200),
            image_format="PNG",
            mode="RGBA",
            color=(10, 20, 30, 128),
        ),
        filename="foto.png",
        content_type="image/png",
    )
    assert small.status_code == 200
    assert_variants(
        small.json(),
        {400: (300, 200), 800: (300, 200), 1200: (300, 200)},
    )

    exif_event = _create_event(
        db_session, organizer=organizer, title="Evento con EXIF"
    )
    exif = _upload_image(
        client,
        event_id=exif_event.id,
        headers=headers,
        data=_image_bytes(
            size=(160, 80),
            image_format="JPEG",
            exif_orientation=6,
        ),
    )
    assert exif.status_code == 200
    assert_variants(
        exif.json(),
        {400: (80, 160), 800: (80, 160), 1200: (80, 160)},
    )

    webp_event = _create_event(
        db_session, organizer=organizer, title="Evento WebP"
    )
    webp = _upload_image(
        client,
        event_id=webp_event.id,
        headers=headers,
        data=_image_bytes(size=(640, 480), image_format="WEBP"),
        filename="foto.webp",
        content_type="image/webp",
    )
    assert webp.status_code == 200
    assert_variants(
        webp.json(),
        {400: (400, 300), 800: (640, 480), 1200: (640, 480)},
    )


def test_evt_ac_21_replacing_event_image_generates_new_key_and_deletes_old_variants(
    client: TestClient,
    db_session: Session,
    media_root,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session, organizer=organizer, title="Evento reemplazo"
    )
    headers = _auth_headers(organizer)

    first = _upload_image(
        client,
        event_id=event.id,
        headers=headers,
        data=_image_bytes(size=(1600, 900), image_format="JPEG"),
    )
    assert first.status_code == 200
    first_urls = first.json()["image_urls"]
    assert first_urls is not None
    first_key = (
        first_urls["w400"].rsplit("/", 1)[-1].removesuffix("_400w.webp")
    )
    first_files = [
        media_root / "events" / f"{first_key}_{width}w.webp"
        for width in (400, 800, 1200)
    ]
    assert all(path.exists() for path in first_files)

    second = _upload_image(
        client,
        event_id=event.id,
        headers=headers,
        data=_image_bytes(size=(800, 400), image_format="PNG"),
        filename="nueva.png",
        content_type="image/png",
    )
    assert second.status_code == 200
    second_urls = second.json()["image_urls"]
    assert second_urls is not None
    second_key = (
        second_urls["w400"].rsplit("/", 1)[-1].removesuffix("_400w.webp")
    )
    assert second_key != first_key
    assert all(not path.exists() for path in first_files)
    for width in (400, 800, 1200):
        new_file = media_root / "events" / f"{second_key}_{width}w.webp"
        assert new_file.exists()
        assert (
            second_urls[f"w{width}"]
            == f"/api/media/events/{second_key}_{width}w.webp"
        )


def test_evt_ac_22_upload_image_rejects_empty_400_unsupported_corrupt_400_and_over_5mb_413(
    client: TestClient,
    db_session: Session,
    media_root,
) -> None:
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session, organizer=organizer, title="Evento imagen inválida"
    )
    headers = _auth_headers(organizer)
    unsupported_detail = (
        "Formato de imagen no soportado. Usa JPEG, PNG o WebP"
    )

    invalid_cases = (
        (b"", 400, "El archivo de imagen está vacío"),
        (b"not-an-image", 400, unsupported_detail),
        (b"texto plano renombrado", 400, unsupported_detail),
        (
            _image_bytes(size=(10, 10), image_format="GIF"),
            400,
            unsupported_detail,
        ),
        (
            b"0" * (5 * 1024 * 1024 + 1),
            413,
            "La imagen no debe superar los 5 MB",
        ),
    )
    for data, expected_status, expected_detail in invalid_cases:
        response = _upload_image(
            client,
            event_id=event.id,
            headers=headers,
            data=data,
        )
        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}

    db_session.refresh(event)
    assert event.image_key is None

    missing_file = client.post(
        f"/api/events/{event.id}/image",
        headers=headers,
    )
    assert missing_file.status_code == 422
    missing_data = missing_file.json()
    assert (
        missing_data["detail"]
        == "Error de validación en los datos enviados"
    )
    assert any(
        err["field"] == "file" and err["message"]
        for err in missing_data["errors"]
    )


def test_evt_ac_23_redis_caches_list_and_detail_and_invalidates_on_every_write(
    client: TestClient,
    db_session: Session,
    media_root,
) -> None:
    from app.core.cache import get_cache_client
    from app.main import app

    fake_cache = FakeCache()
    app.dependency_overrides[get_cache_client] = lambda: fake_cache
    try:
        organizer = _create_user(
            db_session,
            email="organizer@example.com",
            role=UserRole.ORGANIZER,
        )
        event = _create_event(
            db_session,
            organizer=organizer,
            title="Título original",
            status=EventStatus.PUBLISHED,
        )
        headers = _auth_headers(organizer)

        first_list = client.get("/api/events?page=1&size=10")
        assert first_list.status_code == 200
        assert len(fake_cache.set_calls) == 1
        list_key, ttl = fake_cache.set_calls[0]
        assert list_key == (
            "events:list:scope=public:page=1:size=10:"
            "search=:status=:mine=0"
        )
        assert ttl == 60

        event.title = "Mutado directamente en BD"
        db_session.add(event)
        db_session.commit()

        second_list = client.get("/api/events?page=1&size=10")
        assert second_list.status_code == 200
        assert second_list.json() == first_list.json()
        assert len(fake_cache.set_calls) == 1

        first_detail = client.get(f"/api/events/{event.id}")
        assert first_detail.status_code == 200
        detail_key = f"events:detail:id={event.id}:scope=public"
        assert (detail_key, 60) in fake_cache.set_calls

        event.title = "Otro cambio directo"
        db_session.add(event)
        db_session.commit()
        second_detail = client.get(f"/api/events/{event.id}")
        assert second_detail.status_code == 200
        assert second_detail.json() == first_detail.json()

        patched = client.patch(
            f"/api/events/{event.id}",
            headers=headers,
            json={"title": "Actualizado por API"},
        )
        assert patched.status_code == 200
        assert "events:" in fake_cache.invalidated
        refreshed = client.get(f"/api/events/{event.id}")
        assert refreshed.status_code == 200
        assert refreshed.json()["title"] == "Actualizado por API"

        invalidations_before_create = len(fake_cache.invalidated)
        created = client.post(
            "/api/events",
            headers=headers,
            json={
                "title": "Evento creado para caché",
                "description": "Descripción suficientemente larga.",
                "date": "2026-11-20T10:00:00Z",
                "total_capacity": 30,
            },
        )
        assert created.status_code == 201
        assert len(fake_cache.invalidated) > invalidations_before_create

        invalidations_before_image = len(fake_cache.invalidated)
        image = _upload_image(
            client,
            event_id=event.id,
            headers=headers,
            data=_image_bytes(size=(120, 80), image_format="JPEG"),
        )
        assert image.status_code == 200
        assert len(fake_cache.invalidated) > invalidations_before_image

        to_delete = _create_event(
            db_session,
            organizer=organizer,
            title="Evento para eliminar",
        )
        invalidations_before_delete = len(fake_cache.invalidated)
        deleted = client.delete(
            f"/api/events/{to_delete.id}", headers=headers
        )
        assert deleted.status_code == 204
        assert len(fake_cache.invalidated) > invalidations_before_delete
        assert set(fake_cache.invalidated) == {"events:"}
    finally:
        app.dependency_overrides.pop(get_cache_client, None)


def test_evt_ac_24_redis_failure_degrades_to_postgres_and_isolates_cache_scopes(
    client: TestClient,
    db_session: Session,
    media_root,
) -> None:
    from redis.exceptions import RedisError

    from app.core.cache import get_cache_client
    from app.main import app

    class FailingCache:
        def get(self, key: str):
            raise RedisError("redis down")

        def set(self, key: str, value, ttl_seconds: int = 60) -> bool:
            raise RedisError("redis down")

        def invalidate_prefix(self, prefix: str) -> bool:
            raise RedisError("redis down")

    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento resiliente",
        status=EventStatus.PUBLISHED,
    )
    headers = _auth_headers(organizer)

    app.dependency_overrides[get_cache_client] = lambda: FailingCache()
    try:
        listing = client.get("/api/events")
        assert listing.status_code == 200
        assert listing.json()["total"] == 1

        detail = client.get(f"/api/events/{event.id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == event.id

        created = client.post(
            "/api/events",
            headers=headers,
            json={
                "title": "Evento con Redis caído",
                "description": "Descripción suficientemente larga.",
                "date": "2026-11-21T10:00:00Z",
                "total_capacity": 12,
            },
        )
        assert created.status_code == 201

        patched = client.patch(
            f"/api/events/{event.id}",
            headers=headers,
            json={"title": "Evento resiliente editado"},
        )
        assert patched.status_code == 200

        image = _upload_image(
            client,
            event_id=event.id,
            headers=headers,
            data=_image_bytes(size=(90, 60), image_format="JPEG"),
        )
        assert image.status_code == 200

        deleted = client.delete(
            f"/api/events/{created.json()['id']}", headers=headers
        )
        assert deleted.status_code == 204
    finally:
        app.dependency_overrides.pop(get_cache_client, None)

    class BadPayloadCache(FakeCache):
        def get(self, key: str):
            self.get_calls.append(key)
            return {"unexpected": "payload"}

    bad_cache = BadPayloadCache()
    app.dependency_overrides[get_cache_client] = lambda: bad_cache
    try:
        fallback_list = client.get("/api/events")
        assert fallback_list.status_code == 200
        assert fallback_list.json()["total"] == 1
        fallback_detail = client.get(f"/api/events/{event.id}")
        assert fallback_detail.status_code == 200
        assert bad_cache.set_calls
    finally:
        app.dependency_overrides.pop(get_cache_client, None)

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
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    own_draft = _create_event(
        db_session,
        organizer=organizer,
        title="Borrador del organizador",
        date=_utc(2026, 12, 1),
        status=EventStatus.DRAFT,
    )
    own_published = _create_event(
        db_session,
        organizer=organizer,
        title="Publicado del organizador",
        date=_utc(2026, 12, 2),
        status=EventStatus.PUBLISHED,
    )
    other_draft = _create_event(
        db_session,
        organizer=other_organizer,
        title="Borrador ajeno",
        date=_utc(2026, 12, 3),
        status=EventStatus.DRAFT,
    )
    other_published = _create_event(
        db_session,
        organizer=other_organizer,
        title="Publicado ajeno",
        date=_utc(2026, 12, 4),
        status=EventStatus.PUBLISHED,
    )

    scoped_cache = FakeCache()
    app.dependency_overrides[get_cache_client] = lambda: scoped_cache
    try:
        organizer_list = client.get(
            "/api/events?size=50", headers=headers
        )
        assert organizer_list.status_code == 200
        assert [item["id"] for item in organizer_list.json()["items"]] == [
            event.id,
            own_draft.id,
            own_published.id,
            other_published.id,
        ]

        public_list = client.get("/api/events?size=50")
        assert public_list.status_code == 200
        assert [item["id"] for item in public_list.json()["items"]] == [
            event.id,
            own_published.id,
            other_published.id,
        ]

        attendee_list = client.get(
            "/api/events?size=50", headers=_auth_headers(attendee)
        )
        assert attendee_list.status_code == 200
        assert [item["id"] for item in attendee_list.json()["items"]] == [
            event.id,
            own_published.id,
            other_published.id,
        ]

        other_list = client.get(
            "/api/events?size=50", headers=_auth_headers(other_organizer)
        )
        assert other_list.status_code == 200
        assert [item["id"] for item in other_list.json()["items"]] == [
            event.id,
            own_published.id,
            other_draft.id,
            other_published.id,
        ]

        admin_list = client.get(
            "/api/events?size=50", headers=_auth_headers(admin)
        )
        assert admin_list.status_code == 200
        assert [item["id"] for item in admin_list.json()["items"]] == [
            event.id,
            own_draft.id,
            own_published.id,
            other_draft.id,
            other_published.id,
        ]

        cached_scopes = {
            key.split(":scope=")[1].split(":page=")[0]
            for key in scoped_cache.store
            if key.startswith("events:list:")
        }
        assert cached_scopes == {
            "public",
            f"org:{organizer.id}",
            f"org:{other_organizer.id}",
            f"admin:{admin.id}",
        }

        public_key = next(
            key
            for key in scoped_cache.store
            if key.startswith("events:list:scope=public:")
        )
        public_payload = scoped_cache.store[public_key]
        assert isinstance(public_payload, dict)
        assert own_draft.id not in [
            item["id"] for item in public_payload["items"]
        ]

        own_draft_detail = client.get(
            f"/api/events/{own_draft.id}", headers=headers
        )
        assert own_draft_detail.status_code == 200

        anonymous_draft = client.get(f"/api/events/{own_draft.id}")
        assert anonymous_draft.status_code == 404
        assert anonymous_draft.json() == {"detail": "Evento no encontrado"}

        other_draft_detail = client.get(
            f"/api/events/{own_draft.id}",
            headers=_auth_headers(other_organizer),
        )
        assert other_draft_detail.status_code == 404
        assert other_draft_detail.json() == {
            "detail": "Evento no encontrado"
        }
    finally:
        app.dependency_overrides.pop(get_cache_client, None)


def test_evt_ac_25_postgres_events_schema_constraints_gin_trgm_index_and_openapi_contract(
    client: TestClient,
    test_engine,
) -> None:
    inspector = inspect(test_engine)
    assert "events" in inspector.get_table_names()

    columns = {
        column["name"]: column
        for column in inspector.get_columns("events")
    }
    assert set(columns) == {
        "id",
        "organizer_id",
        "title",
        "description",
        "date",
        "total_capacity",
        "status",
        "image_key",
        "created_at",
        "updated_at",
    }
    assert columns["title"]["type"].length == 160
    assert columns["status"]["type"].length == 20
    for column_name in ("date", "created_at", "updated_at"):
        assert columns[column_name]["type"].timezone is True
    assert columns["image_key"]["nullable"] is True

    check_constraints = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("events")
    }
    assert "ck_events_status" in check_constraints
    assert "DRAFT" in check_constraints["ck_events_status"]
    assert "PUBLISHED" in check_constraints["ck_events_status"]
    assert "CANCELLED" in check_constraints["ck_events_status"]
    assert "ck_events_total_capacity_positive" in check_constraints
    assert "total_capacity" in check_constraints[
        "ck_events_total_capacity_positive"
    ]

    foreign_keys = inspector.get_foreign_keys("events")
    assert any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["organizer_id"]
        for fk in foreign_keys
    )

    with test_engine.connect() as connection:
        index_rows = connection.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'events'"
            )
        ).all()
    indexes = {row[0]: row[1] for row in index_rows}
    for index_name in (
        "ix_events_organizer_id",
        "ix_events_status",
        "ix_events_date",
        "ix_events_title_trgm",
    ):
        assert index_name in indexes
    trgm_index = indexes["ix_events_title_trgm"].lower()
    assert "using gin" in trgm_index
    assert "gin_trgm_ops" in trgm_index

    with test_engine.connect() as connection:
        constraint_rows = connection.execute(
            text(
                "SELECT conname, contype FROM pg_constraint "
                "WHERE conrelid = 'events'::regclass"
            )
        ).all()
    constraint_types = {row[0]: row[1] for row in constraint_rows}
    assert constraint_types["ck_events_status"] == "c"
    assert constraint_types["ck_events_total_capacity_positive"] == "c"
    assert any(
        constraint_type == "f" for constraint_type in constraint_types.values()
    )

    openapi = client.get("/api/openapi.json")
    assert openapi.status_code == 200
    schema = openapi.json()
    paths = schema["paths"]
    assert "get" in paths["/api/events"]
    assert "post" in paths["/api/events"]
    assert "get" in paths["/api/events/{event_id}"]
    assert "patch" in paths["/api/events/{event_id}"]
    assert "delete" in paths["/api/events/{event_id}"]
    assert "post" in paths["/api/events/{event_id}/image"]
    assert paths["/api/events"]["get"]["tags"] == ["events"]

    list_responses = paths["/api/events"]["get"]["responses"]
    assert {"200", "401", "403", "422"} <= set(list_responses)
    assert list_responses["422"]["description"] == (
        "Error de validación en los datos enviados"
    )
    assert {"201", "401", "403", "422"} <= set(
        paths["/api/events"]["post"]["responses"]
    )

    detail_operations = paths["/api/events/{event_id}"]
    assert {"200", "401", "404", "422"} <= set(
        detail_operations["get"]["responses"]
    )
    assert {"200", "401", "403", "404", "409", "422"} <= set(
        detail_operations["patch"]["responses"]
    )
    assert {"204", "401", "403", "404", "409"} <= set(
        detail_operations["delete"]["responses"]
    )
    assert detail_operations["get"]["responses"]["404"]["description"] == (
        "Recurso no encontrado"
    )

    image_responses = paths["/api/events/{event_id}/image"]["post"]["responses"]
    assert {
        "200",
        "400",
        "401",
        "403",
        "404",
        "409",
        "413",
        "422",
    } <= set(image_responses)
    assert image_responses["413"]["description"] == (
        "La imagen no debe superar los 5 MB"
    )

    components = schema["components"]["schemas"]
    event_read = components["EventRead"]["properties"]
    for field in (
        "id",
        "title",
        "description",
        "date",
        "total_capacity",
        "registered_count",
        "available_capacity",
        "status",
        "organizer_id",
        "image_urls",
        "created_at",
        "updated_at",
    ):
        assert field in event_read
    assert set(components["EventImageUrls"]["properties"]) == {
        "w400",
        "w800",
        "w1200",
    }
    assert "EventCreate" in components
    assert "EventUpdate" in components

    docs = client.get("/api/docs")
    assert docs.status_code == 200


def test_evt_ac_24_redis_corrupt_json_payload_degrades_to_postgres(
    client: TestClient,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    import redis

    from app.core.config import settings

    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )
    event = _create_event(
        db_session,
        organizer=organizer,
        title="Evento con caché corrupta",
        status=EventStatus.PUBLISHED,
    )
    cache_key = (
        "events:list:scope=public:page=1:size=10:"
        "search=:status=:mine=0"
    )
    raw_client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    raw_client.set(cache_key, "no-es-json")
    try:
        with caplog.at_level(logging.WARNING, logger="app.core.cache"):
            response = client.get("/api/events")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert [item["id"] for item in data["items"]] == [event.id]
        assert any(
            "Redis get failed" in record.getMessage()
            and cache_key in record.getMessage()
            for record in caplog.records
        )
    finally:
        raw_client.delete(cache_key)
        raw_client.close()
