# ADR-010: cyq_chips schema 对齐 — 存 per-price 明细

- 状态：Accepted
- 日期：2026-06-22
- 决策者：product-lead（业务方向）+ tech-lead（技术细化签字）
- 影响范围：services/sql/init_postgres.sql + backend/alembic/versions/009_cyq_chips_align.py（新增）；packages/kronos-data/kronos_data/etl.py 与 packages/kronos-factors/ **零改动**
- 编号说明：ADR-008 sw_daily / ADR-009 pledge+rt_sw+toplist 已 Accepted；本决策顺延 ADR-010

## 上下文

`cyq_chips`（筹码分布）当前 schema 与 Tushare 实际返回**完全错位**。探针实测（2026-06-22）：`pro.cyq_chips(ts_code='000001.SZ', trade_date='20260618')` 返回字段只有 `ts_code, trade_date, price, percent`，且是 **per-price-level 明细**（每股每日约 104 个价格档位，每个档位一条）。但 PG 表 `cyq_chips` 当前建的是 `code, trade_date, avg_cost, concentration_90, profit_ratio`（聚合指标）——**Tushare 根本不返回这 3 个字段，它们是建表时凭空想象的死列**，sync 从未写入过真实值。

下游 `packages/kronos-factors/kronos_factors/scorer/advanced_factors.py:1076` 读 `SELECT price, percent FROM cyq_chips ... ORDER BY price`，但因为表物理列是聚合名，`_insert_rows` 静默吞掉 sync 的 price/percent（ADR-008 §上下文 问题 #2），下游 `UndefinedColumn` 优雅降级 → 筹码集中度因子长期 fallback 中性分。

`sync_cyq_chips`（`etl.py:1156`）的 cols 列表 `["code","trade_date","price","percent"]` 已正确对齐 Tushare，row tuple 也已对齐——**唯一缺的是表结构**。这是 6 表数据模型债中改动最轻的一表：表加列 + 改 PK 后 sync/下游零改动。

不做此决策：筹码集中度因子永久失效（同 sw_daily 的 pe 因子、pledge 的 pledge_total_ratio 因子），50 维评分继续缺一项。

## 决策

### 决策 0：文件改动白名单（对 backend-dev 的硬约束）

⚠️ **本 ADR 明确列出允许修改的文件清单。backend-dev 不得修改清单外的任何文件。越界改动 = 违约，PL 直接回退。**（沿用 ADR-009 决策 0 风格。）

| # | 文件 | 允许改动 |
|---|---|---|
| 1 | `backend/alembic/versions/009_cyq_chips_align.py` | **新建**（revision=009, down_revision=008）—— 本次 tech-lead 已起草，backend-dev 仅审阅 + 执行 |
| 2 | `services/sql/init_postgres.sql` | 仅 cyq_chips CREATE TABLE 段（L296-303）；**不得动其他表** |
| 3 | `packages/kronos-data/kronos_data/etl.py` | **零改动**（`sync_cyq_chips` L1139-1172 cols 与 row tuple 已正确） |
| 4 | 下游因子代码（`packages/kronos-factors/`） | **零改动**（`advanced_factors.py:1076` 读 `price, percent` 字面一致） |

**不在白名单内的常见误改项**（明确禁止）：`backend/alembic/versions/001-008_*`；`pg_adapter.py`；`advanced_factors.py`；`scheduler.py`；其他表 schema。

### 决策 1：存 Tushare 原始 per-price 明细，删 3 死列

**目标列集**（对齐 Tushare 返回 + 下游读法）：`code, trade_date, price, percent`。

| 列 | 动作 | 类型 | Tushare 语义 | 备注 |
|---|---|---|---|---|
| `code` | 保留（PK 一部分） | TEXT NOT NULL | 股票裸码 | sync 已 split ts_code (etl.py:1165) |
| `trade_date` | 保留（PK 一部分） | DATE NOT NULL | 交易日期 | sync 已格式化为 "YYYY-MM-DD" |
| `price` | **新增**（PK 一部分） | NUMERIC NOT NULL | 价格档位 | 同股同日多档，PK 区分维度；NUMERIC 精度对齐 Tushare 不定小数位 |
| `percent` | **新增** | NUMERIC | 该价格档持仓占比（0-100） | 下游聚合算 avg_cost = Σ(price×percent) / Σ(percent) |
| ~~`avg_cost`~~ | **删除** | — | — | Tushare 不返回；从无数据；下游不读 |
| ~~`concentration_90`~~ | **删除** | — | — | 同上 |
| ~~`profit_ratio`~~ | **删除** | — | — | 同上 |

