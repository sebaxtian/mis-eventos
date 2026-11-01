"""Request and response schemas for the events domain."""

from typing import Any

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.datetime_utils import UTCDateTime
from app.core.pagination import PaginationParams
from app.events.models import EventStatus


def _strip_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


class EventImageUrls(BaseModel):
    w400: str
    w800: str
    w1200: str


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=5000)
    date: UTCDateTime
    total_capacity: int = Field(ge=1, le=100000)
    status: EventStatus = EventStatus.DRAFT

    @field_validator("title", "description", mode="before")
    @classmethod
    def _strip_fields(cls, value: Any) -> Any:
        return _strip_text(value)

    @field_validator("status")
    @classmethod
    def _validate_initial_status(cls, value: EventStatus) -> EventStatus:
        if value not in (EventStatus.DRAFT, EventStatus.PUBLISHED):
            raise ValueError("El estado inicial debe ser DRAFT o PUBLISHED")
        return value


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(
        default=None, min_length=10, max_length=5000
    )
    date: UTCDateTime | None = None
    total_capacity: int | None = Field(default=None, ge=1, le=100000)
    status: EventStatus | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def _strip_fields(cls, value: Any) -> Any:
        return _strip_text(value)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "EventUpdate":
        if not self.model_fields_set or all(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError(
                "Debes indicar al menos un campo para actualizar"
            )
        return self


class EventListParams(PaginationParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=50),
        search: str | None = Query(default=None),
        status: EventStatus | None = Query(default=None),
        mine: bool = Query(default=False),
    ) -> None:
        super().__init__(page=page, size=size)
        normalized_search = search.strip() if search is not None else None
        if normalized_search is not None and len(normalized_search) > 100:
            raise RequestValidationError(
                [
                    {
                        "type": "string_too_long",
                        "loc": ("query", "search"),
                        "msg": "String should have at most 100 characters",
                        "input": search,
                        "ctx": {"max_length": 100},
                    }
                ]
            )
        self.search = normalized_search or None
        self.status = status
        self.mine = mine


class EventRead(BaseModel):
    id: int
    title: str
    description: str
    date: UTCDateTime
    total_capacity: int
    registered_count: int
    available_capacity: int
    status: EventStatus
    organizer_id: int
    image_urls: EventImageUrls | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
