from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session


def test_auth_ac_01_register_returns_attendee_without_password_hash(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "ana@example.com"
    assert payload["full_name"] == "Ana Pérez"
    assert payload["role"] == "ATTENDEE"
    assert payload["is_active"] is True
    assert isinstance(payload["id"], int)
    assert "created_at" in payload
    assert "updated_at" in payload
    assert "access_token" not in payload
    assert "token" not in payload
    assert "password_hash" not in payload
    assert "password" not in payload


def test_auth_ac_02_register_duplicate_email_returns_409_case_insensitive(
    client: TestClient,
    db_session: Session,
) -> None:
    first = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert first.status_code == 201

    duplicate = client.post(
        "/api/auth/register",
        json={
            "email": " Ana@Example.COM ",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Ya existe una cuenta con este correo electrónico"
    }

    total = db_session.exec(text("SELECT count(*) FROM users")).scalar_one()
    assert total == 1


def test_auth_ac_03_register_rejects_role_field_with_spanish_422(
    client: TestClient,
    db_session: Session,
) -> None:
    for forbidden_field, forbidden_val in (("role", "ADMIN"), ("is_active", False)):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "ana@example.com",
                "password": "Secreto123",
                "full_name": "Ana Pérez",
                forbidden_field: forbidden_val,
            },
        )

        assert response.status_code == 422
        payload = response.json()
        assert payload["detail"] == "Error de validación en los datos enviados"
        assert {
            "field": forbidden_field,
            "message": "Este campo no está permitido",
        } in payload["errors"]

    total = db_session.exec(text("SELECT count(*) FROM users")).scalar_one()
    assert total == 0

    valid_res = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert valid_res.status_code == 201
    assert valid_res.json()["role"] == "ATTENDEE"


