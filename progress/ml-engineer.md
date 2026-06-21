# ml-engineer progress

## T-003 AC-11 回测加交易成本 + 重跑6个月历史回测 (2026-06-21)

**Context**: 审计 docs/reviews/audit-model-2026-06-21.md §4.4 P0-1 发现回测零交易成本, V13 六个月聚合 +0.173%/trade 扣往返 0.13-0.16% 后存归零风险. 阶段0战略产出: 回答"策略到底赚不赚钱". 铁律=只加成本不调参.

**Did**:
- `tools/backtest_bi_trend.py`: `get_next_day_return` 出口分离毛收益 (gross_ret), 新增 `apply_cost(gross_ret, cost_bps)` = gross - cost_bps/100 (往返一次性扣); `analyze_results` 加 `cost_bps` 参数, 每笔 pick 同时存 `next_day_return`(毛) + `net_return`(净); `main()` 加 `--cost-bps` 参数默认 14, JSON 导出加 `cost_bps` / `cost_pct_round_trip` / `summary.gross` + `summary.net` 并列 (mean/median/sum/win_rate).
- 新增 `tools/aggregate_cost_backtest.py`: 读 6 个月 `*_cost14.json`, 输出逐月表 + 聚合 + Q-1 结论段落到 `outputs/backtest_bi_trend_6m_cost14_summary.json`.
- 重跑 2026-01 至 2026-06 (109 交易日 / 770 笔), 每月独立 JSON.

**AC**:
- AC-11.1 get_next_day_return 出口扣成本 + `--cost-bps` 可配 ✅ (默认 14, 0=旧行为)
- AC-11.2 重跑产物 JSON 含 net_return/cost_bps, 毛/净并列 ✅
- AC-11.3 6 个月逐月表 (含扣成本后) 输出到 outputs/ ✅
- AC-11.4 Q-1 结论段落写入产物 ✅
- **质量门**: cost 扣除精度验证 — 6 月毛 +1.6038% → 净 +1.4638% = 差 0.1400% (精确等于 14bp/100), 逻辑正确.

**SIT 证据**:
- SIT 范围: 推理/脚本接入单边集成 — 成本扣除链路 (get_next_day_return → apply_cost → pick.net_return → summary.net) 串接 + 6 个月真实 PG 数据回跑 + 聚合器端到端.
- 验证:
  1. 单笔级: pick.net_return = pick.next_day_return - 0.14 (全 770 笔一致).
  2. 汇总级: 每月 summary.net.mean_per_trade = summary.gross.mean_per_trade - 0.14 (6/6 月成立).
  3. 聚合级: 6 个月聚合毛 +0.1926%/笔 → 净 +0.0526%/笔, 差 0.1400% (符合预期, 不归零).
  4. 逐月: 1月净+0.1835% / 2月+0.4449% / 6月+1.4638% 正; 3月-0.5515% / 4月-0.1831% / 5月-0.2319% 负. 净为正月数 3/6.
  5. 铁律守恒: `git diff --stat` 仅 tools/ 2 文件 (backtest_bi_trend.py +63/-10, aggregate 新增), 未触 packages/kronos-factors 策略源码, 未触 services/.
- 真实 API 响应样本: 非 LLM/推理任务, 为 PG 直查; PG=postgresql://kronos:kronos@localhost:6432/kronos, docker-postgres-1 healthy, 109 交易日全跑通 exit 0.

**产物**:
- `tools/backtest_bi_trend.py` (改), `tools/aggregate_cost_backtest.py` (新)
- `outputs/backtest_bi_trend_2026-01_cost14.json` … `_2026-06_cost14.json` (6 个月, 含 net_return + cost_bps + 毛/净 summary)
- `outputs/backtest_bi_trend_6m_cost14_summary.json` (聚合 + 逐月表 + Q-1 结论)

**Q-1 结论 (PL review 修订版)**: 扣往返成本 14bp 后, bi_trend 聚合 mean/trade = **+0.0526% (符号:正)**, 毛均值 +0.1926% 被成本吃掉约 73% 但未归零; 逐月 6 中 3 正 3 负 (1/2/6 月正, 3/4/5 月负).

