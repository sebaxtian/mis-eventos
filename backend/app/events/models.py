"""Event domain models."""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlmodel import Field, SQLModel

from app.core.datetime_utils import utc_now


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"


class Event(SQLModel, table=True):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'CANCELLED')",
            name="ck_events_status",
        ),
        CheckConstraint(
            "total_capacity >= 1",
            name="ck_events_total_capacity_positive",
        ),
        Index("ix_events_organizer_id", "organizer_id"),
        Index("ix_events_status", "status"),
        Index("ix_events_date", "date"),
        Index(
            "ix_events_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    organizer_id: int = Field(
        sa_column=Column(
            "organizer_id",
            Integer,
            ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    title: str = Field(
        sa_column=Column("title", String(160), nullable=False),
    )
    description: str = Field(
        sa_column=Column("description", Text, nullable=False),
    )
    date: datetime = Field(
        sa_column=Column("date", DateTime(timezone=True), nullable=False),
    )
    total_capacity: int = Field(
        sa_column=Column("total_capacity", Integer, nullable=False),
    )
    status: EventStatus = Field(
        default=EventStatus.DRAFT,
        sa_column=Column(
            "status",
            String(20),
            nullable=False,
            server_default=text("'DRAFT'"),
        ),
    )
    image_key: str | None = Field(
        default=None,
        sa_column=Column("image_key", String(64), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
