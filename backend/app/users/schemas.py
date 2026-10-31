"""Request and response schemas for user profiles."""

from typing import Any

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.datetime_utils import UTCDateTime
from app.core.pagination import PaginationParams
from app.users.models import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime


class UpdateMeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=120)

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_full_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _require_full_name(self) -> "UpdateMeRequest":
        if self.full_name is None:
            raise ValueError("Debes indicar al menos un campo para actualizar")
        return self


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_full_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "AdminUserUpdateRequest":
        if (
            self.full_name is None
            and self.role is None
            and self.is_active is None
        ):
            raise ValueError("Debes indicar al menos un campo para actualizar")
        return self


class UserListParams(PaginationParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=50),
        role: UserRole | None = Query(None),
        is_active: bool | None = Query(None),
    ) -> None:
        super().__init__(page=page, size=size)
        self.role = role
        self.is_active = is_active
