"""pledge_detail / rt_sw_k / top_list schema 批量对齐（3 表）.

ADR-009: docs/adr/009-pledge-rtsw-toplist-schema-alignment.md

问题背景:
  3 表均存在 schema ⊊ sync cols 脱节 + 命名映射断裂双重问题, _insert_rows 静默吞列
  导致下游因子读到 NULL/空集后 fallback 中性分:
  - pledge_detail: 表 4 列(code/end_date/pledge_amount/pledge_ratio) vs sync 6 列, 交集仅 2 列;
    下游 advanced_factors 读 pledge_total_ratio (列不存在) → UndefinedColumn 优雅降级 → 质押扣分永不触发
  - rt_sw_k: 表 6 列缺 name/pre_close/vol/amount/pct_change; sync 用 ts_code(未split)/trade_time(datetime)
    与 PK 期望的 code(裸码)/trade_date(DATE) 对不上; 下游 screening_scorers 读 pre_close → 实时行业动量永不触发
  - top_list: 表 6 列缺 name/close/pct_change/turnover_rate/amount; sync 的 l_sell/l_buy 与表的
    sell_amount/buy_amount 命名对不上; 下游 net_amount 在交集所以因子勉强跑通

本迁移 (ADR §决策5):
  - pledge_detail: 删 end_date/pledge_ratio (sync 从未写/下游从不读) + 加 4 列(ann_date/pledgor/pledgee/
    pledge_total_ratio) + 加 PK(code, ann_date) (修无 PK 重复累积问题)
  - rt_sw_k: 加 5 列(name/pre_close/vol/amount/pct_change), PK(code, trade_date) 不变
  - top_list: 加 5 列(name/close/pct_change/turnover_rate/amount), PK(code, trade_date) 不变
  - 全用原生 SQL op.execute (ADD COLUMN IF NOT EXISTS), 禁 op.add_column (ADR-008 教训: 非幂等)

执行顺序 (ADR §决策5 风险1):
  先 TRUNCATE 3 表 → 再 upgrade head (pledge 加 PK 前表必须空, 否则重复行阻塞) → 再回补
"""
from alembic import op

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    # ── pledge_detail (ADR §决策1) ──
    # 删 end_date/pledge_ratio (表原有但 sync 从未写、下游从不读; 列名与 sync 端 ann_date/pledge_total_ratio 冲突)
    # 加 4 列对齐 sync cols + 下游读法 (advanced_factors:1038,1051 读 pledge_total_ratio)
    op.execute("""
        ALTER TABLE pledge_detail
            DROP COLUMN IF EXISTS end_date,
            DROP COLUMN IF EXISTS pledge_ratio,
            ADD COLUMN IF NOT EXISTS ann_date DATE,
            ADD COLUMN IF NOT EXISTS pledgor TEXT,
            ADD COLUMN IF NOT EXISTS pledgee TEXT,
            ADD COLUMN IF NOT EXISTS pledge_total_ratio DOUBLE PRECISION
    """)
    # 加 PK(code, ann_date): 修无 PK 导致 ON CONFLICT DO NOTHING 退化为普通 INSERT 累积重复行的问题
    # 必须在 TRUNCATE 之后执行 (执行顺序: 先 TRUNCATE → upgrade → 回补), 否则重复行阻塞 ADD CONSTRAINT
    op.execute("""
        ALTER TABLE pledge_detail
            ADD CONSTRAINT pledge_detail_pkey PRIMARY KEY (code, ann_date)
    """)

    # ── rt_sw_k (ADR §决策2) ──
    # 加 5 列: pre_close 是下游 screening_scorers:1418 算涨幅的核心读列; name/vol/amount/pct_change 同接口返回零成本存
    # PK(code, trade_date) 不变; 物理列名用 engine 命名, 下游 WHERE ts_code=? 经 pg_adapter 译 ts_code→code
    op.execute("""
        ALTER TABLE rt_sw_k
            ADD COLUMN IF NOT EXISTS name TEXT,
            ADD COLUMN IF NOT EXISTS pre_close DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS vol DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS pct_change DOUBLE PRECISION
    """)

    # ── top_list (ADR §决策3) ──
    # 加 5 列: name/close/pct_change/turnover_rate/amount 全为扩展字段 (net_amount 已在交集, 因子主路径已跑通)
    # pct_change 物理列名 (非 change_pct): 下游无消费者, 与 sync r.get("pct_change") 直通零映射; ADR 显式记录与
    # sw_daily.change_pct 的命名分歧, 未来跨表 JOIN 另开 ADR 统一
    op.execute("""
        ALTER TABLE top_list
            ADD COLUMN IF NOT EXISTS name TEXT,
            ADD COLUMN IF NOT EXISTS close DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS pct_change DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS turnover_rate DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION
    """)


def downgrade():
    # 逆序: top_list → rt_sw_k → pledge_detail
    # top_list: 删 5 列
    op.execute("""
        ALTER TABLE top_list
            DROP COLUMN IF EXISTS name,
            DROP COLUMN IF EXISTS close,
            DROP COLUMN IF EXISTS pct_change,
            DROP COLUMN IF EXISTS turnover_rate,
            DROP COLUMN IF EXISTS amount
    """)
    # rt_sw_k: 删 5 列
    op.execute("""
        ALTER TABLE rt_sw_k
            DROP COLUMN IF EXISTS name,
            DROP COLUMN IF EXISTS pre_close,
            DROP COLUMN IF EXISTS vol,
            DROP COLUMN IF EXISTS amount,
            DROP COLUMN IF EXISTS pct_change
    """)
    # pledge_detail: 先删 PK 再删列, 最后恢复 end_date/pledge_ratio 旧列
    op.execute("ALTER TABLE pledge_detail DROP CONSTRAINT IF EXISTS pledge_detail_pkey")
    op.execute("""
        ALTER TABLE pledge_detail
            DROP COLUMN IF EXISTS ann_date,
            DROP COLUMN IF EXISTS pledgor,
            DROP COLUMN IF EXISTS pledgee,
            DROP COLUMN IF EXISTS pledge_total_ratio,
            ADD COLUMN IF NOT EXISTS end_date DATE,
            ADD COLUMN IF NOT EXISTS pledge_ratio DOUBLE PRECISION
    """)
