"""Bootstrap helper for the initial administrator account."""

import logging

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.schemas import RegisterRequest
from app.auth.security import hash_password
from app.core.config import Settings, settings
from app.core.database import engine
from app.users.models import User, UserRole

logger = logging.getLogger(__name__)


def ensure_bootstrap_admin(
    session: Session,
    email: str | None,
    password: str | None,
    full_name: str = "Administrador",
) -> User | None:
    raw_email = (email or "").strip()
    raw_password = password or ""
    has_email = bool(raw_email)
    has_password = bool(raw_password.strip())
    if not has_email and not has_password:
        return None
    if not has_email or not has_password:
        raise RuntimeError("Configuración incompleta del administrador inicial")

    normalized_email = raw_email.lower()
    existing = session.exec(
        select(User).where(User.email == normalized_email)
    ).first()
    if existing is not None:
        logger.warning(
            "Bootstrap skipped: user already exists with user_id=%s role=%s",
            existing.id,
            existing.role,
        )
        return existing

    try:
        validated = RegisterRequest(
            email=normalized_email,
            password=raw_password,
            full_name=full_name or "Administrador",
        )
    except ValidationError as exc:
        raise RuntimeError(
            "Configuración inválida del administrador inicial"
        ) from exc

    admin = User(
        email= str(validated.email),
        password_hash=hash_password(validated.password),
        full_name=validated.full_name,
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return session.exec(
            select(User).where(User.email == normalized_email)
        ).first()
    session.refresh(admin)
    logger.info("Bootstrap administrator created with user_id=%s", admin.id)
    return admin


def run_startup_bootstrap(current_settings: Settings = settings) -> User | None:
    raw_email = (current_settings.bootstrap_admin_email or "").strip()
    raw_password = current_settings.bootstrap_admin_password or ""
    has_email = bool(raw_email)
    has_password = bool(raw_password.strip())
    if not has_email and not has_password:
        return None
    if not has_email or not has_password:
        raise RuntimeError("Configuración incompleta del administrador inicial")
    with Session(engine) as session:
        return ensure_bootstrap_admin(
            session,
            email=raw_email,
            password=raw_password,
            full_name=current_settings.bootstrap_admin_full_name,
        )
