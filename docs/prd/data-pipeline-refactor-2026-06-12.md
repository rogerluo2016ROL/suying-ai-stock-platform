# PRD — 数据管道重构：data-service 直写 PG

- **Date**: 2026-06-12
- **Owner**: product-lead
- **Status**: Approved
- **Estimated effort tier**: Medium（7 个独立 task，涉及 data-service 核心链路 + SQL schema 改动，不涉及新服务或新依赖）
- **ADR**: [ADR-006](../adr/006-data-pipeline.md) — 6 项技术决策已由 tech-lead 落盘

## 1. Background

速赢AI平台的数据管道目前处于半重构状态，核心问题是一条脆弱的 4 跳链路：

```
Tushare API → data-service SQLite (tushare.py)  ─┐
Tushare API → Kronos SQLite (sync_all.py)        ─┤→ 同一 SQLite 文件
                                                  ─┘       │
                                          subprocess 调用 sync_to_pg.py
                                                           │
                                                     PostgreSQL ─→ 后端服务
```

**痛点**：

1. **两套代码写同一个 SQLite**：`data-service/app/sync/tushare.py`（盘后同步）和 `Kronos/tools/sync_all.py`（统一入口）功能重叠，各有自己的列名/日期格式约定，维护成本双倍
2. **subprocess 桥接脆弱**：`pg_writer.sync_daily_to_pg()` 通过硬编码路径 `subprocess.run("python3", "Kronos/tools/sync_to_pg.py")` 把 SQLite 数据搬到 PG——路径假设、超时 300s、错误透传不透明
3. **PG 双写不完整**：仅 `stk_mins`（`rt_min.py`）做了实时 PG 双写；日线/资金流/涨跌停/每日指标等核心表全部只在 SQLite，等盘后 subprocess 才能进 PG
4. **数据就绪延迟**：选股/回测/信号/预测等服务读 PG，但 PG 数据要等 `sync_all.py → sync_to_pg.py` 整个链路跑完才更新
5. **物化视图无告警**：`pg_writer.refresh_materialized_views()` 失败静默吞错
6. **stocks 基础表无同步**：股票列表没有自动化初始化和增量更新机制，PG stocks 表长期为空，物化视图 JOIN 无结果

## 2. Goal & Non-Goals

**目标**：

- 一句话：消除 `data-service → SQLite → subprocess → PG` 的脆弱中间层，让 data-service 直接写 PG，使数据在 Tushare 就绪后最快 30 秒内进 PG 并被下游服务消费
- KPI：
  - **数据延迟**：盘后核心表（daily_kline/moneyflow/stk_limit）在 Tushare 数据就绪后 120 秒内 PG 可查
  - **健壮性**：PG 写入异常不阻断 SQLite 路径，异常信息通过 scheduler status API 可查
  - **stocks 就绪**：data-service 启动后 stocks 表至少有全 A 股列表（>= 4000 行）

**Non-Goals**：

- 不删除 SQLite——Kronos 训练管线仍依赖 SQLite 读（Phase B 评估迁移）
- 不修改 Kronos/tools/sync_all.py 或 sync_to_pg.py 的业务逻辑（sync_to_pg.py 仅加 `# LEGACY` 注释）
- 不引入新的 Python 依赖（psycopg2 已在用）
- 不改变下游服务（screener/signal/backtest 等）的 PG 读取逻辑
- 不处理 Redis 缓存更新、历史数据全量回填、盘中日线增量更新、多数据源支持（后续 feature）

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 量化分析师 | 盘后 15:35 就能在选股页面看到今日数据 | 不需要等 sync_to_pg 跑完，选股决策更快 |
| US-2 | 系统运维 | 数据同步异常时能通过 API 查询到具体失败原因 | 不用登机器看 subprocess 日志就能定位问题 |
| US-3 | 后端开发者 | 股票列表自动保持最新 | 新上市的股票能被选股和模型覆盖 |
| US-4 | AI 模型工程师 | 训练/预测用的 PG 数据始终保持最新 | 模型训练不因数据延迟而等 |

