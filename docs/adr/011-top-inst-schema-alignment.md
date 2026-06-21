# ADR-011: top_inst schema 对齐 — 存 per-institution 明细 + 自增 PK + 下游应用层聚合

- 状态：Accepted
- 日期：2026-06-22
- 决策者：product-lead（业务方向）+ tech-lead（技术细化签字）
- 影响范围：services/sql/init_postgres.sql（L161-165） + backend/alembic/versions/010_top_inst_align.py（新建） + `packages/kronos-data/` 与 `packages/kronos-factors/` **零改动**
- 编号说明：ADR-008 sw_daily / ADR-009 pledge+rtsw+toplist / ADR-010 cyq_chips 均已 Accepted；本决策顺延 ADR-011

## 上下文

`top_inst`（龙虎榜机构席位）当前 schema 与 Tushare 实际返回**完全错位**。探针实测（2026-06-22）：`pro.top_inst(trade_date='20260618')` 返回 `ts_code, trade_date, exalter, buy, buy_rate, sell, sell_rate, net_buy`（8 字段），**per-institution 明细**——单日 1020 行、每股约 10 个机构席位（买方 5 个 + 卖方 5 个），`exalter`（席位名）大量为「机构专用」匿名席位，但 `buy/sell/net_buy` 是真实金额。

PG 表 `top_inst` 当前 schema（`init_postgres.sql:161-165`，**无 PK**）：

```sql
CREATE TABLE IF NOT EXISTS top_inst (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    inst_name TEXT, buy_amount DOUBLE PRECISION, sell_amount DOUBLE PRECISION, net_amount DOUBLE PRECISION
);
```

错位事实：
- 表列 `inst_name / buy_amount / sell_amount / net_amount` —— **Tushare 不返回这 4 列**，是建表时凭空想象的死列名。
- sync `etl.py:888-914` cols `["code","trade_date","exalter","buy","buy_rate","sell","sell_rate","net_buy"]` —— 与 Tushare 字段一一对应。但 `_insert_rows`（`etl.py:167-200`）的"自动过滤无效列"止血逻辑（commit 2d311fa）会丢弃 `exalter / buy / buy_rate / sell / sell_rate / net_buy` 全部 6 列，表的 `inst_name / buy_amount / sell_amount / net_amount` 4 列从未被 sync 写入过——**写入实际 0 列**，表恒为空或只有 (code, trade_date) 两个非空列。
- 无 PK：即便有数据，`ON CONFLICT DO NOTHING`（`etl.py:189`）在无 PK/无 UNIQUE 时退化为普通 INSERT，sync 重复运行会累积重复行；当前靠 `clean_before_write(db, "top_inst", days_back)`（`etl.py:895`）窗口删旧重写兜底，但失去数据完整性约束。

下游消费 `advanced_factors.py:886`：`SELECT * FROM top_inst WHERE code=? ORDER BY trade_date DESC LIMIT 30`，再在应用层 `sum(r["net_buy"] for r in ti_rows)` / `sum(r["buy"] for r in ti_rows)` / `sum(r["sell"] for r in ti_rows)`（`advanced_factors.py:945-953`）—— **下游已用 per-institution 明细按席位累加**，根本不依赖 stock/day 预聚合。只要表里有 per-institution 明细，下游零改动直接生效。

不做此决策：龙虎榜机构因子（`tushare_top_inst`，`advanced_factors.py:945-953`，权重 0.05-0.06 见 `engine/modes.py:206,261` + `screening_scorers.py:1533`）永久 fallback 中性 5.0 分（不可用 flag `available: False`），50 维评分继续缺一项；与已 Accepted 的 ADR-008 sw_daily / ADR-009 pledge+rtsw+toplist / ADR-010 cyq_chips 形成最后一块拼图。

## 决策

### 决策 0：文件改动白名单（对 backend-dev 的硬约束）

⚠️ **本 ADR 明确列出允许修改的文件清单。backend-dev 不得修改清单外的任何文件。越界改动 = 违约，PL 直接回退。**（沿用 ADR-010 决策 0 风格。）

| # | 文件 | 允许改动 |
|---|---|---|
| 1 | `backend/alembic/versions/010_top_inst_align.py` | **新建**（revision=010, down_revision=009）—— 按本 ADR §决策 4 模板起草 |
| 2 | `services/sql/init_postgres.sql` | 仅 top_inst CREATE TABLE 段（L161-165）+ 紧随其后追加 `idx_top_inst_code_date` 索引；**不得动其他表** |
| 3 | `packages/kronos-data/kronos_data/etl.py` | **零改动**（`sync_top_inst` L888-914 cols 与 row tuple 已正确） |
| 4 | 下游因子代码（`packages/kronos-factors/`） | **零改动**（`advanced_factors.py:886,945-953` 读 `SELECT *` 后应用层 `r["buy"]` / `r["sell"]` / `r["net_buy"]` 字面与新物理列一致） |

