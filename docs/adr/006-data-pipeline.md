# ADR-006: 数据管道架构 — 统一写入策略与 PG 主存储

- 状态：Proposed
- 日期：2026-06-12
- 决策者：tech-lead
- 影响范围：data-service + Kronos/tools/sync_to_pg.py + init_postgres.sql + 调度器

## 上下文

速赢 AI 平台的数据管道处于半重构状态。当前架构存在以下问题：

1. **写入路径不一致**：`rt_min` (stk_mins) 直接写 PG + SQLite 双写，但所有盘后同步表（daily_kline, moneyflow, stk_limit, index_daily, daily_basic）先写 SQLite，再通过 subprocess 调用 `sync_to_pg.py` 桥接到 PG。两条路径分属 `data-service` 和 `Kronos/tools/` 两个代码库，逻辑重复、错误处理各搞一套。
2. **subprocess 桥脆弱**：`pg_writer.sync_daily_to_pg()` 通过 `subprocess.run()` 调用 `Kronos/tools/sync_to_pg.py`，硬编码相对路径、独立错误上下文、300s 硬超时、输出截断 200 字符。SQLite 写成功但 subprocess 失败时 PG 数据丢失且无感知。
3. **stocks 基础表无数据**：`init_postgres.sql` 定义了 `stocks` 表，但没有数据填充脚本。`collect_rt_min()` 依赖 SQLite 的 stocks 表获取代码列表，PG 侧的 stocks 表长期为空，导致物化视图 JOIN 无结果。
4. **错误处理 best-effort**：所有异常只 log 不告警，没有重试、没有熔断、没有数据质量校验。
5. **Tushare 限频控制不一致**：`tushare.py` 声明 `_RATE_LIMIT=400` 但从未强制执行；`sync_all.py` 有 `_rate_limit()` 实际控制但仅限 Kronos CLI 使用；`rt_min.py` 无限频控制。
6. **无数据管道 ADR**：现有 5 个 ADR（认证/交易/策略/训练/诊断）均不覆盖数据管道技术基线。

不做此决策的后果：PG 数据完整性依赖 subprocess 的脆弱链路；重构方向不明导致每次改动都在两条路径之间摇摆；stocks 表长期为空导致物化视图不可用；数据异常时无告警、无感知、排查全靠手工翻日志。

## 决策

### 决策 1：写入目标 — PG 为主，SQLite 为 fallback

| 维度 | 选型 | 理由 |
|------|------|------|
| 主存储 | **PostgreSQL 15** | PG 是服务层查询的权威数据源（screener/backtest/signal/prediction 均读 PG）；支持物化视图、GIN 索引、JSONB 查询；数据完整性由 FK 约束保障。与 ADR-001/003/004 数据库选型一致。 |
| 回退存储 | **SQLite（Kronos legacy）** | Kronos 训练管线 (`Kronos/tools/`) 仍读 SQLite；Phase A 双库并存策略（见 [[dual-db-phase-a]]）。SQLite 写失败不应阻塞 PG 主路径。 |
| 写入顺序 | **先 PG 后 SQLite** | PG 是主存储，写入失败应报错；SQLite 是 fallback，写入失败仅 WARN。否决先 SQLite 后 PG：会导致 PG 写入被 SQLite 状态耦合。 |

**否决的备选**：

- **A. PG 唯一存储，废弃 SQLite** — 最简洁，但 Kronos 训练管线 (`train_lgbm_ranker.py`、`screen.py` 等) 全部硬编码 SQLite 路径，一次性迁移风险不可控。Phase B 可重新评估。
- **B. 保留当前 subprocess 桥，只做增量修复** — 改动最小，但 subprocess 调用是架构层面的反模式：独立进程、独立连接池、独立错误上下文。修复不如替换。

### 决策 2：PG 直写覆盖范围 — 全 P0 + P1 表

| 维度 | 选型 | 理由 |
|------|------|------|
| 直写范围 | **P0: daily_kline, moneyflow, stk_limit, index_daily, stk_mins + P1: daily_basic, ths_daily, limit_list_d** | 覆盖所有服务层查询依赖的表。一次性消除 subprocess 桥，统一写入路径。 |
| 写入方式 | **`INSERT ... ON CONFLICT DO UPDATE` (upsert)** | 幂等写入，支持重复拉取同一天数据不抛异常。与 `sync_to_pg.py` 现有策略一致。 |
| 并行策略 | **ThreadPoolExecutor（max_workers=2）内同步写 PG + SQLite** | 不引入 asyncpg 新依赖（Tushare SDK 本身同步阻塞，ThreadPool 是合理选择）。数据采集本质是 IO-bound，2 workers 足够覆盖 PG + SQLite 双写。否决 asyncio + asyncpg：需引入 `asyncpg` 依赖（当前 data-service 未安装），且 Tushare `pro_api()` 是同步的，混用 async/blocking 反而增加复杂度。 |
| 速率控制 | **全局 `_RATE_LIMIT=400`，`_rate_limit()` 在每个 Tushare API 调用前执行** | 400 次/分钟留 20% 安全余量（Tushare 限频 500 次/分钟）。在 `data-service/app/sync/` 层统一实现，所有 sync 函数共用同个 rate limiter。 |

