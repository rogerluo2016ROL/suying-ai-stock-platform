# ADR-009: pledge_detail / rt_sw_k / top_list schema 对齐（批量 3 表）

- 状态：Proposed
- 日期：2026-06-22
- 决策者：tech-lead
- 影响范围：services/sql/init_postgres.sql + packages/kronos-data/kronos_data/etl.py（3 个 sync 函数）+ backend/alembic/versions/008 + 下游因子消费方
- 编号说明：ADR-007 = secrets-audit、ADR-008 = sw_daily（已 Accepted，commit 48c8b6a），本决策顺延 ADR-009

## 上下文

ADR-008（sw_daily）试水成功，验证了 "改表加列对齐 sync + TRUNCATE 重拉" 的模式可行。本 ADR 把同模式批量推到另外 3 张存在 **schema ⊊ sync cols 脱节 + 命名映射断裂** 双重问题的表。与 sw_daily 的关键差异：sw_daily 的 sync cols 已与表对齐（零 etl 改动），这 3 表不是——sync 函数的 cols 与 row tuple 要改，否则即便加列也对不上。

三表的共同病根是 `etl._insert_rows`（`etl.py:167-208`）的"静默吞列"止血逻辑：查 information_schema 拿实际列名，丢弃表中不存在的列，WARN 不报错。结果是表面同步成功、实则大量字段黑洞，下游因子长期读到 NULL/空集后 fallback 到中性分。具体：

### pledge_detail（股权质押明细，最严重）

- **表 schema**（`init_postgres.sql:275-279`，无主键、无索引）：`code, end_date, pledge_amount, pledge_ratio` —— 4 列。
- **sync cols**（`etl.py:1063`）：`code, ann_date, pledgor, pledgee, pledge_amount, pledge_total_ratio` —— 6 列。
- **交集**：仅 `code, pledge_amount`。sync 写的 `ann_date / pledgor / pledgee / pledge_total_ratio` 全被吞；表里的 `end_date / pledge_ratio` 从来没被 sync 写过，永远是 NULL。
- **下游**（`advanced_factors.py:1038,1051`）：`SELECT pledge_total_ratio FROM pledge_detail WHERE code=?` → `max(p["pledge_total_ratio"])`。该列物理不存在 → `pg_adapter` 的 `UndefinedColumn` 优雅降级返回空游标（`pg_adapter.py:120-125`）→ `ev_pledge` 为空 → 质押因子永不触发 → `tushare_events` 分项里的质押扣分永远跳过。
- **双重错位**：不是单纯"加列"，而是表的列名集合（`end_date/pledge_ratio`）与 sync+下游期望的列名集合（`ann_date/pledge_total_ratio`）几乎不重叠。表定义和实际使用两端各自跑偏。

### rt_sw_k（申万实时行情快照）

- **表 schema**（`init_postgres.sql:412-417`，PK `(code, trade_date)`）：`code, trade_date, open, high, low, close` —— 6 列。
- **sync cols**（`etl.py:1316-1317`）：`trade_time, ts_code, name, close, pre_close, open, high, low, vol, amount, pct_change` —— 11 列。
- **交集**：仅 `open, high, low, close`。sync 写的 `trade_time / ts_code / name / pre_close / vol / amount / pct_change` 全被吞。
- **命名断裂**：sync 用 `ts_code`（未 split，如 "801010.SI"）作为 code 列、用 `trade_time`（datetime 字符串）作为 date 列；表 PK 期望的 `code` 是裸码（"801010"）、`trade_date` 是 DATE。即便不缺列，`ts_code`→`code` 也对不上 PK，且 `trade_time` 的 datetime 写不进 DATE 列会抛异常。
- **下游**（`screening_scorers.py:1414-1422`）：`SELECT close, pre_close FROM rt_sw_k WHERE ts_code=?` → 算 `(close/pre_close-1)*100`。`pre_close` 列不存在 → 同样 UndefinedColumn 优雅降级 → 实时行业动量（P4 因子）永不触发。
- **额外坑**：sync 默认 `days_back=1`（实时快照，无历史），下游用 `ORDER BY trade_date DESC LIMIT 1` 取最新；rt_sw_k 表本质是"最新快照覆盖写"，但 sync 用 `_insert_rows` 的 `ON CONFLICT DO NOTHING`（`etl.py:189`），同 code 同 trade_date 第二次写会冲突跳过——日内多次拉取无法更新，只能存首次快照。

### top_list（龙虎榜明细）