**不在白名单内的常见误改项**（明确禁止）：`backend/alembic/versions/001-009_*`；`pg_adapter.py` 的 `_COLUMN_MAP`/`_KEY_MAP`；`advanced_factors.py`、`screening_scorers.py`；`scheduler.py`；其他表 schema；不得引入物化视图 `mv_top_inst_daily`（见决策 4 否决理由）。

### 决策 1：存 Tushare 原始 per-institution 明细，删 4 死列

**目标列集**（对齐 Tushare 返回 + sync cols + 下游读法）：`code, trade_date, exalter, buy, buy_rate, sell, sell_rate, net_buy`。

| 列 | 动作 | 类型 | Tushare 语义 | 备注 |
|---|---|---|---|---|
| `code` | 保留 | TEXT NOT NULL | 股票裸码 | sync 已 `_code_from_ts(r["ts_code"])` split（etl.py:906）|
| `trade_date` | 保留 | DATE NOT NULL | 交易日期 | sync 已格式化为 "YYYY-MM-DD"（etl.py:907）|
| `exalter` | **新增** | TEXT | 席位名/营业部名 | 多为「机构专用」匿名；sync `r.get("exalter")` 直通 |
| `buy` | **新增** | DOUBLE PRECISION | 买入金额（元） | sync `r.get("buy")` 直通 |
| `buy_rate` | **新增** | DOUBLE PRECISION | 买入占比（%） | sync `r.get("buy_rate")` 直通 |
| `sell` | **新增** | DOUBLE PRECISION | 卖出金额（元） | sync `r.get("sell")` 直通 |
| `sell_rate` | **新增** | DOUBLE PRECISION | 卖出占比（%） | sync `r.get("sell_rate")` 直通 |
| `net_buy` | **新增** | DOUBLE PRECISION | 净买入金额（元） | sync `r.get("net_buy")` 直通；下游 SUM 的主指标 |
| ~~`inst_name`~~ | **删除** | — | — | Tushare 不返回此名（实际是 `exalter`）；从无数据；下游不读 |
| ~~`buy_amount`~~ | **删除** | — | — | Tushare 不返回此名（实际是 `buy`）；从无数据；下游不读 |
| ~~`sell_amount`~~ | **删除** | — | — | 同上（实际是 `sell`）|
| ~~`net_amount`~~ | **删除** | — | — | 同上（实际是 `net_buy`）；注意：与 `top_list.net_amount`（ADR-009 决策 3 保留）名字相同但语义不同，不要混淆 |

**为什么 DOUBLE PRECISION 而非 NUMERIC**：top_inst 的金额字段是元为单位的浮点（如 `123456789.12`），下游只做 SUM 聚合，无需 NUMERIC 的精确小数语义；与已 Accepted 的 ADR-009 top_list `net_amount DOUBLE PRECISION` 同基线，避免跨表类型分歧。

**为什么不扩展存 `side` / `reason`**：Tushare top_inst 接口实测**不返回** `side` / `reason` 字段（大纲笔误，与 `top_list` 接口混淆——`top_list` 才有 `reason`，见 ADR-009 决策 3）。sync `etl.py:897-898` cols 也未取这两列。本 ADR 严格对齐 sync 现状，不引入凭空字段。若未来 Tushare 扩展返回 `side`，另开 ADR。

**为什么删 4 死列而非保留**：4 列从无数据、从无 sync 写入路径、下游不读；保留是死列噪音 + 与新列名混淆（"buy_amount 和 buy 到底用哪个？"）。删列在 TRUNCATE 后进行，无数据损失（NULL 删除等于零损失）。沿用 ADR-009 pledge_detail `end_date/pledge_ratio` 删列 + ADR-010 cyq_chips `avg_cost/concentration_90/profit_ratio` 删列哲学。

### 决策 2：主键策略 — BIGSERIAL 自增 id 主键 + (code, trade_date) 业务索引

**核心权衡**：`exalter` 大量为「机构专用」匿名席位，**同 code 同 trade_date 内可能有多个「机构专用」**（实测同股一日买方 1-5 个匿名席位 + 卖方 1-5 个，且不同匿名席位 buy/sell 金额可能相同），任何基于业务字段的复合 PK 都会偶发去重失败或反模式。

**决策**：新增 `id BIGSERIAL PRIMARY KEY`（自增 surrogate key），业务唯一性约束**不强制**；通过 `clean_before_write` 窗口删旧重写防累积。

| 维度 | 方案 i：BIGSERIAL id PK | 方案 ii：(code,trade_date,exalter) PK | 方案 iii：(code,trade_date,exalter,buy,sell) PK |
|---|---|---|---|
| 数据完整性 | ✅ 全保留（多个「机构专用」不丢） | ❌ 同股同日多个「机构专用」第 2+ 个被 ON CONFLICT DO NOTHING 静默丢失 | ⚠️ 极端情况两个「机构专用」buy/sell 恰好相同时丢失；且 DOUBLE 作 PK 浮点反模式 |
| 重复 sync 累积 | clean_before_write 兜底（已存在，etl.py:895） | PK 强约束防累积 | 同左 |
| Tushare 真实场景 | 适应（实测匿名席位频繁） | 数据损失（业务上同一席位类型多次出现是合法的） | 反模式（同 ADR-010 备选 E 否决理由：浮点 PK） |
| 配套索引 | `(code, trade_date)` 普通索引覆盖下游 `WHERE code=? ORDER BY trade_date DESC LIMIT 30` | PK 前导列已覆盖 | 同方案 ii |

