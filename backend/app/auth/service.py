"""Authentication business services."""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth import security
from app.auth.schemas import RegisterRequest
from app.auth.security import hash_password, password_needs_rehash, verify_password
from app.users.models import User, UserRole


class EmailAlreadyExistsError(Exception):
    """Raised when the requested email is already registered."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(session: Session, payload: RegisterRequest) -> User:
    email = normalize_email(payload.email)
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing is not None:
        raise EmailAlreadyExistsError

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.ATTENDEE,
        is_active=True,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailAlreadyExistsError from exc
    session.refresh(user)
    return user


def authenticate_user(
    session: Session,
    email: str,
    password: str,
) -> User | None:
    normalized = normalize_email(email)
    user = session.exec(select(User).where(User.email == normalized)).first()
    if user is None:
        verify_password(password, security.DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        user.updated_at = datetime.now(timezone.utc)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
