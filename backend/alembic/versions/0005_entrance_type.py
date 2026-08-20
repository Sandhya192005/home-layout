"""add entrance_type column to requirements

Revision ID: 0005_entrance_type
Revises: 0004_wheelchair_accessible
Create Date: 2026-08-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_entrance_type"
down_revision: Union[str, None] = "0004_wheelchair_accessible"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requirements",
        sa.Column("entrance_type", sa.String(length=20), server_default="veranda", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("requirements", "entrance_type")