**选方案 i 的关键理由**：
1. `advanced_factors.py:946-953` 应用层 `sum(r["net_buy"] for r in ti_rows)` 是席位级累加—— **多个匿名席位的金额必须各自保留**（每行独立 SUM 才得正确总和），方案 ii 会丢数据导致因子分数偏离真实。
2. `clean_before_write(db, "top_inst", days_back)`（`etl.py:895`）已实现"窗口删旧重写"，重复 sync 不累积；PK 的"防累积"价值已由 clean_before_write 替代，PK 真正剩余的价值是数据完整性约束—— BIGSERIAL 是最契合的方案。
3. 与 SQLite legacy `models.py:504-515` 的 `id INTEGER PRIMARY KEY AUTOINCREMENT` 哲学一致（虽 SQLite 加了 `UNIQUE(code,trade_date,exalter)` 这一层，PG 不复制此约束因 ADR-010 已确认 SQLite legacy 是降级 fallback、非真实部署目标，且该 UNIQUE 在 PG 同样会丢数据）。
4. BIGSERIAL（8-byte）vs SERIAL（4-byte）：龙虎榜单日 1020 行 × 365 天 × 多年 ≈ 千万级，BIGSERIAL 上限 9.2×10^18 远超需求；预防未来全市场扩展时 SERIAL 溢出。

**配套索引**：`CREATE INDEX idx_top_inst_code_date ON top_inst(code, trade_date)` —— 覆盖下游唯一查询模式 `WHERE code=? ORDER BY trade_date DESC LIMIT 30`，与 SQLite legacy `models.py:766` 同名索引一致。

**关于 ON CONFLICT DO NOTHING 在 BIGSERIAL PK 下的行为**：BIGSERIAL 每次 INSERT 生成新 id，永不冲突 → `ON CONFLICT DO NOTHING` 永不触发跳过 → 每行必写。这是预期行为（数据完整性优先于去重），重复 sync 由 `clean_before_write` 防累积。

### 决策 3：sync 与下游因子零代码改动（同 ADR-010 哲学）

`etl.py:888-914` 的 cols `["code","trade_date","exalter","buy","buy_rate","sell","sell_rate","net_buy"]` 与 row tuple `(_code_from_ts(r["ts_code"]), d[:4]+"-"+d[4:6]+"-"+d[6:8], r.get("exalter"), r.get("buy"), r.get("buy_rate"), r.get("sell"), r.get("sell_rate"), r.get("net_buy"))` **已按 8 列正确顺序写好**，加列 + 删死列后：

- `_insert_rows._get_pg_columns` 返回 8 列（外加 `id` 自增不在 INSERT 列表），`valid_cols` 不再丢列。
- 8 列业务数据从下一次 sync 开始自动落盘，`id` 由 PG 自增生成。
- `advanced_factors.py:886` `SELECT * FROM top_inst WHERE code=?` 直接返回所有业务列 + id，应用层 `r["net_buy"]` / `r["buy"]` / `r["sell"]` 字段直接命中。
- **零 etl 改动 + 零下游改动 = 零回归风险**，与 ADR-010 cyq_chips 哲学完全一致。

**字段映射确认**（探针实测 2026-06-22）：

| Tushare 字段 | etl `r.get(...)` | 物理列 | 备注 |
|---|---|---|---|
| `ts_code` | `_code_from_ts(r["ts_code"])` | `code` | 已 split（etl.py:906）|
| `trade_date` | `d[:4]+"-"+d[4:6]+"-"+d[6:8]` | `trade_date` | etl.py:907 已格式化 |
| `exalter` | `r.get("exalter")` | `exalter` | **新列**，Tushare 原名直通 |
| `buy` | `r.get("buy")` | `buy` | **新列**，Tushare 原名直通 |
| `buy_rate` | `r.get("buy_rate")` | `buy_rate` | **新列**，Tushare 原名直通 |
| `sell` | `r.get("sell")` | `sell` | **新列**，Tushare 原名直通 |
| `sell_rate` | `r.get("sell_rate")` | `sell_rate` | **新列**，Tushare 原名直通 |
| `net_buy` | `r.get("net_buy")` | `net_buy` | **新列**，Tushare 原名直通；下游 SUM 主指标 |

8 个字段名 Tushare → sync → 物理列 → 下游 `r["xxx"]` 全程字面一致，**无需扩展 `pg_adapter._COLUMN_MAP` / `_KEY_MAP`**。

### 决策 4：下游聚合 — 应用层 SUM，不引物化视图

**关键发现**：`advanced_factors.py:946-953` 的因子算法**已经是应用层 SUM**：