def test_auth_ac_04_register_normalizes_email_and_validates_full_name(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/auth/register",
        json={
            "email": "  Ana.Perez@Example.COM  ",
            "password": "Secreto123",
            "full_name": "  Ana María O'Connor-López  ",
        },
    )
    assert created.status_code == 201
    created_data = created.json()
    assert created_data["email"] == "ana.perez@example.com"
    assert created_data["full_name"] == "Ana María O'Connor-López"

    bad_email = client.post(
        "/api/auth/register",
        json={
            "email": "correo-invalido",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert bad_email.status_code == 422
    bad_email_data = bad_email.json()
    assert bad_email_data["detail"] == "Error de validación en los datos enviados"
    assert {
        "field": "email",
        "message": "El correo electrónico no es válido",
    } in bad_email_data["errors"]

    for invalid_name in ("A", "   a   ", "   ", "N" * 121):
        bad_name = client.post(
            "/api/auth/register",
            json={
                "email": "otro@example.com",
                "password": "Secreto123",
                "full_name": invalid_name,
            },
        )
        assert bad_name.status_code == 422
        bad_name_data = bad_name.json()
        assert bad_name_data["detail"] == "Error de validación en los datos enviados"
        assert any(
            err["field"] == "full_name" and "caracteres" in err["message"]
            for err in bad_name_data["errors"]
        )


def test_auth_ac_05_password_policy_accepts_8_and_128_rejects_7_and_129(
    client: TestClient,
    db_session: Session,
) -> None:
    from app.auth.security import verify_password
    from app.users.models import User

    res_8 = client.post(
        "/api/auth/register",
        json={
            "email": "eight@example.com",
            "password": "  ab12  ",
            "full_name": "Usuario Ocho",
        },
    )
    assert res_8.status_code == 201

    res_128 = client.post(
        "/api/auth/register",
        json={
            "email": "max128@example.com",
            "password": "P" * 128,
            "full_name": "Usuario Max",
        },
    )
    assert res_128.status_code == 201

    user_8 = db_session.get(User, res_8.json()["id"])
    assert user_8 is not None
    assert user_8.password_hash != "  ab12  "
    assert user_8.password_hash.startswith("$argon2id$")
    assert verify_password("  ab12  ", user_8.password_hash) is True
    assert verify_password("ab12", user_8.password_hash) is False

    for invalid_password in ("1234567", "P" * 129, "        "):
        bad_res = client.post(
            "/api/auth/register",
            json={
                "email": "invalid@example.com",
                "password": invalid_password,
                "full_name": "Usuario Inválido",
            },
        )
        assert bad_res.status_code == 422
        bad_data = bad_res.json()
        assert bad_data["detail"] == "Error de validación en los datos enviados"
        assert any(
            err["field"] == "password"
            and (
                "caracteres" in err["message"]
                or "espacios" in err["message"]
                or "contraseña" in err["message"].lower()
            )
            for err in bad_data["errors"]
        )


def test_auth_ac_06_login_returns_bearer_jwt_with_expected_claims(
    client: TestClient,
) -> None:
    import jwt
    from app.core.config import settings

    reg = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert reg.status_code == 201
    registered_user = reg.json()

    login_res = client.post(
        "/api/auth/login",
        json={
            "email": "  ANA@Example.com  ",
            "password": "Secreto123",
        },
    )
    assert login_res.status_code == 200
    payload = login_res.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 28800
    assert payload["user"]["id"] == registered_user["id"]
    assert payload["user"]["email"] == "ana@example.com"
    assert payload["user"]["role"] == "ATTENDEE"
    assert "password_hash" not in payload["user"]

    header = jwt.get_unverified_header(payload["access_token"])
    assert header["alg"] == "HS256"

    claims = jwt.decode(
        payload["access_token"],
        settings.jwt_secret_key,
        algorithms=["HS256"],
    )
    assert set(claims.keys()) == {"sub", "role", "iat", "exp"}
    assert claims["sub"] == str(registered_user["id"])
    assert claims["role"] == "ATTENDEE"
    assert claims["exp"] - claims["iat"] == 28800
    assert "jti" not in claims
    assert "iss" not in claims
    assert "aud" not in claims


def test_auth_ac_07_login_is_generic_for_unknown_wrong_and_inactive(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    from app.auth import security, service
    from app.users.models import User

    reg = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert reg.status_code == 201
    user_id = reg.json()["id"]

    verified_hashes: list[str] = []
    real_verify = security.verify_password

    def _spy_verify(password: str, password_hash: str) -> bool:
        verified_hashes.append(password_hash)
        return real_verify(password, password_hash)

    monkeypatch.setattr(service, "verify_password", _spy_verify)

    unknown_res = client.post(
        "/api/auth/login",
        json={"email": "noexiste@example.com", "password": "Secreto123"},
    )
    assert unknown_res.status_code == 401
    assert unknown_res.json() == {"detail": "Credenciales inválidas"}
    assert unknown_res.headers.get("www-authenticate") == "Bearer"
    assert verified_hashes == [security.DUMMY_PASSWORD_HASH]

    wrong_res = client.post(
        "/api/auth/login",
        json={"email": "ana@example.com", "password": "Incorrecta999"},
    )
    assert wrong_res.status_code == 401
    assert wrong_res.json() == {"detail": "Credenciales inválidas"}
    assert wrong_res.headers.get("www-authenticate") == "Bearer"

    user = db_session.get(User, user_id)
    assert user is not None
    user.is_active = False
    db_session.add(user)
    db_session.commit()

    inactive_res = client.post(
        "/api/auth/login",
        json={"email": "ana@example.com", "password": "Secreto123"},
    )
    assert inactive_res.status_code == 401
    assert inactive_res.json() == {"detail": "Credenciales inválidas"}
    assert inactive_res.headers.get("www-authenticate") == "Bearer"


def test_auth_ac_08_missing_token_returns_401_with_www_authenticate(
    client: TestClient,
) -> None:
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json() == {"detail": "No autenticado o sesión expirada"}
    assert res.headers.get("www-authenticate") == "Bearer"

    non_bearer_res = client.get(
        "/api/auth/me",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert non_bearer_res.status_code == 401
    assert non_bearer_res.json() == {"detail": "No autenticado o sesión expirada"}
    assert non_bearer_res.headers.get("www-authenticate") == "Bearer"


def test_auth_ac_09_tampered_or_wrong_algorithm_token_returns_401(
    client: TestClient,
) -> None:
    import base64
    from datetime import datetime, timedelta, timezone
    import json
    import jwt
    from app.core.config import settings

    reg = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert reg.status_code == 201
    user_id = str(reg.json()["id"])

    now = datetime.now(timezone.utc)
    base_claims = {
        "sub": user_id,
        "role": "ATTENDEE",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=60)).timestamp()),
    }

    wrong_secret_token = jwt.encode(
        base_claims,
        "other-secret-key-with-at-least-32-chars",
        algorithm="HS256",
    )
    hs512_token = jwt.encode(
        base_claims,
        settings.jwt_secret_key,
        algorithm="HS512",
    )
    valid_token = jwt.encode(
        base_claims,
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    tampered_token = valid_token[:-4] + ("AAAA" if valid_token[-4:] != "AAAA" else "BBBB")

    def _b64url(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    alg_none_token = f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(base_claims)}."
    missing_exp_token = jwt.encode(
        {"sub": user_id, "role": "ATTENDEE", "iat": int(now.timestamp())},
        settings.jwt_secret_key,
        algorithm="HS256",
    )

    for bad_token in (
        wrong_secret_token,
        hs512_token,
        tampered_token,
        alg_none_token,
        missing_exp_token,
        "not-a-jwt-token",
    ):
        res = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert res.status_code == 401
        assert res.json() == {"detail": "No autenticado o sesión expirada"}
        assert res.headers.get("www-authenticate") == "Bearer"


def test_auth_ac_10_expired_token_returns_401(
    client: TestClient,
) -> None:
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.core.config import settings

    reg = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert reg.status_code == 201
    user_id = str(reg.json()["id"])

    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    expired_token = jwt.encode(
        {
            "sub": user_id,
            "role": "ATTENDEE",
            "iat": int((past - timedelta(minutes=60)).timestamp()),
            "exp": int(past.timestamp()),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )

    res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res.status_code == 401
    assert res.json() == {"detail": "No autenticado o sesión expirada"}
    assert res.headers.get("www-authenticate") == "Bearer"


def test_auth_ac_11_token_for_missing_user_returns_401(
    client: TestClient,
) -> None:
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.core.config import settings

    now = datetime.now(timezone.utc)
    for bad_sub in ("999999", "not-an-int"):
        token = jwt.encode(
            {
                "sub": bad_sub,
                "role": "ATTENDEE",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=60)).timestamp()),
            },
            settings.jwt_secret_key,
            algorithm="HS256",
        )
        res = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 401
        assert res.json() == {"detail": "No autenticado o sesión expirada"}
        assert res.headers.get("www-authenticate") == "Bearer"


