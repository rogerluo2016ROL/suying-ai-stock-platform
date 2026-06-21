# ADR-008: sw_daily 数据模型对齐方案

- 状态：Proposed
- 日期：2026-06-22
- 决策者：tech-lead
- 影响范围：services/sql/init_postgres.sql + packages/kronos-data/kronos_data/etl.py + backend/alembic/versions/ + 下游因子消费方 (packages/kronos-factors/)
- 编号说明：ADR-007 已被《Phase0 Secrets Audit》占用，本决策顺延为 ADR-008

## 上下文

`sw_daily` 表存储申万行业指数日行情，是 `advanced_factors`（行业估值因子）与 `screening_scorers`（板块动量）的核心数据源。当前数据流存在 **schema 与 ETL 代码双向脱节** 的问题：

1. **表 schema 缺列**。`services/sql/init_postgres.sql:94-100` 定义的 `sw_daily` 只有 7 列（code / trade_date / open / high / low / close / change_pct），而 `packages/kronos-data/kronos_data/etl.py:1274-1296` 的 `sync_sw_daily` 已经按 15 列写入（多出 `name / change / pe / pb / float_mv / total_mv / vol / amount` 共 8 列）。etl 代码注释里早就写了 "PG columns: ... name, ... pe, pb, float_mv ..."，但 init SQL 从未跟上。

2. **`_insert_rows` 静默吞列**。`etl.py:167-208` 的止血逻辑会查 information_schema 拿实际列名，然后丢弃表中不存在的列（`etl.py:180-183` 打 WARN 但不报错）。结果是 **每次同步表面成功、实则 8 个估值/成交字段全部丢入黑洞**。PG 表里现有 491,937 行（OHLC + change_pct 是齐的），但 `name / pe / pb / vol / amount / float_mv / total_mv / change` 全为 NULL。

3. **下游因子读不到数据**。`packages/kronos-factors/kronos_factors/scorer/advanced_factors.py:1206-1218` 的 `tushare_sector_val` 因子查 `SELECT ts_code, pe FROM sw_daily WHERE name LIKE ? ...` —— `name` 是 NULL，LIKE 匹配不到任何行业；即便匹配到，`pe` 也 NULL。整个"行业估值分位"因子长期处于 fallback（`available: False, score: 5.0`），对 50 维综合评分的实际贡献为零。同理 `screening_scorers.py:1380-1392` 的板块动量因子靠 `name LIKE` 定位行业代码也会失败。

4. **命名层透明映射已就位**。下游因子代码用的是 SQLite/engine 命名（`ts_code`、`pct_change`），`pg_adapter._COLUMN_MAP`（`pg_adapter.py:70-74`）已把 `ts_code → code`、`pct_change → change_pct` 做了 word-boundary 正则替换。**只要新加的列沿用 engine 命名约定（`code / trade_date / change_pct` 而非 Tushare 原始命名 `ts_code / pct_change`），下游零改动即可读到新列**。新增列 `name / pe / pb / vol / amount / float_mv / total_mv / change` 本身无 SQLite/PG 命名分歧，直接照搬。

不做此决策的后果：行业估值因子永久失效、板块动量因子半失效、`tushare_sector_val` 与 `tushare_sector` 两个评分项持续返回中性 5.0，50 维评分退化成 48 维；且 `_insert_rows` 的静默吞列模式不破除，未来任何 ETL 列追加都会重演此坑。

## 决策

### 决策 1：加 8 列对齐 etl 写入端，列名沿用 engine 命名

新增 8 列（全部 NULLABLE，类型对齐 Tushare 输出语义）：