```python
# top_inst（advanced_factors.py:945-953 现状）
if ti_rows:  # ti_rows 来自 SELECT * FROM top_inst WHERE code=? ORDER BY trade_date DESC LIMIT 30
    net = sum(r["net_buy"] or 0 for r in ti_rows)
    bt = sum(r["buy"] or 0 for r in ti_rows)
    st = sum(r["sell"] or 0 for r in ti_rows)
    total = bt + st
    ...
```

下游拿到 per-institution 明细 30 行后用 Python `sum()` 直接累加—— **per-institution 明细即下游所需格式**，无需在 SQL 层预聚合到 stock/day。

**否决 mv_top_inst_daily 物化视图**（大纲选项 A）：
- pros: 大纲设想"下游读 stock/day 聚合零代码改动"——但实测下游本就读 per-institution 明细 + 应用层 SUM，物化视图反而需要改下游 SQL `SELECT * FROM mv_top_inst_daily`（违反白名单决策 0 「下游零改动」）。
- cons: 物化视图刷新策略（盘后 REFRESH MATERIALIZED VIEW）增加运维复杂度；千万级数据全量 REFRESH 耗时；CONCURRENTLY 需 UNIQUE 索引（同样卡「机构专用」匿名问题）。
- **否决理由**：YAGNI——下游应用层 SUM 已正确工作，物化视图是为了解决一个**不存在的问题**（下游并不需要预聚合）；与 ADR-010 备选 D「保留死列」否决理由同型（单一来源原则）。

**否决 SQL `SUM() GROUP BY` 改下游**（大纲选项 B）：
- 同上理由：违反白名单决策 0「下游因子代码零改动」，且应用层 SUM 与 SQL SUM 结果等价、性能在 LIMIT 30 行场景下无差异。

**结论**：本 ADR 不创建物化视图、不改下游 SQL。`advanced_factors.py:945-953` 现有应用层 SUM 在 schema 对齐后**自动从 fallback 中性 5.0 切换到真实数据驱动评分**。

### 决策 5：Alembic 010 迁移脚本（破坏性改 schema + 加 BIGSERIAL PK）

**起草 `backend/alembic/versions/010_top_inst_align.py`**（revision=010, down_revision=009）。

**upgrade()** 关键步骤：

```python
def upgrade():
    # 1. 当前无 PK, 跳过 DROP CONSTRAINT (与 ADR-010 cyq_chips 差异: 后者有旧 PK 需 DROP)
    #    但保留 IF EXISTS 兜底防 init_postgres.sql 未来意外加 PK
    op.execute("ALTER TABLE top_inst DROP CONSTRAINT IF EXISTS top_inst_pkey")

    # 2. 单条 ALTER: 删 4 死列 + 加 6 业务列 (id 列单独 ADD 因 BIGSERIAL 语法分歧)
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

    # 3. 加自增 id 列 + PRIMARY KEY (BIGSERIAL = BIGINT + GENERATED ... AS IDENTITY 或 sequence)
    #    PG 15 推荐 GENERATED AS IDENTITY (SQL 标准, 优于 SERIAL); 但为对齐已有迁移风格用 BIGSERIAL 等价
    op.execute("""
        ALTER TABLE top_inst
            ADD COLUMN IF NOT EXISTS id BIGSERIAL
    """)
    op.execute("""
        ALTER TABLE top_inst
            ADD CONSTRAINT top_inst_pkey PRIMARY KEY (id)
    """)

    # 4. 业务索引覆盖下游 WHERE code=? ORDER BY trade_date DESC 模式
    op.execute("CREATE INDEX IF NOT EXISTS idx_top_inst_code_date ON top_inst(code, trade_date)")
```

**downgrade()** 逆序：

```python
def downgrade():
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
```

**幂等性**：全用 `IF NOT EXISTS` / `IF EXISTS`。**禁止用 `op.add_column` / `op.drop_column` / `op.create_primary_key`**（非幂等，ADR-008 教训）。

**执行顺序约束**：
1. **先 TRUNCATE top_inst**（盘后运维手动执行）—— 旧表数据全是无意义的 (code, trade_date) 二元组（4 业务列全 NULL），无业务价值；且若保留旧行，加 BIGSERIAL `id` 列时 PG 会为旧行回填 id（无问题），但旧行的 buy/sell/net_buy 全 NULL 会污染下游 SUM 直到下次 clean_before_write 窗口外移。**TRUNCATE 是清洁起点的必需操作**。
2. `alembic upgrade head` —— 执行 010 迁移。
3. 运行 `sync_top_inst(days_back=30)` 回补。

**与 ADR-010 cyq_chips 差异**：cyq_chips 旧 PK `(code, trade_date)` 与新 PK `(code, trade_date, price)` 冲突，必须 DROP CONSTRAINT 后加新 PK 前 TRUNCATE。top_inst **无旧 PK**，TRUNCATE 不是技术必需（迁移自身能跑通）但是**数据洁净度必需**——否则旧 NULL 行污染下游评分至 30 天后窗口移出。

### 决策 6：TRUNCATE + sync 回补

**回补脚本**（盘后运维执行，不进 scheduler cron）：

```sql
TRUNCATE top_inst;
```

