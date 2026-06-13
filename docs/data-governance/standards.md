# 数据治理规范 — 格式标准与质量规则

> 版本：1.0  
> 生效日期：2026-06-13  
> 适用范围：秋神盘中选股模型依赖的全部数据表（PG `kronos` 库）  
> 关联文档：`docs/data-governance/inventory.md`（盘点报告）、ADR-006（数据管道架构）

---

## 1. 列命名规范（Column Naming Convention）

### 1.1 规则概要

| 规则 ID | 规则 | 说明 |
|---------|------|------|
| CN-01 | 股票代码统一用 `code`（纯数字 6 位） | 禁止 `ts_code` 作为主列名 |
| CN-02 | 指数/概念代码允许 `code`（含后缀如 `883984.TI`） | 与股票 `code` 在同一表中时需显式注明 |
| CN-03 | 涨跌幅统一用 `change_pct` | 禁止 `pct_chg`、`pct_change` |
| CN-04 | 交易日统一用 `trade_date`，类型 `DATE` | 禁止 TEXT 类型存储日期 |
| CN-05 | 分钟级时间戳用 `trade_time`，类型 `TIMESTAMP` 或 ISO-8601 TEXT | 当前 TEXT 可接受，但需统一格式 |
| CN-06 | 金额统一用原始单位（元），列名后缀 `_amount` | 禁止用 `_yi` 等换算单位做列名 |

### 1.2 当前现状与违规清单

#### `code` vs `ts_code` 混用

| 表名 | 主列名 | 是否含后缀 | 违规 |
|------|--------|-----------|------|
| `stocks` | `code` | 否 (纯数字) | -- |
| `daily_kline` | `code` | 否 | -- |
| `stk_limit` | `code` | 否 | -- |
| `moneyflow` | `code` | 否 | -- |
| `daily_basic` | `code` | 否 | -- |
| `sw_daily` | `code` | 否 | -- |
| `index_daily` | `code` | 否 | -- |
| `index_basic` | `code` | 否 | -- |
| `stk_mins` | `code` | 否（PG） | -- |
| **`stk_factor_pro`** | `ts_code` | **是** (含 `.SH/.SZ/.BJ`) | 🔴 CN-01 |
| **`limit_list_d`** | 双列 `code` + `ts_code` | `ts_code` 含后缀 | 🟡 冗余 |
| **`ths_daily`** | `code` | 含后缀（概念指数 `.TI`） | 🟡 CN-02 例外 |
| **`ths_member`** | `ts_code` | 含后缀 | 🔴 CN-01 |

**PG Adapter 翻译层**（`pg_adapter.py:70-73`）：
```python
_COLUMN_MAP = {"pct_chg": "change_pct", "ts_code": "code"}
_KEY_MAP = {"change_pct": "pct_chg"}
```
该映射在 SQL→PG 查询时自动将 `ts_code`→`code`、`pct_chg`→`change_pct`，查询结果中再将 `change_pct`→`pct_chg` 反向翻译。这是一个**技术债务层**，长期目标应是消除该映射。

#### `change_pct` vs `pct_chg` vs `pct_change` 混用

| 表名 | 实际列名 | 备注 |
|------|---------|------|
| `daily_kline` | `change_pct` | 22.83% NULL（历史退市股） |
| `index_daily` | `change_pct` | 映射为 `pct_chg`（pg_writer 写入时） |
| `sw_daily` | `change_pct` | -- |
| `ths_daily` | `change_pct` | **模型代码误用 `pct_change`** ← P0-1 BUG |
| `limit_list_d` | `change_pct` (NULL) / `pct_chg` (有值) | **双列冗余**，`change_pct` 100% NULL |
| `stk_factor_pro` | 含 `pct_chg` 列 | 写入列映射可能错位 |

**关键 BUG**：`leader_intraday.py:673` 查询 `ths_daily` 时使用 `pct_change`，而 PG 实际列名为 `change_pct`。该查询静默失败（`except Exception: pass`），导致同花顺概念板块路径完全失效，跌落到准确度较低的 `index_daily` 关键词匹配路径。

#### 日期列类型不一致

