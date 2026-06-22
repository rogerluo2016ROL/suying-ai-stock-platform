# Path #4 inline executemany 盘点报告

> 日期: 2026-06-22 | 生成: `services/sql/audit/path4_survey.py` | ADR-015 §决策 0-6

## §1 候选模块清单

实测: **13** 模块（12 dual + 0 SQLite-only + 1 PG-only）

| 模块 | 源文件 | 主表 | 目标 | executemany | 风险 |
|---|---|---|---|---|---|
| announcements | services/data-service/app/sync/announcements.py | announcements | dual | L89 | low |
| cctv_news | services/data-service/app/sync/cctv_news.py | cctv_news | dual | L85 | low |
| mp_report | services/data-service/app/sync/mp_report.py | mp_report | dual | L84 | low |
| interact | services/data-service/app/sync/interact.py | interact_qa | dual | L133 | low |
| policy_law | services/data-service/app/sync/policy_law.py | policy_law | dual | L147 | low |
| fina_mainbz | services/data-service/app/sync/fina_mainbz.py | fina_mainbz | dual | L106 | low |
| fina_audit | services/data-service/app/sync/fina_audit.py | fina_audit | dual | L148 | low |
| stock_profiles | services/data-service/app/sync/stock_profiles.py | stock_profiles | dual | L105 | high |
| namechange | services/data-service/app/sync/namechange.py | st_history | pg-only | L123 | medium |
| stocks | services/data-service/app/sync/stocks.py | stocks | dual | L85, L160 | high |
| rt_min | services/data-service/app/sync/rt_min.py | stk_mins | dual | L91 | low |
| tushare | services/data-service/app/sync/tushare.py | daily_kline | dual | L66, L186, L194 | medium |
| etl_rt_k | packages/kronos-data/kronos_data/etl.py | rt_k | dual | none | low |


## §2 维度盘点矩阵

| 模块 | 目标 | PG 路径 | SQLite 路径 | PG 表 | 列 | sync 函数 | executemany | 风险 |
|---|---|---|---|---|---|---|---|---|
| announcements | dual | _pg_write | inline-executemany | Yes | 5 | sync_announcements | L89 | low |
| cctv_news | dual | _pg_write | inline-executemany | Yes | 5 | sync_cctv_news | L85 | low |
| mp_report | dual | _pg_write | inline-executemany | Yes | 6 | sync_mp_report | L84 | low |
| interact | dual | _pg_write | inline-executemany | Yes | 7 | sync_interact_qa | L133 | low |
| policy_law | dual | _pg_write | inline-executemany | Yes | 8 | sync_policy_law | L147 | low |
| fina_mainbz | dual | _pg_write | inline-executemany | Yes | 6 | sync_fina_mainbz | L106 | low |
| fina_audit | dual | _pg_write | inline-executemany | Yes | 7 | sync_fina_audit | L148 | low |
| stock_profiles | dual | inline-execute_values | inline-executemany | Yes | 16 | sync_stock_profiles | L105 | high |
| namechange | pg-only | inline-cursor | inline-executemany | Yes | 5 | sync_st_history | L123 | medium |
| stocks | dual | inline-cursor | inline-executemany | Yes | 11 | sync_stock_list, sync_stocks_incremental | L85, L160 | high |
| rt_min | dual | _pg_write (via thin wrapper) | inline-executemany | Yes | 10 | collect_rt_min, collect_auction_snapshot | L91 | low |
| tushare | dual | _pg_write (via thin wrapper) | inline-executemany | Yes | 12 | sync_daily_kline, sync_single_table, sync_post_market_core... | L66, L186, L194, L265 | medium |
| etl_rt_k | dual | inline-execute_values | inline-execute | Yes | 12 | sync_rt_k, sync_rt_sw_k | none | low |


### 逐模块详情

### announcements

- 文件: `services/data-service/app/sync/announcements.py`
- 主表: `announcements` (PG: 存在, 5 列)
- 目标: **dual** | PG: `_pg_write` | SQLite: `inline-executemany`
- executemany: L89
- 风险: **low** | 优先级: **P2**

