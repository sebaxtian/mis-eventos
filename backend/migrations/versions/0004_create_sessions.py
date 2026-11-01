"""Create the sessions table.

Revision ID: 0004_create_sessions
Revises: 0003_create_events
Create Date: 2026-10-31 22:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_create_sessions"
down_revision: Union[str, None] = "0003_create_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("speaker", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "start_time < end_time",
            name="ck_sessions_time_range",
        ),
        sa.CheckConstraint(
            "capacity >= 1",
            name="ck_sessions_capacity_positive",
        ),
        sa.CheckConstraint(
            "capacity <= 100000",
            name="ck_sessions_capacity_max",
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 3 AND 160",
            name="ck_sessions_title_length",
        ),
        sa.CheckConstraint(
            "char_length(speaker) BETWEEN 2 AND 120",
            name="ck_sessions_speaker_length",
        ),
        sa.CheckConstraint(
            "description IS NULL OR char_length(description) <= 2000",
            name="ck_sessions_description_length",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_sessions_event_id_events",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sessions_event_id_start_time",
        "sessions",
        ["event_id", "start_time"],
    )
    op.create_index(
        "ix_sessions_event_id_end_time",
        "sessions",
        ["event_id", "end_time"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sessions_event_id_end_time",
        table_name="sessions",
    )
    op.drop_index(
        "ix_sessions_event_id_start_time",
        table_name="sessions",
    )
    op.drop_table("sessions")
