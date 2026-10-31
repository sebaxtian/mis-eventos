from datetime import datetime, timezone
from typing import Annotated
from pydantic import AfterValidator, PlainSerializer


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def serialize_utc_iso(value: datetime) -> str:
    normalized = ensure_utc(value)
    return normalized.isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[
    datetime,
    AfterValidator(ensure_utc),
    PlainSerializer(serialize_utc_iso, return_type=str, when_used="json"),
]