**为什么 NUMERIC 而非 DOUBLE PRECISION**：Tushare cyq_chips 的 price 是离散档位（非连续浮点），percent 是 0-100 的占比百分比；NUMERIC 保留 Tushare 返回的精确小数（无浮点误差），下游聚合 `Σ(price×percent)` 也无累积误差。存储开销 NUMERIC（变长，约 5-8 bytes/值）对比 DOUBLE（8 bytes 定长）忽略不计。

**为什么删列而不是保留**：3 个聚合列从无数据、从无 sync 写入路径、下游不读；保留是死列噪音 + 误导（"avg_cost 怎么全 NULL？"）。删列在 TRUNCATE 后进行，无数据损失（NULL 删除等于零损失）。

### 决策 2：主键改为三列复合 (code, trade_date, price)

**现状**：`cyq_chips_pkey` 是 `btree(code, trade_date)`——与新 schema 冲突（同 code 同 date 有 ~104 行）。

**决策**：DROP 旧 PK → ADD 新 PK `(code, trade_date, price)`。

- `price` 是同股同日内的档位区分维度，三列复合唯一性自然成立。
- 下游 `advanced_factors.py:1076` 用 `WHERE code=? AND trade_date=(SELECT MAX...)` + `ORDER BY price`，三列 PK 覆盖此查询模式。
- `_insert_rows` 用 `ON CONFLICT DO NOTHING`（`etl.py:189`）；加 PK 后同股同日同档位重复写跳过，符合预期。

**不新增其他索引**：当前下游唯一查询模式 `(code, MAX(trade_date), ORDER BY price)` 已被 PK 前导列 `code` 索引覆盖。等出现 `WHERE trade_date BETWEEN ...` 跨股聚合再加 `idx_cyq_chips_date`——YAGNI。

### 决策 3：sync_cyq_chips / 下游因子零代码改动

`etl.py:1156` 的 cols `["code","trade_date","price","percent"]` 与 row tuple `(code, "YYYY-MM-DD", r.get("price"), r.get("percent"))` **已按 4 列正确顺序写好**，加列+改 PK 后：

- `_insert_rows._get_pg_columns` 返回 4 列，`valid_cols` 不再丢列。
- 4 列数据从下一次 sync 开始自动落盘。
- `advanced_factors.py:1076` `SELECT price, percent FROM cyq_chips` 字段直接命中，无需 `pg_adapter._COLUMN_MAP` 翻译（price/percent 无 SQLite/PG 命名分歧）。
- **零 etl 改动 + 零下游改动 = 零回归风险**，是 6 表债中最简单的一表。

**字段映射确认**（探针实测 2026-06-22）：

| Tushare 字段 | etl `r.get(...)` | 物理列 | 备注 |
|---|---|---|---|
| `ts_code` | `_ts_code(code)` 反向（etl 已用裸码 split） | `code` | 已正确处理 |
| `trade_date` | `d[:4]+"-"+d[4:6]+"-"+d[6:8]` | `trade_date` | etl:1165 已格式化 |
| `price` | `r.get("price")` | `price` | **新列**，Tushare 原名直通 |
| `percent` | `r.get("percent")` | `percent` | **新列**，Tushare 原名直通 |

### 决策 4：Alembic 009 迁移脚本（破坏性改 PK）

**已落 `backend/alembic/versions/009_cyq_chips_align.py`**（revision=009, down_revision=008）：

**upgrade()** 三步：
1. `DROP CONSTRAINT IF EXISTS cyq_chips_pkey`（旧 PK 不兼容新 schema）
2. 单条 ALTER：`DROP COLUMN IF EXISTS avg_cost/concentration_90/profit_ratio` + `ADD COLUMN IF NOT EXISTS price NUMERIC, percent NUMERIC`
3. `ADD CONSTRAINT cyq_chips_pkey PRIMARY KEY (code, trade_date, price)`