- **表 schema**（`init_postgres.sql:148-154`，PK `(code, trade_date)`）：`code, trade_date, reason, buy_amount, sell_amount, net_amount` —— 6 列。
- **sync cols**（`etl.py:341-342`）：`code, trade_date, name, close, pct_change, turnover_rate, amount, l_sell, l_buy, net_amount, reason` —— 11 列。
- **交集**：`code, trade_date, reason, net_amount`。sync 写的 `name / close / pct_change / turnover_rate / amount` 被吞；`l_sell / l_buy` 与表的 `sell_amount / buy_amount` 命名对不上，也全被吞。
- **下游**：
  - `advanced_factors.py:885,936,940,942`：`SELECT * FROM top_list ...` 读 `net_amount`（存在，OK）、理论上也能读 `buy_amount/sell_amount`（存在但从未被 sync 写入，恒 NULL）。
  - `diagnosis_engine.py:326`：`SELECT net_amount AS net_buy FROM top_list` —— net_amount 存在，OK。
- **top_list 是 3 表中"下游主路径仍能跑"的唯一一表**：因为 `net_amount` 在交集里，龙虎榜净买入因子（`tushare_top_list`）实际能算分。缺的是 `buy_amount/sell_amount/name/close` 等扩展字段，下游目前没强依赖，但 sync 拉了不存是浪费 + 未来扩展受阻。

不做此决策的后果：pledge_detail 质押因子和 rt_sw_k 实时行业动量因子永久失效（同 sw_daily 的 pe 因子）；top_list 表面可用但数据残缺；`_insert_rows` 静默吞列的反模式继续在 30+ 个 sync 函数里埋雷。

## 决策

### 决策 0：文件改动白名单（对 backend-dev 的硬约束）

⚠️ **本 ADR 明确列出允许修改的文件清单。backend-dev 不得修改清单外的任何文件，包括但不限于其他 alembic migration、其他表 DDL、下游因子代码。越界改动 = 违约，PL 直接回退。**（吸取 ADR-008 试水中 backend-dev 越界改 006 迁移的教训。）

| # | 文件 | 允许改动 |
|---|---|---|
| 1 | `backend/alembic/versions/008_pledge_rtsw_toplist_align.py` | **新建**（revision=008, down_revision=007） |
| 2 | `services/sql/init_postgres.sql` | 仅 pledge_detail（L275-279）、rt_sw_k（L412-417）、top_list（L148-154）三处 CREATE TABLE；**不得动其他表** |
| 3 | `packages/kronos-data/kronos_data/etl.py` | 仅 `sync_pledge_detail`（L1053-1077）、`sync_rt_sw_k`（L1306-1339）、`sync_top_list`（L331-360+）三个函数的 cols 列表与 row tuple；**不得动 `_insert_rows`、不得动其他 sync 函数** |
| 4 | 下游因子代码（`packages/kronos-factors/`） | **零改动**（pg_adapter 透明翻译；见各表决策） |

**不在白名单内的常见误改项**（明确禁止）：`backend/alembic/versions/006_*`、`007_*`；`pg_adapter.py` 的 `_COLUMN_MAP`/`_KEY_MAP`；`advanced_factors.py`、`screening_scorers.py`、`diagnosis_engine.py`；`scheduler.py`。

---

### 决策 1：pledge_detail — 表对齐 sync+下游列名（加 4 列 + 重命名 2 列语义）

**目标列集**（对齐 sync cols + 下游读法）：`code, ann_date, pledgor, pledgee, pledge_amount, pledge_total_ratio`。

| 列 | 动作 | 类型 | Tushare 语义 | 备注 |
|---|---|---|---|---|
| `code` | 保留 | TEXT NOT NULL | 股票代码 | 不变 |
| `ann_date` | **新增** | DATE | 公告日期 | sync 已写 `ann_date`（`etl.py:1071`），下游无读但为事件时间锚；类型 DATE 接收 sync 的 "YYYYMMDD"→需 sync 侧格式化（见决策 4） |
| `pledgor` | **新增** | TEXT | 出质人 | sync 已写 |
| `pledgee` | **新增** | TEXT | 质权人 | sync 已写 |
| `pledge_amount` | 保留 | DOUBLE PRECISION | 质押数量（万股） | 不变 |
| `pledge_total_ratio` | **新增** | DOUBLE PRECISION | 质押比例（%） | **下游 `advanced_factors.py:1038,1051` 读的就是这个列名**；Tushare 原始字段名也是 `pledge_total_ratio` |
| ~~`end_date`~~ | **删除** | — | — | 表原有但 sync 从未写、下游从不读；保留只会让"两套日期列"混淆 |
| ~~`pledge_ratio`~~ | **删除** | — | — | 同上，被 `pledge_total_ratio` 取代 |