## 4. Acceptance Criteria

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-1 | P0 | `POST /api/v1/data/sync/post_market?date=2026-06-12` 返回 `core` + `ext` 结果后，30 秒内 PG `daily_kline` 表对该日期 `SELECT COUNT(*)` > 0 | curl + psql |
| AC-2 | P0 | `POST /api/v1/data/sync/post_market` 中任一 PG 写入失败时，不影响 SQLite 写入成功返回，且 scheduler status API 返回该 job 的 `last_result` 包含 PG 写入失败的计数 | curl /status |
| AC-3 | P0 | 移除 scheduler.py 中 `pg_sync` 任务（原 `"cron": "36 15 * * 1-5"` 调用 `sync_daily_to_pg`），且 `GET /api/v1/data/status` 返回的 jobs 列表中不含 `pg_sync` | curl /status |
| AC-4 | P1 | `POST /api/v1/data/sync/stocks` 调用后，PG `stocks` 表至少有 4000 行股票记录 | curl + `psql -c "SELECT COUNT(*) FROM stocks"` |
| AC-5 | P1 | PG 物化视图刷新任务（`pg_refresh`）中任一 view 刷新失败时，scheduler status API 的 `last_result` 字段包含失败的 view 名称和错误原因 | 模拟 PG 不可达 + curl /status |
| AC-6 | P1 | 盘中 `rt_min`（每分钟）执行后，PG `stk_mins` 表能在 60 秒内查到最新 `trade_time`（不退化） | curl /sync/rt_min + psql |
| AC-7 | P2 | `sync_daily_to_pg` 函数代码从 `pg_writer.py` 中移除（subprocess 调用链路废弃） | grep 确认函数不存在 |
| AC-8 | P2 | `GET /api/v1/data/status` 返回的每个 job 对象包含 `pg_write_status` 字段（ok/partial/fail/skipped） | curl /status + jq |

## 5. Design

### 5.1 目标数据流（ADR-006 决策 1+3）

```
                    ┌──────────────────────────────────┐
                    │       data-service (8001)         │
                    │                                    │
 Tushare API ──────▶│  sync/tushare.py ──▶ PG (first)   │
 (rt_min/daily/     │       │                            │
  moneyflow/...)    │       ▼                            │
                    │  SQLite (fallback)                 │
                    │       │                            │
 Tushare stock_basic│  sync/stocks.py ──▶ PG + SQLite   │
                    │       │                            │
                    │       ▼                            │
                    │  pg_refresh → 物化视图             │
                    │  rate_limiter.py (统一限频)        │
                    └──────────────────────────────────┘
                                     │
                           PG ◀─────┘
                            │
                    ┌───────┼───────┐
                    ▼       ▼       ▼
               screener  signal  prediction ...
```

### 5.2 核心架构决策（引用 ADR-006）

| 决策 | 内容 | ADR-006 引用 |
|---|---|---|
| 写入顺序 | **先 PG 后 SQLite**；PG 失败报 ERROR，SQLite 失败仅 WARN | 决策 1 |
| 直写范围 | P0+P1 全表：daily_kline, moneyflow, stk_limit, index_daily, stk_mins, daily_basic, ths_daily, limit_list_d | 决策 2 |
| 写入方式 | `INSERT ... ON CONFLICT DO UPDATE` (upsert)，幂等可重入 | 决策 2 |
| subprocess 桥 | 移除 `sync_daily_to_pg()`，sync_to_pg.py 保留为手动历史回填工具 + `# LEGACY` 注释 | 决策 3 |
| stocks 同步 | Tushare `stock_basic` API，每周六 02:00 全量 + 每日盘前增量（`list_date = today`） | 决策 4 |
| 物化视图 | 保留现有 3 个 + 新增 `mv_daily_composite_ranking`（涨幅+量比+资金流入加权排名） | 决策 5 |
| 速率控制 | 全局 `_rate_limit()` 在每次 Tushare API 调用前执行，400 次/分钟留 20% 余量 | 决策 2 |
| 错误处理 | 3 次指数退避重试（网络/PG 连接错误）+ 数据量门禁（< 3000 行 WARN，< 1000 行 ERROR） | 决策 6 |

### 5.3 调度器变更（ADR-006 决策 3）

```
旧调度链:
  post_market_core (15:30) → SQLite only
  post_market_ext  (15:35) → SQLite only
  pg_sync          (15:36) → subprocess → SQLite read → PG write  ← 移除
  pg_refresh       (15:37) → REFRESH MATERIALIZED VIEW

新调度链:
  post_market_core (15:30) → PG first + SQLite fallback
  post_market_ext  (15:35) → PG first + SQLite fallback
  pg_refresh       (15:37) → REFRESH MATERIALIZED VIEW (PG 已有数据)
  stocks_sync      (周六 02:00) → 新增，stock_basic 全量刷新
```

### 5.4 改动文件清单