### cctv_news

- 文件: `services/data-service/app/sync/cctv_news.py`
- 主表: `cctv_news` (PG: 存在, 5 列)
- 目标: **dual** | PG: `_pg_write` | SQLite: `inline-executemany`
- executemany: L85
- 风险: **low** | 优先级: **P2**

### mp_report

- 文件: `services/data-service/app/sync/mp_report.py`
- 主表: `mp_report` (PG: 存在, 6 列)
- 目标: **dual** | PG: `_pg_write` | SQLite: `inline-executemany`
- executemany: L84
- 风险: **low** | 优先级: **P2**

### interact

- 文件: `services/data-service/app/sync/interact.py`
- 主表: `interact_qa` (PG: 存在, 7 列)
- 目标: **dual** | PG: `_pg_write` | SQLite: `inline-executemany`
- executemany: L133
- 风险: **low** | 优先级: **P2**

### policy_law

- 文件: `services/data-service/app/sync/policy_law.py`
- 主表: `policy_law` (PG: 存在, 8 列)
- 目标: **dual** | PG: `_pg_write` | SQLite: `inline-executemany`
- executemany: L147
- 风险: **low** | 优先级: **P2**

### fina_mainbz

- 文件: `services/data-service/app/sync/fina_mainbz.py`
- 主表: `fina_mainbz` (PG: 存在, 6 列)
- 目标: **dual** | PG: `_pg_write` | SQLite: `inline-executemany`
- executemany: L106
- 风险: **low** | 优先级: **P2**

### fina_audit

- 文件: `services/data-service/app/sync/fina_audit.py`
- 主表: `fina_audit` (PG: 存在, 7 列)
- 目标: **dual** | PG: `_pg_write` | SQLite: `inline-executemany`
- executemany: L148
- 风险: **low** | 优先级: **P2**

### stock_profiles

- 文件: `services/data-service/app/sync/stock_profiles.py`
- 主表: `stock_profiles` (PG: 存在, 16 列)
- 目标: **dual** | PG: `inline-execute_values` | SQLite: `inline-executemany`
- executemany: L105
- 风险: **high** | 优先级: **P2**

### namechange

- 文件: `services/data-service/app/sync/namechange.py`
- 主表: `st_history` (PG: 存在, 5 列)
- 目标: **pg-only** | PG: `inline-cursor` | SQLite: `inline-executemany`
- executemany: L123
- 风险: **medium** | 优先级: **P3**

### stocks

- 文件: `services/data-service/app/sync/stocks.py`
- 主表: `stocks` (PG: 存在, 11 列)
- 目标: **dual** | PG: `inline-cursor` | SQLite: `inline-executemany`
- executemany: L85, L160
- 风险: **high** | 优先级: **P1**

### rt_min

- 文件: `services/data-service/app/sync/rt_min.py`
- 主表: `stk_mins` (PG: 存在, 10 列)
- 目标: **dual** | PG: `_pg_write (via thin wrapper)` | SQLite: `inline-executemany`
- executemany: L91
- 风险: **low** | 优先级: **excluded**

### tushare

- 文件: `services/data-service/app/sync/tushare.py`
- 主表: `daily_kline` (PG: 存在, 12 列)
- 目标: **dual** | PG: `_pg_write (via thin wrapper)` | SQLite: `inline-executemany`
- executemany: L66, L186, L194, L265
- 风险: **medium** | 优先级: **P1**

### etl_rt_k

- 文件: `packages/kronos-data/kronos_data/etl.py`
- 主表: `rt_k` (PG: 存在, 12 列)
- 目标: **dual** | PG: `inline-execute_values` | SQLite: `inline-execute`
- executemany: none
- 风险: **low** | 优先级: **excluded**



## §3 风险评估

