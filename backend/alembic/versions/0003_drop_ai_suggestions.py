"""drop ai_suggestions table (feature removed)

Revision ID: 0003_drop_ai_suggestions
Revises: 0002_audit_columns
Create Date: 2026-08-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_drop_ai_suggestions"
down_revision: Union[str, None] = "0002_audit_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("ai_suggestions")


def downgrade() -> None:
    op.create_table(
        "ai_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("requirements.id", ondelete="CASCADE"), index=True),
        sa.Column("suggestions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_ai_suggestions_deleted_at", "ai_suggestions", ["deleted_at"])
