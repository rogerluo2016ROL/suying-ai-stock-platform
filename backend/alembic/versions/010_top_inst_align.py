"""top_inst schema 对齐 sync 写入端 — 存 Tushare per-institution 明细 + BIGSERIAL PK.

ADR-011: docs/adr/011-top-inst-schema-alignment.md

问题背景:
  top_inst (龙虎榜机构席位) 表 schema 与 Tushare 实际返回完全错位:
    - 表 6 列 (code/trade_date/inst_name/buy_amount/sell_amount/net_amount) ── 凭空想象的死列, 无 PK
    - Tushare pro.top_inst(trade_date) 返回 8 字段 (ts_code/trade_date/exalter/buy/buy_rate/sell/sell_rate/net_buy)
      ── per-institution 明细 (每股每日 ~10 个机构席位, 含「机构专用」匿名席位)
    - sync_top_inst (etl.py:888-914) cols 已对齐 Tushare: ["code","trade_date","exalter","buy","buy_rate","sell","sell_rate","net_buy"]
    - _insert_rows 自动过滤无效列 → 6 业务列从未被 sync 写入 → 表里只有 (code, trade_date) 二元组
    - 下游 advanced_factors.py:945-953 应用层 SUM(r["net_buy"]) / SUM(r["buy"]) / SUM(r["sell"]) 全 NULL → 评分 fallback
  4 个死列 (inst_name/buy_amount/sell_amount/net_amount) Tushare 不返回 (实际字段是 exalter/buy/sell/net_buy), 全表 NULL.

本迁移 (ADR §决策 5):
  - 当前无旧 PK, 但保留 DROP CONSTRAINT IF EXISTS 兜底
  - DROP 4 死列 (inst_name/buy_amount/sell_amount/net_amount): Tushare 无此名, 旧数据全 NULL, 无业务损失
  - ADD 6 业务列 (exalter/buy/buy_rate/sell/sell_rate/net_buy) DOUBLE PRECISION 对齐 sync cols + 下游 SELECT 字段
  - ADD 自增 BIGSERIAL id PK: 「机构专用」匿名席位同股同日可多次出现 → 任何业务字段复合 PK 都会丢数据,
    BIGSERIAL surrogate key 全保留 (ADR §决策 2 论证); 重复 sync 累积由 clean_before_write 兜底 (etl.py:895)
  - ADD idx_top_inst_code_date (code, trade_date) 索引: 覆盖下游 WHERE code=? ORDER BY trade_date DESC LIMIT 30
  - 全用原生 SQL op.execute (ADR-008/010 教训: 禁 op.add_column/op.create_primary_key 非幂等)

执行顺序 (ADR §决策 5 执行顺序约束):
  TRUNCATE top_inst → upgrade head → sync_top_inst(days_back=30) 回补
  TRUNCATE 非技术必需 (迁移自身能跑通) 但是数据洁净度必需: 旧 (code, trade_date) 二元组业务列全 NULL,
  保留会污染下游 SUM 直至 30 天后 clean_before_write 窗口移出.

数据量评估 (ADR §数据量评估):
  ~1020 行/日 × 22 交易日 ≈ 22000 行/次 30 天回补; 一年 ~250000 行; PG 15 单表 < 10M 行无压力
"""
from alembic import op

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: DROP 旧 PK (当前实际无 PK, 但保留兜底 IF EXISTS 防 init_postgres.sql 未来意外加 PK)
    op.execute("ALTER TABLE top_inst DROP CONSTRAINT IF EXISTS top_inst_pkey")

    # Step 2: 单条 ALTER: 删 4 死列 + 加 6 业务列
    # inst_name/buy_amount/sell_amount/net_amount: Tushare 不返回此名 (实际 exalter/buy/sell/net_buy), 全表 NULL, 删之
    # exalter (TEXT): 席位名/营业部名, 多为「机构专用」匿名
    # buy/buy_rate/sell/sell_rate/net_buy (DOUBLE PRECISION): 金额与占比, 下游 SUM 聚合
    op.execute("""
        ALTER TABLE top_inst
            DROP COLUMN IF EXISTS inst_name,
            DROP COLUMN IF EXISTS buy_amount,
            DROP COLUMN IF EXISTS sell_amount,
            DROP COLUMN IF EXISTS net_amount,
            ADD COLUMN IF NOT EXISTS exalter TEXT,
            ADD COLUMN IF NOT EXISTS buy DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS buy_rate DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS sell DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS sell_rate DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS net_buy DOUBLE PRECISION
    """)

    # Step 3: ADD BIGSERIAL id 列 + PRIMARY KEY (id)
    # ADR §决策 2: 「机构专用」匿名席位同股同日多次出现 → 业务字段复合 PK 会丢数据 → 用 surrogate key
    # BIGSERIAL = INT8 + sequence + DEFAULT nextval(...) + NOT NULL, 上限 9.2×10^18 防未来扩展溢出
    op.execute("""
        ALTER TABLE top_inst
            ADD COLUMN IF NOT EXISTS id BIGSERIAL
    """)
    op.execute("""
        ALTER TABLE top_inst
            ADD CONSTRAINT top_inst_pkey PRIMARY KEY (id)
    """)

    # Step 4: 业务索引覆盖下游 WHERE code=? ORDER BY trade_date DESC LIMIT 30 (advanced_factors.py:886)
    # 与 SQLite legacy models.py:766 同名索引一致
    op.execute("CREATE INDEX IF NOT EXISTS idx_top_inst_code_date ON top_inst(code, trade_date)")


def downgrade():
    # 逆序: 删业务索引 → 删新 PK + id 列 + 6 业务列 → 加回 4 死列
    # idx_top_inst_date (旧 schema 已有, 本迁移未删) 保持现状不动
    op.execute("DROP INDEX IF EXISTS idx_top_inst_code_date")
    op.execute("ALTER TABLE top_inst DROP CONSTRAINT IF EXISTS top_inst_pkey")
    op.execute("""
        ALTER TABLE top_inst
            DROP COLUMN IF EXISTS id,
            DROP COLUMN IF EXISTS exalter,
            DROP COLUMN IF EXISTS buy,
            DROP COLUMN IF EXISTS buy_rate,
            DROP COLUMN IF EXISTS sell,
            DROP COLUMN IF EXISTS sell_rate,
            DROP COLUMN IF EXISTS net_buy,
            ADD COLUMN IF NOT EXISTS inst_name TEXT,
            ADD COLUMN IF NOT EXISTS buy_amount DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS sell_amount DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS net_amount DOUBLE PRECISION
    """)
