"""ths_daily schema 反向追认 DB 现状 + 补 BIGSERIAL PK + 业务索引.

ADR-013: docs/adr/013-ths-daily-schema-alignment.md

问题背景:
  ths_daily 表 DDL 与 DB 现状完全错位 (历史 schema drift):
    - init_postgres.sql:551-561 旧 DDL 8 列 (ts_code/trade_date/name/close/pct_change/avg_price/total_mv/float_mv)
      + PK(ts_code, trade_date)
    - DB 实际 17 列 (id integer 无 PK, trade_date text, code text, name, open, high, low, close,
      pre_close, avg_price, change_pct, change, total_mv, float_mv, updated_at text, vol, turnover_rate)
      + UNIQUE(code, trade_date) 约束
    - cb_sync.sync_ths_daily cols=5 (含 pct_change), 经 _insert_rows 自动列过滤永远丢 pct_change
      → 下游 leader_intraday 因子查 change_pct 长期为 NULL → fallback
  pg_adapter._COLUMN_MAP["pct_change":"change_pct"] 读侧翻译已生效但写侧无人 patch.

本迁移 (ADR §决策 1 「DB 现状为权威」原则):
  - 反向追认 DB 实际 17 列形态 (不改 trade_date text / updated_at text 类型, 列入 ADR-014 audit)
  - 把 id integer (隐式自增 但 1.93M 历史行全 NULL 且无 PK 约束) 升级为 BIGSERIAL PRIMARY KEY
    * CREATE SEQUENCE → ALTER TYPE bigint → SET DEFAULT nextval → UPDATE 回填全 NULL 行
    * setval 续接序列 → SET NOT NULL → ADD CONSTRAINT PRIMARY KEY → OWNED BY 关联
  - 补 idx_ths_daily_code_date 业务索引 (与 ths_daily_code_date_uniq UNIQUE 隐式索引并存,
    ADR §决策 1 DDL 段显式声明; 冗余但与下游 SELECT 模式对齐 + 与 sw_daily/cyq_chips 同型)
  - 全用原生 SQL op.execute (ADR-008/010/011 教训: 禁 op.add_column / op.create_primary_key 非幂等)

执行顺序 (ADR §决策 8 阶段 1):
  upgrade → SIT-1 (alembic upgrade head 成功) → SIT-2 (重跑幂等) → SIT-3 (downgrade -1 + 重 upgrade)
  → SIT-4 (\\d ths_daily 显示 17 列 + UNIQUE + BIGSERIAL PK + idx_ths_daily_code_date)
  不 TRUNCATE: 历史 1.93M 行业务数据保留 (change_pct/code/trade_date 字段已对齐, 仅缺 NULL id 回填).

数据量评估 (ADR §决策 7 SIT-1):
  UPDATE 1.93M 行回填 id (单事务 < 30s on PG 15 + 本地 SSD); 索引 CREATE ~5s.
"""
from alembic import op

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: 创建独立序列 (不依赖 SERIAL/BIGSERIAL 语法糖, 便于 downgrade 精确清理)
    # 与 PG SERIAL 自动产物同名约定 "<table>_<col>_seq" 保持一致, 减少未来 introspect 工具识别歧义
    op.execute("CREATE SEQUENCE IF NOT EXISTS ths_daily_id_seq")

    # Step 2: id integer → bigint (DB 现状 integer 32-bit 上限 ~2.14B, 当前 1.93M 行远未触及,
    # 但 ADR §决策 1 DDL 段声明 BIGSERIAL 即 bigint = INT8 = 9.2×10^18 防未来扩展溢出)
    op.execute("ALTER TABLE ths_daily ALTER COLUMN id TYPE bigint")

    # Step 3: SET DEFAULT nextval — 未来 INSERT 不显式传 id 时自动取序列下一值
    op.execute("ALTER TABLE ths_daily ALTER COLUMN id SET DEFAULT nextval('ths_daily_id_seq')")

    # Step 4: 回填历史行 id (DB 现状 1.93M 行 id 全 NULL — 整数列从未被写入过)
    # 单 UPDATE 整表回填, 全用 nextval 保证唯一性; PG 15 + 本地 SSD ~20s 完成
    op.execute("UPDATE ths_daily SET id = nextval('ths_daily_id_seq') WHERE id IS NULL")

    # Step 5: setval 续接 — 把序列推进到 MAX(id) + 1, 后续 INSERT 不撞回填值
    # COALESCE 兜底空表场景 (理论不会, 但防御性)
    op.execute("""
        SELECT setval('ths_daily_id_seq',
                      COALESCE((SELECT MAX(id) FROM ths_daily), 0) + 1, false)
    """)

    # Step 6: SET NOT NULL — 与 BIGSERIAL 完整语义对齐
    op.execute("ALTER TABLE ths_daily ALTER COLUMN id SET NOT NULL")

    # Step 7: ADD PRIMARY KEY (id) — 当前无 PK, IF NOT EXISTS 防 init_postgres.sql 未来意外加 PK
    # 命名沿用 PG 默认 "<table>_pkey", 与 top_inst (ADR-011)/cyq_chips (ADR-010) 同型
    op.execute("ALTER TABLE ths_daily DROP CONSTRAINT IF EXISTS ths_daily_pkey")
    op.execute("ALTER TABLE ths_daily ADD CONSTRAINT ths_daily_pkey PRIMARY KEY (id)")

    # Step 8: 序列关联到列 — 列 DROP 时序列自动清理, downgrade 精确性 + 防孤儿序列
    op.execute("ALTER SEQUENCE ths_daily_id_seq OWNED BY ths_daily.id")

    # Step 9: 业务索引 (ADR §决策 1 DDL 段显式声明)
    # 与 ths_daily_code_date_uniq UNIQUE 隐式索引并存, 形式冗余但与 sw_daily/cyq_chips 同型
    # 覆盖下游 leader_intraday 因子 WHERE code=? ORDER BY trade_date DESC 模式
    op.execute("CREATE INDEX IF NOT EXISTS idx_ths_daily_code_date ON ths_daily(code, trade_date)")


def downgrade():
    # 逆序: 删业务索引 → 解关联序列 → 删 PK → SET NULL → 清 DEFAULT → bigint→integer → 删序列
    # 不清 id 列数据 (UPDATE 回填的 id 值留存; 用户可手工重置, 但 downgrade 不主动破坏数据)
    op.execute("DROP INDEX IF EXISTS idx_ths_daily_code_date")
    op.execute("ALTER SEQUENCE IF EXISTS ths_daily_id_seq OWNED BY NONE")
    op.execute("ALTER TABLE ths_daily DROP CONSTRAINT IF EXISTS ths_daily_pkey")
    op.execute("ALTER TABLE ths_daily ALTER COLUMN id DROP NOT NULL")
    op.execute("ALTER TABLE ths_daily ALTER COLUMN id DROP DEFAULT")
    # id bigint → integer 回退 (1.93M 行远小于 int4 上限, 安全)
    op.execute("ALTER TABLE ths_daily ALTER COLUMN id TYPE integer")
    op.execute("DROP SEQUENCE IF EXISTS ths_daily_id_seq")
