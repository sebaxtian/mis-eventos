"""Request and response schemas for the registrations domain."""

from fastapi import Query
from pydantic import BaseModel

from app.core.datetime_utils import UTCDateTime
from app.core.pagination import PaginatedResponse, PaginationParams
from app.events.models import EventStatus
from app.registrations.models import RegistrationStatus


class RegistrationEventSummary(BaseModel):
    id: int
    title: str
    date: UTCDateTime
    status: EventStatus


class RegistrationSessionSummary(BaseModel):
    id: int
    title: str
    speaker: str
    start_time: UTCDateTime
    end_time: UTCDateTime


class RegistrationRead(BaseModel):
    id: int
    user_id: int
    event_id: int
    session_id: int | None
    status: RegistrationStatus
    event: RegistrationEventSummary
    session: RegistrationSessionSummary | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class RegistrationListRead(PaginatedResponse[RegistrationRead]):
    pass


class RegistrationListParams(PaginationParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=50),
        status: RegistrationStatus | None = Query(default=None),
        event_id: int | None = Query(default=None, ge=1),
    ) -> None:
        super().__init__(page=page, size=size)
        self.status = status
        self.event_id = event_id


class EventRegistrationListParams(PaginationParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=50),
        status: RegistrationStatus | None = Query(default=None),
    ) -> None:
        super().__init__(page=page, size=size)
        self.status = status
