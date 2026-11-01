"""Create the registrations table.

Revision ID: 0005_create_registrations
Revises: 0004_create_sessions
Create Date: 2026-11-01 10:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_create_registrations"
down_revision: Union[str, None] = "0004_create_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
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
            "status IN ('ACTIVE', 'CANCELLED')",
            name="ck_registrations_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_registrations_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_registrations_event_id_events",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_registrations_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_registrations_active_event",
        "registrations",
        ["user_id", "event_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'ACTIVE' AND session_id IS NULL"
        ),
    )
    op.create_index(
        "uq_registrations_active_session",
        "registrations",
        ["user_id", "session_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'ACTIVE' AND session_id IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_registrations_event_id_status",
        "registrations",
        ["event_id", "status"],
    )
    op.create_index(
        "ix_registrations_session_id_status",
        "registrations",
        ["session_id", "status"],
    )
    op.create_index(
        "ix_registrations_user_id_status_created_at",
        "registrations",
        ["user_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_registrations_user_id_status_created_at",
        table_name="registrations",
    )
    op.drop_index(
        "ix_registrations_session_id_status",
        table_name="registrations",
    )
    op.drop_index(
        "ix_registrations_event_id_status",
        table_name="registrations",
    )
    op.drop_index(
        "uq_registrations_active_session",
        table_name="registrations",
    )
    op.drop_index(
        "uq_registrations_active_event",
        table_name="registrations",
    )
    op.drop_table("registrations")