**主键决策**：**新增 PK `(code, ann_date)`**。
- 现状无 PK 无索引，`_insert_rows` 用 `ON CONFLICT DO NOTHING`（`etl.py:189`）在无 PK/无 UNIQUE 约束时等价于普通 INSERT，每次 sync 都会累积重复行。
- Tushare `pledge_detail` 同一 code 同一 ann_date 可能返回多条（多个 pledgor/pledgee 对），但作为因子输入只需"最新或最大质押比例"，`(code, ann_date)` PK + `ON CONFLICT DO UPDATE` 取最新即可（见决策 4 sync 改动）。
- 若担心同 code 同 ann_date 多 pledgor 丢失，备选是 `(code, ann_date, pledgor, pledgee)` 复合 PK——但因子层只用 `pledge_total_ratio` 的 max，多行 vs 单行不影响 `max()` 结果。选简单 PK。

**为什么删列而不是保留**：`end_date/pledge_ratio` 从无数据、从无下游、列名与 sync 端冲突（`end_date` vs `ann_date` 是不同日期语义）。保留是死列 + 误导。删列在 TRUNCATE+重拉前进行，无数据损失。

### 决策 2：rt_sw_k — 表对齐 sync 列名 + 命名映射（加 6 列 + sync 改 ts_code/trade_time 映射）

**目标列集**：`code, trade_date, name, close, pre_close, open, high, low, vol, amount, pct_change`。

| 列 | 动作 | 类型 | Tushare 语义 | 备注 |
|---|---|---|---|---|
| `code` | 保留（PK 一部分） | TEXT NOT NULL | 行业代码（裸码） | sync 必须 split 出裸码（见决策 4） |
| `trade_date` | 保留（PK 一部分） | DATE NOT NULL | 交易日期 | sync 从 `trade_time` 抽日期部分（见决策 4） |
| `open/high/low/close` | 保留 | DOUBLE PRECISION | OHLC 点位 | 不变 |
| `name` | **新增** | TEXT | 指数名称 | 下游 `screening_scorers:1415` 用 `ts_code=?` 精确查（pg_adapter 译 `ts_code→code`），name 非必需但 Tushare 同接口返回，零成本存 |
| `pre_close` | **新增** | DOUBLE PRECISION | 昨收点位 | **下游 `screening_scorers:1418` 读 `pre_close` 算涨幅**，核心缺列 |
| `vol` | **新增** | DOUBLE PRECISION | 成交量（万股） | 单位同 sw_daily（ADR-008 §决策1） |
| `amount` | **新增** | DOUBLE PRECISION | 成交额（万元） | 同上 |
| `pct_change` | **新增** | DOUBLE PRECISION | 涨跌幅（%） | 命名沿用 sw_daily 约定——但注意 rt_sw_k 下游用 `pre_close` 手算涨幅而非直接读 `pct_change`，存 `pct_change` 是冗余保险 + 未来扩展 |

**主键决策**：**保留 `(code, trade_date)` 不变**。理由同 ADR-008 决策2——同 code 同 date 只有一个快照。

**下游 `WHERE ts_code=?` 的透明翻译**：`screening_scorers:1415` 的 SQL 用 `ts_code`，`pg_adapter._COLUMN_MAP`（`pg_adapter.py:70-74`）已把 `ts_code→code` 做 word-boundary 替换。**物理列名用 `code`，下游零改动**。这是与 sw_daily 一致的处理，已验证。

### 决策 3：top_list — 表对齐 sync 列名 + l_buy/l_sell 重命名（加 5 列 + sync 改 l_buy→buy_amount）

**目标列集**：`code, trade_date, name, close, pct_change, turnover_rate, amount, buy_amount, sell_amount, net_amount, reason`。

| 列 | 动作 | 类型 | Tushare 语义 | 备注 |
|---|---|---|---|---|
| `code` | 保留（PK） | TEXT NOT NULL | 股票代码 | 不变 |
| `trade_date` | 保留（PK） | DATE NOT NULL | 交易日期 | 不变 |
| `reason` | 保留 | TEXT | 上榜原因 | 不变 |
| `buy_amount` | 保留 | DOUBLE PRECISION | 买入额（元） | sync 端 `l_buy` 映射到此列（见决策 4） |
| `sell_amount` | 保留 | DOUBLE PRECISION | 卖出额（元） | sync 端 `l_sell` 映射到此列 |
| `net_amount` | 保留 | DOUBLE PRECISION | 净额（元） | 下游主读列，不变 |
| `name` | **新增** | TEXT | 股票名称 | Tushare 同接口返回 |
| `close` | **新增** | DOUBLE PRECISION | 收盘价 | 扩展字段 |
| `pct_change` | **新增** | DOUBLE PRECISION | 涨跌幅（%） | 物理列名 `pct_change` 而非 `change_pct`——**这是 top_list 与 sw_daily/pledge 的命名分歧点，见决策 4 注** |
| `turnover_rate` | **新增** | DOUBLE PRECISION | 换手率（%） | 扩展字段 |
| `amount` | **新增** | DOUBLE PRECISION | 成交额（千元） | 扩展字段 |

