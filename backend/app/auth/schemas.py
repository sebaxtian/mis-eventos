"""Request and response schemas for authentication."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.users.schemas import UserRead


def _normalize_email_value(value: Any) -> Any:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if len(normalized) > 254:
            raise ValueError("El correo electrónico no es válido")
        return normalized
    return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128, repr=False)
    full_name: str = Field(min_length=2, max_length=120)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: Any) -> Any:
        return _normalize_email_value(value)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("La contraseña no puede contener solo espacios")
        return value

    @field_validator("full_name", mode="before")
    @classmethod
    def _normalize_full_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128, repr=False)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: Any) -> Any:
        return _normalize_email_value(value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserRead
