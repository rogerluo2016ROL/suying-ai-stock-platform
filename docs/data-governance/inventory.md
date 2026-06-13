# 秋神盘中选股模型 — 数据源盘点报告

> 审计日期：2026-06-13  
> 审计范围：`leader_intraday.py` 依赖的全部数据表（含间接引用）  
> 数据库：PostgreSQL `postgresql://kronos:kronos@localhost:6432/kronos`  
> 采集模块：`services/data-service/app/sync/` + `packages/kronos-data/kronos_data/etl.py`

---

## 1. 数据源盘点矩阵

### 图例

| 标记 | 含义 |
|------|------|
| 🟢 | 健康：新鲜度达标，NULL 率 < 5%，30 天无缺口 |
| 🟡 | 注意：轻微滞后、部分 NULL 或列名不一致 |
| 🔴 | 故障：严重滞后、关键字段全 NULL、模型路径断裂 |

### 核心表（模型直接查询）

| # | 表名 | 来源 API | 同步频率 | 最新日期 | 总行数 | 去重代码数 | 覆盖交易日 | 关键 NULL 率 | 近 30 天缺失 | 质量 |
|---|------|----------|----------|----------|--------|-----------|-----------|-------------|-------------|------|
| 1 | `stk_mins` | Tushare `rt_min` | L0 每分钟 (9:30-15:00) | 2026-06-12 | 16,663,222 | 5,522 | 73 | open/close/vol/amt: 0% | **6/1-6/4 缺口** (仅 39-1332 只 vs 正常 ~5000) | 🟡 |
| 2 | `daily_kline` | Tushare `daily` | L2 盘后 15:30 | 2026-06-12 | 8,536,898 | 5,563 | 8,696 | change_pct: **22.83%** (历史退市股) | 6/9 仅 4169 只 (正常 ~5500) | 🟡 |
| 3 | `stocks` | Tushare `stock_basic` | L3 每周六 02:00 + 每日 08:00 增量 | N/A | 5,644 | 5,644 | N/A | industry: 1.95%, float_mv: 2.29% | N/A (静态表) | 🟢 |
| 4 | `stk_limit` | Tushare `stk_limit` | L2 盘后 15:30 | 2026-06-12 | 13,059,802 | 8,316 | 2,534 | pre_close: **99.57%** (近期开始修复，6/12 已 0% NULL) | 5/25-5/29 100% NULL | 🔴→🟡 |
| 5 | `limit_list_d` | Tushare `limit_list_d` | L1 每30分钟 + L2 盘后 | 2026-06-12 | 2,812 | 1,318 | 24 | change_pct: **100% NULL** (pct_chg 有值), fd_amount: 21%, first_time: 14% | 仅 24 个交易日 | 🟡 |
| 6 | `moneyflow` | Tushare `moneyflow` | L2 盘后 15:30 | 2026-06-12 | 14,242,709 | 5,673 | 4,704 | net_mf_amount: 4.47% | **6/1=0**, 6/12 仅 3 只 | 🟢 |
| 7 | `ths_daily` | Tushare `ths_daily` | L2 盘后 16:00 (cb_sync.py) | 2026-06-12 | 71,502 | 1,511 | 52 | change_pct: 0% | 周五数据偏少 (~1230 vs ~1505) | 🟡 |
| 8 | `sw_daily` | Tushare `sw_daily` | L2 盘后 16:05 (etl.py) | **2026-06-08** | 488,425 | 596 | 1,020 | change_pct: 0% | **6/9-6/12 缺口 (4天)** | 🔴 |
| 9 | `index_daily` | Tushare `index_daily` | L2 盘后 16:00 (etl.py) | 2026-06-12 | 1,802 | **8** | 347 | change_pct: 0% | 6/9=0, 6/11=4, 6/12=1 | 🟡 |
| 10 | `stk_factor_pro` | Tushare `stk_factor_pro` | L2 盘后 16:05 | **2026-06-05** | 27,536 | 5,515 | **5** | ma5/ma10/macd: **100% NULL** | 6/6-6/12 无数据 (7天缺口) | 🔴 |
| 11 | `daily_basic` | Tushare `daily_basic` | L2 盘后 15:35 | 2026-06-12 | 10,688,884 | 5,768 | 2,532 | pe: 14.88%, pb: 0.63% | 6/1=0, 6/5=0, 6/9=0 | 🟡 |
| 12 | `moneyflow_hsgt` | Tushare `moneyflow_hsgt` | L3 每周一 08:30 | **2026-06-03** | 2,716 | N/A | 2,716 | north_net_inflow: **100% NULL**, south: **100% NULL** | 6/4-6/12 无数据 (9天) | 🔴 |

### 辅助表（模型通过 JOIN 间接引用）

| # | 表名 | 用途 | 总行数 | 质量 |
|---|------|------|--------|------|
| A1 | `index_basic` | 板块名称→代码映射，用于 sector_index 查询 | 1,103 | 🟢 |
| A2 | `ths_member` | 股票→同花顺概念映射，用于 get_sector_index THS 路径 | 117,013 (200 股, 8,275 概念) | 🟡 仅覆盖 200 只股票 |

---

## 2. 数据依赖拓扑图

```
                    ┌──────────────────────────────────────────────┐
                    │           leader_intraday.py                 │
                    │        秋神盘中龙头战法 V5.4                   │
                    └──────────────────────────────────────────────┘
                                         │
            ┌────────────────────────────┼────────────────────────────┐
            │                            │                            │
     ┌──────▼──────┐            ┌───────▼────────┐           ┌───────▼────────┐
     │  Level 0    │            │   Level 1       │           │   Level 2      │
     │  实时快照    │            │   日内辅助       │           │   基本面/因子   │
     └──────┬──────┘            └───────┬────────┘           └───────┬────────┘
            │                            │                            │
    ┌───────┴────────┐          ┌───────┴────────┐           ┌───────┴────────┐
    │ stk_mins       │          │ limit_list_d   │           │ daily_basic    │
    │ (14:40快照)    │          │ (涨停板检测)    │           │ (float_mv过滤) │
    │ • close/high/  │          │ • first_time   │           │ stk_factor_pro │
    │   low/amount   │          │ • fd_amount    │           │ (技术因子) ⚠️   │
    │ • VWAP 均价    │          │ • open_times   │           │ 100% NULL MA   │
    │ • 量比/放量    │          │ • up_stat      │           └────────────────┘
    └───────┬────────┘          └───────┬────────┘
            │                            │
    ┌───────┴────────────────────────────┴────────────────────────────┐
    │                        Level 3                                  │
    │                     历史K线 + 板块                               │
    └───────┬────────────────────────────┬────────────────────────────┘
            │                            │
    ┌───────┴────────┐          ┌───────┴────────────────────┐
    │ daily_kline    │          │ 板块行情 (3路径优先级)      │
    │ • pre_close    │          │                            │
    │ • MA5/10/20    │          │ ① ths_daily + ths_member  │
    │ • 60日K线      │          │    (同花顺概念, psycopg2) │
    │ • 量比基准     │          │                            │
    │ • 涨跌比计算   │          │ ② index_daily + index_basic│
    └────────────────┘          │    (申万行业关键词匹配)     │
                                │                            │
                                │ ③ sw_daily (fallback)     │
                                │    申万行业板块行情         │
                                └────────────────────────────┘
                                            │
                            ┌───────────────┴───────────────┐
                            │         股票池基础              │
                            │                               │
                            │  stocks (code/name/industry)  │
                            │  stk_limit (pre_close 备用)   │
                            │  moneyflow (主力资金, 间接)    │
                            │  moneyflow_hsgt (沪深港通,间接)│
                            └───────────────────────────────┘
```

### 数据依赖链（关键路径）

```
选股结果 ← 9因子评分 ← 14:40快照(stk_mins) + 前收盘(daily_kline)
                    ← 板块龙头(stk_mins JOIN stocks JOIN stk_limit)
                    ← 涨停检测(limit_list_d)
                    ← 板块行情(ths_daily → index_daily → sw_daily)
                    ← 均线趋势(daily_kline 60日)
                    ← 板块高潮(index_daily + index_basic + limit_list_d)
                    ← 股票池过滤(stocks + daily_basic.float_mv)
```

---

## 3. 数据质量详细审计

### 3.1 stk_mins — 盘中实时分钟线 🟡

**用途**：14:40 实时快照、VWAP 均价、量比、累计成交额预估

**关键发现**：
- 正常交易日覆盖 ~5000 只股票，48 个时段（9:30-15:00 每 5 分钟）
- **6/1-6/4 数据缺口**：仅 39-1332 只股票，可能是 Tushare API 故障或同步任务未执行
- 6/1-6/2 仅 39 只股票且只有 15:00 时点数据——疑似仅采集了尾盘
- 采集代码：`rt_min.py` → 批量 100 只/次，ThreadPool 8 workers，每分钟调用
- NULL 率：OHLCV 全 0%，数据完整度好

**建议**：排查 6/1-6/4 采集任务日志，确认是 Tushare 服务端限流还是本地调度中断

### 3.2 daily_kline — 历史日K线 🟡

**用途**：前收盘价 (pre_close)、MA5/MA10/MA20 均线、60 日量比基准、涨跌比计算

**关键发现**：
- 覆盖 1990 年至今 8,696 个交易日，5,563 只股票
- `change_pct` 22.83% NULL——主要集中在 2016 年以前的历史退市股，不影响盘中选股
- 近 30 天连续性：6/9 仅 4169 只（正常 5500+）——T+1 数据延迟，盘后同步未覆盖全量
- 采集代码：`tushare.py sync_daily_kline()` → 分页拉取（每页 5000），最多 10 页
- 同步时机：L2 盘后 15:30（`sync_post_market_core`）——此时 Tushare daily API 数据可能尚未就绪

**建议**：将 daily_kline 盘后同步延后至 16:30，或增加 17:00 二次回补

### 3.3 stocks — 股票池基础 🟢

**用途**：股票代码/名称/行业/ST 过滤/流通市值过滤

**关键发现**：
- 5,644 只上市股票，255 只 ST，industry NULL 110 只（1.95%）
- float_mv NULL 129 只（2.29%），模型过滤条件 `float_mv IS NULL OR float_mv >= 20` 对 NULL 宽容
- 同步：每周六全量 + 每日 08:00 增量（新股上市检测）

**建议**：为 NULL industry 的 110 只股票补全行业分类

### 3.4 stk_limit — 涨跌停价格 🔴→🟡

**用途**：前收盘价（备用，实际模型优先用 daily_kline）、板块龙头统计中的 pre_close

**关键发现**：
- `pre_close` 整体 NULL 率 99.57%——历史遗留问题
- **近期已修复**：6/1 起 pre_close 开始被填充，6/12 达到 0% NULL
- 5/25-5/29 期间仍为 100% NULL——那段时间的选股回测会受影响
- 模型正确使用 `daily_kline.close` 作为主 pre_close 来源，`stk_limit.pre_close` 仅用于 `_precompute_industry_stats` 中的 JOIN 过滤条件

**建议**：确认 pre_close 修复是否持久，监控未来是否再次漂移

### 3.5 limit_list_d — 涨停板列表 🟡

**用途**：涨停封板检测（first_time / fd_amount / open_times / up_stat）

**关键发现**：
- 仅 24 个交易日数据（5/12 起），历史覆盖不足
- PG 表有双列 `change_pct`(100% NULL) 和 `pct_chg`(有值)，模型使用 `pct_chg` 正确
- `fd_amount` 21% NULL——封单金额缺失影响封板强度判断
- `first_time` 14% NULL——影响 14:00 前封板判断
- 同步：L1 每 30 分钟增量（U/D/Z 全类型）+ L2 盘后全量

**建议**：补全更早历史数据（至少 60 交易日）；排查 fd_amount 缺失原因

### 3.6 moneyflow — 资金流向 🟢

**用途**：主力大单资金流向（模型未直接使用，但属于数据平台标配）

**关键发现**：
- 覆盖 2007 年至今，5,673 只股票
- net_mf_amount 4.47% NULL——多为历史早期数据
- 近 30 天缺口：6/1 完全缺失，6/12 仅 3 只（T+1 延迟）
- 采集代码：`tushare.py` 中 `sync_post_market_core` 并行拉取，2 workers

### 3.7 ths_daily + ths_member — 同花顺概念板块 🟡

**用途**：板块龙头判断中的概念板块涨跌幅（模型 `get_sector_index` 首选路径）

**关键发现**：
- `ths_daily`：1,511 个概念板块，52 个交易日，数据完整度好
- **列名不匹配 BUG**：模型查询 `pct_change` 但 PG 列名为 `change_pct` → 查询失败 → 静默 fallback 到 index_daily 路径
- `ths_member`：仅覆盖 200 只股票（vs 全市场 5500+），概念映射严重不足
- 周五概念数量偏少（~1230 vs 正常 1505），可能为数据源特性
- 同步：L2 盘后 16:00 via `cb_sync.py sync_ths_daily()`

**BUG 详情**（`leader_intraday.py:673-678`）：
```python
sector_5d = db.execute(
    "SELECT SUM(pct_change) as sum5d FROM ("
    "SELECT pct_change FROM ths_daily WHERE name LIKE ? ..."
    #      ^^^^^^^^^^  PG 列名是 change_pct，不是 pct_change
```
该查询抛出 `column "pct_change" does not exist`，被 `except Exception: pass` 吞掉，静默走 sw_daily fallback 路径。

**建议**：修复列名 BUG；扩展 ths_member 覆盖至少 3000+ 股票

### 3.8 sw_daily — 申万行业板块 🔴

**用途**：板块行情 fallback（模型 `get_sector_index` + `get_sector_climax_penalty` 的 sw_daily 路径）

**关键发现**：
- 596 个申万行业板块，1,020 个交易日
- **4 天滞后**：最新数据 6/8，6/9-6/12 无数据
- 6/1-6/5 数据正常（425-439 个板块），6/8 之后停止更新
- 同步：L2 盘后 16:05 via `scheduler.py sync_sw_daily_batch()` → `etl.py sync_sw_daily()`
- 回补：`_BACKFILL_MAP` 中已注册 `sync_sw_daily`，但自动回补未触发

**建议**：排查 6/8 后 sw_daily 同步失败原因；手动触发回补

### 3.9 index_daily + index_basic — 指数日线 🟡

**用途**：上证指数涨跌（`get_shanghai_index`）、板块指数涨跌（`get_sector_index` index_daily 路径）

**关键发现**：
- 仅 8 个指数：上证指数、上证50、沪深300、科创50、中证500、深证成指、中小100、创业板指
- index_basic 有 1,103 个指数定义，但 index_daily 仅覆盖 8 个——大部分申万/中证行业指数无日线数据
- 模型通过 `index_basic.name LIKE '%keyword%'` 做模糊匹配——仅当 name 匹配时才有效
- 6/9 缺失，6/11 仅 4 个，6/12 仅 1 个——T+1 延迟

**建议**：扩展 index_daily 覆盖至少申万一级行业指数（28 个）+ 主流概念指数

### 3.10 stk_factor_pro — 股票技术因子 🔴

**用途**：MA5/MA10/MACD 等技术指标（模型未直接查询此表，从 daily_kline 自行计算）

**关键发现**：
- **仅有 5 个交易日数据（5/26-6/5）**
- **ma5/ma10/macd 100% NULL** —— 列存在但从未被填充
- 表中有 30+ 列（含 kdj_k/rsi/boll 等），但实际写入的列集合与 PG schema 可能不匹配
- 模型使用 `get_kline_data` 从 daily_kline 自行计算 MA，不依赖此表——所以当前未影响选股
- 同步：L2 盘后 16:05 via `scheduler.py sync_stk_factor_pro_daily()`

**建议**：修复 stk_factor_pro 写入逻辑（列映射错误导致技术因子未填充）；或评估是否移除此表减少维护成本

### 3.11 daily_basic — 每日基本面 🟡

**用途**：流通市值 `float_mv`（实际模型从 stocks 表取 float_mv，非此表）

**关键发现**：
- 10.7M 行，覆盖 2016 年至今
- pe 14.88% NULL——小盘股/亏损股无 PE
- 近 30 天缺口：6/1=0, 6/5=0, 6/9=0，存在单日缺口
- 同步：L2 盘后 15:35 `sync_post_market_ext()`

**建议**：增加盘后重试机制覆盖单日缺口

### 3.12 moneyflow_hsgt — 沪深港通资金 🔴

**用途**：北向/南向资金流向（模型未直接使用）

**关键发现**：
- **north_net_inflow 和 south_net_inflow 100% NULL** —— 表有 2,716 行但所有资金数据为空
- 最新日期 6/3，9 天滞后
- 同步：L3 每周一 08:30 via `etl.py sync_moneyflow_hsgt()`
- Tushare `moneyflow_hsgt` API 可能变更了返回字段名

**建议**：排查 Tushare API 字段映射；确认 API 权限是否包含沪深港通数据

---

## 4. 数据采集代码审查

### 4.1 API 限频配置

| 组件 | 配置 | 评估 |
|------|------|------|
| `rate_limiter.py` | 滑动窗口 400 次/分钟 (Tushare 限额 500/min) | ✅ 留有 20% 安全边际 |
| `rt_min.py` | 批量 100 只/次，ThreadPool 8 workers | ✅ 约 55 次 API 调用 × 1/min |
| `tushare.py daily_kline` | 分页 5000/页，最多 10 页 | ✅ 单线程分页 |
| `tushare.py sync_post_market_core` | moneyflow + stk_limit 并行 2 workers | ✅ |
| `tushare.py index_daily` | 4 个指数逐个调用 | ⚠️ 应批量 `ts_code='000001.SH,399001.SZ,...'` 一次调用 |
| `stocks.py` | stock_basic 不计入限频 | ✅ 文档说明明确 |

### 4.2 错误处理

| 模式 | 位置 | 评估 |
|------|------|------|
| PG 写入失败 → SQLite fallback | `tushare.py`, `rt_min.py`, `stocks.py` | ✅ PG-first + SQLite 备份 |
| `_pg_write` 3 次指数退避重试 (1s/4s/16s) | `pg_writer.py:12-47` | ✅ ADR-006 决策 6 |
| `sync_post_market_core` 返回 dict 含 warning | `tushare.py:91` | ✅ 可观测 |
| 数据量门禁 (<1000 ERROR, <3000 WARN) | `pg_writer.py:50-58` | ✅ 异常检测 |
| rt_min 批次失败 → 继续下一批 (不阻塞) | `rt_min.py:48-49` | ⚠️ 静默丢弃，无重试 |
| ths_daily 3 次重试（2^n 秒退避） | `cb_sync.py:114-126` | ✅ |
| Model 层 SQL 异常 → `except Exception: pass` | `leader_intraday.py:894` | 🔴 吞掉所有异常，包括 ths_daily 列名错误 |

### 4.3 调度覆盖

| 分层 | 频率 | 覆盖表 | 缺口 |
|------|------|--------|------|
| L0 实时 | 每分钟 (9:30-15:00) | stk_mins | ✅ |
| L1 日内 | 每 30 分钟 | limit_list_d, 午间全量同步 | ✅ |
| L2 盘后 | 15:30-16:30 | daily_kline, moneyflow, stk_limit, daily_basic, ths_daily, index_daily, sw_daily, stk_factor_pro, limit_list_d | ⚠️ sw_daily 滞后 |
| L3 周级 | 每周一/六 | stocks, moneyflow_hsgt, cb_price_chg | ⚠️ moneyflow_hsgt 失效 |
| L4 回补 | 每日 04:00 | 自动检测 + 回补 | ⚠️ sw_daily 回补未触发 |

---

## 5. 问题清单

### P0 — 影响选股结果正确性

| ID | 问题 | 影响 | 修复建议 |
|----|------|------|----------|
| P0-1 | **ths_daily 列名 BUG**：模型查询 `pct_change`，PG 列名 `change_pct` | THS 概念板块路径完全失效，静默 fallback 到准确性较低的 index_daily 关键词匹配 | 修改 `leader_intraday.py:673` 将 `pct_change` 改为 `change_pct` |
| P0-2 | **stk_mins 6/1-6/4 数据缺口**：仅 39-1332 只股票 | 该期间选股结果不可用，回测数据不完整 | 排查采集日志，尝试从 Tushare 回补（rt_min 历史数据可能不可得） |
| P0-3 | **sw_daily 6/9-6/12 滞后 4 天**：板块行情 fallback 路径失效 | 当 THS 路径失败时，sw_daily fallback 也无数据，板块行情完全缺失 | 手动触发回补，排查 sync_sw_daily_batch 执行日志 |

### P1 — 影响数据完整性