**downgrade()** 逆序：删新 PK → 删 price/percent + 恢复 3 死列 → 加回旧 PK。

**幂等性**：全用 `IF NOT EXISTS` / `IF EXISTS`。**禁止用 `op.add_column`/`op.drop_column`/`op.create_primary_key`**（非幂等，ADR-008 教训）。

**PK 加法必须在 TRUNCATE 之后**：旧行 PK 是 `(code, trade_date)`，新 PK 含 price 但旧行 price=NULL（DROP 旧列+ADD 新列后），违反 PK NOT NULL 约束 → 加 PK 失败。**强制执行顺序：先 TRUNCATE 再 upgrade**。

### 决策 5：TRUNCATE + sync 回补

**回补脚本**（盘后运维执行，不进 scheduler cron）：

```sql
TRUNCATE cyq_chips;
```
```python
from kronos_data.etl import sync_cyq_chips
sync_cyq_chips(days_back=5)  # 默认值; 30 天回补传 30
```

**为什么 TRUNCATE 而非增量**：旧表 3 死列全 NULL（无业务价值），DROP 列直接清零数据；改 PK 又强制要求 price 列非空——TRUNCATE 是技术必需，非可选。

**配额评估**：
- Tushare `cyq_chips` 需 **6000 积分**（`etl.py:1140` 注释；sync 函数 docstring 已记录）。
- sync 限制：top 300 股 × 5 天 × 每天最多 1 次成功（`break` 出 offset 循环）= 最多 300 次 API 调用。`_rate_limit()` 控频 400 次/分钟 → 实际耗时约 45 秒（300/400×60）。
- 数据量：~104 行/股/日 × 300 股 × 5 天 = **~15.6 万行/次 sync**（默认 days_back=5）。
- 30 天回补：~93 万行，PG 15 单表可控。

**前置验证**：
1. `TUSHARE_TOKEN` 账号积分 ≥ 6000（先跑探针 `pro.cyq_chips(ts_code='000001.SZ', trade_date='<近 5 日某交易日>')` 确认非空）
2. `KRONOS_PG_URL` 指向正确库
3. 回补后验证：
   - `SELECT COUNT(*) FROM cyq_chips WHERE price IS NOT NULL` > 100000
   - `SELECT COUNT(DISTINCT code) FROM cyq_chips` ≈ 300（top 300 股）
   - `SELECT COUNT(*) FROM cyq_chips WHERE code='000001' AND trade_date=(SELECT MAX(trade_date) FROM cyq_chips)` ≈ 104

### 决策 6：下游影响评估

| 因子 | 位置 | 现状 | 迁移+回补后 |
|---|---|---|---|
| 筹码集中度（cyq_concentration） | `advanced_factors.py:1075-1076` | `SELECT price, percent` 列不存在 → UndefinedColumn 优雅降级 → 空集 → 跳过筹码因子 | price/percent 有数据 → 集中度/平均成本/获利盘比例算分生效 |

**回归风险**：
- 下游因子分数从"稳定中性"变为"基于真实筹码数据波动"，属预期修复。回补后跑一次 screener 全量评分抽样对比（同 ADR-008/009）。
- 同 (code, trade_date) 多次 sync 调用：`ON CONFLICT DO NOTHING` + 新 PK (code, trade_date, price)，重复档位跳过，无累积错误。

**下游零代码改动**：`advanced_factors.py:1076` 的 SQL 字段名 `price, percent` 与新物理列名字面一致，`pg_adapter._COLUMN_MAP` 无需扩展。

## 备选方案

- **A. 改 sync 反向算聚合写表（avg_cost/concentration_90）** — pros: 表不动；cons: Tushare 无这些字段，sync 要自己 `Σ(price×percent)` 算 avg_cost，且下游 advanced_factors 读的是 `price/percent`（不是 `avg_cost`），改了 sync 还得改下游；算两次。**否决理由**：违背"存原始、下游加工"（ADR-006 §决策2），且 sync + 下游双改比单改表更重。

- **B. 明细 + 聚合双列都存** — pros: 下游想用哪个都行；cons: 聚合列冗余（可从明细算），双写易不一致。**否决理由**：违反单一来源原则。

