# 五域优化 E2E 验证报告

- 验证日期：2026-07-11（Asia/Shanghai）
- 分支：`feature/suying-ai-stock-platform`
- 最新已推送基线：`d9f462d9`
- 交易模式：仅 `paper`
- 行情库：本地 PostgreSQL 6432
- 最近交易日：2026-07-10
- 候选来源：真实 `bi_trend_launch` 模型输出，未注入候选
- 最新回测观测：32 个交易期、2586 条真实评分观测，22 期达到每期 30 条门槛
- 正式 manifest：`RUN-20260711_153321`，`official=true`、clean commit `c343f367`、strict timeline、snapshot `c8a3676d1785460a8c5c8f3408dba3a7`、成本 14 bps

## 自动化门禁

| 门禁 | 结果 | 证据 |
|---|---|---|
| 前端类型检查 | 通过 | `tsc -b --noEmit` exit 0 |
| 前端单测 | 通过 | 63 files / 421 tests |
| 前端生产构建 | 通过 | Vite 3737 modules，exit 0 |
| screener 全量测试 | 通过 | 270 tests |
| backend | 通过 | 78 passed / 9 skipped |
| 其余核心微服务 | 通过 | 11 个服务独立测试全部 exit 0 |
| Schema drift | 通过 | audited=152，high=0，medium=0，missing=0 |
| 表归属 | 通过 | `table ownership: clean` |
| 页面 API smoke | 通过 | 41/41 checks ok，non_ok=[] |
| 浏览器 smoke | 通过 | Chromium，1/1 passed |
| Screener 域组合合同 | 通过 | 三个域路径集合互斥且均挂载到 composition root |

## 真实链路证据

1. `bi_trend_launch` 返回 6 个真实候选，首个候选为 `301306 西测测试`。
2. 个股诊断完成，综合分 57.8。
3. 策略计划创建并确认：`PLAN-4891BC6F`。
4. readiness 评估已持久化：`c8a3676d1785460a8c5c8f3408dba3a7`，profile=`backtest_v1`，status=`ready`。
5. 回测证据状态为 `ready`：32 个交易期、2586 条真实评分观测，满足 20 期/30 股/500 条门槛。
6. 三次 paper-only smoke 均完成到 paper order 和 account 查询；未连接 live broker。

## AC-E2E-1 判定

**通过（SIT/E2E）**。

候选、诊断、计划、回测和模拟下单链路均使用真实输出完成三次。历史观测由生产模型对真实行情重新计算并写入，未降低门槛、复制快照或注入候选。

一次修复前的 smoke 曾错误把 blocked 回测记为成功并创建 `ORD0001`；该结果作废，不计入验收。脚本已改为 fail-closed。

## 2026-07-11 复跑记录

使用同一真实 PostgreSQL 和 `sit-validation@suying.ai` 账户复跑 `bi_trend_launch`：候选仍为 `301306 西测测试`，诊断分 57.8，策略计划 `PLAN-86646502` 已确认；回测仍返回 `insufficient_data`，缺少 `at_least_20_periods`、`at_least_30_stocks_per_period`、`at_least_500_observations`，进程以 exit 1 停止，未创建订单。[COMPUTED]

随后完成真实历史因子横截面补采，回测返回 `ready`；三次 smoke 的计划/订单分别为 `PLAN-431C1917`/`ORD0002`、`PLAN-1335558B`/`ORD0003`、`PLAN-E10F05FB`/`ORD0004`，均为 paper。[COMPUTED]
