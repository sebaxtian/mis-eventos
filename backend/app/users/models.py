"""User domain models."""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlmodel import Field, SQLModel

from app.core.datetime_utils import utc_now


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    ORGANIZER = "ORGANIZER"
    ATTENDEE = "ATTENDEE"


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "role IN ('ADMIN', 'ORGANIZER', 'ATTENDEE')",
            name="ck_users_role",
        ),
        Index("ix_users_role", "role"),
        Index("ix_users_is_active", "is_active"),
    )

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(
        sa_column=Column("email", String(254), nullable=False),
    )
    password_hash: str = Field(
        sa_column=Column("password_hash", String(255), nullable=False),
        repr=False,
    )
    full_name: str = Field(
        sa_column=Column("full_name", String(120), nullable=False),
    )
    role: UserRole = Field(
        default=UserRole.ATTENDEE,
        sa_column=Column(
            "role",
            String(20),
            nullable=False,
            server_default=text("'ATTENDEE'"),
        ),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(
            "is_active",
            Boolean,
            nullable=False,
            server_default=text("true"),
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