def test_auth_ac_12_inactive_user_token_returns_401(
    client: TestClient,
    db_session: Session,
) -> None:
    from app.users.models import User

    reg = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert reg.status_code == 201
    user_id = reg.json()["id"]

    login_res = client.post(
        "/api/auth/login",
        json={"email": "ana@example.com", "password": "Secreto123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    user = db_session.get(User, user_id)
    assert user is not None
    user.is_active = False
    db_session.add(user)
    db_session.commit()

    res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401
    assert res.json() == {"detail": "No autenticado o sesión expirada"}
    assert res.headers.get("www-authenticate") == "Bearer"


def test_auth_ac_13_authorization_uses_database_role_not_token_claim(
    client: TestClient,
    db_session: Session,
) -> None:
    from datetime import datetime, timedelta, timezone
    from fastapi import Depends
    import jwt
    from app.auth.dependencies import require_roles
    from app.core.config import settings
    from app.main import app
    from app.users.models import User, UserRole

    @app.get("/api/_test/admin-only")
    def _admin_only(
        current_user: User = Depends(require_roles(UserRole.ADMIN)),
    ) -> dict[str, str]:
        return {"role": current_user.role.value}

    try:
        reg = client.post(
            "/api/auth/register",
            json={
                "email": "ana@example.com",
                "password": "Secreto123",
                "full_name": "Ana Pérez",
            },
        )
        assert reg.status_code == 201
        user_id = reg.json()["id"]

        now = datetime.now(timezone.utc)
        forged_admin_claim_token = jwt.encode(
            {
                "sub": str(user_id),
                "role": "ADMIN",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=60)).timestamp()),
            },
            settings.jwt_secret_key,
            algorithm="HS256",
        )

        denied = client.get(
            "/api/_test/admin-only",
            headers={"Authorization": f"Bearer {forged_admin_claim_token}"},
        )
        assert denied.status_code == 403
        assert denied.json() == {
            "detail": "No tienes permisos para realizar esta acción"
        }

        attendee_claim_token = jwt.encode(
            {
                "sub": str(user_id),
                "role": "ATTENDEE",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=60)).timestamp()),
            },
            settings.jwt_secret_key,
            algorithm="HS256",
        )
        user = db_session.get(User, user_id)
        assert user is not None
        user.role = UserRole.ADMIN
        db_session.add(user)
        db_session.commit()

        allowed = client.get(
            "/api/_test/admin-only",
            headers={"Authorization": f"Bearer {attendee_claim_token}"},
        )
        assert allowed.status_code == 200
        assert allowed.json() == {"role": "ADMIN"}
    finally:
        app.router.routes = [
            r
            for r in app.router.routes
            if getattr(r, "path", None) != "/api/_test/admin-only"
        ]


