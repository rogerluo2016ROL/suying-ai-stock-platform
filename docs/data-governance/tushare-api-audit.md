# Tushare API 字段映射审计报告

> 审计日期：2026-06-13  
> 审计方法：ETL 写入代码 → PG Schema → 模型查询 SQL 三层逐字段对照  
> 审计范围：12 张核心表

---

## 1. 审计方法论

Tushare 官方文档为动态渲染页面，WebFetch 无法直接提取。采用**代码级逆向工程**：
```
Tushare API → ETL 采集代码(cols) → PG 实际列名 → 模型 SQL 查询列
```
对每张表执行三层逐字段对比，标注映射断层。

| 符号 | 含义 |
|:--:|------|
| ✅ | 三层一致，字段正常流通 |
| ⚠️ | 列名不一致 / 部分NULL |
| ❌ | 字段存在但 100% NULL / 不写 |

---

## 2. 逐表审计

### `stk_mins` ✅
PG 列: code/trade_time/open/high/low/close/volume/amount/freq
三层映射完全一致，数据完整度好。仅 6/1-6/4 数据缺口(已回补)。

### `daily_kline` ⚠️
`change_pct` 历史 22.83% NULL —— `tushare.py:sync_daily_kline()` 只写 OHLCV，`etl.py:sync_daily_kline()` 包含 `pct_chg` 但未纳入调度。两条采集路径字段不一致。
**模型影响**：模型从 `close/pre_close` 自行计算涨跌幅 → 低影响。

### `stocks` ✅
字段链路完整，`float_mv` 2.29% NULL（模型对 NULL 宽容）。

### `stk_limit` 🔴→🟡
`pre_close` 历史 99.57% NULL，6/1 起开始填充 → 近期已修复。

### `limit_list_d` ⚠️
双列冗余：`ts_code`(有值) + `code`(NULL)，`pct_chg`(有值) + `change_pct`(NULL)。
`first_time` 14% NULL，`fd_amount` 21% NULL。

### `moneyflow` ✅
字段链路完整。

### `ths_daily` 🔴(已修复)
P0-1: 模型曾查 `pct_change`，PG 列名 `change_pct` → 修复为 `change_pct`(`20dfb10`)。
Tushare API 返回 `pct_change`，`cb_sync.py` 写入时映射为 `change_pct` → 正确。

### `sw_daily` ⚠️
Tushare API 返回 `pct_change`，`etl.py` 写入时映射为 `change_pct` → 正确。
6/9-6/12 滞后 4 天(已回补 1,756 行)。

### `index_daily` 🔴 P0-1
**`etl.py:sync_index_daily()` 写 `pct_chg` 但 PG 列名是 `change_pct` → 列名不匹配！**
psycopg2 直接 INSERT `pct_chg` 到 PG 会失败(SQLite fallback 可能救了)。

### `stk_factor_pro` 🔴 P0-2
全部技术因子(ma5/ma10/macd/rsi/boll/kdj) **100% NULL**。
表有 21 列但写入逻辑与 PG schema 不匹配。模型不依赖此表 → 低影响。
**建议**：排查 `scheduler.py:sync_stk_factor_pro_daily()` 的 INSERT 列 vs API 返回字段，或评估移除此表。

### `daily_basic` ⚠️
字段链路完整。pe/pb 部分 NULL(亏损股无 PE)。单日缺口(T+1 延迟)。

### `moneyflow_hsgt` 🔴 P0-3
`north_net_inflow` 和 `south_net_inflow` **100% NULL**。
可能原因：Tushare API 字段名已变更 / 权限不足 / etl.py 字段映射错误。

---

## 3. 问题清单

### P0 — 数据完全不可用

| ID | 表 | 问题 | 修复 |
|----|------|------|------|
| P0-1 | `index_daily` | ETL写 `pct_chg`，PG列 `change_pct` | 改 etl.py |
| P0-2 | `stk_factor_pro` | 21列100% NULL | 排查写入 |
| P0-3 | `moneyflow_hsgt` | 资金数据100% NULL | 排查API |

### P1 — 影响完整性

| ID | 表 | 问题 | 建议 |
|----|------|------|------|
| P1-1 | `daily_kline` | 两条采集路径字段不一致 | 统一 |
| P1-2 | `limit_list_d` | 冗余列100% NULL | 清理 |
| P1-3 | `stk_limit` | pre_close 历史99.57% NULL | 回填 |

### P2 — 架构改进

| ID | 问题 | 建议 |
|----|------|------|
| P2-1 | PG Adapter 覆盖不全 | 消除翻译层 |
| P2-2 | `stk_factor_pro` 用 `ts_code` | 统一为 `code` |
| P2-3 | API 调用可合并 | index_daily 8→1 |

---

## 4. 更新时点偏差

| 表 | API 可用 | 调度时点 | 偏差 | 
|------|------|------|:--:|
| daily_kline | T+1 15:30-16:00 | 15:30 | ⚠️ 偏早 |
| moneyflow | T+1 16:00-17:00 | 15:30 | 🔴 过早 |
| daily_basic | T+1 18:00 | 15:35 | 🔴 过早 |
| ths_daily | T+1 18:00 | 16:00 | ⚠️ 偏早 |
| stk_factor_pro | T+1 18:00 | 16:05 | ⚠️ 偏早 |

---

## 5. 架构优化

1. **消除 PG Adapter 翻译层**：长期统一 ETL 写入列名为 PG 列名，移除 `_COLUMN_MAP`/`_KEY_MAP`
2. **API 批量调用**：`index_daily` 8 个指数合并为 1 次 `ts_code='000001.SH,...'`
3. **评估移除 `stk_factor_pro`**：模型自行计算技术指标，此表 100% NULL → 维护成本 > 价值
4. **调度时点后移**：`moneyflow` 15:30→17:00，`daily_basic` 15:35→19:00

## 6. 修复优先级

| 优先级 | 动作 | 工作量 |
|:--:|------|:--:|
| 🔴 | 修复 `index_daily` 列名 | 1行 |
| 🔴 | 排查 `stk_factor_pro` | 30min |
| 🔴 | 排查 `moneyflow_hsgt` | 30min |
| 🟡 | 调整调度时点 | 改 cron |
| 🟢 | 评估移除 `stk_factor_pro` | 讨论 |
