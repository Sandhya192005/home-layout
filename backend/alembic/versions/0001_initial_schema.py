"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    op.create_table(
        "requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plot_length", sa.Float(), nullable=False),
        sa.Column("plot_width", sa.Float(), nullable=False),
        sa.Column("facing", sa.String(length=20), nullable=False, server_default="north"),
        sa.Column("family_members", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("bedrooms", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("bathrooms", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("has_living_room", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("has_dining_room", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("has_pooja_room", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_study_room", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_utility_room", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("balconies", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cars", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("two_wheelers", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("floors", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("budget", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vastu_compliant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("additional_rooms", sa.JSON(), nullable=False),
        sa.Column("other_requirements", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"])

    op.create_table(
        "floor_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "requirement_id", sa.Integer(), sa.ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="generated"),
        sa.Column("plan_data", sa.JSON(), nullable=False),
        sa.Column("total_built_up_area", sa.Float(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_floor_plans_project_id", "floor_plans", ["project_id"])
    op.create_index("ix_floor_plans_requirement_id", "floor_plans", ["requirement_id"])

    op.create_table(
        "ai_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "requirement_id", sa.Integer(), sa.ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("suggestions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_suggestions_project_id", "ai_suggestions", ["project_id"])
    op.create_index("ix_ai_suggestions_requirement_id", "ai_suggestions", ["requirement_id"])


def downgrade() -> None:
    op.drop_table("ai_suggestions")
    op.drop_table("floor_plans")
    op.drop_table("requirements")
    op.drop_table("projects")
    op.drop_table("users")