**否决的备选**：

- **A. 仅直写 P0 表，P1 保留 subprocess 桥** — 改动更小，但保留了技术债务（subprocess 桥），且 P1 表（daily_basic）在 screening 和 diagnosis 中被频繁查询，不值得保留第二条路径。
- **B. 全部改为 asyncpg + asyncio** — 性能最优，但 Tushare SDK 是同步阻塞的，async 无实际收益；需新增依赖；重构面大（scheduler 是 asyncio 但 sync 函数当前全同步）。

### 决策 3：消除 subprocess 桥

| 维度 | 选型 | 理由 |
|------|------|------|
| pg_sync 调度步骤 | **移除** | `post_market_core` 和 `post_market_ext` 已内置 PG 直写，不再需要独立 `pg_sync` 步骤。 |
| sync_to_pg.py | **保留为独立工具，改为仅限手动全量迁移使用** | 不删除——历史数据迁移场景仍需"从 SQLite 读 → 写 PG"的桥。增加 `--mode full` 和免责声明注释，明确标记为 `# LEGACY: use data-service for daily sync`。 |
| pg_writer.sync_daily_to_pg() | **废弃** | 替换为 `pg_writer.write_table(name, rows)` 通用接口，供 sync 函数直调。 |

**调度器优化**（scheduler.py）：

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

### 决策 4：stocks 基础表同步

| 维度 | 选型 | 理由 |
|------|------|------|
| 数据来源 | **Tushare `stock_basic` API** | 返回全量 A 股列表（code, name, industry, list_date, is_hs 等），覆盖沪深京三市。 |
| 同步频率 | **每周六 02:00 全量刷新 + 每日盘前增量检测** | 新股上市频率低（平均每周 2-5 只），周级全量刷新足够；每日增量检测仅拉取 `list_date = today` 的股票，1 次 API 调用即可。 |
| 写入目标 | **PG + SQLite 双写** | stocks 表是多个服务的代码清单来源（rt_min、screening、物化视图 JOIN）。PG 为主，SQLite 为 Kronos 兼容。 |
| 字段映射 | `ts_code → code` (去掉后缀), `industry`, `list_date`, `is_hs`, `market` (SH/SZ/BJ 分类) | 对齐 `init_postgres.sql` 中 `stocks` 表的列定义。 |

**否决的备选**：

- **A. 手工维护 stocks.csv 文件** — 无自动更新、无增量，新股上市需人工添加。不可接受。
- **B. 从 daily_kline 表 DISTINCT code** — 只能获取有交易的股票，无法区分 ST、行业、上市日期等元信息。数据不完整。

### 决策 5：物化视图 — 维持 3 个，新增 1 个综合排名视图

| 维度 | 选型 | 理由 |
|------|------|------|
| 当前 3 个 | **保持不变**：`mv_today_strong_stocks`、`mv_sector_momentum`、`mv_top_capital_inflow` | 三个视图覆盖了龙虎战法的核心查询（强势股发现、板块资金、主力流入）。物化视图的维护成本 = REFRESH 耗时 + 磁盘占用，不宜过多。 |
| 新增 | **`mv_daily_composite_ranking`**（综合排名：涨幅 + 量比 + 资金流入加权） | 满足 Dashboard "今日综合排名" 看板需求，避免每次查询做复杂 JOIN + 加权计算。 |
| 刷新时机 | **盘后 `post_market_core` + `post_market_ext` 完成后（15:37），且 stocks 表已就绪** | 物化视图 JOIN stocks 表，必须在 stocks 有数据后刷新。 |
| 盘中刷新 | **不做** | 物化视图用于盘后分析（选股、复盘），盘中需求由 screener-service 实时查询覆盖。盘中 REFRESH CONCURRENTLY 会锁表影响写入性能。 |

**否决的备选**：

- **A. 为每个 screening 模式建一个物化视图** — screener-service 已有 6 种选股模式，6 个物化视图维护成本高（每次刷新 6 × REFRESH CONCURRENTLY），且 screening 查询本身已有索引优化（`idx_daily_kline_code`、`idx_daily_kline_date`），实时查询延迟可接受。
- **B. 物化视图改为普通视图** — 普通视图每次查询重新计算，在 5000+ 股票 × 3 表 JOIN 场景下延迟不可控（3-10 秒 vs 物化视图 10ms）。物化视图用磁盘空间换查询速度，符合分析场景的读多写少特性。

