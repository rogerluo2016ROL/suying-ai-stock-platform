# 数据自动更新治理方案 —— 按频率分层的调度与回补

> 版本: v1.0  
> 日期: 2026-06-13  
> 作者: backend-dev  
> 关联 ADR: ADR-006 (数据管道 — PG-first 直写)

## 1. 问题分析

### 1.1 当前调度缺口

| 缺口 | 描述 |
|---|---|
| **L1 日内增量缺失** | `limit_list_d` 仅在盘后 `sync_post_market_ext` 中采集 U（涨停）类型，缺少 D（跌停）/ Z（炸板）及日中实时数据。盘中选股模型需要近实时涨跌停信息。 |
| **L2 盘后覆盖不全** | `sw_daily`（申万行业日线）和 `stk_factor_pro`（股票技术因子）未纳入任何调度任务。两者均为秋神盘中选股模型依赖因子。 |
| **L3 周级缺漏** | `moneyflow_hsgt`（沪深港通资金流向）在 `kronos_data/etl.py` 中有完整实现，但未注册调度任务。 |
| **L4 历史回补无自动化** | `sync_stk_mins` 等历史回补函数需手动调用。6/11 的 `stk_mins` 数据缺失 48 天才被发现并手动回补。 |
| **无数据完整性检测** | 调度器盲目执行任务，不做事后验证。任务失败 / 服务宕机 / API 限频导致的静默丢数据无法被发现。 |

### 1.2 已知数据质量问题

- `daily_kline.change_pct` 全 NULL —— `sync_post_market_core` 中的 `sync_daily_kline` 仅采集 OHLCV（open/high/low/close/vol/amount），未写入 `pre_close` / `change` / `pct_chg`。etl.py 版本的 `sync_daily_kline` 包含 `pct_chg` 列，双写口径不一致。
- `limit_list_d` 仅 U 类型 —— `sync_post_market_ext` 调用 `pro.limit_list_d(limit_type="U")`，缺失 D/Z。
- Tushare API 限频 400 次/分钟由各自 `rate_limit()` 独立管理，无跨任务统一视图。

---

## 2. 分层调度矩阵

### 2.1 层级总览

| 层级 | 频率 | 触发时段 | 触发条件 | 涉及表 |
|---|---|---|---|---|
| **L0 实时** | 每 1 分钟 | 交易日 9:30–15:00 | 自动 (`*/1 9-15 * * 1-5`) | `stk_mins` |
| **L1 日内** | 每 30 分钟 | 交易日 9:30–15:00 | 自动 (`*/30 9-15 * * 1-5`) | `limit_list_d` |
| **L2 盘后** | 每日 15:30–16:30 | 交易日盘后 | 自动 (分 5 个批次错峰) | 9 张核心表 |
| **L3 周级** | 每周 / 每月 | 非交易时段 | 自动 (每周一 / 每月 1 日) | `stocks` / `moneyflow_hsgt` / `cb_price_chg` |
| **L4 回补** | 每日 04:00 | 凌晨 | 自动检测 + 触发 | 全部监控表 |

### 2.2 调度矩阵明细