| 表名 | 日期列 | PG 类型 | 格式 |
|------|--------|---------|------|
| `daily_kline` | `trade_date` | `DATE` | 原生日期 |
| `stk_limit` | `trade_date` | `DATE` | 原生日期 |
| `moneyflow` | `trade_date` | `DATE` | 原生日期 |
| `daily_basic` | `trade_date` | `DATE` | 原生日期 |
| `index_daily` | `trade_date` | `DATE` | 原生日期 |
| `sw_daily` | `trade_date` | `DATE` | 原生日期 |
| **`stk_mins`** | `trade_time` | **TEXT** | `YYYY-MM-DD HH:MM:SS` |
| **`limit_list_d`** | `trade_date` | **TEXT** | `YYYYMMDD` |
| **`ths_daily`** | `trade_date` | **TEXT** | `YYYYMMDD` |
| **`stk_factor_pro`** | `trade_date` | **TEXT** | `YYYYMMDD` |

**影响**：TEXT 存储的 `trade_date` 需要应用层转换（`d.replace('-','')` ↔ `f"{d[:4]}-{d[4:6]}-{d[6:8]}"`），增加 JOIN 复杂度和出错概率。`pg_writer.py` 中的 `write_limit_list_d`、`write_ths_daily` 均在做此转换。

---

## 2. NULL 处理规范（NULL Handling Standards）

### 2.1 分级策略

| 级别 | 场景 | 处理方式 | 示例 |
|------|------|---------|------|
| **L0 致命** | 主键或核心过滤字段 NULL | **拒绝入库**，触发告警 | `daily_kline.code IS NULL` |
| **L1 关键** | 选股模型直接使用字段 NULL | **替换为安全默认值** + log warning | `pre_close` → 从 `daily_kline` 回退 |
| **L2 重要** | 模型间接引用字段 NULL | **标记跳过**，不影响其他计算 | `stk_limit.pre_close` 99.57% NULL → 模型已正确 fallback |
| **L3 可容忍** | 展示/辅助字段 NULL | 正常通过，下游自行处理 | `daily_basic.pe` 14.88% NULL（亏损股无 PE） |

### 2.2 当前模型中的 NULL 处理模式（`leader_intraday.py`）

```python
# 模式 A: 显式守卫（推荐）
if close_14 <= 0 or pre_close <= 0:
    return None  # 明确跳过

# 模式 B: OR 兜底（推荐）
float(r["open"] or 0)  # None → 0

# 模式 C: IS NULL 宽容（可接受）
float_mv IS NULL OR float_mv >= 20  # NULL 视为通过

# 模式 D: 静默吞异常（反模式，禁止）
except Exception:
    pass  # 吞掉列名 BUG 等关键错误

# 模式 E: 双源 fallback（正确）
raw_code = r.get("code") or r.get("ts_code","")  # 防御两种列名
```

### 2.3 强制规则

| 规则 ID | 规则 | 违规后果 |
|---------|------|---------|
| NH-01 | 价格/成交量字段 NULL 不得静默转为 0 — 必须显式守卫 `if x <= 0: return None` | 假数据通过筛选 |
| NH-02 | pre_close 缺失时按 `daily_kline 前日 close → stk_limit.pre_close` 优先级 fallback | 选股缺基准价 |
| NH-03 | float_mv 过滤必须对 NULL 宽容（`IS NULL OR >= N`） | 误杀无市值数据的新股 |
| NH-04 | 不得用 `except Exception: pass` 吞掉查询异常 — 至少 `logger.debug()` | 静默数据损坏 |
| NH-05 | PG adapter 对 `UndefinedColumn`/`UndefinedTable` 做 `_EmptyCursor` 降级时，必须 `logger.debug()` 记录 | 无法追溯 fallback |

---

## 3. 类型转换规则（Type Casting Rules）

### 3.1 股票代码

```
Tushare 格式 (ts_code)  →  PG 格式 (code)
===========================================
"000001.SZ"              →  "000001"
"600519.SH"              →  "600519"
"688981.SH"              →  "688981"
"430047.BJ"              →  "430047"
```

**转换入口**：
- `tushare.py:_code_from_ts()` — `ts_code.split(".")[0][:6]`
- `pg_writer.py:write_stk_mins()` — `ts_code.split(".")[0][:6]`
- `rt_min.py:_ts_code()` — 反向转换 `code → ts_code`（按首字母判断交易所）

### 3.2 交易日

