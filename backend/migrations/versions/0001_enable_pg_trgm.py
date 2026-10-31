"""Enable pg_trgm extension in PostgreSQL.

Revision ID: 0001_enable_pg_trgm
Revises:
Create Date: 2026-10-31 12:00:00

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0001_enable_pg_trgm"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