| 层级 | Job ID | 目标表 | 数据源 | Cron | 限频策略 | 失败重试 | 备注 |
|---|---|---|---|---|---|---|---|
| L0 | `rt_min` | `stk_mins` | `pro.rt_min(freq="5MIN")` | `*/1 9-15 * * 1-5` | rate_limit() 每次调用 | 3 次 (1s/4s/16s) | ThreadPool 并行, PG 主写 + SQLite fallback |
| L0 | `auction` | `stk_auction_o` | `stk_mins[09:30-09:35]` 聚合 | `25 9 * * 1-5` | — (复用 rt_min) | 3 次 | 9:25 触发, 等 rt_min 采集 9:30 首根 K 线 |
| L1 | `limit_list_d_intra` | `limit_list_d` | `pro.limit_list_d(U/D/Z)` | `*/30 9-15 * * 1-5` | rate_limit() 每次类型 | 3 次 | 日内增量含 U/D/Z 三类型 |
| L1 | `intraday_sync` | `daily_kline/moneyflow/stk_limit/daily_basic/ths_daily/limit_list_d` | 复用 post_market_core/ext | `0 13 * * 1-5` | 各子函数自带 rate_limit() | 3 次 | 13:00 午间批量同步上午数据 |
| L2 | `post_market_core` | `daily_kline/moneyflow/stk_limit/index_daily` | `pro.daily/moneyflow/stk_limit` | `30 15 * * 1-5` | rate_limit() 每次分页/API | 3 次 | P0 核心表, 盘后 15:30 第一批 |
| L2 | `post_market_ext` | `daily_basic/ths_daily/limit_list_d(U)` | `pro.daily_basic/ths_daily/limit_list_d` | `35 15 * * 1-5` | rate_limit() 每次 | 3 次 | P1 扩展表, 15:35 第二批 |
| L2 | `pg_refresh` | 物化视图 | `REFRESH MATERIALIZED VIEW` | `37 15 * * 1-5` | — | 1 次 | PG 物化视图刷新, 15:37 |
| L2 | `ths_daily` | `ths_daily` | `cb_sync.sync_ths_daily` | `0 16 * * 1-5` | rate_limit() | 3 次 | 同花顺概念板块, 16:00 |
| L2 | `cb_daily` | `cb_daily` | `etl.sync_cb_daily` | `0 16 * * 1-5` | rate_limit() 每次 | 3 次 | 可转债日线, 16:00 |
| L2 | `index_daily` | `index_daily` | `etl.sync_index_daily` | `0 16 * * 1-5` | rate_limit() 每次指数 | 3 次 | 8 大指数日线, 16:00 |
| L2 | `sw_daily` | `sw_daily` | `etl.sync_sw_daily` | `5 16 * * 1-5` | rate_limit() 每 30 天批次 | 3 次 | **新增**: 申万行业日线 |
| L2 | `stk_factor_pro` | `stk_factor_pro` | `pro.stk_factor_pro` | `5 16 * * 1-5` | rate_limit() 1 次调用 | 3 次 | **新增**: 股票技术因子 (MACD/KDJ/RSI/BOLL/ATR) |
| L2 | `stk_auction_o` | `stk_auction_o` | `pro.stk_auction_o` | `30 15 * * 1-5` | rate_limit() 1 次 | 3 次 | 集合竞价数据 (需权限) |
| L2 | `cb_factor` | `cb_factor` | `etl.sync_cb_factor` | `30 16 * * 1-5` | rate_limit() 每次日期 | 3 次 | 可转债技术因子, 16:30 |
| L3 | `stocks_sync` | `stocks` | `pro.stock_basic` | `0 2 * * 6` | 不计入限频配额 | 3 次 | 全量同步, 每周六凌晨 |
| L3 | `stocks_incremental` | `stocks` | `pro.stock_basic(list_date=today)` | `0 8 * * 1-5` | 不计入限频配额 | 3 次 | 增量同步新上市股票 |
| L3 | `moneyflow_hsgt` | `moneyflow_hsgt` | `etl.sync_moneyflow_hsgt` | `30 8 * * 1` | rate_limit() 每次日期 | 3 次 | **新增**: 沪深港通周级, 每周一 08:30 |
| L3 | `cb_price_chg` | `cb_price_chg` | `cb_sync.sync_cb_price_chg_all` | `0 9 * * 1` | rate_limit() 每只 | 3 次 | 转股价变动, 每周一 09:00 |
| L3 | `ths_concept_map` | `ths_concept_map` | `cb_sync.sync_ths_concept_map` | `0 3 1 * *` | rate_limit() 1 次 | 3 次 | 同花顺概念映射, 每月 1 日 |
| L4 | `data_integrity` | 全部 12 张监控表 | `check_table_latest_date()` → `trigger_data_backfill()` | `0 4 * * *` | 各回补函数自带 rate_limit() | 3 次 | **新增**: 完整性检查 + 自动回补, 每日 04:00 |

### 2.3 限频统一管控

```
┌─────────────────────────────────────────────┐
│  所有 Tushare pro.xxx() 调用前强制         │
│  app.sync.rate_limiter.rate_limit()         │
│  滑动窗口: 400 次/60秒 (安全上限)          │
│  stock_basic 不计入配额 (Tushare 规则)     │
│  线程安全: threading.Lock                  │
└─────────────────────────────────────────────┘
```

- L0 `rt_min` 每次采集约 5400 只股票 / 100 只一批 = 54 次 API 调用，远低于 400/min 限制。
- L4 回补在凌晨 04:00 执行，与 L0-L2 无时间冲突，不争抢配额。
- 回补时每个表独立调用 `days_back` 天数据，按日遍历时每日期执行 `rate_limit()`。

### 2.4 失败重试策略