| 文件 | 改动类型 | 内容 |
|---|---|---|
| `services/data-service/app/sync/pg_writer.py` | 重构 | 通用 `write_table()` + 各表写入函数；`refresh_materialized_views()` 改为返回每 view 结果；移除 `sync_daily_to_pg()` |
| `services/data-service/app/sync/tushare.py` | 修改 | 所有 sync 函数增加 PG 直写调用（先 PG 后 SQLite 改为 PG-first） |
| `services/data-service/app/sync/rate_limiter.py` | **新增** | 统一 `_rate_limit()` 实现，所有 sync 函数共用 |
| `services/data-service/app/sync/stocks.py` | **新增** | `sync_stocks()` — Tushare stock_basic → PG + SQLite 双写 |
| `services/data-service/app/scheduler.py` | 修改 | 移除 `pg_sync` job，新增 `stocks_sync` job；保持 `pg_refresh` |
| `services/data-service/app/routers/data.py` | 修改 | 新增 `POST /api/v1/data/sync/stocks`；status 增强（含 pg_write_status） |
| `services/sql/init_postgres.sql` | 修改 | 确保 `limit_list_d`、`ths_daily`、`rt_k`、`stk_auction_o` 等缺失表存在 |
| `Kronos/sql/materialized_views.sql` | 修改 | 新增 `mv_daily_composite_ranking` 物化视图 |
| `Kronos/tools/sync_to_pg.py` | 注释 | 增加 `# LEGACY: use data-service for daily sync` 标记（不改逻辑） |

## 6. Technical Constraints

- 必须遵守 `.claude/standards/coding.md`、`security.md`、`observability.md`
- PG 双写使用 `psycopg2`（已在 `pg_writer.py` 中使用），不引入 `asyncpg`/`SQLAlchemy` 新依赖
- 表名/列名约定：PG 列名以 `services/sql/init_postgres.sql` 为准（`code` 而非 `ts_code`，`change_pct` 而非 `pct_chg`）
- SQLite 写入路径不受影响（PG 双写是 additive）
- 性能预算：单表 PG 批量写入 ≤ 30s（5000 行级别）
- 速率控制：Tushare API 调用前执行 `_rate_limit()`，每分钟 ≤ 400 次
- 写入顺序：**先 PG 后 SQLite**（ADR-006 决策 1）

## 7. Cost Estimate

- 预估 LLM token / 月：0（纯数据管道，无 LLM 调用）
- 预估 Agent Team 开发 token：~200K（7 个 task × 每个 ~30K，含 review + QA）
- 触发 cost-budget.md：Medium 档

## 8. Out of Scope / Future Work

- **历史数据全量回填**：通过 `sync_to_pg.py --days N` 手动回填（工具保留）
- **Redis 缓存自动刷新**：后续 feature
- **Kronos/tools 目录清理**：本次只标记 LEGACY，Phase B 评估废弃
- **盘中日线增量更新**（利用 rt_k/rt_min 实时数据）：后续 feature
- **数据质量监控面板**（Prometheus + Grafana）：后续 feature
- **多数据源支持**（Wind/BaoStock）：后续 feature
- **P2 表（top_list, margin_detail 等）PG 同步**：保留 subprocess 桥，待后续 ADR 覆盖

## 9. Open Questions

> 全部 5 个问题已由 ADR-006 决议，2026-06-12 tech-lead 落盘。

| ID | 问题 | 决议 | ADR-006 引用 |
|---|---|---|---|
| Q-1 | stocks 同步频率 | 每周六 02:00 全量 + 每日盘前增量检测（`list_date=today`） | 决策 4 |
| Q-2 | PG 写入策略（DO NOTHING vs DO UPDATE） | `ON CONFLICT DO UPDATE` (upsert)，幂等可重入 | 决策 2 |
| Q-3 | 物化视图刷新失败处理 | 3 次指数退避重试（仅网络/PG 连接错误）+ 分级日志；连续 2 次 P0 失败 → ERROR | 决策 6 |
| Q-4 | Kronos/tools 处置 | sync_to_pg.py 加 `# LEGACY` 注释保留为手动工具；sync_all.py 不动 | 决策 3 |
| Q-5 | stk_limit pre_close PG schema 对齐 | PG `stk_limit` 表无 `pre_close` 列（init_postgres.sql:71-77）→ 本次不对齐，物化视图通过 `daily_kline.close` 计算涨跌幅 | — |

## 10. Sign-offs

- [x] product-lead: 初稿 2026-06-12
- [x] tech-lead: 技术可行性 review — ADR-006 落盘 2026-06-12
- [ ] backend-dev: 实现确认（待派单后 Plan Mode 报告）

## Changelog

- 2026-06-12: 初稿，基于 team-lead 需求和代码审计
- 2026-06-12: v1.1 — 纳入 ADR-006 全部 6 项决策；5 个 Open Questions 已决议；状态 → Approved；Design §5.2 新增架构决策表