| 模块 | 列错位风险 | PG _pg_write | 需 upsert | 优先级 |
|---|---|---|---|---|
| announcements | low | Yes | No | P2 |
| cctv_news | low | Yes | No | P2 |
| mp_report | low | Yes | No | P2 |
| interact | low | Yes | No | P2 |
| policy_law | low | Yes | No | P2 |
| fina_mainbz | low | Yes | No | P2 |
| fina_audit | low | Yes | No | P2 |
| stock_profiles | high | No | Yes | P2 |
| namechange | medium | No | Yes | P3 |
| stocks | high | No | Yes | P1 |
| rt_min | low | No | No | excluded |
| tushare | medium | No | No | P1 |
| etl_rt_k | low | No | No | excluded |


## §4 ADR-012 兼容性

| 模块 | 兼容性评估 |
|---|---|
| announcements | PG 已走 _pg_write 主干 — 可直接切换，SQLite 侧沿用 inline executemany（方案 A 预期行为） |
| cctv_news | PG 已走 _pg_write 主干 — 可直接切换，SQLite 侧沿用 inline executemany（方案 A 预期行为） |
| mp_report | PG 已走 _pg_write 主干 — 可直接切换，SQLite 侧沿用 inline executemany（方案 A 预期行为） |
| interact | PG 已走 _pg_write 主干 — 可直接切换，SQLite 侧沿用 inline executemany（方案 A 预期行为） |
| policy_law | PG 已走 _pg_write 主干 — 可直接切换，SQLite 侧沿用 inline executemany（方案 A 预期行为） |
| fina_mainbz | PG 已走 _pg_write 主干 — 可直接切换，SQLite 侧沿用 inline executemany（方案 A 预期行为） |
| fina_audit | PG 已走 _pg_write 主干 — 可直接切换，SQLite 侧沿用 inline executemany（方案 A 预期行为） |
| stock_profiles | 需 upsert 扩展 — PG 当前 execute_values + ON CONFLICT DO update，SQLite 列子集（6/15） |
| namechange | 需 upsert 扩展 — PG 当前 cur.executemany + ON CONFLICT DO update，无 SQLite 路径 |
| stocks | 需 upsert 扩展（ADR-015.0 前置）— PG 当前单条 cur.execute 循环 + ON CONFLICT DO update，不兼容 _pg_write |
| rt_min | PG 已走 write_stk_mins thin wrapper，SQLite 为 best-effort backup — 低优先级 |
| tushare | PG 已全走 pg_writer thin wrapper，SQLite executemany 为 fallback — 需确认 insert-or-replace 语义兼容 |
| etl_rt_k | kronos-data etl 通过 _get_etl_db() 统一 PG/SQLite，非 path #4 治理范围 |


**关键**: stocks/stock_profiles/namechange 需 upsert 语义 → ADR-015.0 前置; 7 模块可直接切换 _pg_write

## §5 子 ADR-015.X 推荐清单

| 优先级 | 模块 | 子 ADR | 工作量 | 备注 |
|---|---|---|---|---|
| P0 (前置) | `_pg_write` upsert 扩展 | **ADR-015.0** | 0.5d | 阻断 P1 stocks.py |
| P1 | stocks | ADR-015.1 | 1-2d | high risk |
| P1 | tushare | ADR-015.2 | 1-2d | medium risk |
| P2 | announcements/cctv_news/mp_report/policy_law (合并) | ADR-015.3 | 1-2d | 4 模块同参数签名 |
| P2 | fina_mainbz/fina_audit/stock_profiles (合并) | ADR-015.4 | 1-2d | fina_* 同型, stock_profiles 需 upsert |
| P3 | namechange | ADR-015.5 | 0.5d | PG-only inline, 最小改动 |


子 ADR 数: 5（含 ADR-015.0）。实施: P0 → P1(stocks/tushare) → P2(公告+财务) → P3(namechange)

## §6 排除模块清单

| 模块 | 表 | 目标 | 排除理由 |
|---|---|---|---|
| rt_min | stk_mins | dual | 实时分钟线 PG 已走 write_stk_mins thin wrapper，SQLite 为 best-effort backup |
| etl_rt_k | rt_k | dual | kronos-data etl 通过 _get_etl_db() 统一 PG/SQLite，非 path #4 治理范围 |


引用: ADR-012 §决策 0 + ADR-015 §决策 0-6 + 方案 A + 基线 2026-06-22