| ID | 问题 | 影响 | 修复建议 |
|----|------|------|----------|
| P1-1 | **stk_factor_pro 100% NULL (MA/MACD)**：5 天数据但技术因子全空 | 表完全不可用——但模型不依赖此表，影响有限 | 修复 `write_stk_factor_pro` 列映射或评估移除此表 |
| P1-2 | **moneyflow_hsgt 100% NULL**：2,716 行全为空值 | 沪深港通资金流向数据完全不可用 | 排查 Tushare API 字段变更，更新 `etl.py` 字段映射 |
| P1-3 | **limit_list_d 仅 24 交易日**：历史覆盖不足 | 板块高潮检测的昨日涨停数统计在 5/12 前无法计算 | 回补至少 60 交易日历史数据 |
| P1-4 | **daily_kline change_pct 22.83% NULL** | 影响历史回测中的涨跌幅统计 | 从 close/pre_close 重新计算 change_pct |
| P1-5 | **moneyflow 单日缺口 (6/1, 6/12)** | 资金流向分析不完整 | 增加盘后重试 + L4 回补覆盖 |

### P2 — 改进建议

| ID | 问题 | 建议 |
|----|------|------|
| P2-1 | **index_daily 仅 8 个指数**：无法覆盖申万行业板块行情 | 扩展至申万一级 28 个行业指数 + 主流概念指数 |
| P2-2 | **ths_member 仅 200 只股票**：概念映射不足 | 扩展至至少 3000 只（ths_member API 全量拉取） |
| P2-3 | **stk_limit pre_close 历史遗留 99.57% NULL** | 从 daily_kline 回填历史 pre_close |
| P2-4 | **rt_min 批次失败静默丢弃** | 增加失败批次重试（至少 1 次） |
| P2-5 | **model 层静默异常吞没** (`except Exception: pass`) | 至少 log warning，关键路径（如板块行情查询失败）应告警 |
| P2-6 | **daily_kline 盘后同步过早 (15:30)** | 延后至 16:30 或增加 17:00 二次回补确保 T+1 数据就绪 |

---

## 6. 数据质量 SLA 现状

| 指标 | 目标 | 实际 | 达标 |
|------|------|------|------|
| 盘中快照新鲜度 (stk_mins) | < 5 分钟 | 1 分钟 | ✅ |
| 日线数据 T+1 就绪 (daily_kline) | < 24h | ~24h (偶有延迟) | ⚠️ |
| 涨停板数据实时性 (limit_list_d) | < 30 分钟 | 30 分钟 | ✅ |
| 板块行情数据新鲜度 | < 24h | **4 天 (sw_daily)** | ❌ |
| 技术因子完整性 | > 95% | **0%** | ❌ |
| 沪深港通数据可用性 | > 95% | **0%** | ❌ |
| 数据采集成功率 | > 99% | 未统计 | ⚠️ |

---

## 附录 A：查询方法说明

所有数据通过以下查询获取：

```sql
-- 表基本信息
SELECT MIN(date_col), MAX(date_col), COUNT(*), COUNT(DISTINCT code), COUNT(DISTINCT date_col)
FROM table_name;

-- 关键字段 NULL 率
SELECT ROUND(100.0 * SUM(CASE WHEN col IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2)
FROM table_name;

-- 30 天连续性
WITH dates AS (SELECT generate_series(CURRENT_DATE - 30, CURRENT_DATE, '1 day')::date AS dt)
SELECT d.dt, COUNT(DISTINCT code) FROM dates d LEFT JOIN table t ON t.date_col = d.dt GROUP BY d.dt;
```

## 附录 B：相关文件路径

| 文件 | 说明 |
|------|------|
| `packages/kronos-factors/kronos_factors/engine/leader_intraday.py` | 盘中选股模型主逻辑 |
| `services/data-service/app/sync/tushare.py` | 盘后批量同步（daily_kline/moneyflow/stk_limit/index_daily） |
| `services/data-service/app/sync/rt_min.py` | 实时分钟线采集 |
| `services/data-service/app/sync/stocks.py` | 股票列表同步 |
| `services/data-service/app/sync/pg_writer.py` | PG 批量写入 + 数据量门禁 |
| `services/data-service/app/sync/rate_limiter.py` | Tushare API 限频控制 |
| `services/data-service/app/sync/cb_sync.py` | 同花顺概念 + 可转债同步 |
| `services/data-service/app/scheduler.py` | 定时任务调度 + L4 回补 |
| `packages/kronos-data/kronos_data/etl.py` | ETL 回补函数（sw_daily / moneyflow_hsgt / stk_mins 等） |
