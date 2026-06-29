"""Add decision_contexts lineage snapshots.

Revision ID: 016
Revises: 015
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_contexts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("decision_context_id", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("account_id", sa.String(length=100), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("plan_id", sa.String(length=100), nullable=True),
        sa.Column("candidate_id", sa.String(length=100), nullable=True),
        sa.Column("intent", sa.String(length=50), nullable=False, server_default="manual_order"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_context_id", name="uq_decision_contexts_context_id"),
        sa.CheckConstraint(
            "source_type IN ('candidate', 'plan', 'order', 'strategy', 'manual')",
            name="ck_decision_contexts_source_type",
        ),
    )

    op.create_index(
        "idx_decision_contexts_scope_created",
        "decision_contexts",
        ["tenant_id", "account_id", "created_at"],
        postgresql_using="btree",
    )
    op.create_index("idx_decision_contexts_context_id", "decision_contexts", ["decision_context_id"])
    op.create_index("idx_decision_contexts_symbol", "decision_contexts", ["symbol"])
    op.create_index("idx_decision_contexts_plan_id", "decision_contexts", ["plan_id"])
    op.create_index("idx_decision_contexts_candidate_id", "decision_contexts", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("decision_contexts")