```python
from kronos_data.etl import sync_top_inst
sync_top_inst(days_back=30)  # 默认 30 天回补
```

**配额评估**：
- Tushare `top_inst` 需 **2000 积分**（Tushare 接口文档；项目现有 token 已使用过该接口，见 scheduler.py:994 cron 配置）。
- sync 限制：按 trade_date 批量（`pro.top_inst(trade_date=d)`），每个交易日 1 次 API 调用。`_get_trade_dates(30)` 返回近 30 天的约 22 个交易日 → 22 次 API 调用。`_rate_limit()` 400 次/分钟 → 实际耗时 < 5 秒。
- 数据量：~1020 行/日 × 22 交易日 = **~22000 行/次 30 天回补**，PG 15 单表可忽略。

**前置验证**：
1. `TUSHARE_TOKEN` 账号积分 ≥ 2000（先跑探针 `pro.top_inst(trade_date='<近 5 日某交易日 YYYYMMDD>')` 确认非空）
2. `KRONOS_PG_URL` 指向正确库
3. 回补后验证：
   - `SELECT COUNT(*) FROM top_inst WHERE net_buy IS NOT NULL` > 5000（22 天 × 平均 500+ 席位）
   - `SELECT COUNT(DISTINCT code) FROM top_inst` > 50（30 天龙虎榜涉及股票数）
   - `SELECT COUNT(*) FROM top_inst WHERE exalter LIKE '%机构专用%'` > 1000（验证匿名席位存在 + 数据完整保留）

### 决策 7：下游影响评估

| 因子 | 位置 | 现状 | 迁移+回补后 |
|---|---|---|---|
| 龙虎榜机构净买入（tushare_top_inst） | `advanced_factors.py:945-953` | 表写入 0 业务列 → ti_rows 即使非空，`r["net_buy"]` / `r["buy"]` / `r["sell"]` 全 NULL → 应用层 SUM = 0 → 进入 elif 分支但条件全不命中 → 实际接近"available=False"的退化态 | 8 列有真实数据 → 应用层 SUM 得真实金额 → `bt > st*1.5` 等条件正常触发 → 评分基于真实机构买卖动态 |

**因子权重影响**：
- `engine/modes.py:261` 短线模式 `tushare_top_inst` 权重 0.05
- `engine/modes.py:206` 龙虎榜大类 `top_inst` 权重 0.05
- `screening_scorers.py:1533` 主流程 `tushare_top_inst` 权重 0.06
- 总权重影响：评分中 5-6% 维度从"中性 5.0 分"切换到"基于真实数据 0-10 分波动"——回归全量评分后对个股排名预期有小幅扰动（属预期修复）。

**回归风险**：
- 同 ADR-008 / 009 / 010：分数从"稳定中性"变为"基于真实数据波动"，需运维 / tech-lead 抽样对比一轮 screener 全量评分（前 50 标的排名变化 < 20%为正常，> 50% 触发因子归一化检查）。
- `ON CONFLICT DO NOTHING` + BIGSERIAL PK：永不冲突，每行必写；重复 sync 由 clean_before_write 兜底——若 clean_before_write 失败（如 days_back 设错），表会累积重复 → 加运维监控 `SELECT trade_date, COUNT(*)/COUNT(DISTINCT code) FROM top_inst WHERE trade_date >= NOW() - INTERVAL '7 days' GROUP BY trade_date` 单日单股席位数 > 30 触发告警（正常 ~10）。

## 备选方案

- **A. 改 sync 反向聚合写表（保留 stock/day 聚合 schema）** — pros: 表/下游不动；cons: sync 要按 (code,trade_date) GROUP BY SUM，丢机构维度（最大买方席位、匿名席位数等信息永久丢失），且 Tushare 明细才是原始数据；下游 `advanced_factors.py:945-953` 应用层 SUM 已正确工作，sync 端反向聚合反而是双重劳动。**否决理由**：信息损失 + 违背"存原始、下游加工"（ADR-006 §决策 2 + ADR-010 决策 1 同型）。

- **B. 明细 + 聚合双表（top_inst_detail + top_inst_daily）** — pros: 明细/聚合各取所需；cons: 双写复杂、双表一致性维护、且下游已应用层 SUM 不需要聚合表。**否决**（YAGNI + 单一来源原则）。

- **C. 不动表，让下游从 top_list 读机构数据** — pros: 零改动；cons: top_list 是龙虎榜营业部明细（`l_buy / l_sell` 见 ADR-009 决策 3），top_inst 是机构席位明细，语义不同——top_list 不含机构席位维度，不可替代。**否决**。

- **D. PK 用 (code, trade_date, exalter) 三列复合** — pros: 业务唯一约束；cons: 同 code 同 trade_date 内多个「机构专用」匿名席位会被 ON CONFLICT DO NOTHING 丢失第 2+ 条，下游 SUM 结果偏低（实测匿名席位金额可能与具名席位等量级 → 评分偏差显著）。**否决理由**：数据完整性损失（同 ADR-010 备选 E「四列含 percent 浮点 PK」否决理由同型，但此处是匿名重复而非浮点精度）。