```
Tushare 格式         →  PG DATE 格式        →  模型 SQL 格式
================================================================
"20260612"            →  DATE '2026-06-12'   →  "2026-06-12"
"20260612" (TEXT)     →  TEXT '20260612'     →  "20260612"  ← limit_list_d/ths_daily
```

**问题**：`limit_list_d.trade_date` 和 `ths_daily.trade_date` 存储为 TEXT `YYYYMMDD`，模型查询时需手动拼接：
```python
td = trade_date.replace('-', '')  # "2026-06-12" → "20260612"
# 用于 limit_list_d WHERE trade_date=? 
```

### 3.3 涨跌幅

```
Tushare 原始  →  PG 存储      →  模型计算
============================================
pct_chg (API) → change_pct    → gain_14 = (close/pre_close-1)*100
pct_change    → change_pct    → 列名不一致导致查询失败 (BUG)
```

**验证公式**（任何表中的 `change_pct` 应满足）：
```sql
ABS(change_pct - (close / pre_close - 1) * 100) < 0.01
```

### 3.4 成交额单位

```
Tushare API  →  PG 存储 (元)  →  模型展示 (亿元)
===================================================
amount (元)   →  DOUBLE (元)   →  / 1e8
vol (手)      →  DOUBLE (手)   →  原始
```

---

## 4. 数据质量校验规则

### 4.1 单表关键字段完整性

每张表的必检字段及阈值：

| 表名 | 必检字段 | 允许 NULL 率上限 | 当前实际 | 达标 |
|------|---------|-----------------|---------|------|
| `stk_mins` | open, high, low, close, volume, amount | <0.1% | 0% | ✅ |
| `daily_kline` | open, high, low, close, volume, amount | <1% | 0% | ✅ |
| `daily_kline` | change_pct（近1年） | <5% | ~5% | 🟡 |
| `stocks` | code, name, is_st | 0% | 0% | ✅ |
| `stocks` | industry | <5% | 1.95% | ✅ |
| `stk_limit` | pre_close（近30天） | <1% | 0%（6/12） | ✅ |
| `limit_list_d` | pct_chg | <5% | 0%（pct_chg 有值） | ✅ |
| `limit_list_d` | fd_amount | <30% | 21% | 🟡 |
| `limit_list_d` | first_time | <20% | 14% | ✅ |
| `moneyflow` | net_mf_amount（近1年） | <10% | ~5% | ✅ |
| `ths_daily` | change_pct | <5% | 0% | ✅ |
| `sw_daily` | change_pct | <5% | 0% | ✅ |
| `index_daily` | change_pct | <5% | 0% | ✅ |
| `stk_factor_pro` | ma5, ma10, macd | <5% | **100%** | 🔴 |
| `daily_basic` | pe, pb, total_mv, circ_mv | pe<20%, 其他<5% | pe 14.88% | ✅ |
| `moneyflow_hsgt` | north_net_inflow, south_net_inflow | <10% | **100%** | 🔴 |

### 4.2 跨表一致性检验

| 规则 ID | 检验内容 | SQL | 允许偏差 |
|---------|---------|-----|---------|
| CC-01 | stocks.code 覆盖 daily_kline.code | `SELECT code FROM stocks EXCEPT SELECT DISTINCT code FROM daily_kline` | 新股可缺 |
| CC-02 | stk_mins.code 在 stocks 中存在 | `SELECT DISTINCT code FROM stk_mins WHERE code NOT IN (SELECT code FROM stocks)` | < 10 只 |
| CC-03 | daily_kline.change_pct 与计算值一致 | `ABS(change_pct - (close/lag(close)-1)*100)` | < 0.01 |
| CC-04 | stk_limit.up_limit 计算正确 | `up_limit = ROUND(pre_close * 1.10, 2)` (A股主板) | < 0.02 |
| CC-05 | limit_list_d.pct_chg 在合理区间 | `pct_chg >= 9.5` (涨停) 或 `pct_chg <= -9.5` (跌停) | 允许 ±0.5% |
| CC-06 | ths_member.ts_code 在 stocks 中存在 | `SELECT DISTINCT ts_code FROM ths_member WHERE ts_code NOT IN (SELECT code\|'.'\|market FROM stocks)` | 当前仅 200 只 |