**主键决策**：**保留 `(code, trade_date)` 不变**。

**关于 `pct_change` vs `change_pct` 的命名抉择**：
- sw_daily / daily_kline 等表的涨跌幅物理列叫 `change_pct`（engine 命名）。
- top_list 表下游目前**无人读涨跌幅列**（`advanced_factors:885 SELECT *` 拿到但不用 pct_change；diagnosis 只读 net_amount）。
- sync 端 `r.get("pct_change")`（Tushare 原名）。
- 若物理列叫 `change_pct`，sync 要改写 `r.get("pct_change")` 值到 `change_pct` 列（多一步显式映射）。
- 若物理列叫 `pct_change`，与 sw_daily 的 `change_pct` 命名不一致，但 `pg_adapter` 不需要翻译（下游不读）。
- **决策：物理列叫 `pct_change`**，理由：(a) 下游无消费者，无需 pg_adapter 翻译；(b) 与 sync 的 `r.get("pct_change")` 直通，sync cols 列表直接写 `"pct_change"` 零映射；(c) top_list 是龙虎榜专用表，与行情表的命名族本就可不同。**在 ADR 里显式记录此命名分歧，未来若下游要读 top_list.pct_change 并跨表 JOIN 行情，需统一命名（另开 ADR）。**

### 决策 4：3 个 sync 函数的具体改动（逐函数列清）

#### 4a. `sync_pledge_detail`（`etl.py:1053-1077`）改动

| 改动点 | 旧 | 新 |
|---|---|---|
| cols（L1063） | `["code", "ann_date", "pledgor", "pledgee", "pledge_amount", "pledge_total_ratio"]` | **不变**（表加列后对齐） |
| row tuple（L1071-1073） | `(code, str(ann_date), pledgor, pledgee, pledge_amount, pledge_total_ratio)` | `ann_date` 需格式化为 "YYYY-MM-DD"（同 sw_daily 的 trade_date 格式化模式 `etl.py:1289-1291`）：`td[:4]+"-"+td[4:6]+"-"+td[6:8] if len(td)==8 else td` |
| `_insert_rows` 调用（L1075） | `ON CONFLICT DO NOTHING` | 加 PK 后改 `ON CONFLICT (code, ann_date) DO UPDATE SET pledge_amount=EXCLUDED.pledge_amount, pledge_total_ratio=EXCLUDED.pledge_total_ratio` —— **但** `_insert_rows` 是通用函数，不在此 ADR 改（白名单禁止）；改为在 `sync_pledge_detail` 内独立调 `db.execute` 做带 ON CONFLICT 的 upsert，绕过 `_insert_rows` |

**简化方案（推荐）**：`_insert_rows` 不改，pledge_detail 的 sync 仍用 `ON CONFLICT DO NOTHING`。加了 PK 后，同 (code, ann_date) 重复写会跳过——首次写谁的 `pledge_total_ratio` 谁就留下。因子层 `max(p["pledge_total_ratio"])`（`advanced_factors:1051`）取最大值，只要任一 pledgor 的高比例被写入即可。**选此方案**，sync 侧零逻辑改动（仅 ann_date 格式化）。

#### 4b. `sync_rt_sw_k`（`etl.py:1306-1339`）改动

| 改动点 | 旧 | 新 |
|---|---|---|
| cols（L1316-1317） | `["trade_time", "ts_code", "name", "close", "pre_close", "open", "high", "low", "vol", "amount", "pct_change"]` | `["code", "trade_date", "name", "close", "pre_close", "open", "high", "low", "vol", "amount", "pct_change"]` —— **trade_time→trade_date, ts_code→code** |
| row tuple（L1328-1334） | `(str(trade_time), str(ts_code), name, close, pre_close, open, high, low, vol, amount, pct_change)` | **code**：`tc = str(r["ts_code"]); code = tc.split(".")[0] if "." in tc else tc`（同 `etl.py:1287-1288` sw_daily 的 split 模式）<br>**trade_date**：从 `trade_time`（datetime 字符串）抽 date 部分：`str(r.get("trade_time",""))[:10]`（取 "YYYY-MM-DD" 前 10 字符；rt_sw_k 返回形如 "2026-06-22 14:55:00"）<br>其余字段不变 |

