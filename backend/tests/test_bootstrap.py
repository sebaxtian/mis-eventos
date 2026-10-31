from sqlalchemy import text
from sqlmodel import Session

from app.auth.security import verify_password
from app.users.models import UserRole


def test_auth_ac_20_bootstrap_creates_single_admin_idempotently(
    db_session: Session,
) -> None:
    from app.users.bootstrap import ensure_bootstrap_admin

    first = ensure_bootstrap_admin(
        db_session,
        email="  BootAdmin@Example.com  ",
        password="AdminBootPassword1!",
        full_name="  Administrador Inicial  ",
    )
    assert first is not None
    assert first.email == "bootadmin@example.com"
    assert first.full_name == "Administrador Inicial"
    assert UserRole(first.role) == UserRole.ADMIN
    assert first.is_active is True
    original_hash = first.password_hash
    assert verify_password("AdminBootPassword1!", original_hash) is True

    second = ensure_bootstrap_admin(
        db_session,
        email="bootadmin@example.com",
        password="DifferentPassword2!",
        full_name="Otro Nombre",
    )
    assert second is not None
    assert second.id == first.id
    assert second.password_hash == original_hash
    assert verify_password("AdminBootPassword1!", second.password_hash) is True
    assert verify_password("DifferentPassword2!", second.password_hash) is False

    total = db_session.exec(text("SELECT count(*) FROM users")).scalar_one()
    assert total == 1


def test_auth_ac_21_bootstrap_does_not_modify_existing_email(
    db_session: Session,
    caplog,
) -> None:
    import logging
    from app.auth.security import hash_password
    from app.users.bootstrap import ensure_bootstrap_admin
    from app.users.models import User

    existing_attendee = User(
        email="attendee@example.com",
        password_hash=hash_password("OriginalPass123!"),
        full_name="Ana Asistente",
        role=UserRole.ATTENDEE,
        is_active=True,
    )
    db_session.add(existing_attendee)
    db_session.commit()
    db_session.refresh(existing_attendee)
    original_hash = existing_attendee.password_hash

    with caplog.at_level(logging.WARNING):
        result = ensure_bootstrap_admin(
            db_session,
            email="ATTENDEE@example.com",
            password="AttemptedAdminPass999!",
            full_name="Intento Admin",
        )

    assert result is not None
    assert result.id == existing_attendee.id
    assert UserRole(result.role) == UserRole.ATTENDEE
    assert result.password_hash == original_hash
    assert verify_password("OriginalPass123!", result.password_hash) is True
    assert verify_password("AttemptedAdminPass999!", result.password_hash) is False

    total = db_session.exec(text("SELECT count(*) FROM users")).scalar_one()
    assert total == 1

    assert len(caplog.records) >= 1
    assert "attendee@example.com" not in caplog.text.lower()
    assert "AttemptedAdminPass999!" not in caplog.text


def test_auth_ac_22_bootstrap_partial_env_fails_with_generic_spanish_error(
    db_session: Session,
) -> None:
    import pytest
    from app.core.config import Settings
    from app.users.bootstrap import ensure_bootstrap_admin, run_startup_bootstrap

    for partial_email, partial_password in (
        ("admin@example.com", None),
        ("admin@example.com", "   "),
        (None, "SuperSecretBootstrapPass!"),
        ("   ", "SuperSecretBootstrapPass!"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            ensure_bootstrap_admin(
                db_session,
                email=partial_email,
                password=partial_password,
            )
        msg = str(exc_info.value)
        assert msg == "Configuración incompleta del administrador inicial"
        assert "SuperSecretBootstrapPass!" not in msg
        assert "admin@example.com" not in msg

        partial_settings = Settings(
            _env_file=None,
            bootstrap_admin_email=partial_email,
            bootstrap_admin_password=partial_password,
        )
        with pytest.raises(RuntimeError) as startup_exc:
            run_startup_bootstrap(partial_settings)
        assert (
            str(startup_exc.value)
            == "Configuración incompleta del administrador inicial"
        )
        assert "SuperSecretBootstrapPass!" not in str(startup_exc.value)


def test_auth_ac_23_jwt_secret_validation_rejects_short_or_placeholder_in_production() -> None:
    from pathlib import Path
    import pytest
    from app.core.config import Settings

    short_secret = "short-secret-value-123"
    with pytest.raises(ValueError) as short_exc:
        Settings(_env_file=None, jwt_secret_key=short_secret)
    assert short_secret not in str(short_exc.value)
    assert "32" in str(short_exc.value)

    placeholder = "change-me-in-production-min-32-chars"
    with pytest.raises(ValueError) as prod_exc:
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key=placeholder,
        )
    assert placeholder not in str(prod_exc.value)

    valid_prod = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="custom-production-jwt-key-with-more-than-32-chars",
    )
    assert valid_prod.app_env == "production"

    env_example = (
        Path(__file__).resolve().parents[2] / ".env.example"
    ).read_text(encoding="utf-8")
    for expected_var in (
        "APP_ENV=development",
        "JWT_SECRET_KEY=change-me-in-production-min-32-chars",
        "JWT_EXPIRE_MINUTES=480",
        "BOOTSTRAP_ADMIN_EMAIL=",
        "BOOTSTRAP_ADMIN_PASSWORD=",
        "BOOTSTRAP_ADMIN_FULL_NAME=Administrador",
    ):
        assert expected_var in env_example