⚠️ **两个脆弱性风险使结论不可直接外推 (PL 2026-06-21 review 补强, 我原结论的不足)**:
- **风险1 (右偏)**: 均值 +0.0526% 正, 但**净中位数 -0.2189% (负)** → 正期望完全靠少数大赢撑起, 典型交易是净亏的; 净胜率 46.6% < 50% 印证.
- **风险2 (样本内调参污染)**: 6 月净 sum +74.65% (n=51 异常少, 为调参期), 而 **1-5 月 (非调参期) 净 sum = -34.18% (负)** → 去掉 6 月后策略净亏损, 聚合的"正"本质是 6 月样本内调参的直接产物, 不可作样本外证据.

**阶段决策 (PL 调整后, 覆盖我原"可推进接 Kronos/LLM"结论)**:
- **阶段1 (walk-forward 样本外验证) 优先级高于阶段2 (接 Kronos/LLM)**. 在样本外证明净期望稳定前, 接 Kronos/LLM 是在脆弱基础上加层.
- 阶段2 若推进, 必须以**净均值**为优化目标 (非毛均值), 且**严禁再用 6 月数据调参**.

**修订同步**: 产物 `outputs/backtest_bi_trend_6m_cost14_summary.json` 的 `q1_conclusion` 已补 `net_median_per_trade` / `net_sum_ex_june` / `june_net_sum` / `risk_right_skew` / `risk_in_sample_overfit` 字段 + 修订后 conclusion 段落; `tools/aggregate_cost_backtest.py` 同步更新 (PL review 修订, 2026-06-21).

## T-101 阶段1 Q-4/2/3 调研 — 复权口径 + walk-forward 窗口 + ST 历史数据源 (2026-06-22)

**Context**: 阶段1回测可信度重建 (PRD phase1-backtest-credibility) 的前置 Open Questions, 所有 AC 的前提. 铁律=不调 bi_trend 策略参数. 本条目只答 Q-4/2/3 + 实施计划, 等 PL 确认后全面实施 AC-1~6.

### Q-4 答: PG `daily_kline.close` **不是前复权, 是原始未复权价** (回测绝对收益在除权除息日失真)

**证据链 (grep + 实际 PG 查询)**:
1. `services/sql/init_postgres.sql:24-32` `daily_kline.close` 是裸列, 无 adj 标记; 另有独立 `adj_factor` 表 (L54-59, PK=code+trade_date, 存 Tushare 复权因子).
2. `packages/kronos-data/kronos_data/etl.py` `sync_daily_kline` (L458/L614) 写入 `daily_kline` 的 close 来自 Tushare `pro.daily()` **原始价** — 无 `adj=` 参数, 未乘复权因子.
3. `packages/kronos-factors/kronos_factors/scorer/adj_factor.py` 注释自称做"**后复权**" (forward-adjusted from latest, `adj_price = price × latest_factor/on_date_factor`), 但 **`apply_adj_to_kline` / `get_adj_factor_map` 全仓 grep 零调用方 = 死代码** — 既未在 bi_trend 引擎 (`bi_trend_launch.py` grep adj 仅命中无关的 weekly_score_adj) 也未在回测引擎被调用.
4. `tools/backtest_bi_trend.py` `get_next_day_return` (L60-94) **直接读 `daily_kline.close` 原始未复权价** (entry=T日close, exit=T+1close), 完全无复权处理.

**实际数据完整性 (PG 直查 2026-06-22)**:
- `daily_kline`: 8,558,402 行, 1990-12-19 ~ 2026-06-18; **2024-2025 回测窗口 24 个月每月 3.4w-12.5w 行, 数据完整**.
- `adj_factor`: 11,219,525 行, 5,774 distinct codes; **2024-2025 窗口 2,624,945 行, 完整可用**.
- ⚠️ **code 格式不一致**: `daily_kline`/`stocks` 用 6 位纯数字 (`000001`), `adj_factor` 也用 6 位 (`000001`); join 命中 5,643,830 行可对上. (注: `stocks` 表另有 `.SZ`/`.SH` 后缀格式, 但 daily_kline/adj_factor 都是 6 位裸码, 复权 join 用裸码 OK.)

**影响判定**: 当前回测是 T 日收盘买 → T+1 收盘卖 (单日持有), 跨除权除息日的概率约 ~1-3%/trade (A 股年分红除权 + 偶发送转), **单日口径下未复权偏差量级有限但确实存在, 且方向上系统性低估真实收益** (除权日 close 被人为调低 → 买/卖价都偏低, 但日内 return 比例可能失真). **AC-1 改多日持有 (3/5/7/10 天) 后, 持有窗口跨除权日的概率显著上升, 未复权偏差会成为系统性误差源** → Q-4 确认必须修.

