"""replace entrance_type with independent has_veranda / has_foyer flags

Revision ID: 0006_entrance_checkboxes
Revises: 0005_entrance_type
Create Date: 2026-08-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_entrance_checkboxes"
down_revision: Union[str, None] = "0005_entrance_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requirements",
        sa.Column("has_veranda", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "requirements",
        sa.Column("has_foyer", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute("UPDATE requirements SET has_veranda = (entrance_type = 'veranda'), has_foyer = (entrance_type = 'foyer')")
    op.drop_column("requirements", "entrance_type")


def downgrade() -> None:
    op.add_column(
        "requirements",
        sa.Column("entrance_type", sa.String(length=20), server_default="veranda", nullable=False),
    )
    op.execute("UPDATE requirements SET entrance_type = CASE WHEN has_veranda THEN 'veranda' ELSE 'foyer' END")
    op.drop_column("requirements", "has_foyer")
    op.drop_column("requirements", "has_veranda")