| 新增列 | PG 类型 | Tushare 字段语义 | 单位 | 理由 |
|---|---|---|---|---|
| `name` | `TEXT` | 指数名称（如"农林牧渔"） | — | 下游 `name LIKE '%行业%'` 必须有值；用于按行业名匹配 |
| `change` | `DOUBLE PRECISION` | 涨跌点位（绝对值） | 点 | etl 已写 `r.get("change")`；与 `change_pct`（涨跌幅%）并存，语义不同不可混 |
| `pe` | `DOUBLE PRECISION` | 市盈率 | 倍 | `advanced_factors` 行业估值分位核心读字段 |
| `pb` | `DOUBLE PRECISION` | 市净率 | 倍 | 估值因子扩展预留（当前未读，但 Tushare 同接口同成本返回） |
| `float_mv` | `DOUBLE PRECISION` | 流通市值 | 万元 | 成交结构分析预留 |
| `total_mv` | `DOUBLE PRECISION` | 总市值 | 万元 | 成交结构分析预留 |
| `vol` | `DOUBLE PRECISION` | 成交量 | 万股 | 与 daily_kline 的 vol（手）单位约定一致：直接存 Tushare 原值，单位注释在表 DDL |
| `amount` | `DOUBLE PRECISION` | 成交额 | 万元 | 同上 |

**命名约定**（CLAUDE.md "PG 与 SQLite 列名差异" 段已确立）：
- 主键列沿用 engine 命名：`code`（非 `ts_code`）、`trade_date`、`change_pct`（非 `pct_change`）。
- 新增 8 列 Tushare 原始命名（`name / change / pe / pb / float_mv / total_mv / vol / amount`）与 engine 命名无分歧，直接采用 Tushare 名。
- **禁用** `ts_code` / `pct_change` 作为物理列名——那会让 `pg_adapter._COLUMN_MAP` 反向翻译产生歧义。

**单位约定**：Tushare `sw_daily` 的 `vol`/`amount`/`float_mv`/`total_mv` 单位是"万股 / 万元 / 万元 / 万元"（Tushare 官方文档原文："成交量（万股）/ 成交额（万元）/ 流通市值（万元）/ 总市值（万元）"）。DDL 注释里写明单位，因子代码如需换算到"股/元"自行 ×10000，**不在 sync 层做单位转换**（与 ADR-006 §决策2"直写不做额外加工"原则一致）。

### 决策 2：主键不变 — 维持 (code, trade_date)

**现状**：`sw_daily_pkey` 是 `btree(code, trade_date)`，另有 `idx_sw_daily_date` on `trade_date`。

**决策**：加列后主键不变。理由：
- `name / pe / pb` 等都是某 `(code, trade_date)` 的属性，不存在"同 code 同 date 多版本"的需求。
- 加列对 (code, trade_date) 的唯一性约束零影响。
- `idx_sw_daily_date` 保留（下游按 `trade_date` 范围扫 20 日窗口依赖它）。

**不新增索引**：`advanced_factors` 按 `name LIKE` 查（无法用 B-tree 索引，且行业数 < 500，全表扫可接受）；按 `trade_date` 查已有索引覆盖。等下游出现明确的 `WHERE name = ?`（精确等值）查询再加 `idx_sw_daily_name`——YAGNI。

### 决策 3：sync_sw_daily 零代码改动，靠表加列承接

`etl.py:1274-1296` 的 cols 列表与 row tuple **已按 15 列正确顺序写好**（注释 `# PG columns: code, trade_date, name, ...` 也写对了），**唯一缺的是表结构**。表加列后：
- `_insert_rows` 的 `_get_pg_columns` 会返回 15 列，`valid_cols` 不再丢列，WARN 消失。
- 8 个新列从下一次 sync 开始自动落盘。
- **零 etl 代码改动 = 零回归风险**。这是本方案优于备选 A（改 etl）的关键。

