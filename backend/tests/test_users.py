from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import create_access_token, hash_password
from app.users.models import User, UserRole


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


def test_auth_ac_15_admin_lists_and_updates_other_profiles(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(
        db_session,
        email="admin@example.com",
        full_name="Admin Uno",
        role=UserRole.ADMIN,
    )
    attendee = _create_user(
        db_session,
        email="attendee@example.com",
        full_name="Ana Asistente",
        role=UserRole.ATTENDEE,
    )
    organizer_inactive = _create_user(
        db_session,
        email="organizer@example.com",
        full_name="Carlos Organizador",
        role=UserRole.ORGANIZER,
        is_active=False,
    )
    headers = _auth_headers(admin)

    list_res = client.get("/api/users?page=1&size=10", headers=headers)
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] == 3
    assert list_data["page"] == 1
    assert list_data["size"] == 10
    assert list_data["pages"] == 1
    assert [item["id"] for item in list_data["items"]] == [
        admin.id,
        attendee.id,
        organizer_inactive.id,
    ]
    assert all("password_hash" not in item for item in list_data["items"])

    filtered_res = client.get(
        "/api/users?role=ORGANIZER&is_active=false",
        headers=headers,
    )
    assert filtered_res.status_code == 200
    filtered_data = filtered_res.json()
    assert filtered_data["total"] == 1
    assert [item["id"] for item in filtered_data["items"]] == [
        organizer_inactive.id
    ]

    detail_res = client.get(f"/api/users/{attendee.id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["email"] == "attendee@example.com"

    patch_res = client.patch(
        f"/api/users/{attendee.id}",
        headers=headers,
        json={
            "full_name": "  Ana Promovida  ",
            "role": "ORGANIZER",
            "is_active": False,
        },
    )
    assert patch_res.status_code == 200
    patched = patch_res.json()
    assert patched["full_name"] == "Ana Promovida"
    assert patched["role"] == "ORGANIZER"
    assert patched["is_active"] is False
    assert "password_hash" not in patched


def test_auth_ac_16_non_admin_user_management_returns_403(
    client: TestClient,
    db_session: Session,
) -> None:
    attendee = _create_user(
        db_session,
        email="attendee@example.com",
        role=UserRole.ATTENDEE,
    )
    organizer = _create_user(
        db_session,
        email="organizer@example.com",
        role=UserRole.ORGANIZER,
    )

    for non_admin in (attendee, organizer):
        headers = _auth_headers(non_admin)
        for res in (
            client.get("/api/users", headers=headers),
            client.get(f"/api/users/{attendee.id}", headers=headers),
            client.patch(
                f"/api/users/{attendee.id}",
                headers=headers,
                json={"full_name": "Intento"},
            ),
        ):
            assert res.status_code == 403
            assert res.json() == {
                "detail": "No tienes permisos para realizar esta acción"
            }


def test_auth_ac_17_admin_cannot_change_own_role_or_deactivate_self(
    client: TestClient,
    db_session: Session,
) -> None:
    admin1 = _create_user(
        db_session,
        email="admin1@example.com",
        role=UserRole.ADMIN,
    )
    _create_user(
        db_session,
        email="admin2@example.com",
        role=UserRole.ADMIN,
    )
    headers = _auth_headers(admin1)

    role_res = client.patch(
        f"/api/users/{admin1.id}",
        headers=headers,
        json={"role": "ORGANIZER"},
    )
    assert role_res.status_code == 400
    assert role_res.json() == {"detail": "No puedes cambiar tu propio rol"}

    deactivate_res = client.patch(
        f"/api/users/{admin1.id}",
        headers=headers,
        json={"is_active": False},
    )
    assert deactivate_res.status_code == 400
    assert deactivate_res.json() == {
        "detail": "No puedes desactivar tu propia cuenta"
    }

    name_res = client.patch(
        f"/api/users/{admin1.id}",
        headers=headers,
        json={"full_name": "Admin Uno Editado"},
    )
    assert name_res.status_code == 200
    assert name_res.json()["full_name"] == "Admin Uno Editado"


def test_auth_ac_18_last_active_admin_cannot_be_demoted_or_deactivated(
    client: TestClient,
    db_session: Session,
) -> None:
    from app.auth.dependencies import require_admin
    from app.main import app

    sole_admin = _create_user(
        db_session,
        email="sole-admin@example.com",
        role=UserRole.ADMIN,
    )
    other_actor = _create_user(
        db_session,
        email="actor@example.com",
        role=UserRole.ORGANIZER,
    )

    app.dependency_overrides[require_admin] = lambda: other_actor
    try:
        demote_res = client.patch(
            f"/api/users/{sole_admin.id}",
            json={"role": "ATTENDEE"},
        )
        assert demote_res.status_code == 409
        assert demote_res.json() == {
            "detail": "Debe existir al menos un administrador activo"
        }

        deactivate_res = client.patch(
            f"/api/users/{sole_admin.id}",
            json={"is_active": False},
        )
        assert deactivate_res.status_code == 409
        assert deactivate_res.json() == {
            "detail": "Debe existir al menos un administrador activo"
        }
    finally:
        app.dependency_overrides.pop(require_admin, None)


def test_auth_ac_18_concurrent_last_admin_demotions_keep_one_admin(
    test_engine,
    db_truncate,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from sqlmodel import select
    from app.users.schemas import AdminUserUpdateRequest
    from app.users.service import LastActiveAdminError, update_user_by_admin

    db_truncate()
    with Session(test_engine) as setup_session:
        admin1 = _create_user(
            setup_session,
            email="concurrent-admin1@example.com",
            role=UserRole.ADMIN,
        )
        admin2 = _create_user(
            setup_session,
            email="concurrent-admin2@example.com",
            role=UserRole.ADMIN,
        )
        admin1_id = admin1.id
        admin2_id = admin2.id
    assert admin1_id is not None and admin2_id is not None

    start_barrier = threading.Barrier(2)
    commit_barrier = threading.Barrier(2, timeout=0.2)

    def _demote(actor_id: int, target_id: int) -> str:
        with Session(test_engine) as session:
            actor = session.get(User, actor_id)
            assert actor is not None
            orig_commit = session.commit

            def _synced_commit() -> None:
                try:
                    commit_barrier.wait()
                except threading.BrokenBarrierError:
                    pass
                orig_commit()

            session.commit = _synced_commit  # type: ignore[method-assign]
            start_barrier.wait()
            try:
                update_user_by_admin(
                    session,
                    target_user_id=target_id,
                    actor=actor,
                    payload=AdminUserUpdateRequest(role=UserRole.ATTENDEE),
                )
                return "ok"
            except LastActiveAdminError:
                session.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_demote, admin1_id, admin2_id)
        f2 = pool.submit(_demote, admin2_id, admin1_id)
        results = sorted([f1.result(), f2.result()])

    assert results == ["conflict", "ok"]

    with Session(test_engine) as check_session:
        remaining_admins = list(
            check_session.exec(
                select(User).where(
                    User.role == UserRole.ADMIN.value,
                    User.is_active.is_(True),  # type: ignore[attr-defined]
                )
            ).all()
        )
        assert len(remaining_admins) == 1


def test_auth_ac_19_admin_update_validates_body_role_and_unknown_user(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    attendee = _create_user(
        db_session,
        email="attendee@example.com",
        role=UserRole.ATTENDEE,
    )
    headers = _auth_headers(admin)

    empty_res = client.patch(
        f"/api/users/{attendee.id}",
        headers=headers,
        json={},
    )
    assert empty_res.status_code == 422
    assert empty_res.json()["detail"] == "Error de validación en los datos enviados"
    assert any(
        err["message"] == "Debes indicar al menos un campo para actualizar"
        for err in empty_res.json()["errors"]
    )

    bad_role_res = client.patch(
        f"/api/users/{attendee.id}",
        headers=headers,
        json={"role": "SUPERADMIN"},
    )
    assert bad_role_res.status_code == 422
    assert bad_role_res.json()["detail"] == "Error de validación en los datos enviados"
    assert any(
        err["field"] == "role" and "Valor no permitido" in err["message"]
        for err in bad_role_res.json()["errors"]
    )

    email_field_res = client.patch(
        f"/api/users/{attendee.id}",
        headers=headers,
        json={"email": "nuevo@example.com"},
    )
    assert email_field_res.status_code == 422
    assert email_field_res.json()["detail"] == "Error de validación en los datos enviados"
    assert {
        "field": "email",
        "message": "Este campo no está permitido",
    } in email_field_res.json()["errors"]

    missing_res = client.patch(
        "/api/users/999999",
        headers=headers,
        json={"full_name": "Inexistente"},
    )
    assert missing_res.status_code == 404
    assert missing_res.json() == {"detail": "Usuario no encontrado"}


def test_auth_ac_31_admin_user_list_pagination_filters_and_spanish_422(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(
        db_session,
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    for idx in range(1, 4):
        _create_user(
            db_session,
            email=f"att{idx}@example.com",
            role=UserRole.ATTENDEE,
            is_active=(idx % 2 == 1),
        )
    headers = _auth_headers(admin)

    page1 = client.get("/api/users?page=1&size=2", headers=headers)
    assert page1.status_code == 200
    p1 = page1.json()
    assert p1["total"] == 4
    assert p1["page"] == 1
    assert p1["size"] == 2
    assert p1["pages"] == 2
    assert len(p1["items"]) == 2

    beyond = client.get("/api/users?page=5&size=2", headers=headers)
    assert beyond.status_code == 200
    assert beyond.json() == {
        "items": [],
        "total": 4,
        "page": 5,
        "size": 2,
        "pages": 2,
    }

    for invalid_query, expected_field in (
        ("page=0", "page"),
        ("size=0", "size"),
        ("size=51", "size"),
        ("role=INVALID", "role"),
        ("is_active=notabool", "is_active"),
    ):
        bad_res = client.get(f"/api/users?{invalid_query}", headers=headers)
        assert bad_res.status_code == 422
        bad_data = bad_res.json()
        assert bad_data["detail"] == "Error de validación en los datos enviados"
        assert any(
            err["field"] == expected_field and err["message"]
            for err in bad_data["errors"]
        )

    not_found_res = client.get("/api/users/999999", headers=headers)
    assert not_found_res.status_code == 404
    assert not_found_res.json() == {"detail": "Usuario no encontrado"}

    invalid_id_res = client.get("/api/users/0", headers=headers)
    assert invalid_id_res.status_code == 422
    assert (
        invalid_id_res.json()["detail"]
        == "Error de validación en los datos enviados"
    )