#### 4c. `sync_top_list`（`etl.py:331-360`）改动

| 改动点 | 旧 | 新 |
|---|---|---|
| cols（L341-342） | `["code", "trade_date", "name", "close", "pct_change", "turnover_rate", "amount", "l_sell", "l_buy", "net_amount", "reason"]` | `["code", "trade_date", "name", "close", "pct_change", "turnover_rate", "amount", "sell_amount", "buy_amount", "net_amount", "reason"]` —— **l_sell→sell_amount, l_buy→buy_amount** |
| row tuple（L354-360） | `...r.get("l_sell"), r.get("l_buy"), r.get("net_amount")...` | `...r.get("l_sell"), r.get("l_buy"), r.get("net_amount")...` —— **r.get 不变**（Tushare 返回的就是 l_sell/l_buy），只改 cols 列表让值落到对的列名 |

**top_list 是 3 表中 sync 改动最简单的**：只改 cols 列表里 2 个列名（l_sell→sell_amount, l_buy→buy_amount），row tuple 的 r.get 完全不动（值的来源字段名不变）。

### 决策 5：Alembic 008 迁移脚本（批量 3 表，revision=008, down_revision=007）

**落 `backend/alembic/versions/008_pledge_rtsw_toplist_align.py`**：

**upgrade()**（3 段，每表一段，顺序 pledge → rt_sw_k → top_list）：

```python
# ── pledge_detail ──
op.execute("""
    ALTER TABLE pledge_detail
        DROP COLUMN IF EXISTS end_date,
        DROP COLUMN IF EXISTS pledge_ratio,
        ADD COLUMN IF NOT EXISTS ann_date DATE,
        ADD COLUMN IF NOT EXISTS pledgor TEXT,
        ADD COLUMN IF NOT EXISTS pledgee TEXT,
        ADD COLUMN IF NOT EXISTS pledge_total_ratio DOUBLE PRECISION
""")
op.execute("""
    ALTER TABLE pledge_detail
        ADD CONSTRAINT pledge_detail_pkey PRIMARY KEY (code, ann_date)
""")

# ── rt_sw_k ──
op.execute("""
    ALTER TABLE rt_sw_k
        ADD COLUMN IF NOT EXISTS name TEXT,
        ADD COLUMN IF NOT EXISTS pre_close DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS vol DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS pct_change DOUBLE PRECISION
""")

# ── top_list ──
op.execute("""
    ALTER TABLE top_list
        ADD COLUMN IF NOT EXISTS name TEXT,
        ADD COLUMN IF NOT EXISTS close DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS pct_change DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS turnover_rate DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION
""")
```

**downgrade()**（逆序，反操作）：

```python
# top_list
op.execute("""ALTER TABLE top_list
    DROP COLUMN IF EXISTS name, DROP COLUMN IF EXISTS close,
    DROP COLUMN IF EXISTS pct_change, DROP COLUMN IF EXISTS turnover_rate,
    DROP COLUMN IF EXISTS amount""")
# rt_sw_k
op.execute("""ALTER TABLE rt_sw_k
    DROP COLUMN IF EXISTS name, DROP COLUMN IF EXISTS pre_close,
    DROP COLUMN IF EXISTS vol, DROP COLUMN IF EXISTS amount,
    DROP COLUMN IF EXISTS pct_change""")
# pledge_detail: 先删 PK 再删列、恢复旧列
op.execute("ALTER TABLE pledge_detail DROP CONSTRAINT IF EXISTS pledge_detail_pkey")
op.execute("""ALTER TABLE pledge_detail
    DROP COLUMN IF EXISTS ann_date, DROP COLUMN IF EXISTS pledgor,
    DROP COLUMN IF EXISTS pledgee, DROP COLUMN IF EXISTS pledge_total_ratio,
    ADD COLUMN IF NOT EXISTS end_date DATE,
    ADD COLUMN IF NOT EXISTS pledge_ratio DOUBLE PRECISION""")
```

**幂等性**：全用 `IF NOT EXISTS` / `IF EXISTS`。**禁止用 `op.add_column`（非幂等，ADR-008 教训）**，全用 `op.execute("ALTER ... ADD COLUMN IF NOT EXISTS ...")` 原生 SQL。

