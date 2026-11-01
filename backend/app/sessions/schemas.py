"""Request and response schemas for the sessions domain."""

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from app.core.datetime_utils import serialize_utc_iso
from app.sessions.models import (
    CAPACITY_MAX,
    CAPACITY_MIN,
    DESCRIPTION_MAX_LENGTH,
    SPEAKER_MAX_LENGTH,
    SPEAKER_MIN_LENGTH,
    TITLE_MAX_LENGTH,
    TITLE_MIN_LENGTH,
)

START_BEFORE_END_MESSAGE = "La hora de inicio debe ser anterior a la hora de fin"
AWARE_DATETIME_MESSAGE = (
    "La fecha y hora debe incluir zona horaria (por ejemplo, Z)"
)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError(AWARE_DATETIME_MESSAGE)
    return value.astimezone(timezone.utc)


AwareUTCDateTime = Annotated[
    datetime,
    AfterValidator(_ensure_aware_utc),
    PlainSerializer(serialize_utc_iso, return_type=str, when_used="json"),
]


def _strip_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=TITLE_MIN_LENGTH,
        max_length=TITLE_MAX_LENGTH,
    )
    speaker: str = Field(
        min_length=SPEAKER_MIN_LENGTH,
        max_length=SPEAKER_MAX_LENGTH,
    )
    description: str | None = Field(
        default=None,
        max_length=DESCRIPTION_MAX_LENGTH,
    )
    start_time: AwareUTCDateTime
    end_time: AwareUTCDateTime
    capacity: int = Field(ge=CAPACITY_MIN, le=CAPACITY_MAX)

    @field_validator("title", "speaker", "description", mode="before")
    @classmethod
    def _strip_fields(cls, value: Any) -> Any:
        return _strip_text(value)

    @field_validator("description", mode="after")
    @classmethod
    def _empty_description_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value or None

    @model_validator(mode="after")
    def _validate_time_range(self) -> "SessionCreate":
        if self.start_time >= self.end_time:
            raise ValueError(START_BEFORE_END_MESSAGE)
        return self


class SessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(
        default=None,
        min_length=TITLE_MIN_LENGTH,
        max_length=TITLE_MAX_LENGTH,
    )
    speaker: str | None = Field(
        default=None,
        min_length=SPEAKER_MIN_LENGTH,
        max_length=SPEAKER_MAX_LENGTH,
    )
    description: str | None = Field(
        default=None,
        max_length=DESCRIPTION_MAX_LENGTH,
    )
    start_time: AwareUTCDateTime | None = None
    end_time: AwareUTCDateTime | None = None
    capacity: int | None = Field(
        default=None,
        ge=CAPACITY_MIN,
        le=CAPACITY_MAX,
    )

    @field_validator("title", "speaker", "description", mode="before")
    @classmethod
    def _strip_fields(cls, value: Any) -> Any:
        return _strip_text(value)

    @field_validator("description", mode="after")
    @classmethod
    def _empty_description_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value or None

    @model_validator(mode="after")
    def _require_updatable_fields(self) -> "SessionUpdate":
        if not self.model_fields_set:
            raise ValueError(
                "Debes indicar al menos un campo para actualizar"
            )
        for name in self.model_fields_set:
            if name != "description" and getattr(self, name) is None:
                raise ValueError("Este campo no puede ser nulo")
        return self


class SessionRead(BaseModel):
    id: int
    event_id: int
    title: str
    description: str | None
    speaker: str
    start_time: AwareUTCDateTime
    end_time: AwareUTCDateTime
    capacity: int
    registered_count: int
    available_capacity: int
    created_at: AwareUTCDateTime
    updated_at: AwareUTCDateTime


class SessionListRead(BaseModel):
    items: list[SessionRead]
    total: int
