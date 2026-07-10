"""Align existing databases with indexes declared by the schema contract.

Revision ID: 027
Revises: 026
"""

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


INDEXES = (
    ("idx_cb_call_code", "cb_call", "ts_code"),
    ("idx_cb_call_date", "cb_call", "call_date"),
    ("idx_cb_daily_code", "cb_daily", "ts_code"),
    ("idx_cb_daily_date", "cb_daily", "trade_date"),
    ("idx_cb_factor_code", "cb_factor", "ts_code"),
    ("idx_cb_factor_date", "cb_factor", "trade_date"),
    ("idx_cb_price_chg_code", "cb_price_chg", "ts_code"),
    ("idx_fina_audit_result", "fina_audit", "audit_result"),
    ("idx_stk_mins_code", "stk_mins", "code"),
    ("idx_stock_profiles_province", "stock_profiles", "province"),
)


def upgrade():
    for name, table, column in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})")


def downgrade():
    for name, _, _ in reversed(INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