- **C. 新建 `cyq_chips_detail` 表双写灰度** — pros: 零停机；cons: cyq_chips 是日级 ETL 非高频，TRUNCATE+重拉窗口 < 1 分钟；双表复杂度收益比不成立（同 ADR-008 备选 B、ADR-009 备选 B 否决理由）。**否决**。

- **D. 不删 avg_cost/concentration_90/profit_ratio，保留死列** — pros: downgrade 更简单；cons: 3 个死列永远 NULL，与 price/percent 列名混淆（"到底用聚合列还是明细列？"），未来 sync/下游误用风险。**否决理由**：单一来源原则——表的列集应与 sync+下游的实际使用一致，死列是噪音（同 ADR-009 备选 C 否决理由）。

- **E. PK 用 (code, trade_date, price, percent) 四列** — pros: 防同档位重复；cons: percent 是浮点 NUMERIC，作为 PK 易因小数精度问题影响 ON CONFLICT 匹配；同档位 percent 必然相同（Tushare 同次返回），三列已足够唯一。**否决理由**：YAGNI + 浮点 PK 反模式。

## 影响

### 对现有代码（按白名单）
- `services/sql/init_postgres.sql`：cyq_chips DDL 改写（L296-303，4 列 + 三列 PK）。
- `backend/alembic/versions/009_cyq_chips_align.py`：新建（本 ADR 已起草）。
- `packages/kronos-data/kronos_data/etl.py`：**零改动**。
- 下游因子（`packages/kronos-factors/`）：**零改动**。

### 对成本
- **API**：300 次/sync × 5 天 = 1500 次/月（基线频率），不增量；一次性回补 30 天 ≈ 9000 次（一次性）。
- **存储**：93 万行 × 4 列 × ~10 bytes ≈ 40 MB（30 天回补后），PG 15 无压力。
- **人力**：迁移 + init SQL 同步 ~0.3d（已完成 by tech-lead），回补验证 ~0.3d。

### 对运维
- 新增监控：`SELECT COUNT(*) FROM cyq_chips WHERE trade_date >= NOW() - INTERVAL '7 days'` > 50000（每周新增至少 5 万行）。
- `scheduler.py` 的 cyq_chips gap_threshold 保持现状（若有；本 ADR 不动调度逻辑）。

### 数据量评估

| 场景 | 行数估算 | 是否需分区 |
|---|---|---|
| 当前 (top 300 × 5 天) | ~15.6 万行/次 sync | 否 |
| 30 天回补 (top 300 × 30 天) | ~93 万行 | 否，PG 15 单表 < 10M 行无需分区 |
| 全市场扩展 (5000 股 × 30 天) | ~1560 万行 | 接近阈值，考虑按 trade_date 分区，另开 ADR |
| 全市场长历史 (5000 股 × 1 年 / 240 交易日) | ~1.25 亿行 | **必须分区**，另开 ADR |

**本 ADR 决策范围**：仅覆盖当前 top 300 × days_back=5 默认场景；扩展场景见"不覆盖"。

### 风险
1. **TRUNCATE 后 upgrade 之间窗口下游查空表** → 筹码因子短暂 fallback。**缓解**：盘后 16:30 执行（盘后无实时评分请求），窗口 < 1 分钟。
2. **TUSHARE_TOKEN 积分不足 6000** → sync 静默 continue（`etl.py:1163`），表为空。**缓解**：运维执行前先跑探针 `pro.cyq_chips(ts_code='000001.SZ', trade_date=<昨日>)` 确认非空。
3. **Tushare cyq_chips 接口字段变更** → sync row tuple 取值返回 None，price/percent 全 NULL，新 PK 因 price NOT NULL 写入失败。**缓解**：探针验证后再 TRUNCATE；若 Tushare 改字段名，sync 函数同步改 `r.get("...")` key，另开 ADR。

## 本 ADR 不覆盖的决策

- **cyq_chips 全市场扩展**（top 300 → 全市场 5000 股）：数据量 ~5×，需评估按 trade_date 分区，另开 ADR。
- **cyq_chips 长期历史回补**（> 30 天 / 年级）：单表 > 1000 万行强制按 trade_date 分区。
- **聚合指标的下游实现**（avg_cost / 集中度 / 获利盘比例 从明细算的具体公式）：属因子实现细节，非 schema 决策；advanced_factors.py 现有读法直接生效。
- **`_insert_rows` 通用函数重构**（ON CONFLICT 策略参数化）：见 ADR-009 §不覆盖，跨表问题不在本 ADR。
- **其他剩余表 schema 脱节**（hk_holdings/repurchase/share_float 等）：见项目记忆 `data-pipeline-write-debt.md`，另开 ADR-011+。