- **E. PK 用 (code, trade_date, exalter, buy, sell) 五列复合** — pros: 极端情况外几乎唯一；cons: `buy/sell` 是 DOUBLE PRECISION，作 PK 浮点反模式（同 ADR-010 备选 E 否决）；且两个匿名席位 buy/sell 恰好相同时仍丢失。**否决理由**：浮点 PK + 仍非真正唯一。

- **F. 引入物化视图 `mv_top_inst_daily(code, trade_date, sum_buy, sum_sell, sum_net)`** — pros: 大纲设想；cons: 下游本就读 per-institution 明细应用层 SUM，物化视图反而需改下游 SQL 违反白名单决策 0；且千万级数据 REFRESH 增加运维复杂度（无 UNIQUE 索引就无 CONCURRENTLY 刷新）。**否决理由**：解决不存在的问题（YAGNI）+ 违反白名单。

- **G. 保留 4 死列不删（避免破坏性变更）** — pros: downgrade 更简单 / 兼容潜在历史读取者；cons: 4 死列永远 NULL，与 6 新列名混淆（"net_amount vs net_buy 用哪个？"），且 grep 验证全仓无 top_inst.inst_name / buy_amount / sell_amount / net_amount 的消费者（只在 init_postgres.sql 自身和 ADR 文档出现），保留是噪音。**否决理由**：单一来源原则（同 ADR-009 备选 C + ADR-010 备选 D 否决理由）。

## 影响

### 对现有代码（按白名单）
- `services/sql/init_postgres.sql`：top_inst DDL 改写（L161-165，8 业务列 + id BIGSERIAL PK + idx_top_inst_code_date 索引）。
- `backend/alembic/versions/010_top_inst_align.py`：新建（按本 ADR §决策 5 模板）。
- `packages/kronos-data/kronos_data/etl.py`：**零改动**。
- 下游因子（`packages/kronos-factors/`）：**零改动**。

### 对成本
- **API**：22 次/sync × 30 天 = 22 次/次回补；基线 cron（scheduler.py:994 每交易日 17:03）= 1 次/日 × 245 交易日/年 ≈ 245 次/年，不增量。
- **存储**：30 天回补 ~22000 行 × 8 列 × ~50 bytes ≈ 9 MB（PG 15 无压力）；全年 ~250000 行 ≈ 100 MB。
- **人力**：迁移 + init SQL 同步 ~0.3d（已由本 ADR 指明模板），回补验证 ~0.3d。

### 对运维
- 新增监控：
  - `SELECT COUNT(*) FROM top_inst WHERE trade_date >= NOW() - INTERVAL '7 days'` > 3000（每周至少 3000 行）
  - `SELECT trade_date, COUNT(*)/NULLIF(COUNT(DISTINCT code),0) FROM top_inst WHERE trade_date >= NOW() - INTERVAL '7 days' GROUP BY trade_date` —— 单股席位数 > 30 触发去重失败告警
- `scheduler.py:994` 的 top_inst cron `"3 17 * * 1-5"` 保持现状（本 ADR 不动调度逻辑）。
- BIGSERIAL `id` 列：永不溢出（9.2×10^18），无需运维干预。

### 数据量评估

| 场景 | 行数估算 | 是否需分区 |
|---|---|---|
| 当前（30 天 × 22 交易日） | ~22000 行 | 否 |
| 一年（245 交易日） | ~250000 行 | 否 |
| 五年（1225 交易日） | ~1250000 行 | 否，PG 15 单表 < 10M 行无需分区 |
| 全市场长历史扩展 | — | 见"不覆盖" |

**本 ADR 决策范围**：仅覆盖当前默认场景；十年+ 长历史回补另议。

### 风险
1. **TRUNCATE 后 upgrade 之间窗口下游查空表** → top_inst 因子短暂 fallback。**缓解**：盘后 16:30+ 执行（盘后无实时评分请求），窗口 < 1 分钟。
2. **TUSHARE_TOKEN 积分不足 2000** → sync 静默 continue（`etl.py:902` `try ... except: continue`），表为空。**缓解**：运维执行前先跑探针 `pro.top_inst(trade_date=<昨日>)` 确认非空（同 ADR-010 风险 2 处理模式）。
3. **Tushare top_inst 接口字段变更** → sync row tuple `r.get(...)` 返回 None，新列全 NULL；BIGSERIAL PK 不约束业务字段非空 → 表能写入但下游 SUM = 0。**缓解**：探针验证字段名后再 TRUNCATE；若 Tushare 改字段名，sync `r.get("...")` key 同步改，另开 ADR（同 ADR-010 风险 3 处理模式）。
4. **「机构专用」匿名席位重复存储无业务唯一约束** → 同股同日多个「机构专用」row 全保留；若 sync 函数被改成多次调用同一 trade_date 而 clean_before_write 未生效，会累积重复行。**缓解**：保留 clean_before_write 调用（etl.py:895）+ 运维监控单股单日席位数（见上文运维段）。

## 本 ADR 不覆盖的决策

