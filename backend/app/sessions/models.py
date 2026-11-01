"""Session domain models."""

from datetime import datetime

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
)
from sqlmodel import Field, SQLModel

from app.core.datetime_utils import utc_now

TITLE_MIN_LENGTH = 3
TITLE_MAX_LENGTH = 160
SPEAKER_MIN_LENGTH = 2
SPEAKER_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 2000
CAPACITY_MIN = 1
CAPACITY_MAX = 100000


class Session(SQLModel, table=True):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "start_time < end_time",
            name="ck_sessions_time_range",
        ),
        CheckConstraint(
            "capacity >= 1",
            name="ck_sessions_capacity_positive",
        ),
        CheckConstraint(
            "capacity <= 100000",
            name="ck_sessions_capacity_max",
        ),
        CheckConstraint(
            "char_length(title) BETWEEN 3 AND 160",
            name="ck_sessions_title_length",
        ),
        CheckConstraint(
            "char_length(speaker) BETWEEN 2 AND 120",
            name="ck_sessions_speaker_length",
        ),
        CheckConstraint(
            "description IS NULL OR char_length(description) <= 2000",
            name="ck_sessions_description_length",
        ),
        Index(
            "ix_sessions_event_id_start_time",
            "event_id",
            "start_time",
        ),
        Index(
            "ix_sessions_event_id_end_time",
            "event_id",
            "end_time",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(
        sa_column=Column(
            "event_id",
            Integer,
            ForeignKey(
                "events.id",
                name="fk_sessions_event_id_events",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
    )
    title: str = Field(
        sa_column=Column("title", String(TITLE_MAX_LENGTH), nullable=False),
    )
    speaker: str = Field(
        sa_column=Column("speaker", String(SPEAKER_MAX_LENGTH), nullable=False),
    )
    description: str | None = Field(
        default=None,
        sa_column=Column("description", Text, nullable=True),
    )
    start_time: datetime = Field(
        sa_column=Column(
            "start_time",
            DateTime(timezone=True),
            nullable=False,
        ),
    )
    end_time: datetime = Field(
        sa_column=Column(
            "end_time",
            DateTime(timezone=True),
            nullable=False,
        ),
    )
    capacity: int = Field(
        sa_column=Column("capacity", Integer, nullable=False),
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
