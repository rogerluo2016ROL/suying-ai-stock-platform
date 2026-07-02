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
    # screening_snapshots 建表：核心业务表（recorder INSERT / signal SELECT）。
    # IF NOT EXISTS 保证两条路径都安全：
    #   - 正向（UAT/部署）：services/sql/init_postgres.sql 容器启动时先建表 + 全部多周期列
    #   - 反向（dev 无 init SQL）：alembic 单独建表 + 补列
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
    # 多周期列：必须用 ADD COLUMN IF NOT EXISTS（init_postgres.sql:594 已预建这些列），
    # 否则 init SQL + alembic upgrade 正向路径撞 DuplicateColumn → 迁移回滚 → 无 alembic_version/auth 表。
    # PG 类型映射：sa.Double→double precision / sa.Boolean→boolean / sa.DateTime→timestamp。
    for col, pgtype in [
        ("outcome_at", "TIMESTAMP"),
        ("ret_3d", "DOUBLE PRECISION"), ("ret_5d", "DOUBLE PRECISION"),
        ("ret_10d", "DOUBLE PRECISION"), ("ret_20d", "DOUBLE PRECISION"),
        ("is_win_3d", "BOOLEAN"), ("is_win_5d", "BOOLEAN"),
        ("is_win_10d", "BOOLEAN"),
        ("ret_3d_at", "TIMESTAMP"), ("ret_5d_at", "TIMESTAMP"),
        ("ret_10d_at", "TIMESTAMP"), ("ret_20d_at", "TIMESTAMP"),
    ]:
        op.execute(
            f"ALTER TABLE screening_snapshots ADD COLUMN IF NOT EXISTS {col} {pgtype}"
        )


def downgrade():
    for col in ["outcome_at", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
                "is_win_3d", "is_win_5d", "is_win_10d",
                "ret_3d_at", "ret_5d_at", "ret_10d_at", "ret_20d_at"]:
        op.execute(f"ALTER TABLE screening_snapshots DROP COLUMN IF EXISTS {col}")
