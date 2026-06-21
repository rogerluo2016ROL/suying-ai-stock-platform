"""sw_daily schema 对齐 etl 写入端 — 加 8 列承接 Tushare 全量字段。

ADR-008: https://docs/adr/008-sw-daily-schema-alignment.md

问题背景:
  etl.py:1274-1296 的 sync_sw_daily 已按 15 列写入, 但 init SQL / 物理表只有 7 列,
  _insert_rows 的止血逻辑静默丢弃 name/pe/pb/vol/amount 等 8 列,
  导致 advanced_factors 的 tushare_sector_val 因子长期 fallback (pe/name NULL).

本迁移:
  - 加 8 列对齐 etl 写入端, 列名沿用 engine 命名 (无 SQLite/PG 命名分歧)
  - 全部 NULLABLE, 类型对齐 Tushare 输出语义
  - 不动主键 (code, trade_date) 不加索引 (YAGNI, 见 ADR §决策2)
  - 数据回补由 sync_sw_daily 独立运维步骤承担 (见 ADR §决策5), 迁移只改结构

新增列 (Tushare sw_daily 5000 积分接口原字段):
  - name        TEXT              指数名称 (如"农林牧渔")
  - change      DOUBLE PRECISION  涨跌点位 (绝对值, 与 change_pct% 并存语义不同)
  - pe          DOUBLE PRECISION  市盈率 (倍)
  - pb          DOUBLE PRECISION  市净率 (倍)
  - float_mv    DOUBLE PRECISION  流通市值 (万元)
  - total_mv    DOUBLE PRECISION  总市值 (万元)
  - vol         DOUBLE PRECISION  成交量 (万股)
  - amount      DOUBLE PRECISION  成交额 (万元)
"""
from alembic import op

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    # 单条 ALTER 加 8 列 (PG 15 支持). 全用 IF NOT EXISTS 幂等.
    # 单位注释见 docstring; sync 层不做单位转换 (ADR-006 §决策2 直写原则).
    op.execute("""
        ALTER TABLE sw_daily
        ADD COLUMN IF NOT EXISTS name TEXT,
        ADD COLUMN IF NOT EXISTS change DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS pe DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS pb DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS float_mv DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS total_mv DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS vol DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION
    """)


def downgrade():
    # 单条 ALTER 删 8 列. IF EXISTS 幂等.
    op.execute("""
        ALTER TABLE sw_daily
        DROP COLUMN IF EXISTS name,
        DROP COLUMN IF EXISTS change,
        DROP COLUMN IF EXISTS pe,
        DROP COLUMN IF EXISTS pb,
        DROP COLUMN IF EXISTS float_mv,
        DROP COLUMN IF EXISTS total_mv,
        DROP COLUMN IF EXISTS vol,
        DROP COLUMN IF EXISTS amount
    """)
