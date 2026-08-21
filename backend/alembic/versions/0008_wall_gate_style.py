"""add compound_wall_style and gate_style columns to requirements

Revision ID: 0008_wall_gate_style
Revises: 0007_floor_type
Create Date: 2026-08-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_wall_gate_style"
down_revision: Union[str, None] = "0007_floor_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requirements",
        sa.Column("compound_wall_style", sa.String(length=20), server_default="wall", nullable=False),
    )
    op.add_column(
        "requirements",
        sa.Column("gate_style", sa.String(length=20), server_default="swing", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("requirements", "gate_style")
    op.drop_column("requirements", "compound_wall_style")
