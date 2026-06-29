"""Add candidate pools and strategy plans.

Revision ID: 018
Revises: 017
Create Date: 2026-06-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_pools",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pool_id", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("account_id", sa.String(length=100), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
        sa.Column("data_scope", sa.String(length=20), nullable=False, server_default="account"),
        sa.Column("source_module", sa.String(length=40), nullable=False),
        sa.Column("source_mode", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("candidates", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pool_id", name="uq_candidate_pools_pool_id"),
        sa.CheckConstraint(
            "visibility IN ('private', 'tenant_shared', 'public')",
            name="ck_candidate_pools_visibility",
        ),
        sa.CheckConstraint(
            "data_scope IN ('public', 'tenant', 'user', 'account')",
            name="ck_candidate_pools_data_scope",
        ),
    )
    op.create_index("idx_candidate_pools_pool_id", "candidate_pools", ["pool_id"])
    op.create_index(
        "idx_candidate_pools_scope_updated",
        "candidate_pools",
        ["tenant_id", "owner_user_id", "account_id", "updated_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "idx_candidate_pools_source",
        "candidate_pools",
        ["source_module", "source_mode", "updated_at"],
        postgresql_using="btree",
    )

    op.create_table(
        "strategy_plans",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("model_name", sa.String(length=80), nullable=False, server_default="all"),
        sa.Column("capital", sa.Numeric(18, 2), nullable=False, server_default="1000000"),
        sa.Column("max_positions", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("single_max_pct", sa.Numeric(8, 4), nullable=False, server_default="0.2"),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("account_id", sa.String(length=100), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
        sa.Column("data_scope", sa.String(length=20), nullable=False, server_default="account"),
        sa.Column("picks", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", name="uq_strategy_plans_plan_id"),
        sa.CheckConstraint(
            "status IN ('draft', 'predicting', 'backtesting', 'confirmed', 'active', 'archived')",
            name="ck_strategy_plans_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('private', 'tenant_shared', 'public')",
            name="ck_strategy_plans_visibility",
        ),
        sa.CheckConstraint(
            "data_scope IN ('public', 'tenant', 'user', 'account')",
            name="ck_strategy_plans_data_scope",
        ),
    )
    op.create_index("idx_strategy_plans_plan_id", "strategy_plans", ["plan_id"])
    op.create_index(
        "idx_strategy_plans_scope_updated",
        "strategy_plans",
        ["tenant_id", "owner_user_id", "account_id", "updated_at"],
        postgresql_using="btree",
    )
    op.create_index("idx_strategy_plans_status", "strategy_plans", ["status"])


def downgrade() -> None:
    op.drop_table("strategy_plans")
    op.drop_table("candidate_pools")
