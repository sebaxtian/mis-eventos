"""Password hashing and JWT helpers."""

from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import jwt

from app.core.config import settings
from app.users.models import User, UserRole

_password_hasher = PasswordHasher()

DUMMY_PASSWORD_HASH = _password_hasher.hash("mis-eventos-dummy-password")


def get_password_hasher() -> PasswordHasher:
    return _password_hasher


def hash_password(password: str) -> str:
    return get_password_hasher().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return get_password_hasher().verify(password_hash, password) is True
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return get_password_hasher().check_needs_rehash(password_hash)
    except (InvalidHashError, VerificationError):
        return False


def create_access_token(user: User) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    role_val = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    payload = {
        "sub": str(user.id),
        "role": role_val,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    encoded = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    return encoded, settings.jwt_expire_minutes * 60


class InvalidAccessTokenError(Exception):
    """Raised when an access token is invalid."""


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as exc:
        raise InvalidAccessTokenError from exc

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.isdigit():
        raise InvalidAccessTokenError
    return payload