### 4.3 每日数据完整性检查（已实现于 `scheduler.py:detect_data_gaps`）

```python
MONITORED_TABLES = {
    "stk_mins":       {"date_col": "trade_time",  "gap_threshold": 1},
    "daily_kline":    {"date_col": "trade_date",  "gap_threshold": 1},
    "moneyflow":      {"date_col": "trade_date",  "gap_threshold": 1},
    "stk_limit":      {"date_col": "trade_date",  "gap_threshold": 1},
    "daily_basic":    {"date_col": "trade_date",  "gap_threshold": 1},
    "ths_daily":      {"date_col": "trade_date",  "gap_threshold": 1},
    "sw_daily":       {"date_col": "trade_date",  "gap_threshold": 2},
    "index_daily":    {"date_col": "trade_date",  "gap_threshold": 1},
    "stk_factor_pro": {"date_col": "trade_date",  "gap_threshold": 2},
    "limit_list_d":   {"date_col": "trade_date",  "gap_threshold": 1},
    "moneyflow_hsgt": {"date_col": "trade_date",  "gap_threshold": 5},
    "stocks":         {"date_col": "updated_at",  "gap_threshold": 7},
}
```

### 4.4 数据量门禁（已实现于 `pg_writer.py:_check_data_volume`）

| 表名 | 正常日写入量 | 告警阈值 | 错误阈值 |
|------|------------|---------|---------|
| `daily_kline` | ~5500 | <3000 | <1000 |
| `stk_mins` | ~5000 | <3000 | <1000 |
| `moneyflow` | ~5000 | -- | -- |
| `stk_limit` | ~7600 | -- | -- |
| `daily_basic` | ~5500 | -- | -- |

---

## 5. 涨跌幅计算验证规范

### 5.1 公式标准

```
change_pct = (close / pre_close - 1) × 100

其中：
  pre_close = 前一个交易日收盘价（已复权）
  close     = 当日收盘价（已复权）
```

### 5.2 模型中的涨跌幅计算（`leader_intraday.py`）

```python
# 盘中涨幅 — 14:40 快照 vs 前收价
gain_14 = (snap["close"] / pre_close - 1) * 100

# pre_close 来源 — 从 daily_kline 前日 close 获取
pre_closes = get_pre_close_map(db, trade_date)
# 实现：daily_kline 表前日 close，而非 stk_limit.pre_close

# 涨停价计算 — 按板块差异化
if code.startswith(('8','9','4')):   limit_pct = 1.30  # 北交所 30%
elif code.startswith('688'):          limit_pct = 1.20  # 科创板 20%
else:                                 limit_pct = 1.10  # 主板 10%
limit_price = pre_close * limit_pct
```

### 5.3 板块涨跌幅优先级

```
get_sector_index(code, industry, trade_date):
  1. ths_daily.change_pct  (JOIN ths_member, psycopg2 raw query)
     └─ 失败 → fallback
  2. index_daily.change_pct (JOIN index_basic, name LIKE '%keyword%')
     └─ 失败 → fallback
  3. return 0 (无板块数据)
```

---

## 6. 数据采集规范

### 6.1 幂等性要求

| 规则 ID | 规则 | 实现方式 |
|---------|------|---------|
| IM-01 | 所有写入使用 `INSERT ... ON CONFLICT DO NOTHING` | `pg_writer.py:_pg_write()` |
| IM-02 | rt_min 按 `(code, trade_time, freq)` 去重 | UNIQUE 约束 |
| IM-03 | 日线按 `(code, trade_date)` 去重 | UNIQUE 约束 |
| IM-04 | 重跑不产生重复数据 | ON CONFLICT DO NOTHING 保证 |

### 6.2 限频规范（`rate_limiter.py`）

```
Tushare 配额：500 次/分钟
安全上限：  400 次/分钟（20% 边际）
限频算法：  滑动窗口（60 秒），超限时 sleep 至窗口重置
线程安全：  threading.Lock
```

### 6.3 写入路径规范

```
主路径：PG 直写（psycopg2, ON CONFLICT DO NOTHING, 3 次指数退避重试）
  └─ 失败 → fallback
备用路径：SQLite 写入（INSERT OR REPLACE）
```

### 6.4 重试策略

