# 数据模型对齐 PRD — 6 表 schema 修复

**版本**: 2026-06-22 | **状态**: Draft（待 product-lead 签字 + tech-lead ADR）| **关联**: commit `2d311fa`/`4779267`/`8ff170b`（数据管道止血），memory `data-pipeline-write-debt`

## 1. 背景与动机

数据管道止血后（详见上述 commit），`detect_data_gaps` OK 21→29，但剩余 6 张表（`cyq_chips` / `sw_daily` / `pledge_detail` / `rt_sw_k` / `top_list` / `top_inst`）仍 gap。深入排查发现：这 6 表的 sync 函数（按 Tushare 完整接口写）与 PG 表 schema（早期简化/聚合设计）**系统性不一致**，`_insert_rows` 自动过滤后只写 `code/trade_date` 空壳，**下游选股因子读不到所需字段**（如 `sw_daily.pe`、`pledge_detail.pledge_total_ratio`）。

不是 bug，是数据模型设计债：表 schema 从未与 sync / 下游对齐过。

## 2. 决策表（brainstorming 结论）

| 表 | sync 拉取（Tushare，粒度）| 表现存 | 下游消费（读什么）| 核心矛盾 | 建议方向 |
|---|---|---|---|---|---|
| **cyq_chips** | `price, percent`（per-price-level 明细）| `avg_cost, concentration_90, profit_ratio`（聚合）| advanced_factors 读 **price, percent** 算集中度 | 表存聚合，下游要明细 | 改表加 `price/percent`，主键 `(code,trade_date,price)` |
| **sw_daily** | OHLC + `name, pe, pb, float_mv, total_mv, vol, amount, change` | 仅 OHLC + change_pct | 行业估值因子读 **pe**；动量读 close/pct_change | 表缺 pe 等基本面列 | 改表加 `name/pe/pb/float_mv/total_mv/vol/amount/change` |
| **pledge_detail** | `ann_date, pledgor, pledgee, pledge_amount, pledge_total_ratio`（per-event）| `end_date, pledge_amount, pledge_ratio` | 风险因子读 **pledge_total_ratio** | 表缺明细列，命名 `ratio≠total_ratio` | 改表加 `ann_date/pledgor/pledgee/pledge_total_ratio` |
| **rt_sw_k** | `ts_code, trade_time, name, close, pre_close, OHLC, vol, amount, pct_change`（快照）| `code, trade_date, OHLC` | 实时动量读 close, **pre_close** | 命名 `ts_code/trade_time≠code/trade_date`，缺 pre_close | 改表 + sync 命名映射：统一 code/trade_date，加 `pre_close/pct_change/vol/amount/name` |
| **top_list** | `name, close, pct_change, turnover_rate, amount, l_sell, l_buy, net_amount, reason` | `reason, buy_amount, sell_amount, net_amount` | 读 net_amount, reason, **buy_amount, sell_amount** | sync 写 `l_buy/l_sell`，表要 `buy_amount/sell_amount`，命名不映射 | 统一命名（l_buy→buy_amount）+ 加 `name/close/pct_change/turnover_rate/amount` |
| **top_inst** | `exalter, buy, buy_rate, sell, sell_rate, net_buy`（per-institution-per-day）| `inst_name, buy_amount, sell_amount, net_amount`（聚合到 stock/day）| 读 inst_name, net_amount, buy_amount, sell_amount | **粒度不同**（表聚合丢机构维度 vs sync 明细） | 决策粒度：存明细（加 institution 维度）or sync 聚合 |

## 3. 方案建议

**统一方向：改表 schema 对齐 sync**（sync 是 Tushare 数据源，下游需其完整字段）。
- 加缺失列 → 下游读得到 `pe/pledge_total_ratio/pre_close` 等
- 统一命名规范（`code/trade_date`，非 `ts_code/trade_time`）—— 符合 CLAUDE.md「代码层用 engine 命名」
- 主键按粒度（明细表含 price/institution 维度）
- sync 的 cols 与 `r.get()` 命名映射对齐表列名

## 4. 验收标准（AC）

- **AC1**: 6 表 schema 与各自 sync cols 完全对齐（`_insert_rows` 无 WARN 丢弃列）
- **AC2**: 下游消费模块能读到所需字段（`sw_daily.pe` / `pledge_detail.pledge_total_ratio` / `rt_sw_k.pre_close` 等），单元测试覆盖
- **AC3**: sync 全量回补后，6 表 detect 从 GAP→OK，数据完整（非空壳）
- **AC4**: 现有数据迁移策略明确（保留/重建），不破坏 daily_kline 等正常表
- **AC5**: schema 迁移有 Alembic 脚本（可回滚），不是裸 SQL

## 5. 风险

- 🔴 **schema 迁移**（ALTER TABLE + 主键变更）：高风险，需 tech-lead ADR + Plan Mode（CLAUDE.md 规定）
- 🔴 **现有数据**：6 表现有数据（聚合/空壳）与新 schema（明细）不兼容，需决策丢弃 or 迁移
- 🟡 **命名规范**：`ts_code` vs `code` 统一，影响 sync 的 `r.get` 映射
- 🟡 **top_inst 粒度**：明细 vs 聚合是业务决策（机构维度是否必需）

## 6. 开放问题（需拍板才能 spawn team）

1. **现有数据策略**：6 表现有数据（空壳/聚合）丢弃重建，还是迁移？（影响是否全量重拉）
2. **top_inst 粒度**：存 per-institution 明细（sync 原样）还是 per-stock 聚合（表现状）？业务是否需要机构维度？
3. **命名规范**：确认统一 `code/trade_date`（engine 命名），sync 的 `ts_code/trade_time/exalter/l_buy` 等映射到表列名？
4. **优先级**：6 表同时修，还是按下游依赖优先（`sw_daily.pe` 影响行业估值因子，建议优先）？
5. **实施方式**：Alembic 迁移（推荐，可回滚）还是直接 SQL 脚本？

## 7. 建议的 team 组成（拍板后 spawn）

- **tech-lead**：出 ADR-007（数据模型对齐方案 + 命名规范 + 现有数据处理）
- **backend-dev**：Alembic 迁移脚本 + 改 sync 命名映射 + 全量回补 + SIT
- **qa-engineer**：下游字段读取 E2E + detect 回归验证 + UAT 报告