**pledge_detail PK 加法**：单独一段 `ADD CONSTRAINT ... PRIMARY KEY`，且**必须在 TRUNCATE 之后、回补之前**执行——若表里有重复 (code, ann_date) 行，加 PK 会失败。TRUNCATE 在决策 6 的回补步骤里做，顺序为：迁移（含加 PK）→ 此时表已空（TRUNCATE 是回补第一步）→ 回补写入。**实际执行顺序：alembic upgrade head（加列+加 PK，此时旧数据若重复会阻塞加 PK）→ 若失败先手动 TRUNCATE 再 upgrade → 回补**。

### 决策 6：TRUNCATE + 各自 sync 回补（days_back）

| 表 | TRUNCATE | 回补命令 | days_back | API 配额 |
|---|---|---|---|---|
| `pledge_detail` | `TRUNCATE pledge_detail;` | `sync_pledge_detail(days_back=30)` | 30（默认） | 500 次 API（500 股票 × 1 次/股），约 1-2 分钟 |
| `rt_sw_k` | `TRUNCATE rt_sw_k;` | `sync_rt_sw_k(days_back=1)` | 1（实时快照无历史） | 1 次 API（单次返回全行业快照），<5 秒 |
| `top_list` | `TRUNCATE top_list;` | `sync_top_list(days_back=30)` | 30（默认） | 30 次 API（30 交易日 × 1 次/日），约 30 秒 |

**回补脚本**（运维执行，不进 scheduler cron）：

```sql
TRUNCATE pledge_detail;
TRUNCATE rt_sw_k;
TRUNCATE top_list;
```
```python
from kronos_data.etl import sync_pledge_detail, sync_rt_sw_k, sync_top_list
sync_pledge_detail(days_back=30)
sync_rt_sw_k(days_back=1)
sync_top_list(days_back=30)
```

**为什么 pledge_detail 只拉 30 天**：Tushare `pledge_detail` 是事件型数据（每次质押公告一条），30 天覆盖近期事件足够因子判断；拉全历史（years）API 调用量大且老事件对当前评分意义递减。若需更长历史另开 task。

**为什么 rt_sw_k 只拉 1 天**：`rt_sw_k` 是实时快照接口，无历史回溯能力（Tushare 官方：只返回当前截面）。days_back=1 拉当日最新快照即可。