**字段映射确认**（查 Tushare 官方文档 [sw_daily](https://tushare.pro/wctapi/documents/327.md) 原文）：

| Tushare 字段 | etl `r.get(...)` | 物理列 | 备注 |
|---|---|---|---|
| `ts_code` | `ts_code` → split(".") → `code` | `code` | etl:1287-1288 已正确处理 |
| `trade_date` | `trade_date` → "YYYY-MM-DD" | `trade_date` | etl:1289-1291 已正确格式化 |
| `name` | `name` | `name` | **新列** |
| `open/high/low/close` | 同名 | 同名 | 已存在 |
| `change` | `change` | `change` | **新列**，涨跌点位（与 change_pct 不同） |
| `pct_change` | `pct_change` | `change_pct` | etl:1293 `r.get("pct_change")` 写入 `change_pct` 列，**映射正确** |
| `pe/pb/float_mv/total_mv/vol/amount` | 同名 | 同名 | **新列** |

### 决策 4：Alembic 迁移脚本 — ADD COLUMN + TRUNCATE 回补

落 `backend/alembic/versions/007_sw_daily_add_columns.py`（revision=`007`, down_revision=`006`）：

**upgrade()**：
1. `ALTER TABLE sw_daily ADD COLUMN IF NOT EXISTS name TEXT, change DOUBLE PRECISION, pe DOUBLE PRECISION, pb DOUBLE PRECISION, float_mv DOUBLE PRECISION, total_mv DOUBLE PRECISION, vol DOUBLE PRECISION, amount DOUBLE PRECISION`（单条 ALTER，PG 15 支持）。
2. 不在迁移内做数据回填（见决策 5）——回补由 `sync_sw_daily` 独立步骤承担，迁移只改结构。

**downgrade()**：`ALTER TABLE sw_daily DROP COLUMN IF EXISTS name, change, pe, pb, float_mv, total_mv, vol, amount`。

**幂等性**：全用 `IF NOT EXISTS` / `IF EXISTS`，支持重复执行（与 `005_extend_legacy_tables.py` 风格一致）。

### 决策 5：TRUNCATE + 全量重拉 3650 天（10 年）

**回补策略**：迁移 upgrade 完成后，**不在 alembic 内**（迁移不应有外部 API 依赖），由 data-service 运维侧执行一次性脚本：

```sql
TRUNCATE TABLE sw_daily;
```
然后调 `sync_sw_daily(days_back=3650)`（即 etl 默认值，10 年历史）。

**为什么 TRUNCATE 而非增量补**：
- 现有 491,937 行的 8 个新列全 NULL，逐行 UPDATE 比全表重写慢。
- Tushare `sw_daily` 单次最大 4000 行、可按日期循环，3650 天 / 30 天一批 = 122 批，约 122 次 API 调用。
- 申万行业共约 440 个代码 × 10 年约 2440 交易日 ≈ 107 万行预估，落在 PG 15 可承受范围（单表 < 10M 行无需分区）。

**配额评估**：
- `sw_daily` 需 **5000 积分**（[Tushare 权限文档](https://tushare.pro/document/1?doc_id=108) 原文："申万行业指数日行情 ... 5000积分可调取"）。当前 `TUSHARE_TOKEN` 配置需确认账号已达 5000 积分门槛；未达则 sw_daily 会返回空 df，etl 静默 continue（`etl.py:1282-1283`），表现为 0 写入。
- 5000 积分频次：500 次/分钟/API（[Tushare 频次表](https://tushare.pro/document/1?doc_id=290)）。etl `_rate_limit()` 当前控频 400 次/分钟（ADR-006 §决策2），122 批全量重拉理论耗时约 18 秒（122 / 400 × 60），实际受网络 RTT 影响约 3-5 分钟。配额消耗：122 次 API 调用，单次 < 4000 行，无超额风险。

**前置验证**（运维执行前必须确认）：
1. `TUSHARE_TOKEN` 账号 ≥ 5000 积分。
2. PG 连接 `KRONOS_PG_URL` 指向正确库（否则 sync 写到 SQLite fallback，表依旧空）。
3. `docker exec docker-postgres-1 psql -U kronos -d kronos -c "SELECT COUNT(*) FROM sw_daily WHERE pe IS NOT NULL"` 验证回补后非零。

### 决策 6：下游因子行为变化评估

| 因子 | 位置 | 现状（pe/name 为 NULL） | 迁移+回补后 |
|---|---|---|---|
| `tushare_sector_val` | `advanced_factors.py:1206-1218` | 永久 fallback（score=5.0, available=False） | 行业估值分位生效，影响综合评分 ±2.0 分档 |
| `tushare_sector` | `advanced_factors.py:1143-1165` | 动量按 `name LIKE` 匹配行业失败 → 取全行业均值 | 精确匹配个股行业，动量信号准确化 |
| `sw_sector_momentum` | `screening_scorers.py:1380-1392` | `name LIKE` 查不到 ts_code → 返回 5.0 | 板块 5/10/20 日动量生效 |
| `sector_blacklist_penalty` | `leader_closing.py:716-723` / `leader_intraday.py:819` | sw_daily name NULL → 回退 ths_daily（已可能为空） | sw_daily 兜底链路真正可用 |

**回归风险**：因子分数会从"稳定中性 5.0"变为"基于真实估值/动量波动"。这是 **预期行为修复**，不是回归——但需在回补后跑一次 `screener-service` 全量评分抽样对比，确认没有极端异常（如某行业 pe=10000 导致分位失真）。该抽样验证列为后续工作。

**下游零代码改动**：所有下游因子代码经 `pg_adapter._COLUMN_MAP` 透明翻译，新列 `name/pe` 物理列名与下游 SQL 中的 `name/pe` 字面一致，无需任何修改。

## 备选方案

- **A. 改 etl 端只写表现有的 7 列（反向对齐）** — pros: 表不动、迁移最小；cons: 永久放弃 `pe/pb/name` 等 8 个字段，行业估值因子彻底判死刑，与产品需求（50 维评分）冲突。**否决理由**：业务上不可接受，等于承认数据管道永远拉不全 Tushare 已提供的数据。

- **B. 新建 `sw_daily_v2` 表 + 双写 + 灰度切流** — pros: 零停机、可回滚；cons: 双写增加 etl 复杂度、下游因子要改表名、过渡期数据不一致。**否决理由**：`sw_daily` 不是高频写表（日级 ETL），TRUNCATE+重拉的停机窗口可接受（盘后执行，<5 分钟）；双表方案的复杂度收益比不成立。

- **C. 不 TRUNCATE，用 UPDATE 按 (code, trade_date) 回填 8 列** — pros: 保留现有数据不重拉；cons: 491,937 行 × 8 列 UPDATE 比 TRUNCATE+INSERT 慢 3-5 倍；且 Tushare 按 date 批量返回，UPDATE 要先建 (code,date)→row 映射，代码复杂度高。**否决理由**：性能更差、代码更复杂，无任何优势。

- **D. 不加 `pb/float_mv/total_mv/vol/amount`，只加 `name/pe/change`** — pros: 最小化加列；cons: Tushare 同一次 API 调用已返回全部字段，少存几列不省任何 API 成本，反而堵死未来成交结构分析的扩展。**否决理由**：违背"同接口同成本全量存"原则，省的是存储（每列 8 bytes × 1M 行 ≈ 8MB，可忽略），亏的是扩展性。

## 影响

### 对现有代码
- `services/sql/init_postgres.sql:94-100`：sw_daily DDL 补齐 8 列（保证新环境 init 与迁移后一致）。
- `backend/alembic/versions/007_sw_daily_add_columns.py`：新增迁移脚本。
- `packages/kronos-data/kronos_data/etl.py`：**零改动**（cols 与 row tuple 已正确）。
- `packages/kronos-factors/`：**零改动**（pg_adapter 透明翻译）。
- `services/data-service/app/scheduler.py`：`sync_sw_daily_batch` 增量同步逻辑不变；一次性回补走独立运维脚本（不进 scheduler cron）。

### 对成本
- **API 成本**：一次性全量重拉 122 次 API 调用（5000 积分账户下免费额度内），无增量月成本。
- **存储成本**：8 列 × 8 bytes × ~1M 行 ≈ 64MB 增量，PG 15 无压力。
- **人力成本**：迁移脚本 + init SQL 同步 ~0.5d，回补验证 ~0.5d。

### 对运维
- 新增监控点：`sync_sw_daily` 执行后查 `SELECT COUNT(*) FROM sw_daily WHERE pe IS NOT NULL AND trade_date = (SELECT MAX(trade_date) FROM sw_daily)`，期望 ≈ 440（申万行业代码数）。低于 400 触发告警（数据质量门）。
- `scheduler.py:65` 已有 sw_daily gap_threshold=2 的缺口检测，复用现有告警链路。

### 风险
1. **Tushare 账号积分不足 5000** → sw_daily 返回空，回补静默失败。**缓解**：运维执行前先跑 `pro.sw_daily(trade_date=<昨日>)` 探针调用，确认非空再 TRUNCATE。
2. **TRUNCATE 期间下游查到空表** → 因子短暂 fallback。**缓解**：盘后 16:30 执行（盘后无实时评分请求），窗口 < 5 分钟。
3. **pe 极端值污染分位** → 某行业 pe 异常高（如培训教育 106.12）拉爆分位。**缓解**：`advanced_factors:1210` 已有 `pe > 0` 过滤；建议下游补 `pe < 500` 上限（列为后续工作，不在本 ADR）。

## 本 ADR 不覆盖的决策

- **Tushare 账号积分升级路径**（如何从 2000 攒到 5000）—— 商务问题，非架构决策。
- **sw_daily 历史数据分区策略**（10 年后单表超 10M 行是否按年分区）—— 当前规模不需要，留待数据量触发时另开 ADR。
- **`pe < 500` 异常值过滤**（下游因子层的数据清洗规则）—— 属于因子实现细节，非 schema 决策。
- **ths_daily / index_daily 等其他 ETL 表的同类 schema 脱节修复**——本 ADR 只覆盖 sw_daily；若发现其他表同样存在 etl cols ⊃ schema cols 的静默吞列，另开 ADR-009 系列批量修复。

## 后续工作

- [ ] **backend-dev**：写 `backend/alembic/versions/007_sw_daily_add_columns.py`（revision=007, down_revision=006），upgrade/downgrade 按 §决策4。同步更新 `services/sql/init_postgres.sql:94-100` 的 sw_daily DDL。
- [ ] **backend-dev / devops**：盘后执行 `alembic upgrade head` → `TRUNCATE sw_daily` → `python -c "from kronos_data.etl import sync_sw_daily; sync_sw_daily(3650)"` → 验证 `SELECT COUNT(*) FROM sw_daily WHERE pe IS NOT NULL` ≈ 107 万。
- [ ] **tech-lead**：回补后审查 `advanced_factors.py` 的 `tushare_sector_val` 抽样输出，确认 pe 分位无极端异常；若需要补 `pe < 500` 上限，另开 task。
- [ ] **tech-lead**：grep 其他 ETL 表是否存在同类 cols ⊃ schema cols 静默吞列（etl.py 中所有 `_insert_rows` 调用点），若有则立 ADR-009 批量修复。

## 版本与查证

**查证基线日期**：2026-06-22

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| PostgreSQL | 15.18 (docker `postgres:15-alpine`) | 17.x（PG 17 GA 2024-09） | 2 个 major | Active，PG 15 支持至 2027-11 | [PostgreSQL Versioning Policy](https://www.postgresql.org/support/versioning/) — 本项目 PG 15 与 ADR-001/006 一致；ADD COLUMN IF NOT EXISTS 自 PG 9.6 起原生支持，本版本无兼容性问题 |
| Alembic | 1.18.4 | 1.18.4 | 0 | Active | `pip show alembic` 实测；与 backend/alembic 现有 6 个迁移脚本风格一致（`op.execute` + `ADD COLUMN IF NOT EXISTS`） |
| psycopg2 | 2.9.12 | 2.9.x | 0 | Active | `pip show psycopg2` 实测；`execute_values` (etl.py:192) 自 2.7 起稳定 |
| Tushare | 1.4.29 | 1.4.x | 0 | Active | `pip show tushare` 实测；`pro.sw_daily` 接口签名自 1.2.x 起稳定 |
| Tushare sw_daily 接口字段 | 5000 积分门槛 / 单次 4000 行 | — | — | Stable | [Tushare sw_daily 官方文档](https://tushare.pro/wctapi/documents/327.md) 原文："接口：sw_daily ... 限量：单次最大4000行 ... 5000积分可调取"；输出字段 15 列：ts_code/trade_date/name/open/low/high/close/change/pct_change/vol/amount/pe/pb/float_mv/total_mv，单位：vol=万股、amount=万元、float_mv=万元、total_mv=万元 |

**不引入新依赖**：本 ADR 纯 schema 变更 + 现有 etl 代码零改动，CLAUDE.md Tech Stack 表无需新增行。

**与 CLAUDE.md "PG 与 SQLite 列名差异" 段一致性**：本 ADR 新增 8 列均无 SQLite/PG 命名分歧，无需扩展 `pg_adapter._COLUMN_MAP` 或 `_KEY_MAP`；`change` 列名与 `change_pct` 共存不冲突（下游因子只读 `change_pct`，`change` 目前无下游消费方，为 Tushare 全量存储预留）。