- **top_inst 长期历史回补**（> 30 天 / 年级 / 全部历史）：当前 sync 默认 days_back=30，扩展场景另议；当行数 > 10M 时考虑按 trade_date 分区。
- **top_inst `side` / `reason` 字段扩展**：Tushare 当前接口实测不返回这两列；若未来 Tushare 升级接口返回，另开 ADR 扩展 sync cols + 表列。
- **「机构专用」匿名席位的因子层细化**（如区分匿名 vs 具名席位的权重差异）：属因子算法迭代，非 schema 决策；advanced_factors.py 现读法直接生效。
- **`_insert_rows` 通用函数重构**（ON CONFLICT 策略参数化）：见 ADR-009 §不覆盖，跨表问题不在本 ADR。
- **数据管道写入侧剩余表脱节**（hk_holdings / repurchase / share_float / cyq_perf 等）：见项目记忆 `data-pipeline-write-debt.md`，sw_daily / pledge+rtsw+toplist / cyq_chips / top_inst 共 7 表（ADR-008/009/010/011）已覆盖；剩余表查证后立 ADR-012+ 批量修复。

## 后续工作

- [ ] **backend-dev**（限额重置后 / 新会话）：按本 ADR 实施——(1) 起草 `backend/alembic/versions/010_top_inst_align.py`（按 §决策 5 模板，全幂等 op.execute）；(2) 改 `init_postgres.sql:161-165` top_inst CREATE TABLE + 追加 `idx_top_inst_code_date` 索引；(3) 盘后 `TRUNCATE top_inst` → `alembic upgrade head` → `sync_top_inst(days_back=30)` 回补 → 验证 §决策 6 三条 SQL 非空；(4) **不得越界**改白名单外文件（决策 0）。
- [ ] **tech-lead**（回补后）：审查 `advanced_factors.py:945-953` 龙虎榜机构因子抽样输出，确认从 NULL/0 切换到真实金额；若 `buy_rate` / `sell_rate` 量级与预期不符（如 Tushare 返回 0-1 vs 0-100），开 task 修因子层归一化（非本 ADR 范围）。
- [ ] **tech-lead**：top_inst 是数据管道写入侧债务 7 表中第 7 表（前 6：sw_daily / pledge_detail / rt_sw_k / top_list / cyq_chips；分别在 ADR-008 / 009-1 / 009-2 / 009-3 / 010 覆盖）；剩余 hk_holdings / repurchase / share_float / cyq_perf 等表查证后立 ADR-012 批量修复。

## 版本与查证