**前置验证**（同 ADR-008）：
1. `TUSHARE_TOKEN` 账号积分：`pledge_detail` / `top_list` 需 2000 积分（基础权限）；`rt_sw_k` 需单独申请权限（[Tushare 文档](https://tushare.pro/document/1?doc_id=108)："申万实时行情 ... 独立权限"）。
2. `KRONOS_PG_URL` 指向正确库。
3. 回补后验证：
   - `SELECT COUNT(*) FROM pledge_detail WHERE pledge_total_ratio IS NOT NULL` > 0
   - `SELECT COUNT(*) FROM rt_sw_k WHERE pre_close IS NOT NULL` ≈ 440（申万行业数）
   - `SELECT COUNT(*) FROM top_list WHERE name IS NOT NULL` > 0

### 决策 7：下游影响评估

| 因子 | 位置 | 现状 | 迁移+回补后 |
|---|---|---|---|
| `tushare_events`（质押扣分） | `advanced_factors.py:1038,1051` | pledge_total_ratio 列不存在 → UndefinedColumn 优雅降级 → 空集 → 跳过质押扣分 | 质押比例 >50% 扣 3 分、>30% 扣 1.5 分生效 |
| P4 实时行业动量 | `screening_scorers.py:1414-1422` | pre_close 列不存在 → UndefinedColumn 优雅降级 → 跳过 | 实时行业涨幅 >2% 加 1.5 分、<-2% 扣 1 分生效 |
| `tushare_top_list`（龙虎榜净买） | `advanced_factors.py:885,936-942` | net_amount 存在，因子已生效（唯一已跑通的） | 无行为变化（net_amount 本就在交集）；buy_amount/sell_amount 从此有值，未来可细化买卖力量分析 |
| 龙虎榜净买入（diagnosis） | `diagnosis_engine.py:326` | net_amount 存在，已生效 | 无行为变化 |

**回归风险**：
- pledge_detail 加 PK 后首次回补可能因 (code, ann_date) 冲突丢失同 code 同日多条 pledgor 记录——因子层取 `max(pledge_total_ratio)` 不受影响（见决策 4a 简化方案）。
- rt_sw_k 的 `trade_time` 截取前 10 字符为 trade_date，若 Tushare 返回格式非 "YYYY-MM-DD ..." 会写入 NULL trade_date 触发 PK NOT NULL 约束失败——sync 侧需 fallback（见决策 4b）。
- 下游因子分数会从"稳定中性"变为"基于真实数据波动"，属预期修复。回补后跑一次 screener 全量评分抽样对比（同 ADR-008）。

**下游零代码改动**：所有下游因子经 `pg_adapter._COLUMN_MAP`（`ts_code→code`）透明翻译，新物理列名（`pledge_total_ratio / pre_close / pct_change / name`）与下游 SQL 中的字段面字一致，无需改下游代码。

## 备选方案

- **A. 改 etl 反向只写表现有列（反向对齐）** — pros: 表不动；cons: pledge_detail 永久放弃 `pledge_total_ratio`（下游唯一读的字段）、rt_sw_k 永久放弃 `pre_close`（下游唯一读的字段）→ 两个因子彻底判死刑。**否决理由**：与 sw_daily ADR-008 备选 A 同理，业务不可接受。

- **B. 新建 v2 表双写灰度切流** — pros: 零停机可回滚；cons: 3 表都日级 ETL，TRUNCATE 窗口 < 2 分钟，双表复杂度收益比不成立；且 pg_adapter 要加表名映射。**否决理由**：ADR-008 已证 TRUNCATE+重拉模式可行且低风险，无理由对 3 张更简单的表引入双表复杂度。

- **C. 不删 pledge_detail 的 end_date/pledge_ratio，保留死列** — pros: downgrade 更简单；cons: 死列永远 NULL + 与 ann_date/pledge_total_ratio 列名冲突混淆（"到底看 end_date 还是 ann_date"）。**否决理由**：单一来源原则——表的列集应与 sync+下游的实际使用一致，死列是噪音。

- **D. rt_sw_k 物理列保留 ts_code/trade_time 原名，下游不用 pg_adapter 翻译** — pros: sync 零改动；cons: 破坏 "engine 命名 code/trade_date" 的项目约定（CLAUDE.md），且 rt_sw_k 是唯一例外会带坏后续表；pg_adapter 的 `ts_code→code` 翻译对 sw_daily/daily_kline 已生效，rt_sw_k 跟随零成本。**否决理由**：破坏命名一致性，且 sync 改动极小（2 行）。

- **E. pledge_detail PK 用 (code, ann_date, pledgor, pledgee) 四列复合** — pros: 不丢同日多条；cons: 因子层只用 `max(pledge_total_ratio)`，多行 vs 单行 max 结果同；复合 PK 更重。**否决理由**：YAGNI。

## 影响

### 对现有代码（按白名单）
- `services/sql/init_postgres.sql`：3 处 CREATE TABLE 改写（pledge_detail L275-279 / rt_sw_k L412-417 / top_list L148-154）。
- `backend/alembic/versions/008_pledge_rtsw_toplist_align.py`：新建。
- `packages/kronos-data/kronos_data/etl.py`：3 个 sync 函数局部改动（cols 列表 + 部分 row tuple），见决策 4。
- 下游因子：**零改动**。

### 对成本
- **API**：pledge_detail 500 次 + rt_sw_k 1 次 + top_list 30 次 = 531 次一次性，无增量月成本。
- **存储**：每表新增 5-6 列 × 8 bytes × 万级行 ≈ 各 < 5MB，可忽略。
- **人力**：迁移脚本 + init SQL + sync 改动 ~1d，回补验证 ~0.5d（3 表比 sw_daily 多但每表更简单）。

### 对运维
- 新增监控：3 表各加一条"回补后非空验证"查询（见决策 6 前置验证）。
- `scheduler.py` 的 gap_threshold（pledge_detail=3, rt_sw_k=1, top_list=2，`scheduler.py:86,75,65` 附近）保持不变。

### 风险
1. **pledge_detail 加 PK 时表里有重复 (code, ann_date)** → ADD CONSTRAINT 失败。**缓解**：upgrade 前先 `TRUNCATE pledge_detail`，或在 upgrade 脚本里加 PK 前先 DELETE 重复行（保留 pledge_total_ratio 最大的一条）。**推荐运维顺序**：先 TRUNCATE 再 upgrade 再回补。
2. **rt_sw_k 的 trade_time 格式不稳定** → 截取失败。**缓解**：sync 侧 `str(r.get("trade_time",""))[:10]` + 异常时记 WARN 跳过该行。
3. **Tushare rt_sw_k 独立权限未开通** → 返回空。**缓解**：运维执行前先跑探针 `pro.rt_sw_k()` 确认非空。

## 本 ADR 不覆盖的决策

- **`_insert_rows` 通用函数的重构**（把 `ON CONFLICT DO NOTHING` 参数化、支持 per-table upsert 策略）—— 见后续工作，另开 ADR。
- **其他 ETL 表的同类 schema 脱节批量修复**（hk_holdings/repurchase/share_float/cyq_chips 等若同样存在 cols ⊃ schema cols）—— 本 ADR 只覆盖 3 表；tech-lead 后续 grep 全量 `_insert_rows` 调用点另开 ADR-010 系列。
- **top_list.pct_change 与 sw_daily.change_pct 的跨表命名统一**——若未来下游要 JOIN 两个表的涨跌幅，需统一命名，另开 ADR。
- **pledge_detail 历史回补超 30 天**（拉 years 级全历史）——当前因子只需近 30 天，扩展另开 task。
- **rt_sw_k 日内多次快照覆盖写**（`ON CONFLICT DO UPDATE` 替代 `DO NOTHING`）——需改 `_insert_rows` 通用逻辑，不在本 ADR 白名单。

## 后续工作

- [ ] **backend-dev**：按白名单（决策 0）改 3 个文件——(1) 新建 `backend/alembic/versions/008_pledge_rtsw_toplist_align.py`（决策 5）；(2) `services/sql/init_postgres.sql` 改 3 处 CREATE TABLE（决策 1/2/3 的目标列集）；(3) `etl.py` 改 3 个 sync 函数（决策 4）。**不得越界改白名单外文件。**
- [ ] **backend-dev / devops**：盘后执行——先 `TRUNCATE pledge_detail, rt_sw_k, top_list`（3 表）→ `alembic upgrade head`（升级到 008，含 pledge PK）→ 跑 3 个 sync 回补（决策 6）→ 验证 3 条非空查询。
- [ ] **tech-lead**：回补后审查 `advanced_factors` 的 `tushare_events`（质押扣分）和 `screening_scorers` 的 P4（实时行业动量）抽样输出，确认因子从 fallback 切换到真实数据。
- [ ] **tech-lead**：grep 全量 `_insert_rows` 调用点（`etl.py` 中 30+ 处），识别其他 cols ⊃ schema cols 的静默吞列表，立 ADR-010 批量修复或逐表处理。

## 版本与查证

**查证基线日期**：2026-06-22

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| PostgreSQL | 15.18 (docker `postgres:15-alpine`) | 17.x | 2 个 major | Active，PG 15 支持至 2027-11 | [PostgreSQL Versioning](https://www.postgresql.org/support/versioning/) — 与 ADR-008 一致；`ADD CONSTRAINT ... PRIMARY KEY` + `DROP COLUMN IF EXISTS` 均 PG 15 原生支持 |
| Alembic | 1.18.4 | 1.18.4 | 0 | Active | `pip show alembic` 实测；与 ADR-008 同基线 |
| psycopg2 | 2.9.12 | 2.9.x | 0 | Active | `pip show psycopg2` 实测；与 ADR-008 同基线 |
| Tushare | 1.4.29 | 1.4.x | 0 | Active | `pip show tushare` 实测；`pro.pledge_detail / pro.rt_sw_k / pro.top_list` 接口签名稳定 |
| Tushare pledge_detail 接口 | 2000 积分 | — | — | Stable | [Tushare 权限文档](https://tushare.pro/document/1?doc_id=108) — 字段：ts_code/ann_date/pledgor/pledgee/pledge_amount/pledge_total_ratio |
| Tushare rt_sw_k 接口 | 独立权限申请 | — | — | Stable | [Tushare rt_sw_k 文档](https://tushare.pro/wctapi/documents/417.md) — 申万实时行情，独立权限；字段：ts_code/name/trade_time/close/pre_close/open/high/low/vol/amount/pct_change |
| Tushare top_list 接口 | 2000 积分 | — | — | Stable | [Tushare top_list 文档](https://tushare.pro/document/2?doc_id=105) — 龙虎榜每日明细；字段含 ts_code/name/close/pct_change/turnover_rate/amount/l_sell/l_buy/net_amount/reason |

**不引入新依赖**：本 ADR 纯 schema + sync 局部变更，CLAUDE.md Tech Stack 表无需新增行。

**与 CLAUDE.md "PG 与 SQLite 列名差异" 段一致性**：
- rt_sw_k：物理列 `code/trade_date`（engine 命名），下游 `ts_code→code` 经 pg_adapter 透明翻译，与 sw_daily/ADR-008 一致。
- top_list.pct_change：本 ADR 决策 3 显式记录与 sw_daily.change_pct 的命名分歧，未来跨表 JOIN 时另开 ADR 统一。
- pledge_detail：新增列（ann_date/pledgor/pledgee/pledge_total_ratio）无 SQLite/PG 命名分歧，无需扩展 pg_adapter。