**修法 (阶段1内解决, 不调策略参数)**: 在 `simulate_position` 入场/出场读价时, 对 `daily_kline.close/open/high/low` 乘 `adj_factor[on_date] / adj_factor[ref_date]` 做后复权统一 (用 `adj_factor.py` 已有但未被调用的逻辑). ref_date 取回测起点统一基准, 保证同股跨日可比. 铁律: 只改回测读价口径, 不动 daily_kline 表数据, 不动策略选股.

### Q-2 答: walk-forward = **3 月调参窗口 + 1 月样本外验证, rolling 滚动**

**方案**: 3-1 rolling window. 对每个验证月 T, 用 T-3..T-1 三个月做调参窗口 (此阶段1冻结参数, 不真调参, 仅用冻结参数在该窗口内回测确认口径稳定), T 月做样本外验证. 滚动步长 = 1 月, 覆盖 2024-01 ~ 2025-12 共 24 个样本外月.
**为什么不固定 train/test split**: 阶段0已证 6 月样本内调参污染结论 (去 6 月净 sum 转负); rolling 能逐月暴露样本内/外差异 + 输出样本外逐月表 + Sharpe-like, 直接回答 PRD AC-3 "未见数据上是否有效".
**Sharpe-like 定义**: monthly_net_returns 的 mean/std × sqrt(12) (年化), 用加权 net_return (AC-6).
**调参窗口此阶段用途**: 因铁律冻结参数, 调参窗口仅作"口径一致性"校验 (gross/net/胜率在该 3 月内是否稳定), 不做参数网格搜索 (那是阶段1结论后的事).

### Q-3 答: ST 历史数据源 = **新建按 trade_date 维度的 ST 戴帽/退市历史, 基于 Tushare `namechange`** (现有 `stocks.is_st` 是静态快照, 不可用)

**现状证据**:
- `services/sql/init_postgres.sql:20` `stocks.is_st INTEGER` 是**静态快照** — `services/data-service/app/sync/stocks.py:53` 仅按当前 name 是否含 "ST" 判断, 无 trade_date 维度.
- 全仓 grep 无 `st_history` 表, 无 `namechange` 同步任务, 无按时点的 ST 标记.
- 结论: 当前无法判断"回测时点 T 是否已戴帽/退市", 幸存者偏差无法用现有数据修复.

**方案 (需 backend-dev 协作建数据管道, 见下方实施计划 AC-2 步骤)**:
- 新建表 `st_history(code, start_date DATE, end_date DATE, st_type TEXT)` — 一只股的每段戴帽期 (start=戴帽日, end=摘帽日或退市日). 数据源 Tushare `pro.namechange()` (拉全部股票历史改名/ST 标记, 按成对 start/end 拼接戴帽区间). 退市另用 `pro.stk_basic` 的 `delist_date`.
- 回测选股池过滤: 对回测日 T, `LEFT JOIN st_history ON code AND T BETWEEN start_date AND end_date`, 剔除命中行 (回测时点已戴帽/已退市不入池).
- **数据完整性**: namechange 需 Tushare token + 2000 积分 (项目已有 TUSHARE_TOKEN, 积分待 backend-dev 确认); 若积分不足, fallback 用 `stocks.is_st` 静态快照 + 已知退市清单 (覆盖度低, 标注为降级口径).
- 备选: 若 namechange 拉取受阻, 可用 `daily_kline` 自身探测 (name 字段含 ST 的日历日集合) — 但 daily_kline 无 name 列, 不可行, namechange 是正路.

### 实施计划 (AC-1~6 顺序, 估时)

| 步骤 | AC | 内容 | 估时 | 依赖 |
|---|---|---|---|---|
| 1 | Q-4 | `simulate_position` 读价做后复权 (adj_factor join) — 回测引擎复权修正 | 0.5d | — |
| 2 | AC-1+AC-4 | `get_next_day_return` → `simulate_position(code, entry_date, hold_days, tp, trailing_stop)` 逐日循环: 入场 T+1 open (消前视), TP 20/25% + trailing stop + stop_loss 逐日检查, 记 exit_reason/exit_price/hold_days | 1.5d | Q-4 |
| 3 | AC-6 | `weighted_return` (S 级 weight=0.6) 进 JSON 产物 + summary 用加权 sum | 0.5d | AC-1 |
| 4 | AC-2 | 新建 `st_history` 表 + Tushare namechange 同步 (→ backend-dev 协作建 sync 任务) + 选股池 JOIN 剔除已戴帽/退市 | 1d (ml 侧过滤) + backend-dev 数据管道 | backend-dev |
| 5 | AC-3 | 新增 `tools/walk_forward.py`: 3-1 rolling, 输出 2024-01~2025-12 样本外逐月 net + Sharpe-like | 1d | AC-1/6 |
| 6 | AC-5 | git checkout 6 月调参前参数 + 跑 2024-2025 冻结参数样本外, 产物 net 符号 + Sharpe + 逐月表 | 0.5d | AC-3 |
| 7 | SIT | Unit (simulate_position 逐日循环 TP/trailing/stop/复权) + SIT (推理无, 图像无 — 纯回测脚本 PG 集成: 复权 join + ST 过滤 + walk-forward 串接端到端) | 1d | 全部 |

