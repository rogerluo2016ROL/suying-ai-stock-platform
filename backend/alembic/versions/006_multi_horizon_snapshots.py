"""Add multi-horizon return columns to screening_snapshots.

- ret_3d/5d/10d/20d: forward return at 3/5/10/20 trading days
- is_win_3d/5d/10d: whether the return is positive
- ret_Xd_at: timestamp when the outcome was backfilled
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    # screening_snapshots 建表：核心业务表（recorder INSERT / signal SELECT），此前无 migration/init SQL 创建（schema gap）。
    # schema 取自 recorder.py INSERT 列 + backfill next_day_return/is_win + id PK。IF NOT EXISTS 保证 dev/UAT 都安全。
    op.execute("""
    CREATE TABLE IF NOT EXISTS screening_snapshots (
        id BIGSERIAL PRIMARY KEY,
        model_key TEXT NOT NULL,
        trade_date DATE NOT NULL,
        stock_code TEXT NOT NULL,
        time_slot TEXT,
        factors JSONB,
        total_score DOUBLE PRECISION,
        grade TEXT,
        rank_in_day INTEGER,
        next_day_return DOUBLE PRECISION,
        is_win BOOLEAN,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_screening_snapshots_code_date ON screening_snapshots(stock_code, trade_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_screening_snapshots_model ON screening_snapshots(model_key, trade_date)")
    for col, dtype in [
        ("ret_3d", sa.Double), ("ret_5d", sa.Double),
        ("ret_10d", sa.Double), ("ret_20d", sa.Double),
        ("is_win_3d", sa.Boolean), ("is_win_5d", sa.Boolean),
        ("is_win_10d", sa.Boolean),
        ("ret_3d_at", sa.DateTime), ("ret_5d_at", sa.DateTime),
        ("ret_10d_at", sa.DateTime), ("ret_20d_at", sa.DateTime),
    ]:
        op.add_column('screening_snapshots', sa.Column(col, dtype(), nullable=True))


def downgrade():
    for col in ["ret_3d", "ret_5d", "ret_10d", "ret_20d",
                "is_win_3d", "is_win_5d", "is_win_10d",
                "ret_3d_at", "ret_5d_at", "ret_10d_at", "ret_20d_at"]:
        op.execute(f"ALTER TABLE screening_snapshots DROP COLUMN IF EXISTS {col}")
