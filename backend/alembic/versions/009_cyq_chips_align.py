"""cyq_chips schema 对齐 sync 写入端 — 存 Tushare per-price 明细.

ADR-010: docs/adr/010-cyq-chips-schema-alignment.md

问题背景:
  cyq_chips (筹码分布) 表 schema 与 Tushare 实际返回完全错位:
    - 表 5 列 (code/trade_date/avg_cost/concentration_90/profit_ratio) ── 聚合指标
    - Tushare pro.cyq_chips() 返回 4 字段 (ts_code/trade_date/price/percent) ── per-price-level 明细
    - sync_cyq_chips (etl.py:1156) cols 已对齐 Tushare: ["code","trade_date","price","percent"]
    - _insert_rows 静默吞 price/percent 列 (不存在于物理表) → 表里这两列从未有真实值
    - 下游 advanced_factors.py:1076 读 `SELECT price, percent FROM cyq_chips` → 列不存在
      → pg_adapter UndefinedColumn 优雅降级 → 筹码集中度因子永久 fallback 中性分
  3 个死列 (avg_cost/concentration_90/profit_ratio) Tushare 根本不返回, 是建表时凭空想象, 全表 NULL.

本迁移 (ADR §决策5):
  - DROP 3 死列 (avg_cost/concentration_90/profit_ratio): Tushare 无此字段, 旧数据全 NULL, 无业务损失
  - ADD price/percent (NUMERIC) 对齐 sync cols + 下游 SELECT 字段
  - 改 PK (code, trade_date) → (code, trade_date, price): 同股同日多 price 档, price 是天然区分维度
  - 全用原生 SQL op.execute (ADR-008 教训: 禁 op.add_column 非幂等)

执行顺序 (ADR §决策6 风险1):
  TRUNCATE cyq_chips → upgrade head (DROP PK / DROP 死列 / ADD 新列 / ADD 新 PK) → sync_cyq_chips 回补
  改 PK 是破坏性的, 必须先 TRUNCATE 否则旧 PK (code,trade_date) 行无 price 字段, 新 PK 加不上.

数据量评估 (ADR §数据量评估):
  top 300 股 × ~104 行/股/日 × days_back=5 ≈ 15.6 万行/次 sync (当前合理)
  30 天回补 ~93 万行可控; 超 1000 万行 (全市场 5000 股 × 长历史) 考虑分区, 另议 (本 ADR 不覆盖)
"""
from alembic import op

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: DROP 旧 PK (code, trade_date)
    # 原 PK 不兼容新 schema (同 code 同 date 会有 ~104 个 price 档, 违反唯一性)
    # IF EXISTS 防御: 若历史环境未建 PK 不阻塞
    op.execute("ALTER TABLE cyq_chips DROP CONSTRAINT IF EXISTS cyq_chips_pkey")

    # Step 2: DROP 3 死列 + ADD price/percent (单条 ALTER, PG 15 支持)
    # avg_cost/concentration_90/profit_ratio: Tushare 不返回, 全表 NULL, 删之
    # price/percent: NUMERIC 精度对齐 Tushare 原值 (价格小数位不定, percent 是 0-100 浮点占比)
    op.execute("""
        ALTER TABLE cyq_chips
            DROP COLUMN IF EXISTS avg_cost,
            DROP COLUMN IF EXISTS concentration_90,
            DROP COLUMN IF EXISTS profit_ratio,
            ADD COLUMN IF NOT EXISTS price NUMERIC,
            ADD COLUMN IF NOT EXISTS percent NUMERIC
    """)

    # Step 3: ADD 新 PK (code, trade_date, price)
    # 三列复合 PK: price 是同股同日内的档位区分维度
    # 必须在 TRUNCATE 之后执行 (执行顺序: 先 TRUNCATE → upgrade → 回补), 否则旧行 price=NULL 违反 PK NOT NULL
    op.execute("""
        ALTER TABLE cyq_chips
            ADD CONSTRAINT cyq_chips_pkey PRIMARY KEY (code, trade_date, price)
    """)


def downgrade():
    # 逆序: 删新 PK → 删 price/percent + 恢复 3 死列 → 加回旧 PK
    op.execute("ALTER TABLE cyq_chips DROP CONSTRAINT IF EXISTS cyq_chips_pkey")
    op.execute("""
        ALTER TABLE cyq_chips
            DROP COLUMN IF EXISTS price,
            DROP COLUMN IF EXISTS percent,
            ADD COLUMN IF NOT EXISTS avg_cost DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS concentration_90 DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS profit_ratio DOUBLE PRECISION
    """)
    op.execute("""
        ALTER TABLE cyq_chips
            ADD CONSTRAINT cyq_chips_pkey PRIMARY KEY (code, trade_date)
    """)