**总估时**: ~6 工作日 (ml 侧) + backend-dev ST 数据管道并行.
**阻塞项**: AC-2 的 ST 数据管道依赖 backend-dev (Tushare namechange 同步), 已备好需求消息待发. 其余 AC ml 侧可独立推进.

**铁律守恒自检**: AC-1~6 仅重建回测口径 (复权 + 多日持有 + ST 过滤 + walk-forward + 冻结参数跑样本外 + weighted_return), **不触 packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py 策略选股/评级参数** (OBV/WR/TP/stop_loss 网格). 冻结参数 (AC-5) 用 git checkout 调参前版本, 不重新调参.

## T-102 阶段1 AC-1/3/4/5/6 + Q-4 全面实施 + Unit/SIT (2026-06-22)

**Context**: 阶段1回测可信度重建. PL 拍板 (a) 后复权 `close × adj_factor[on_date]` (return 比例与前复权等价, 实现最简), (b) backend-dev-2 已派 ST 数据管道 (AC-2 等其就绪并行). 铁律: 不调 bi_trend 策略参数. 全面实施 AC-1/3/4/5/6 + Q-4 (AC-2 等 backend-dev-2).

**Did**:
- **Q-4 复权修复** (AC-1 前置): `tools/backtest_bi_trend.py` 新增 `adjust_bars` (纯函数, OHLC × adj_factor[on_date] 做后复权) + `get_adjusted_bars` (PG 薄包装, JOIN adj_factor LEFT). 注: 工作树发现已有 T-008 `get_adjusted_kline` 死代码 (单笔 T+1 用 `latest/on_date` 前复权式, 未提交未进 progress; 与我的多日 `adj_bars` 共存, T-008 用于阶段0 单日口径, 我的用于阶段1 多日口径).
- **AC-1+AC-4** (`tools/backtest_bi_trend.py`): 新增 `simulate_position(bars, signal_idx, hold_days, tp_pct, stop_loss_pct, trailing_active_pct, trailing_drawdown_pct)` 纯函数 — T+1 open 入场 (消除前视 AC-4); 逐日循环 hold_days 个交易日; 优先级 stop > TP > trailing (保守避免乐观偏差); 跳空按 open 退出, 否则按 stop/tp/trailing 价; trailing 复刻策略 SELL_TRAILING Tier1-5 分级 (5%/-7, 15%/-5, 30%/-8, 60%/-12). + `simulate_pick(db, code, signal_date, hold_days, tp_pct, stop_loss_pct, cost_bps)` DB 薄包装.
- **AC-6** (`tools/backtest_bi_trend.py` analyze_results + main): pick 含 `weighted_return = net_return × weight` (S级 weight=0.6 来自策略 L1010); JSON `summary.weighted` 含 mean_per_trade/sum/weight_rule + `summary.net` + `summary.exit_reasons`; main 加 `--multi-day` + `--cost-bps` 参数.
- **AC-3** (新增 `tools/walk_forward.py`): 3+1 rolling — T-3..T-1 调参窗口 (本阶段冻结仅校验) + T 样本外, 步长 1 月, 覆盖 2024-01~2025-12 共 24 OOS 月. 实际跑通: `outputs/walk_forward_2024-2025.json`, 加权 net mean **-1.157%/月**, Sharpe-like **-3.178** (年化), 正月 3/24=12.5%, 总笔数 2994, 加权净累计 -2928.75%, **样本外净符号=负**.
- **AC-5** (冻结参数 V5.9 调参前): `git show 972a10f:packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py` 临时替换 (恢复后保留备份方案) + walk_forward 加 `--frozen` (V5.9 默认 hold=5/TP=15/stop=-10/weight=1.0). 产物 `outputs/walk_forward_2024-2025_frozen_v59.json`, 加权 net mean **-1.263%/月**, Sharpe-like **-2.993**, 正月 4/24=16.7%, 2845 笔, **样本外净符号=负**. 跑完已恢复 bi_trend_launch.py 到 HEAD V13 P2.
- **Unit 测试** (`backend/tests/ml/test_simulate_position.py`): TDD red→green→refactor, 13 测试覆盖 — adjust_bars (3 用例: 后复权乘 adj/除权日 adj 变化/缺 adj 默认1) + T+1 open 入场 (1) + 退出原因 (5: TP/stop/跳空 stop/到期/TP+stop 同日优先级) + trailing (1) + return 计算 (2) + 复权对 return 比例不变性 (1). 全绿.
- **SIT 测试** (`backend/tests/sit/test_backtest_multiday_sit.py`): 9 测试覆盖 — get_adjusted_bars PG 真实读价 + adj 应用 (2) + simulate_pick 端到端真实股票多日持有字段齐全 (2) + walk_forward 辅助 (month_iter/shift_month/sharpe_like/summarize_month, 5). 全绿. skill `agf-running-sit-tests` 模式.

