"""add wheelchair_accessible column to requirements

Revision ID: 0004_wheelchair_accessible
Revises: 0003_drop_ai_suggestions
Create Date: 2026-08-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_wheelchair_accessible"
down_revision: Union[str, None] = "0003_drop_ai_suggestions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requirements",
        sa.Column("wheelchair_accessible", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("requirements", "wheelchair_accessible")