所有定时任务统一使用 `_run_job()` 的指数退避重试：**1s → 4s → 16s**，最多 3 次。PG 写入额外有 `_pg_write()` 的 3 次重试（psycopg2.OperationalError 自动触发）。

---

## 3. 缺失数据自动回补流程

### 3.1 检测逻辑

```
  ┌─────────────────┐
  │ 每日 04:00 触发  │
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │ detect_data_gaps│  遍历 MONITORED_TABLES
  │ (12 张表)        │  PG → SQLite fallback
  └────────┬────────┘
           ▼
  ┌─────────────────┐      ┌──────────────────────┐
  │ check_table_     │      │ SELECT MAX(date_col) │
  │ latest_date()   │ ──── │ FROM <table>          │
  └────────┬────────┘      └──────────────────────┘
           ▼
  ┌─────────────────┐
  │ gap_days >       │── No ──► ok
  │ gap_threshold?   │
  └────────┬────────┘
           │ Yes
           ▼
  ┌─────────────────┐
  │  标记为 gap      │  {status:"gap", latest_date, gap_days}
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │ trigger_data_    │  查 _BACKFILL_MAP → 调用 etl 函数
  │ backfill()      │  days_back = gap_days + 3 (缓冲)
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │  回补完成/失败   │  记录到 job_status
  └─────────────────┘
```

### 3.2 监控表与回补映射

| 表 | 日期列 | 回补函数 (etl.py) | 回补参数 | gap_threshold |
|---|---|---|---|---|
| `daily_kline` | `trade_date` | `sync_daily_kline` | `days_back=gap_days+3` | 1 天 |
| `moneyflow` | `trade_date` | `sync_moneyflow` | `days_back=gap_days+3` | 1 天 |
| `stk_limit` | `trade_date` | `sync_stk_limit` | `days_back=gap_days+3` | 1 天 |
| `daily_basic` | `trade_date` | `sync_daily_basic` | `days_back=gap_days+3` | 1 天 |
| `limit_list_d` | `trade_date` | `sync_limit_list_d` | `days_back=gap_days+3` | 1 天 |
| `moneyflow_hsgt` | `trade_date` | `sync_moneyflow_hsgt` | `days_back=gap_days+3` | 5 天 |
| `sw_daily` | `trade_date` | `sync_sw_daily` | `days_back=gap_days+3` | 2 天 |
| `stk_mins` | `trade_time` | `sync_stk_mins` | `days_back=gap_days+3` | 1 天 |
| `ths_daily` | `trade_date` | `sync_ths_daily` (cb_sync) | 需内联处理 | — |
| `index_daily` | `trade_date` | `sync_index_daily` (etl) | `days_back=30` | — |
| `stk_factor_pro` | `trade_date` | `sync_stk_factor_pro_daily` (scheduler) | 需内联处理 | — |
| `stocks` | `updated_at` | `sync_stock_list` (stocks) | 全量同步 | 7 天 |

> **注意**: `ths_daily` / `stk_factor_pro` / `stocks` 的回补不在 `_BACKFILL_MAP` 中。回补逻辑预留 `no_handler` 分支，记录到日志供运维知晓。

### 3.3 回补安全机制

1. **凌晨执行**: 04:00 执行，避免与交易时段 L0-L2 抢 Tushare 配额。
2. **缓冲区**: `days_back = gap_days + 3`，覆盖非交易日（周末/节假日）。
3. **幂等写入**: PG 使用 `ON CONFLICT DO NOTHING`，SQLite 使用 `INSERT OR REPLACE`，重复运行安全。
4. **错误隔离**: 单表回补失败不影响其他表的回补继续执行。
5. **首次运行**: 无历史数据的表会标记 `no_data`，不触发大量回补（需先手动初始化）。

---

## 4. 代码修改清单

### 4.1 修改文件

| 文件 | 修改类型 | 变更说明 |
|---|---|---|
| `services/data-service/app/scheduler.py` | **增强** | 新增 ~350 行代码: ①MONITORED_TABLES 配置 ②_BACKFILL_MAP 映射 ③`check_table_latest_date()` ④`detect_data_gaps()` ⑤`trigger_data_backfill()` ⑥`run_data_integrity_check()` ⑦`sync_stk_factor_pro_daily()` ⑧`sync_sw_daily_batch()` ⑨`sync_limit_list_d_intraday()` ⑩`sync_moneyflow_hsgt_weekly()` ⑪`start_scheduler()` 新增 5 个 job |

