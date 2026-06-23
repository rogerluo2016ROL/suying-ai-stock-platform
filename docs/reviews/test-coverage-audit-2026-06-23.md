# 测试覆盖审计报告 — 微服务层

> **来源**：2026-06-23 codegraph 驱动的测试覆盖扫描（`codegraph explore` 的 `⚠️ no covering tests found` 标注 + 测试密度统计）。
> **范围**：`services/` 下 13 个微服务。不含 `packages/`（kronos-data/factors/core 有独立测试）、`backend/`（auth，另有测试）。
> **结论一句话**：13 个微服务里 **7 个零测试、3 个测试稀少**，仅 `training-service` 有像样覆盖。这是系统性测试覆盖危机，不是单点问题。

---

## 1. 全局测试密度地图

| 优先级 | 服务 | app源码/测试 | 风险定位 |
|---|---|---|---|
| 🔴 P0 | **data-service** | 19 / 0 | 数据管道全链路依赖 + 已知写入 bug（见 §3） |
| 🔴 P0 | **trade-service** | 11 / 2* | 资金计算，3 个 money bug 已立案（见 §2） |
| 🟠 P1 | strategy-service | 6 / 1 | 自动交易执行（`auto_trading_executor`），资金相关 |
| 🟠 P1 | backtest-service | 4 / 0 | 回测正确性 → 直接影响策略结论（bi_trend 样本外亏损排查依赖回测可信） |
| 🟡 P2 | screener-service | 11 / 1 | 选股引擎（6 模式），量化核心 |
| 🟡 P2 | signal-service | 5 / 0 | 综合信号（50 维） |
| 🟡 P2 | diagnosis-service | 8 / 0 | 五维诊断，面向用户，错则误导 |
| ⚪ P3 | prediction-service | 3 / 0 | Kronos 预测（调外部托管模型，本地逻辑薄） |
| ⚪ P3 | alert-service | 4 / 0 | 预警，非资金核心 |
| ⚪ P3 | api-gateway | 1 / 0 | 网关，1 文件薄层 |
| 🟢 | training-service | 11 / 5 | 唯一像样覆盖，作为基准 |

*trade-service 的 2 个测试含本次新增的 `test_engine_accounting.py`（3 红立案）。

---

## 2. 深挖 A — trade-service（资金计算，3 bug 已立案 ✅）

- **入口**：`codegraph impact BrokerInterface` → 103 受影响符号；`codegraph explore place_order` 标 `⚠️ no covering tests found`
- **结果**：读 `engine.py`（135 行）挖出 3 个 P0 资金 bug，红测试已立案（1 绿 3 红，每处凭空产生 5000 = 50股×100元）：
  - **B1 卖空**：卖不存在持仓 → `available`/`total_capital` 凭空虚增（`place_order` L82 先加钱，`_update_position_sell` L111 无持仓静默跳过）
  - **B2 超卖**：卖量 > 持仓 → pnl 按 `min()` 算但 volume 减全量，超卖部分钱进 `available`
  - **B3 非法方向**：非 BUY/SELL 走 `else` 当 SELL
- **产物**：`services/trade-service/tests/TEST_PLAN_engine.md`（20+ 用例矩阵 + 4 个次要发现 B4-B7）、`tests/test_engine_accounting.py`（红测试）
- **状态**：🔴 待修复（走 backend-dev Plan Mode + tech-lead review，见 §4）

---

## 3. 深挖 B — data-service（数据管道，19 文件 0 测试）

- **结构**：`sync/` 14 个同步模块（公告/可转债/新闻/审计/财报/实时分钟/股票…）+ `pg_writer.py` + `scheduler.py` + `tushare.py` + `rate_limiter.py`。每个 sync = 一个"抓取→映射→写 PG"管道任务。
- **写入枢纽**：`_pg_write`（`pg_writer.py:35`）—— **23 个调用方**（scheduler + 12 个 sync 模块），`codegraph explore` 标 `⚠️ no covering tests found`。
- **复用边界（精确缺口）**：
  - `_pg_write` 是 **thin wrapper**（ADR-012 §5.2），delegate 给 `kronos_data.etl._insert_rows`（`pg_writer.py:76`）
  - **底层 `_insert_rows` 有测试** ✓（`packages/kronos-data/tests/test_insert_rows_upsert.py`，见 memory `[[pg-write-path-unified]]`）
  - **但 wrapper 层 + 9 个 `write_xxx`（write_stk_mins/moneyflow/stk_limit/ths_daily…）0 测试** ✗ —— 这层做 `ts_code→code` 映射（`ts_code.split(".")[0][:6]`）、表名列路由、空数据处理
- **关联已知债**：memory `[[data-pipeline-write-debt]]` 记录的 bug（cyq/pledge 的 `r[code]`、rt_sw_k/sw_daily 缺核心列）**正出在 write_xxx 的列映射层** —— 0 测试 + 已知 bug 同层，风险已实证，非推测。
- **建议优先补**：①`_pg_write` wrapper 的 conflict_action/列过滤透传；②9 个 write_xxx 的列映射正确性（每表一个：ts_code→code、列名对齐 PG schema、空 rows 早退）；③`rate_limiter`（Tushare 限流，错了触发 API 封禁）。

---

## 4. 建议与流程

1. **分优先级、分批派单**，不要一次铺开 7 个服务：
   - **第一批（P0，资金/数据正确性）**：trade-service（已立案，直接修）、data-service（写 PG 写入测试计划 + 红测试立案已知 bug）
   - **第二批（P1）**：strategy-service（auto_trading_executor）、backtest-service（回测可信度）
   - **第三批（P2/P3）**：按业务需要排
2. **每个服务走同一方法**（已验证可复制）：
   - `codegraph impact <核心符号>` 看影响面 → `codegraph explore <符号>` 找 `⚠️ no covering tests` → 读核心模块挖 bug → 写红测试立案（断言正确行为，当前失败）→ 产出 `TEST_PLAN_<module>.md` → 交 backend-dev
3. **合规**：trade-service / strategy-service / data-service 涉及交易或数据正确性，改动按 CLAUDE.md 走 **Plan Mode + tech-lead review**，SIT 证据落 `progress/backend-dev.md`。
4. **基准**：`training-service`（11/5）是当前唯一像样的覆盖，可作为其他服务补测试的"密度基准"参考。

---

## 5. 方法（codegraph 命令备忘）

```bash
codegraph status                                    # 图谱健康
codegraph explore <符号>                            # 旗舰：源码+调用路径+⚠️no covering tests 标注
codegraph impact <符号>                             # 改动影响面（多少调用方）
codegraph callers / callees <符号>                  # 调用方 / 下游
codegraph affected <改的文件>                       # 该跑哪些测试（宽召回，需筛）
# 测试密度统计：
find services -maxdepth 1 -mindepth 1 -type d | while read s; do \
  echo "$(basename $s): app=$(find $s/app -name '*.py'|wc -l) tests=$(find $s/tests -name 'test_*.py'|wc -l)"; done
```