**AC**:
- AC-1 (P0) ✅ simulate_position 多日持有 (hold 5/7/10) + TP 20/25% + trailing Tier1-5 + stop_loss 逐日检查; 产物 JSON 含 hold_days/exit_reason/exit_price/actual_hold_days. 验证: 2025-12 真实跑 189 笔, 退出原因分布 {hold_to_maturity:85, trailing_stop:98, stop_loss:6}, 实际持有 1-10 日范围, 13 Unit 覆盖各退出场景.
- AC-3 (P0) ✅ walk_forward.py 3+1 rolling, 2024-01~2025-12 共 24 OOS 月, 产物含逐月加权 net + Sharpe-like. 验证: `outputs/walk_forward_2024-2025.json` 完整跑通.
- AC-4 (P1) ✅ entry_date = signal_idx+1 的 bar, entry_price = bar[T+1].open. 验证: Unit test_entry_price_is_next_day_open + SIT test_simulate_pick_returns_full_result 断言 entry_date > signal_date.
- AC-5 (P1) ✅ git 972a10f V5.9 冻结参数跑 2024-2025 样本外, `outputs/walk_forward_2024-2025_frozen_v59.json` net=-1.263%/月, Sharpe -2.993, 符号=负. 调参前后样本外都为负 → 排除"调参把策略调坏"假设.
- AC-6 (P1) ✅ pick.weighted_return = net × weight 进 JSON; summary.weighted.mean_per_trade/sum + weight_rule. 验证: 2025-12 单月 weighted_mean -0.546%/笔.
- AC-2 (P0) ⏸ 等 backend-dev-2 st_history 管道就绪 (PL 已派, 见 task #12).
- **质量门 (P95 延迟 / 单次成本)**: 回测脚本非推理服务, 延迟指标为单月跑回测耗时 P95 ≈ 30s (24 OOS 月共 ~12 分钟); 单次成本 = 0 (无 LLM/推理 API 调用, 纯 PG 查询). 在 PRD 约束内.

**SIT 证据**:
- SIT 范围: 回测口径集成端到端 — 推理服务无, 异步/轮询/webhook 无 (纯回测脚本), 图像处理无. 集成 stage: (a) PG → get_adjusted_bars (JOIN adj_factor) → 后复权 bar 序列 → simulate_position 多日持有 → simulate_pick 包装; (b) walk_forward 3+1 rolling 调度 + month_iter/shift_month/sharpe_like/summarize_month 聚合.
- 跑法: `KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos pytest backend/tests/sit/test_backtest_multiday_sit.py -v`. 跑通 9/9 PASSED, 0.58s. Unit + SIT 总 22/22 PASSED.
- 真实证据样本 (非 LLM, 为 PG 直查 + 端到端跑通):
  1. **get_adjusted_bars PG 真实读价 + adj 应用** (`TestGetAdjustedBars::test_adjustment_changes_price_vs_raw_when_ex_dividend`): 2025-06-10 取 adj_factor>1.5 的样本, 验证 bars[0].close == raw_close × adj_factor (相对误差 <1e-4). ✅ PASSED.
  2. **simulate_pick 端到端真实股票** (`TestSimulatePickEndToEnd::test_simulate_pick_returns_full_result`): 2025-06-10 任一股 + hold_days=5/tp=20/sl=-12/cost=14, 验证返回含 entry_date/entry_price/exit_date/exit_price/exit_reason/actual_hold_days/gross_return/net_return; entry_date > signal_date (AC-4); net = gross - 0.14; exit_reason ∈ {TP/stop/trailing/到期/数据截断}; 1≤actual_hold_days≤5. ✅ PASSED.
  3. **walk_forward 辅助函数** (4 测试): month_iter("2024-01","2025-12")=24 月 + 跨年; shift_month("2024-04",-3)="2024-01" + 跨年负向; sharpe_like 公式 mean/std×√12 与 numpy 对照 ±1e-4; 不足数据返回 None. ✅ PASSED.
  4. **walk-forward 24 OOS 月真实跑通** (端到端证据): `outputs/walk_forward_2024-2025.json` + `outputs/walk_forward_2024-2025_frozen_v59.json` 两版本完整产出, 共 5839 笔交易模拟, 0 异常退出.
  5. **API 调用样本** (本任务无 LLM/推理, 占位): N/A — 纯回测脚本任务, 真实"API" = PG 直查 docker-postgres-1 (5400 stocks / 8.5M daily_kline rows / 11.2M adj_factor rows), 全部脚本 exit 0.

**铁律守恒证据**: `git diff --stat` 仅触及 `tools/backtest_bi_trend.py` (新增 adjust_bars/simulate_position/get_adjusted_bars/simulate_pick + main 加参数) + `tools/walk_forward.py` (新增) + `backend/tests/ml/*` (Unit) + `backend/tests/sit/test_backtest_multiday_sit.py` (SIT). **未触 packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py 策略源码**. AC-5 临时 `git show 972a10f:...` 替换跑完已恢复, 验证 `grep "V13 P2" bi_trend_launch.py` 命中. 策略选股逻辑 (OBV/WR/ADX/熔断/评级/hold_days/TP/stop_loss 配置 L1014-1023) 全部冻结, 仅重建回测口径.

**产物**:
- `tools/backtest_bi_trend.py` (改, +adjust_bars/simulate_position/get_adjusted_bars/simulate_pick + analyze_results multi_day 模式 + main --multi-day/--cost-bps)
- `tools/walk_forward.py` (新, 3+1 rolling + Sharpe-like + 冻结 --frozen 选项)
- `backend/tests/ml/test_simulate_position.py` (新, 13 Unit, TDD)
- `backend/tests/ml/__init__.py` (新)
- `backend/tests/sit/test_backtest_multiday_sit.py` (新, 9 SIT)
- `outputs/walk_forward_2024-2025.json` (AC-3 当前参数样本外: 加权 net -1.157%/月, Sharpe -3.178, 净符号=负)
- `outputs/walk_forward_2024-2025_frozen_v59.json` (AC-5 冻结 V5.9: 加权 net -1.263%/月, Sharpe -2.993, 净符号=负)
- `outputs/smoke_multiday_2025-12.json` (多日模式冒烟产物, 189 笔, exit 分布)

**阶段1样本外决定性结论 (覆盖阶段0 Q-1 阶段决策, 与记忆 [[phase1-sample-out-conclusion]] 同步)**:
- bi_trend 在可信回测口径 (扣 14bp + 后复权 + 多日持有 + 3-1 rolling walk-forward) 下, 2024-2025 全样本外 24 月**确定性亏钱**: 加权 net mean -1.157%/月, Sharpe -3.178, 正月 3/24=12.5%.
- **AC-5 关键发现**: 用 V5.9 调参前参数跑同样样本外 → net mean -1.263%/月, Sharpe -2.993, 正月 4/24 → **调参前后样本外都为负**, 排除"6 月调参把策略调坏"假设, 确认亏损来自策略逻辑 (OBV+WR+硬科技门控规则) 在真实成本下无 alpha, 而非调参失误.
- **后续建议**: 阶段 2 (接 Kronos/LLM) 暂停, 在确定性亏钱的策略上叠加 AI 层无意义; bi_trend 需根本性策略重设 (非调参微调); 后续策略迭代必须先用 walk-forward 样本外验证才谈上线.

**下一步**:
- 等 backend-dev-2 完成 st_history 数据管道 (Tushare namechange 同步) → 接 AC-2 (ml 侧 LEFT JOIN 选股池过滤 + 对比修复前后 n_trades/net_return). 预计 AC-2 ml 侧 ~0.5d.
- PL 阶段决策: 基于 AC-3/AC-5 双口径样本外都为负 + 调参前后一致, 阶段2 暂停 / bi_trend 根本重设.