### 4.2 无需修改的文件（原因）

| 文件 | 原因 |
|---|---|
| `services/data-service/app/sync/tushare.py` | 现有同步逻辑无需改动。新增的 `stk_factor_pro` / `sw_daily` 在 scheduler.py 中以 wrapper 实现。 |
| `services/data-service/app/sync/rt_min.py` | L0 逻辑完整，无需改动。 |
| `services/data-service/app/sync/stocks.py` | L3 逻辑完整，无需改动。 |
| `services/data-service/app/config.py` | 配置通过环境变量注入，无需修改文件。 |
| `packages/kronos-data/kronos_data/etl.py` | 回补直接复用现有函数，零重复代码。新增 import 在 scheduler.py 头部扩展。 |

### 4.3 配置环境变量（可选覆盖）

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DATA_INTEGRITY_LOOKBACK` | `30` | L4 完整性检查的回看窗口（天） |
| `KRONOS_PG_URL` | `postgresql://kronos:kronos@localhost:6432/kronos` | PG 连接地址 |
| `TUSHARE_TOKEN` | — | Tushare API token |

---

## 5. 监控建议

### 5.1 数据延迟告警阈值

| 层级 | 表 | 告警阈值 | 严重级别 | 说明 |
|---|---|---|---|---|
| L0 | `stk_mins` | 最新数据 > 10 分钟前 | P1 | 实时分钟线断流，影响盘中选股 |
| L1 | `limit_list_d` | 当日无数据至 10:00 | P2 | 涨跌停日内数据缺失 |
| L2 | `daily_kline` | 最新日期 > 1 个交易日 | P1 | 日线缺失影响所有下游模型 |
| L2 | `moneyflow` | 最新日期 > 1 个交易日 | P2 | 资金流缺失影响选股因子 |
| L2 | `stk_factor_pro` | 最新日期 > 2 个交易日 | P2 | 技术因子缺失影响模型评分 |
| L2 | `sw_daily` | 最新日期 > 2 个交易日 | P3 | 行业数据延迟影响板块分析 |
| L3 | `moneyflow_hsgt` | 最新日期 > 5 个交易日 | P3 | 沪深港通周度数据滞后 |
| L3 | `stocks` | 最新更新 > 7 天 | P2 | 新股/退市未同步 |

### 5.2 监控实施建议

1. **`get_job_status()` API 暴露**: 现有 `/api/data-service/jobs` 端点返回所有 job 状态，含 `last_status` / `pg_write_status` / `last_run`。运维可对接 Prometheus + Grafana 面板。
2. **L4 检测结果持久化**: `run_data_integrity_check()` 返回值写入日志（INFO 级别）。建议后续增加 `data_integrity_log` 表持久化每次检测结果。
3. **自动告警**: 当 `detect_data_gaps()` 返回 `gaps > 0` 时，可在 L4 job 中扩展钉钉/企业微信 Webhook 通知（当前已预留 dry_run 参数，可外挂通知逻辑）。
4. **`stk_mins` 实时监控**: 在 `collect_rt_min()` 中增加 `elapsed` 指标，超过 60s 时 WARN 日志触发。

### 5.3 日志关键字

```
# 缺口检测
Data gap: <table> — latest=<date>, <N> days behind (threshold=<T>)

# 回补执行
Backfill <table>: <N> days, written=<M>

# 回补失败
Backfill <table> FAILED: <error>

# 完整性汇总
Integrity scan: <ok> ok, <gaps> gaps, <no_data> no_data (<elapsed>s)
Integrity backfill: <triggered> triggered, <skipped> skipped (<elapsed>s total)
```

---

## 6. 未来扩展

1. **交易日历集成**: 当前 `gap_days` 基于自然日计算，非交易日会被误判为缺口。后续可引入 `trade_cal` 表（`pro.trade_cal`）精确计算交易日滞后。
2. **L4 回补进度追踪**: 大缺口回补（如数月缺失）可能耗时较长，增加分页/断点续补机制。
3. **物化视图自动刷新**: `refresh_materialized_views` 目前仅刷新已有视图，可扩展到检测 `stk_mins` / `daily_kline` 物化视图的 `pg_stat_user_tables.last_vacuum`。
4. **`daily_kline.change_pct` 修复**: 统一 `sync_post_market_core` 和 `etl.sync_daily_kline` 的采集字段，消除 NULL 列。