### 决策 6：错误处理与监控

| 维度 | 选型 | 理由 |
|------|------|------|
| 重试策略 | **3 次指数退避（1s → 4s → 16s），仅对网络错误和 PG 连接错误重试** | 数据重复性问题（如 Tushare 返回空 DataFrame）不应重试；网络瞬断可以 auto-recovery。 |
| 告警触发 | **连续 2 次 P0 同步失败 → ERROR 日志（可被外部监控系统采集）** | Phase A 不上独立告警系统（Slack/企微 Webhook），ERROR 日志是当前最可行的告警载体。后续可接入 Prometheus Alertmanager。 |
| 数据质量门禁 | **单日写入 < 3000 只股票 → WARN；< 1000 只 → ERROR** | A 股正常交易日应有 4000+ 只股票交易。数据量远低于预期通常是 Tushare API 异常或权限过期。 |
| PG 连接失败 | **连续失败 > 5 分钟 → ERROR，保留 SQLite 写入不中断采集** | PG 故障不应阻断数据采集——SQLite 可临时承接，事后通过 `sync_to_pg.py` 补同步。 |
| 日志级别 | **ERROR: 数据丢失/PG 不可用；WARNING: 重试后恢复/写入量偏低；DEBUG: Tushare API 单次超时（正常波动）** | 清晰的级别分工让运维能快速定位问题。 |

## 备选方案

- **A. 引入 Celery + Redis 做任务队列** — 分布式、可重试、有 Dashboard。否决理由：Phase A 日均任务量 < 20 次，asyncio 内置调度器完全够用；Celery 引入 Redis Broker + Worker 进程，运维复杂度倍增。与 ADR-003 决策 1（否决 Celery for 自动交易）一致。若未来数据采集频率提升到每分钟 100+ API 调用，可通过新 ADR 迁移。

- **B. 数据采集改为独立 Airflow DAG** — 业界标准的数据管道编排工具。否决理由：Airflow 需要独立部署（Scheduler + WebServer + Worker + Metadata DB），当前仅 6 个定时任务，杀鸡用牛刀。Phase B 若需要跨服务 DAG 编排（采集 → 训练 → 预测 → 交易），可重新评估。

- **C. 完全废弃 SQLite，只写 PG** — 架构最干净。否决理由：Kronos 训练管线的 `tools/` 代码全部硬编码 SQLite，一次性迁移风险高（预计影响 15+ 个脚本）；Phase A 双库并存是已知基线（[[dual-db-phase-a]]），不可在此 ADR 推翻。Phase B 若 Kronos 训练管线完成 PG 适配，可通过新 ADR 废弃 SQLite。

## 影响

- **对现有代码**：
  - `services/data-service/app/sync/pg_writer.py`：重构为通用 `write_table(table, rows, pk_cols)` + `refresh_views()` 函数，移除 `sync_daily_to_pg()` subprocess 调用。新增约 150 行。
  - `services/data-service/app/sync/tushare.py`：每个 sync 函数增加 PG 直写调用（`pg_writer.write_table(...)`），在 SQLite 写入后立即执行。修改约 50 行。
  - `services/data-service/app/sync/`：新建 `stocks.py`（`sync_stocks(pro, db)` 函数），约 80 行。
  - `services/data-service/app/sync/`：新建 `rate_limiter.py`（统一 `_rate_limit()` 实现），约 30 行。
  - `services/data-service/app/scheduler.py`：移除 `pg_sync` 任务，新增 `stocks_sync` 任务（周六 02:00）；更新 `_jobs` 列表。修改约 15 行。
  - `services/data-service/app/routers/data.py`：新增 `POST /api/v1/data/sync/stocks` 端点。修改约 15 行。
  - `Kronos/tools/sync_to_pg.py`：增加 `# LEGACY` 标记注释，不删除。修改 0 行（仅注释）。
  - `Kronos/sql/materialized_views.sql`：新增 `mv_daily_composite_ranking` 视图定义。修改约 30 行。

- **对团队**：
  - 后端开发者需理解 PG-first 写入顺序和 upsert 语义（`ON CONFLICT DO UPDATE`）
  - 数据采集逻辑收敛到 `data-service/app/sync/` 统一维护，不再需要理解 `Kronos/tools/sync_all.py` 和 `sync_to_pg.py` 两条路径的差异

- **对成本**：
  - 无新增基础设施费用——复用现有 PostgreSQL 15-alpine 和 SQLite
  - 无新增外部服务费用
  - Tushare API 调用次数不变（仅 stocks_sync 每周新增 1 次 API 调用，stock_basic 不计入限频配额）