**查证基线日期**：2026-06-22

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| PostgreSQL | 15.x（docker `postgres:15-alpine`） | 17.x | 2 个 major | Active，PG 15 支持至 2027-11 | [PostgreSQL Versioning Policy](https://www.postgresql.org/support/versioning/) — 与 ADR-001/006/008/009/010 一致；`DROP CONSTRAINT IF EXISTS` + `ADD COLUMN IF NOT EXISTS` + `ADD CONSTRAINT PRIMARY KEY` + `BIGSERIAL` 均 PG 15 原生支持；BIGSERIAL 自 PG 8.0 起稳定 |
| Alembic | 1.18.4 | 1.18.4 | 0 | Active | `pip show alembic` 实测；与 ADR-008/009/010 同基线；`op.execute` + 原生 SQL 风格沿用 |
| psycopg2 | 2.9.12 | 2.9.x | 0 | Active | `pip show psycopg2` 实测；与 ADR-008/009/010 同基线 |
| Tushare Python SDK | 1.4.29 | 1.4.x | 0 | Active | `pip show tushare` 实测；`pro.top_inst` 接口签名自 1.2.x 起稳定 |
| Tushare top_inst 接口 | 2000 积分门槛 | — | — | Stable | 实测探针 2026-06-22：`pro.top_inst(trade_date='20260618')` 返回字段 **`[ts_code, trade_date, exalter, buy, buy_rate, sell, sell_rate, net_buy]`**（8 字段，**不含** `side` / `reason`），单日 1020 行；`scheduler.py:994` cron `"3 17 * * 1-5"` 已配置；项目现有 token 成功拉取过数据（数据停滞是因表 schema 错位 → `_insert_rows` 过滤后写入 0 业务列，非接口失败）；接口文档 [https://tushare.pro/document/2?doc_id=106](https://tushare.pro/document/2?doc_id=106)（需登录） |

**当前 top_inst 物理 schema 实证**（grep `init_postgres.sql:161-165`，2026-06-22）：

```sql
CREATE TABLE IF NOT EXISTS top_inst (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    inst_name TEXT, buy_amount DOUBLE PRECISION, sell_amount DOUBLE PRECISION, net_amount DOUBLE PRECISION
);
-- 无 PK, 无索引, 与 sync cols 完全不交
```

**sync 端实证**（grep `etl.py:888-914`，2026-06-22）：
- cols `["code", "trade_date", "exalter", "buy", "buy_rate", "sell", "sell_rate", "net_buy"]` ✓
- row tuple `(_code_from_ts(r["ts_code"]), d[:4]+"-"+d[4:6]+"-"+d[6:8], r.get("exalter"), r.get("buy"), r.get("buy_rate"), r.get("sell"), r.get("sell_rate"), r.get("net_buy"))` ✓
- `clean_before_write(db, "top_inst", days_back)` 已存在（etl.py:895） ✓

**下游消费端实证**（grep `advanced_factors.py`，2026-06-22）：
- L886: `db.execute("SELECT * FROM top_inst WHERE code=? ORDER BY trade_date DESC LIMIT 30", (code,)).fetchall()` ✓
- L945-953: `sum(r["net_buy"] or 0 for r in ti_rows)` / `sum(r["buy"] or 0 for r in ti_rows)` / `sum(r["sell"] or 0 for r in ti_rows)` — 应用层 SUM 字段名与本 ADR 新物理列字面一致 ✓
- L1221: `tushare_top_inst` 在因子聚合循环中 ✓
- `screening_scorers.py:1533`: `ts_scores.get("tushare_top_inst",{}).get("score",5)` 权重 0.06 ✓
- `engine/modes.py:206,261`: top_inst 权重 0.05 ✓

**SQLite legacy schema 对比实证**（grep `kronos_data/models.py:504-515`，2026-06-22）：
```sql
CREATE TABLE IF NOT EXISTS top_inst (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    exalter TEXT,
    buy REAL, buy_rate REAL,
    sell REAL, sell_rate REAL,
    net_buy REAL,
    ...
    UNIQUE(code, trade_date, exalter)
);
CREATE INDEX idx_top_inst_code_date ON top_inst(code, trade_date);
```
本 ADR 的 PG schema 与 SQLite legacy **业务列对齐**（8 列同名同序），仅 PK 策略差异（PG 不复制 `UNIQUE(code, trade_date, exalter)`——决策 2 已论证该 UNIQUE 在 PG 同样会丢匿名席位数据）+ 类型差异（PG `DOUBLE PRECISION` vs SQLite `REAL`，跨引擎语义等价）。

**不引入新依赖**：本 ADR 纯 schema + PK 重建 + 索引，CLAUDE.md Tech Stack 表无需新增行。

**与 CLAUDE.md "PG 与 SQLite 列名差异" 段一致性**：
- `exalter / buy / buy_rate / sell / sell_rate / net_buy` 无 SQLite/PG 命名分歧（Tushare 原名直接采用），无需扩展 `pg_adapter._COLUMN_MAP` 或 `_KEY_MAP`。
- 新 BIGSERIAL `id` 列下游不读（只在 PK 内部用），无映射需求。
- `code` / `trade_date` 沿用 engine 命名（与 sw_daily / pledge_detail / cyq_chips 一致），`pg_adapter` 既有翻译规则适用。

---

**Hand-off 给 backend-dev**（限额重置后 / 新会话执行）：

按以下顺序，**严格不越白名单**（决策 0）：

1. **起草 `backend/alembic/versions/010_top_inst_align.py`**：按 §决策 5 upgrade/downgrade 模板，revision=`'010'`, down_revision=`'009'`，全 `op.execute` + `IF NOT EXISTS` / `IF EXISTS` 幂等。
2. **改 `services/sql/init_postgres.sql:161-165`**：top_inst CREATE TABLE 重写为 8 业务列 + `id BIGSERIAL PRIMARY KEY`；紧随其后追加 `CREATE INDEX IF NOT EXISTS idx_top_inst_code_date ON top_inst(code, trade_date);`。
3. **执行迁移 + 回补**（盘后 16:30+）：
   ```bash
   psql "$KRONOS_PG_URL" -c "TRUNCATE top_inst;"
   cd backend && alembic upgrade head
   python -c "from kronos_data.etl import sync_top_inst; print(sync_top_inst(days_back=30))"
   ```
4. **验证**：跑 §决策 6 三条 SQL 全部非空 + `\d top_inst` 确认 8 业务列 + id PK + idx_top_inst_code_date 索引存在。
5. **不得改动**：白名单外任何文件（`etl.py` / `advanced_factors.py` / `screening_scorers.py` / `modes.py` / 其他 alembic / pg_adapter / scheduler）。

SIT 验证清单（dev 自跑后落 `progress/backend-dev.md` SIT 证据段）：

- [ ] `alembic upgrade head` 幂等：连跑 2 次第二次 0 改动
- [ ] `alembic downgrade -1 && alembic upgrade head` 双向迁移无错
- [ ] TRUNCATE + sync 后 `SELECT COUNT(*) FROM top_inst WHERE net_buy IS NOT NULL` > 5000
- [ ] `SELECT COUNT(*) FROM top_inst WHERE exalter LIKE '%机构专用%'` > 1000（验证匿名席位完整保留）
- [ ] 跑一次 `advanced_factors.get_tushare_scores('000001')` 确认 `tushare_top_inst.score` 不再恒为 5.0（脱离 fallback）
- [ ] 全仓 grep `inst_name|buy_amount|sell_amount` 限定 PG 上下文，确认无消费者残留（应仅在本 ADR 文档 + downgrade 段出现）