## 后续工作

- [ ] **backend-dev**（限额重置后 / 新会话）：按本 ADR + 已落迁移 009 + 已改 init_sql 执行——(1) review `backend/alembic/versions/009_cyq_chips_align.py`；(2) 盘后 TRUNCATE cyq_chips → `alembic upgrade head` → `sync_cyq_chips(days_back=5)` 回补 → 验证 §决策5 三条 SQL 非空；(3) **不得越界**改白名单外文件。
- [ ] **tech-lead**：回补后审查 `advanced_factors.py:1075-1100` 筹码因子抽样输出，确认从 fallback 切换到真实数据；若 percent 取值范围与预期不符（如 Tushare 返回 0-1 而非 0-100），开 task 修因子层归一化。
- [ ] **tech-lead**：cyq_chips 是 6 表债中第 4 表（前 3：sw_daily ADR-008 / pledge+rtsw+toplist ADR-009）；剩 hk_holdings/repurchase/share_float/cyq_perf 等表查证后立 ADR-011 批量修复。

## 版本与查证

**查证基线日期**：2026-06-22

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| PostgreSQL | 15.x (docker `postgres:15-alpine`) | 17.x | 2 个 major | Active，PG 15 支持至 2027-11 | [PostgreSQL Versioning Policy](https://www.postgresql.org/support/versioning/) — 与 ADR-001/006/008/009 一致；`DROP CONSTRAINT IF EXISTS` + `ADD COLUMN IF NOT EXISTS` + `ADD CONSTRAINT PRIMARY KEY` 均 PG 15 原生支持；NUMERIC 类型自 PG 6.x 起稳定 |
| Alembic | 1.18.4 | 1.18.4 | 0 | Active | `pip show alembic` 实测；与 ADR-008/009 同基线；`op.execute` + 原生 SQL 风格沿用 007/008 迁移 |
| psycopg2 | 2.9.12 | 2.9.x | 0 | Active | `pip show psycopg2` 实测；与 ADR-008/009 同基线 |
| Tushare Python SDK | 1.4.29 | 1.4.x | 0 | Active | `pip show tushare` 实测；`pro.cyq_chips` 接口签名稳定（自 1.2.x 起） |
| Tushare cyq_chips 接口 | 6000 积分门槛 | — | — | Stable | 实测探针 2026-06-22：`pro.cyq_chips(ts_code='000001.SZ', trade_date='20260618')` 返回字段 `[ts_code, trade_date, price, percent]`，~104 行/股/日；接口文档 [https://tushare.pro/document/2?doc_id=293](https://tushare.pro/document/2?doc_id=293)（JS-rendered，需登录查看完整字段表）；`etl.py:1140` 注释与 `sync_cyq_chips` docstring 均锁定 6000 pts；项目现有 token 已成功拉到数据（snapshot in `outputs/snapshots/`） |

**不引入新依赖**：本 ADR 纯 schema + PK 重建，CLAUDE.md Tech Stack 表无需新增行。

**与 CLAUDE.md "PG 与 SQLite 列名差异" 段一致性**：
- `price` / `percent` 无 SQLite/PG 命名分歧（Tushare 原名直接采用），无需扩展 `pg_adapter._COLUMN_MAP` 或 `_KEY_MAP`。
- 新 PK `(code, trade_date, price)` 中 `code` / `trade_date` 是 engine 命名（与 sw_daily/daily_kline 一致），`price` 是 Tushare 原名（无歧义）。

**与 sync_cyq_chips 现状一致性**（探针 2026-06-22）：
- `etl.py:1156` cols = `["code","trade_date","price","percent"]` ✓
- `etl.py:1165-1166` row tuple `(code, "YYYY-MM-DD", r.get("price"), r.get("percent"))` ✓
- `advanced_factors.py:1076` `SELECT price, percent FROM cyq_chips` ✓
- 三处字面一致，本 ADR 升 Accepted 后实施零代码改动。
