"""Add audit_logs — append-only trade audit trail.

Revision ID: 002
Revises: 001
Create Date: 2026-06-10

Per ADR-002 Decision 4:
- audit_logs is INSERT-only; UPDATE and DELETE are blocked by DB trigger.
- Only the application database role uses INSERT; human admins have SELECT only.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── audit_logs table ───────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "mode IN ('paper', 'live')",
            name="ck_audit_logs_mode",
        ),
        sa.CheckConstraint(
            "action IN ('PLACE_ORDER', 'CANCEL_ORDER', 'MODE_SWITCH', "
            "'BROKER_CONNECT', 'BROKER_DISCONNECT', 'RISK_REJECT', "
            "'CIRCUIT_BREAKER', 'POSITION_SYNC')",
            name="ck_audit_logs_action",
        ),
    )

    # Indexes
    op.create_index("idx_audit_logs_created", "audit_logs", ["created_at"], postgresql_using="btree")
    op.create_index("idx_audit_logs_user", "audit_logs", ["user_id", "created_at"], postgresql_using="btree")
    op.create_index("idx_audit_logs_action", "audit_logs", ["action"])
    op.create_index("idx_audit_logs_symbol", "audit_logs", ["symbol", "created_at"], postgresql_using="btree")

    # ── Append-only trigger ────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only: % not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_no_update
            BEFORE UPDATE ON audit_logs
            FOR EACH STATEMENT
            EXECUTE FUNCTION prevent_audit_mutation();
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_no_delete
            BEFORE DELETE ON audit_logs
            FOR EACH STATEMENT
            EXECUTE FUNCTION prevent_audit_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_delete ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation()")
    op.drop_table("audit_logs")