def test_auth_ac_14_attendee_reads_and_updates_own_profile_only(
    client: TestClient,
) -> None:
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "ana@example.com",
            "password": "Secreto123",
            "full_name": "Ana Pérez",
        },
    )
    assert reg.status_code == 201

    login_res = client.post(
        "/api/auth/login",
        json={"email": "ana@example.com", "password": "Secreto123"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "ana@example.com"
    assert me_res.json()["full_name"] == "Ana Pérez"
    assert me_res.json()["role"] == "ATTENDEE"
    assert "password_hash" not in me_res.json()

    patch_res = client.patch(
        "/api/auth/me",
        headers=headers,
        json={"full_name": "  Ana María Pérez  "},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["full_name"] == "Ana María Pérez"
    assert patch_res.json()["email"] == "ana@example.com"
    assert patch_res.json()["role"] == "ATTENDEE"

    empty_res = client.patch("/api/auth/me", headers=headers, json={})
    assert empty_res.status_code == 422
    assert empty_res.json()["detail"] == "Error de validación en los datos enviados"
    assert any(
        err["message"] == "Debes indicar al menos un campo para actualizar"
        for err in empty_res.json()["errors"]
    )

    for forbidden_field, forbidden_val in (
        ("email", "otra@example.com"),
        ("role", "ADMIN"),
        ("is_active", False),
    ):
        bad_res = client.patch(
            "/api/auth/me",
            headers=headers,
            json={"full_name": "Ana María Pérez", forbidden_field: forbidden_val},
        )
        assert bad_res.status_code == 422
        assert bad_res.json()["detail"] == "Error de validación en los datos enviados"
        assert {
            "field": forbidden_field,
            "message": "Este campo no está permitido",
        } in bad_res.json()["errors"]


def test_auth_ac_29_no_password_hash_or_secret_in_responses_or_logs(
    client: TestClient,
    db_session: Session,
    caplog,
) -> None:
    import logging
    from app.auth.schemas import LoginRequest, RegisterRequest
    from app.core.config import settings
    from app.users.models import User

    raw_password = "ClaveUltraSecreta99!"
    with caplog.at_level(logging.DEBUG):
        reg_res = client.post(
            "/api/auth/register",
            json={
                "email": "privacidad@example.com",
                "password": raw_password,
                "full_name": "Persona Privada",
            },
        )
        assert reg_res.status_code == 201

        login_res = client.post(
            "/api/auth/login",
            json={"email": "privacidad@example.com", "password": raw_password},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        me_res = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200

        bad_reg_res = client.post(
            "/api/auth/register",
            json={
                "email": "privacidad@example.com",
                "password": "short",
                "full_name": "Persona Privada",
            },
        )
        assert bad_reg_res.status_code == 422

    user = db_session.get(User, reg_res.json()["id"])
    assert user is not None

    for response in (reg_res, login_res, me_res, bad_reg_res):
        assert "password_hash" not in response.text
        assert user.password_hash not in response.text
        assert raw_password not in response.text
        assert settings.jwt_secret_key not in response.text
        assert "short" not in response.text

    assert raw_password not in caplog.text
    assert user.password_hash not in caplog.text
    assert settings.jwt_secret_key not in caplog.text
    assert "privacidad@example.com" not in caplog.text

    reg_model = RegisterRequest(
        email="privacidad@example.com",
        password=raw_password,
        full_name="Persona Privada",
    )
    login_model = LoginRequest(
        email="privacidad@example.com",
        password=raw_password,
    )
    assert raw_password not in repr(reg_model)
    assert raw_password not in repr(login_model)
    assert user.password_hash not in repr(user)
    assert settings.jwt_secret_key not in repr(settings)


def test_auth_ac_30_only_attendee_role_can_register_for_events() -> None:
    from app.auth.policies import can_register_for_events
    from app.users.models import UserRole

    assert can_register_for_events(UserRole.ATTENDEE) is True
    assert can_register_for_events(UserRole.ORGANIZER) is False
    assert can_register_for_events(UserRole.ADMIN) is False


def test_auth_ac_08_www_authenticate_header_survives_exception_handler(
    client: TestClient,
) -> None:
    from fastapi import HTTPException
    from app.main import app

    @app.get("/api/_test/unauth-translated")
    def _unauth_translated() -> None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        missing_res = client.get("/api/auth/me")
        assert missing_res.status_code == 401
        assert missing_res.json() == {"detail": "No autenticado o sesión expirada"}
        assert missing_res.headers.get("www-authenticate") == "Bearer"

        invalid_res = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert invalid_res.status_code == 401
        assert invalid_res.json() == {"detail": "No autenticado o sesión expirada"}
        assert invalid_res.headers.get("www-authenticate") == "Bearer"

        translated_res = client.get("/api/_test/unauth-translated")
        assert translated_res.status_code == 401
        assert translated_res.json() == {
            "detail": "No autenticado o sesión expirada"
        }
        assert translated_res.headers.get("www-authenticate") == "Bearer"
    finally:
        app.router.routes = [
            r
            for r in app.router.routes
            if getattr(r, "path", None) != "/api/_test/unauth-translated"
        ]


def test_auth_ac_04_translates_email_and_extra_forbidden_errors_to_spanish(
    client: TestClient,
) -> None:
    from app.core.exceptions import _translate_validation_error

    for bad_email in ("sin-arroba", "ana@dominio-sin-punto", "a" * 250 + "@ex.com"):
        res = client.post(
            "/api/auth/register",
            json={
                "email": bad_email,
                "password": "Secreto123",
                "full_name": "Ana Pérez",
                "unexpected": "x",
            },
        )
        assert res.status_code == 422
        body = res.json()
        assert body["detail"] == "Error de validación en los datos enviados"
        assert {
            "field": "email",
            "message": "El correo electrónico no es válido",
        } in body["errors"]
        assert {
            "field": "unexpected",
            "message": "Este campo no está permitido",
        } in body["errors"]

    assert (
        _translate_validation_error({"type": "string_pattern_mismatch"})
        == "El formato del campo no es válido"
    )
    assert (
        _translate_validation_error(
            {
                "type": "value_error",
                "loc": ("body", "email"),
                "msg": "value error, The part after the @-sign is not valid",
            }
        )
        == "El correo electrónico no es válido"
    )


def test_auth_ac_02_users_email_unique_constraint_and_indexes(
    db_session: Session,
) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.users.models import User

    constraints = {
        row[0]: row[1]
        for row in db_session.exec(
            text(
                """
                SELECT conname, contype
                FROM pg_constraint
                WHERE conrelid = 'users'::regclass
                """
            )
        ).all()
    }
    assert constraints.get("uq_users_email") == "u"
    assert constraints.get("ck_users_role") == "c"

    indexes = {
        row[0]
        for row in db_session.exec(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'users'")
        ).all()
    }
    assert "ix_users_role" in indexes
    assert "ix_users_is_active" in indexes

    inserted = db_session.exec(
        text(
            """
            INSERT INTO users (email, password_hash, full_name)
            VALUES ('sql-default@example.com', '$argon2id$dummy', 'SQL Default')
            RETURNING role, is_active, created_at, updated_at
            """
        )
    ).one()
    assert inserted[0] == "ATTENDEE"
    assert inserted[1] is True
    assert inserted[2] is not None
    assert inserted[3] is not None

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.exec(
                text(
                    """
                    INSERT INTO users (email, password_hash, full_name)
                    VALUES ('sql-default@example.com', '$argon2id$dummy', 'Dup')
                    """
                )
            )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.exec(
                text(
                    """
                    INSERT INTO users (email, password_hash, full_name, role)
                    VALUES ('bad-role@example.com', '$argon2id$dummy', 'Bad', 'SUPERUSER')
                    """
                )
            )

    in_memory = User(
        email="mem@example.com",
        password_hash="$argon2id$dummy",
        full_name="En Memoria",
    )
    assert in_memory.created_at is not None
    assert in_memory.updated_at is not None
