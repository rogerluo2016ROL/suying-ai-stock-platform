"""Add platform-scoped trade order ledger.

Revision ID: 017
Revises: 016
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trade_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.String(length=80), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("account_id", sa.String(length=100), nullable=True),
        sa.Column("trade_mode", sa.String(length=10), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("decision_context_id", sa.String(length=100), nullable=True),
        sa.Column("candidate_id", sa.String(length=100), nullable=True),
        sa.Column("plan_id", sa.String(length=100), nullable=True),
        sa.Column("order_scope", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("risk_verdict", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_trade_orders_order_id"),
        sa.CheckConstraint("trade_mode IN ('paper', 'live')", name="ck_trade_orders_trade_mode"),
        sa.CheckConstraint("direction IN ('BUY', 'SELL')", name="ck_trade_orders_direction"),
    )

    op.create_index(
        "idx_trade_orders_scope_created",
        "trade_orders",
        ["tenant_id", "account_id", "created_at"],
        postgresql_using="btree",
    )
    op.create_index("idx_trade_orders_order_id", "trade_orders", ["order_id"])
    op.create_index("idx_trade_orders_code_created", "trade_orders", ["code", "created_at"])
    op.create_index("idx_trade_orders_decision_context_id", "trade_orders", ["decision_context_id"])
    op.create_index("idx_trade_orders_candidate_id", "trade_orders", ["candidate_id"])
    op.create_index("idx_trade_orders_plan_id", "trade_orders", ["plan_id"])


def downgrade() -> None:
    op.drop_table("trade_orders")
