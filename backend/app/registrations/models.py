"""Registration domain models."""

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
    func,
    text,
)
from sqlmodel import Field, SQLModel

from app.core.datetime_utils import utc_now


class RegistrationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class Registration(SQLModel, table=True):
    __tablename__ = "registrations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'CANCELLED')",
            name="ck_registrations_status",
        ),
        Index(
            "uq_registrations_active_event",
            "user_id",
            "event_id",
            unique=True,
            postgresql_where=text(
                "status = 'ACTIVE' AND session_id IS NULL"
            ),
        ),
        Index(
            "uq_registrations_active_session",
            "user_id",
            "session_id",
            unique=True,
            postgresql_where=text(
                "status = 'ACTIVE' AND session_id IS NOT NULL"
            ),
        ),
        Index("ix_registrations_event_id_status", "event_id", "status"),
        Index(
            "ix_registrations_session_id_status",
            "session_id",
            "status",
        ),
        Index(
            "ix_registrations_user_id_status_created_at",
            "user_id",
            "status",
            "created_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            "user_id",
            Integer,
            ForeignKey(
                "users.id",
                name="fk_registrations_user_id_users",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
    )
    event_id: int = Field(
        sa_column=Column(
            "event_id",
            Integer,
            ForeignKey(
                "events.id",
                name="fk_registrations_event_id_events",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
    )
    session_id: int | None = Field(
        default=None,
        sa_column=Column(
            "session_id",
            Integer,
            ForeignKey(
                "sessions.id",
                name="fk_registrations_session_id_sessions",
                ondelete="CASCADE",
            ),
            nullable=True,
        ),
    )
    status: RegistrationStatus = Field(
        default=RegistrationStatus.ACTIVE,
        sa_column=Column(
            "status",
            String(20),
            nullable=False,
            server_default=text("'ACTIVE'"),
        ),
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