- **对运维**：
  - 新增监控点：
    - P0 同步连续失败告警（外部监控系统采集 ERROR 日志）
    - PG 写入量 < 3000 行告警（数据质量问题）
    - PG 连接失败 > 5 分钟告警
    - stocks 表最新 `list_date` > 7 天告警（新股未同步）
  - pg_sync 步骤移除，减少一个故障点
  - 简化运维：不再需要排查 subprocess 桥的失败原因

## 本 ADR 不覆盖的决策

- **Kronos 训练管线从 SQLite 迁移到 PG**：Phase B 范围，取决于 Kronos 核心模块的 PG 适配进度。本 ADR 仅通过 PG 双写为迁移提供数据基础。
- **data-service 与 sync_all.py 的代码合并**：`sync_all.py` 保留为独立的 CLI 全量同步工具，不做代码级合并。data-service 聚焦定时增量同步，sync_all.py 聚焦手动全量/补同步。
- **P2 表（top_list, margin_detail 等）的 PG 同步**：这些表使用频率低（龙虎榜/融资融券分析），盘后 subprocess 桥可暂时保留。待 P0+P1 直写稳定后由后续 ADR 覆盖。
- **盘中日线数据更新**：Tushare 的 `pro.daily()` 仅在收盘后返回完整日线数据，盘中无法获取当日日线。如需盘中日线级别的更新，需评估其他数据源（如腾讯/新浪实时接口），不在本 ADR 范围。
- **数据采集的跨市场扩展（港股/美股）**：PRD Phase 4 范围。
- **实时行情推送（WebSocket）**：当前全为拉取模式（REST API），推送模式需重构整个数据管道。若产品需要 tick 级实时行情，另开 ADR。

## 后续工作

- [ ] backend-dev: 重构 `pg_writer.py` — 通用 `write_table()` 函数 + 移除 `sync_daily_to_pg()`，预计 0.5d
- [ ] backend-dev: 修改 `tushare.py` 所有 sync 函数增加 PG 直写调用，预计 0.5d
- [ ] backend-dev: 新建 `stocks.py` + `rate_limiter.py`，预计 0.5d
- [ ] backend-dev: 修改 `scheduler.py` — 移除 pg_sync、新增 stocks_sync，预计 0.25d
- [ ] backend-dev: 修改 `routers/data.py` — 新增 stocks 同步端点，预计 0.25d
- [ ] backend-dev: 修改 `materialized_views.sql` — 新增 `mv_daily_composite_ranking`，预计 0.25d
- [ ] backend-dev: 修改 `init_postgres.sql` — 确保所有缺失表（rt_k, stk_auction_o, limit_list_d, ths_daily）存在，预计 0.25d
- [ ] backend-dev: 跑集成测试验证 PG 直写 end-to-end（docker PostgreSQL + Tushare 沙箱 token），预计 0.5d
- [ ] product-lead: 确认 stocks 同步的频率需求（周级是否足够？是否需要假日/停牌检测？）→ ADR accept 前
- [ ] tech-lead: 同步更新 CLAUDE.md Tech Stack 表，新增 data-service 条目

## 版本与查证

> tech-lead 行事原则 #3「先查最新版再决策」的回填段。

**查证基线日期**：2026-06-12

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|------|---------|-----------|-------------|---------|----------------------|
| psycopg2-binary | 2.9.12（已在用） | 2.9.12 | 无差距 | Active — psycopg2 是 Python PG 驱动的事实标准 | 本地 `pip show psycopg2-binary` — "Version: 2.9.12"；项目 `.venv` 已安装 |
| tushare | 1.4.29（已在用） | 1.4.29 | 无差距 | Active — 持续更新中，最新版修复 BSE 920 前缀 | 本地 `pip show tushare` — "Version: 1.4.29"；A 股数据接口稳定 |
| asyncpg | 0.31.0（已在用，backend） | 0.31.0 | 无差距 | Active — 高性能 async PG 驱动 | 本地 `pip show asyncpg` — "Version: 0.31.0"；data-service 不使用（同步模式） |
| PostgreSQL | 15-alpine（已在用） | 17 | 2 个 major 落后 | Active — PG 15 EOL 2027-11 | [docker-compose.yml](../../docker/docker-compose.yml) 已用 `postgres:15-alpine`；同 ADR-001 版本查证 |

**备选（被否决）技术的版本记录**：

| 选型 | 当时最新版 | 否决原因 |
|------|-----------|---------|
| Celery + Redis | 5.6.0 / 7.4.x | Phase A 任务量 < 20 次/天，不需要分布式队列；与 ADR-003 一致 |
| Airflow | 3.x | 当前仅 6 个 cron 任务，独立部署 Airflow 的运维成本远超收益 |
| asyncpg（for data-service） | 0.31.0 | Tushare SDK 同步阻塞，async 无实际收益；不想引入新依赖 |
