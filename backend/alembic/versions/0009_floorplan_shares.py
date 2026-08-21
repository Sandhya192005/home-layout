"""add floor_plan_shares table for shareable read-only links

Revision ID: 0009_floorplan_shares
Revises: 0008_wall_gate_style
Create Date: 2026-08-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_floorplan_shares"
down_revision: Union[str, None] = "0008_wall_gate_style"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "floor_plan_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "floor_plan_id", sa.Integer(), sa.ForeignKey("floor_plans.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_floor_plan_shares_floor_plan_id", "floor_plan_shares", ["floor_plan_id"])
    op.create_index("ix_floor_plan_shares_token", "floor_plan_shares", ["token"], unique=True)
    op.create_index("ix_floor_plan_shares_deleted_at", "floor_plan_shares", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_floor_plan_shares_deleted_at", table_name="floor_plan_shares")
    op.drop_index("ix_floor_plan_shares_token", table_name="floor_plan_shares")
    op.drop_index("ix_floor_plan_shares_floor_plan_id", table_name="floor_plan_shares")
    op.drop_table("floor_plan_shares")