```
指数退避：1s → 4s → 16s（最多 3 次）
触发条件：psycopg2.OperationalError
不可重试：UndefinedColumn / UndefinedTable → 静默降级 + debug log
```

---

## 7. Schema 演化规范

### 7.1 新增列

1. 必须 `ALTER TABLE ... ADD COLUMN` 且带 `DEFAULT NULL`
2. 同步更新 `pg_writer.py` 中的 `_pg_write` 列清单
3. 同步更新 `.claude/standards/coding.md` 中的表结构文档
4. 新增列不得破坏现有模型的 `SELECT *` 假设

### 7.2 列重命名

1. **禁止直接 RENAME** — 破坏现有模型查询
2. 正确做法：ADD 新列 → 迁移数据 → 修改模型代码 → DROP 旧列
3. 必须更新 `pg_adapter.py:_COLUMN_MAP` 和 `_KEY_MAP`

### 7.3 Schema 漂移告警

当 Tushare API 返回字段发生变化时：
1. `rate_limiter.py` 正常执行不阻塞
2. 写入行数为 0 时触发 `_check_data_volume` 门禁
3. `detect_data_gaps` 在次日 04:00 检测到滞后 → 告警
4. **缺失**：无主动字段级 schema 校验（需增加 Great Expectations / JSON Schema 校验层）

---

## 8. 规范合规检查清单

数据工程师在每次数据采集代码变更后必须自查：

- [ ] CN-01：新增表是否使用 `code` 而非 `ts_code`
- [ ] CN-03：涨跌幅列名统一为 `change_pct`
- [ ] CN-04：日期列使用 `DATE` 类型，非 TEXT
- [ ] NH-01：价格字段 NULL 有显式守卫
- [ ] NH-04：SQL 异常不被静默吞掉
- [ ] IM-01：INSERT 使用 ON CONFLICT DO NOTHING
- [ ] 写入量门禁 `_check_data_volume` 覆盖新增表
- [ ] `MONITORED_TABLES` 中注册新增表
- [ ] `_BACKFILL_MAP` 中注册回补函数（如适用）
- [ ] `pg_adapter.py:_COLUMN_MAP` 检查是否需要新增翻译

---

## 附录 A：已知技术债务清单

| ID | 债务项 | 优先级 | 修复方向 |
|----|--------|--------|---------|
| TD-01 | `stk_factor_pro.ts_code` 应为 `code` | P2 | 同 stk_mins 的 pg_writer 翻译模式 |
| TD-02 | `limit_list_d` 双列 `change_pct`(NULL) + `pct_chg`(有值) | P1 | 合并为单一 `change_pct`，回填历史 |
| TD-03 | `limit_list_d.trade_date` TEXT → DATE | P1 | 需同步修改模型代码中的 `replace('-','')` |
| TD-04 | `ths_daily.trade_date` TEXT → DATE | P2 | 同上 |
| TD-05 | `stk_factor_pro.trade_date` TEXT → DATE | P3 | 表可能废弃 |
| TD-06 | pg_adapter `_COLUMN_MAP` 翻译层消除 | P3 | 所有表统一列名后移除 |
| TD-07 | `leader_intraday.py:673` `pct_change` → `change_pct` | **P0** | 立即修复 |

## 附录 B：相关代码位置

| 文件 | 关联规则 |
|------|---------|
| `packages/kronos-factors/kronos_factors/pg_adapter.py:70-73` | CN-01, CN-03, TD-06 (列名翻译) |
| `packages/kronos-factors/kronos_factors/engine/leader_intraday.py:673-678` | CN-03, TD-07 (pct_change BUG) |
| `services/data-service/app/sync/pg_writer.py:63-165` | CN-01, IM-01 (ts_code→code 转换) |
| `services/data-service/app/sync/tushare.py:24-25` | CN-01 (_code_from_ts) |
| `services/data-service/app/sync/rt_min.py:13-17` | CN-01 (_ts_code 反向转换) |
| `services/data-service/app/sync/pg_writer.py:50-58` | 4.4 数据量门禁 |
| `services/data-service/app/scheduler.py:38-67` | 4.3 每日完整性检查 |
| `services/data-service/app/sync/rate_limiter.py` | 6.2 限频规范 |
| `services/data-service/app/sync/pg_writer.py:12-47` | 6.4 重试策略 |
