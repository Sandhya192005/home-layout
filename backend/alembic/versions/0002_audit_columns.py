"""add audit columns (created_by/updated_at/updated_by/deleted_at/deleted_by/is_active)

Revision ID: 0002_audit_columns
Revises: 0001_initial_schema
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_audit_columns"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# tables that already had created_at from 0001 (skip re-adding it)
TABLES_WITH_CREATED_AT = {"users", "projects", "requirements", "floor_plans", "ai_suggestions"}
# tables that already had updated_at from 0001
TABLES_WITH_UPDATED_AT = {"projects"}
# tables that already had is_active from 0001
TABLES_WITH_IS_ACTIVE = {"users"}

ALL_TABLES = ["users", "projects", "requirements", "floor_plans", "ai_suggestions"]


def upgrade() -> None:
    for table in ALL_TABLES:
        if table not in TABLES_WITH_UPDATED_AT:
            op.add_column(
                table,
                sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            )
        if table not in TABLES_WITH_IS_ACTIVE:
            op.add_column(
                table,
                sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            )
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("created_by", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("updated_by", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("deleted_by", sa.Integer(), nullable=True))

        op.create_foreign_key(
            f"fk_{table}_created_by_users", table, "users", ["created_by"], ["id"], ondelete="SET NULL"
        )
        op.create_foreign_key(
            f"fk_{table}_updated_by_users", table, "users", ["updated_by"], ["id"], ondelete="SET NULL"
        )
        op.create_foreign_key(
            f"fk_{table}_deleted_by_users", table, "users", ["deleted_by"], ["id"], ondelete="SET NULL"
        )
        op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"])


def downgrade() -> None:
    for table in ALL_TABLES:
        op.drop_index(f"ix_{table}_deleted_at", table_name=table)
        op.drop_constraint(f"fk_{table}_deleted_by_users", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_updated_by_users", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_created_by_users", table, type_="foreignkey")

        op.drop_column(table, "deleted_by")
        op.drop_column(table, "updated_by")
        op.drop_column(table, "created_by")
        op.drop_column(table, "deleted_at")
        if table not in TABLES_WITH_IS_ACTIVE:
            op.drop_column(table, "is_active")
        if table not in TABLES_WITH_UPDATED_AT:
            op.drop_column(table, "updated_at")
