"""add floor_type column to requirements (duplex vs independent floors)

Revision ID: 0007_floor_type
Revises: 0006_entrance_checkboxes
Create Date: 2026-08-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_floor_type"
down_revision: Union[str, None] = "0006_entrance_checkboxes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requirements",
        sa.Column("floor_type", sa.String(length=20), server_default="duplex", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("requirements", "floor_type")
