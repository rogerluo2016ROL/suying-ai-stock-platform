"""Add risk_verdicts query table.

Revision ID: 015
Revises: 014
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_verdicts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("verdict_id", sa.String(length=80), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("account_id", sa.String(length=100), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False, server_default="order"),
        sa.Column("trade_mode", sa.String(length=10), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("plan_id", sa.String(length=100), nullable=True),
        sa.Column("candidate_id", sa.String(length=100), nullable=True),
        sa.Column("decision_context_id", sa.String(length=100), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("verdict_id", name="uq_risk_verdicts_verdict_id"),
        sa.CheckConstraint(
            "result IN ('pass', 'warn', 'reject', 'manual_review')",
            name="ck_risk_verdicts_result",
        ),
        sa.CheckConstraint(
            "trade_mode IN ('paper', 'live')",
            name="ck_risk_verdicts_trade_mode",
        ),
    )

    op.create_index("idx_risk_verdicts_verdict_id", "risk_verdicts", ["verdict_id"])
    op.create_index(
        "idx_risk_verdicts_scope_created",
        "risk_verdicts",
        ["tenant_id", "account_id", "created_at"],
        postgresql_using="btree",
    )
    op.create_index("idx_risk_verdicts_result", "risk_verdicts", ["result"])
    op.create_index(
        "idx_risk_verdicts_symbol_created",
        "risk_verdicts",
        ["symbol", "created_at"],
        postgresql_using="btree",
    )
    op.create_index("idx_risk_verdicts_order_id", "risk_verdicts", ["order_id"])
    op.create_index("idx_risk_verdicts_plan_id", "risk_verdicts", ["plan_id"])
    op.create_index("idx_risk_verdicts_candidate_id", "risk_verdicts", ["candidate_id"])
    op.create_index(
        "idx_risk_verdicts_decision_context_id",
        "risk_verdicts",
        ["decision_context_id"],
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_risk_verdict_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'risk_verdicts is append-only: % not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_risk_verdict_no_update
            BEFORE UPDATE ON risk_verdicts
            FOR EACH STATEMENT
            EXECUTE FUNCTION prevent_risk_verdict_mutation();
    """)

    op.execute("""
        CREATE TRIGGER trg_risk_verdict_no_delete
            BEFORE DELETE ON risk_verdicts
            FOR EACH STATEMENT
            EXECUTE FUNCTION prevent_risk_verdict_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_risk_verdict_no_update ON risk_verdicts")
    op.execute("DROP TRIGGER IF EXISTS trg_risk_verdict_no_delete ON risk_verdicts")
    op.execute("DROP FUNCTION IF EXISTS prevent_risk_verdict_mutation()")
    op.drop_table("risk_verdicts")
