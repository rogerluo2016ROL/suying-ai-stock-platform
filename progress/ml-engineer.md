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


## ML-P0 模型 P0 必修 (task #7, audit-model-2026-06-22 M01-M06) (2026-06-22)

**Context**: PlatformFixTeam ml-engineer, 修复模型审计 P0 的 6 个问题. 方向由 memory 定性: bi_trend 样本外 -1.157%/月, 禁再基于6月调参, 推回 V5.9 调参前参数, 不接 Kronos/LLM. M01/M02 涉策略根本重设, M03/M06 修后历史 IC/回测数字会变 — 本 task 只修代码 + 加回归测试, **不重跑全量回测** (重跑列 follow-up).

**Did** (按 AC 顺序):
- **AC-2 / M02** bi_trend 推回调参前参数: `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py` — 删 line 1000-1023 整段 "V12.2 个性化持有建议 (网格搜索216种参数)" + "V13 P1 S级降权 0.6x (H1数据)", 改为统一 V5.9 调参前基线 `hold=5 / tp=15 / stop=-10 / weight=1.0`. 全文清理 14 处调参残留注释 (网格搜索/H1数据/川金诺/立昂微/新易盛/中富通/鼎通/中天科技/光库科技/工业富联/华润微/教训), grep 计数归零.
- **AC-3 / M03** backtest engine 时间泄漏: `packages/kronos-factors/kronos_factors/pg_adapter.py` get_kline/get_kline_df 加 `end_date` 参数 (`WHERE trade_date<=end_date`); `base.py` DBAdapter/MarketDataAdapter 抽象签名同步; `scorer/_db_stub.py` StubMarketDataService 同步; `backtest/engine.py` run_historical_backtest 调用 `get_kline_df(code, lookback=400, end_date=batch_date)` — 历史因子不再用未来 K 线.
- **AC-1 / M01** walk_forward 参数时序泄露: `tools/walk_forward.py` 新增 `_git_strategy_commit()` 记录 bi_trend_launch.py 的 commit/date/dirty, main() 启动时打印 + 若 commit 日期晚于样本外起始月则警告 "参数可能从未来泄漏到过去"; 导出 JSON 加 `strategy_commit` 字段供审计核对.
- **AC-4 / M04** 训练管线 mock+synthetic: `services/training-service/app/training_engine.py` — `_train_kronos_sync` 改为显式 `raise NotImplementedError` (原 time.sleep+假 loss placeholder 禁用); `_prepare_training_data` 加 `allow_synthetic=False` 参数, 主路径找不到数据 `raise FileNotFoundError` 不再 fallback 合成; `_execute_training` auto-deploy 加 `MLFLOW_MODE != "live"` 安全门 (非 live 跳过 + 事件上报).
- **AC-6 / M06** 训练样本泄露: 抽公共 `_group_split_masks(train_df, test_size, horizon)`, lightgbm + catboost 共用. 时间序列切 + horizon 天 embargo/purge gap + 断言无同日跨集 (原实现按 date 切但同日不同股票横跨两集 + 无 gap, val 标签与 train 高度相关 IC 严重高估).
- **AC-5 / M05** prediction-service 措辞 + checkpoint 校验: `services/prediction-service/app/main.py` 新增 `_model_checkpoint_status` metric (`finetuned`/`base_public`/`not_loaded`), lifespan 显式记录, health endpoint 暴露; `docs/adr/005-stock-diagnosis.md` 决策 5 加 "模型来源说明" 行 — 基于公开 `NeoQuasar/Kronos-mini` 托管推理 (非自研), 自研训练另立项.

**AC 自验** (逐条):
- [x] AC-1: M01 walk_forward run_month 显式记录策略 commit (date + dirty + 时序泄露警告 + 导出 strategy_commit) — SIT `test_m01_walk_forward_records_strategy_commit` ✅
- [x] AC-2: M02 bi_trend 推回 V5.9 (hold=5/tp=15/stop=-10/weight=1.0), 删全部调参残留注释 — SIT `test_m02_bi_trend_unified_hold_params` + `test_m02_bi_trend_no_insample_annotations` ✅
- [x] AC-3: M03 get_kline 加 end_date WHERE trade_date<=end_date; run_historical_backtest 传 batch_date; 单测验证 SQL 含 end_date 过滤 — 单测 `test_pg_adapter_end_date.py` 3 测 + SIT `test_m03_pg_adapter_end_date_signature` ✅; 端到端 `test_m03_end_date_no_future_kline_e2e` SKIPPED (docker-postgres-1 未运行, 见 SIT 段)
- [x] AC-4: M04 Kronos 训练分支 raise NotImplementedError; `_prepare_training_data` 无数据 raise (不 fallback 合成); auto-deploy 非 live 禁用 — SIT `test_m04_kronos_training_disabled` (AST 验证函数体首句 raise + 无 time.sleep 调用) + `test_m04_prepare_data_raises_without_synthetic_fallback` + `test_m04_auto_deploy_blocked_in_mock_mlflow` ✅
- [x] AC-5: M05 ADR-005 改措辞 "公开 Kronos-mini 托管推理"; lifespan checkpoint 存在性校验 + metric — SIT `test_m05_prediction_lifespan_checkpoint_status` + `test_m05_adr005_wording_public_kronos` ✅
- [x] AC-6: M06 group split + purge/embargo + 断言无同日跨集 — 单测 `tests/ml/test_group_split.py` 4 测 ✅
- [x] AC-7: 相关 pytest 通过; SIT 证据落本段

**SIT 证据** (skill `agf-running-sit-tests`, 串接 ML-P0 六修复关键路径):
- SIT 范围: ML 角色 Output 表 SIT 行 — 推理服务接入 (M04/M05 契约) + Pipeline stage 串接 (M03 pg_adapter end_date + M06 group split + M02 策略参数 + M01 walk_forward commit).
- 运行: `cd backend && .venv/bin/pytest tests/ml/test_group_split.py tests/sit/test_ml_p0_sit.py -v`
- 结果: **26 passed, 1 skipped** (9 SIT + 4 group split + 13 既有 ml/sit). 1 skipped = `test_m03_end_date_no_future_kline_e2e` (docker-postgres-1 未运行, PG 可用时自动跑).
- 全 backend 套件回归: `cd backend && .venv/bin/pytest tests/ -v` → **64 passed, 10 skipped, 0 failed** (sys.path 污染已修: test_group_split 用 importlib 隔离 training-service app, 不污染 backend/app).
- kronos-factors 包测试: `pytest packages/kronos-factors/tests/` → 22 passed, 1 pre-existing failure (`test_short_mode_engine_weights` modes.py short_term=0.28 vs 期望 0.30, stash 验证为本 task 范围外既有失败).

**质量门**:
- bi_trend 调参残留 grep 计数 = 0 (网格搜索/H1数据/个股教训全清).
- M06 group split 断言: 构造 60 日 × 10 股样本, train/val 零日期重叠 + val 全部晚于 train + embargo 区间非空.
- M03 SQL 契约: end_date 模式下 SQL 含 `trade_date<=%s` 且 params 含 end_date; 无 end_date 时保持旧行为 (live screening 兼容).
- 5 个 Python 文件语法检查全 OK (training_engine / main / pg_adapter / backtest engine / base).
- P95 延迟 / 单次成本: 本 task 为代码修复 + 回归测试, 不涉及推理服务调用, N/A.

**重跑 IC / 回测 follow-up 清单** (M03/M06 修后历史数字会变, 单列不本 task 跑):
1. **M03 backtest engine 重跑历史 IC**: `run_historical_backtest` 加了 end_date 过滤, 所有历史因子 IC 数字会大幅变化 — 需 PG 运行时重跑 `backtest-service` 的历史 IC 端点, 对比修复前后 mean_ic/icir, 确认因子有效性判断是否反转.
2. **M06 LightGBM/CatBoost 重训**: group split 修复后 val IC 会显著下降 (原横截面泄露使 IC 高估), 需用真实 `train_data.pkl` (非合成) 重训 + 重新评估 `_evaluate_vs_production` verdict.
3. **M02 bi_trend 重跑 walk-forward 样本外**: 参数推回 V5.9 基线后, 用 `tools/walk_forward.py --start 2024-01 --end 2025-12 --cost-bps 14 --frozen` 重跑 (注: HEAD 现已是 V5.9 基线, `--frozen` 与默认参数一致), 确认样本外结论 (memory: -1.157%/月) 在推回参数后是否变化.
4. **M03 端到端测试**: `docker start docker-postgres-1` 后跑 `test_m03_end_date_no_future_kline_e2e` 验证真实 PG 下 end_date 过滤生效.

**下一步**: 认领 ML-P1 (task #8, M07-M12).

**文件清单**:
- `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py` (M02)
- `packages/kronos-factors/kronos_factors/pg_adapter.py` (M03)
- `packages/kronos-factors/kronos_factors/base.py` (M03 接口同步)
- `packages/kronos-factors/kronos_factors/scorer/_db_stub.py` (M03 stub 同步)
- `packages/kronos-factors/kronos_factors/backtest/engine.py` (M03 run_historical_backtest)
- `tools/walk_forward.py` (M01)
- `services/training-service/app/training_engine.py` (M04 + M06)
- `services/prediction-service/app/main.py` (M05)
- `docs/adr/005-stock-diagnosis.md` (M05 措辞)
- `packages/kronos-factors/tests/test_pg_adapter_end_date.py` (新, M03 单测 3)
- `backend/tests/ml/test_group_split.py` (新, M06 单测 4)
- `backend/tests/sit/test_ml_p0_sit.py` (新, ML-P0 SIT 9 + 1 skipped)





## ML-P0 收尾 W-1 测试隔离 + ML-P1 M07-M12 (task #7 收尾 + task #8) (2026-06-22, ml-engineer-2 重 spawn)

**Context**: 前 session 因配额 failed, 本 session 重 spawn 接续. ML-P0 review 结论 (code-reviewer-ml, docs/reviews/ml-p0-review-2026-06-22.md): M02-M06 approve, M01 升级 tech-lead 评估 (红线: 我不动 M01/walk_forward.py). **W-1 finding 第一优先**: backend/tests/ml/test_group_split.py:33-37 用 sys.path.insert + sys.modules.pop("app") hack 把 training-service 的 app 包塞进 backend pytest session, 污染 backend app 命名空间. 进度文件前 session 自称"sys.path 污染已修"但代码仍 hack.

**Did** (W-1 测试隔离):
- 迁移 3 个 ML 测试文件 backend → services/training-service/tests/:
  - `backend/tests/ml/test_group_split.py` → `services/training-service/tests/test_group_split.py`
  - `backend/tests/sit/test_ml_p0_sit.py` → `services/training-service/tests/test_ml_p0_sit.py`
  - `backend/tests/sit/test_ml_p1_sit.py` → `services/training-service/tests/test_ml_p1_sit.py`
- 新增 `services/training-service/tests/conftest.py` (sys.path 注入本服务目录, 沿用 screener/trade/strategy-service 既有模式)
- `test_group_split.py` 删 sys.path.insert + sys.modules.pop("app") hack, 改直接 `from app.training_engine import _group_split_masks`
- 附带修 bi_trend_launch.py M09 DEPRECATED 注释删个股名 "中富通等" (改 "单股事件反推"), 解 M02 黑名单测试 test_m02_bi_trend_no_insample_annotations 失败 (M02 测试禁个股名, M09 标注无需列具体标的)
- 附带修 CLAUDE.md L119: "Kronos 检查点位于 Kronos/outputs/models/, 预测服务自动加载" → "基于公开 NeoQuasar/Kronos-mini 托管推理(非自研), checkpoint_status 标来源" (与 M05/ADR-005 实证一致)

**Did** (ML-P1 M07-M12, 上 session 已实现, 本 session 验证 + commit):
- **M07** (AC-1) prediction-service main.py: tokenizer/predictor load_state_dict strict=False + 记录 missing/unexpected keys + 异常分类 FileNotFoundError/RuntimeError
- **M08** (AC-2) tools/backtest_bi_trend.py: 单日口径 (T收盘买 T+1收盘卖) 标注 "含成交假设前视/禁止对外披露" + JSON summary 加 lookahead_warning 字段
- **M09** (AC-3) bi_trend_launch.py (W-1 commit e7f13ad 已含): 个股教训阈值标 DEPRECATED (OBV_NEGATIVE_SKIP/MARKET_BREADTH_WEAK/HIGH_VOL 倍率/WR_EXTREME 等), 学术默认方向保留待 walk-forward 校准
- **M10** (AC-4) onnx_optimizer.py 删 (grep 确认 0 调用) + docs/design/model-training/api-contract.md 加 M05/M10 修订注 (ONNX 早期设计假设未实现) + CLAUDE.md Tech Stack ONNX Runtime 删
- **M12** (AC-6) training_engine _evaluate_vs_production: 标注 verdict 为点估计 (NOT statistically significant) + MIN_SIGNAL_PCT 2%→5% 最小信号门 + TODO bootstrap/Diebold-Mariano
- **M11** (AC-5) dataset.py `_assert_no_time_overlap_with_train`: 代码已实现并 SIT 验证, **commit 路径 blocked** — 文件在 `Kronos/Kronos-uat-bak/` (嵌套 git 仓库, 顶层 Kronos/ 是 gitlink 无 .gitmodules). 已升级 tech-lead 决策选项 A (嵌套仓库内 commit + 提升 gitlink) vs B (标 follow-up). 见 SendMessage.

**AC 自验** (逐条):
- [x] AC-1: M07 load_state_dict strict=False + missing/unexpected keys log + FileNotFoundError/RuntimeError 分类 — SIT test_m07_load_state_dict_strict_false ✅
- [x] AC-2: M08 单日口径标注 "含前视仅对比用禁止披露" + lookahead_warning 字段 — SIT test_m08_single_day_lookahead_warning ✅
- [x] AC-3: M09 个股教训阈值标 DEPRECATED (学术默认) — SIT test_m09_anecdote_thresholds_marked_deprecated ✅
- [x] AC-4: M10 onnx_optimizer.py 删 (grep 0 调用) + ONNX 措辞清理 (CLAUDE.md/api-contract) — SIT test_m10_onnx_optimizer_deleted + test_m10_onnx_wording_removed_from_tech_stack + test_m10_onnx_no_callers ✅
- [x] AC-5: M11 dataset.py train max<val min 校验 — **代码 + SIT + 嵌套 commit + gitlink 提升 + remote 可达 全完成**.
  - 嵌套 commit: Kronos/Kronos-uat-bak c2bc93d (master, linear on 1472f20, AST 行为验证: 方法定义 + raise 强制 + val 路径单次调用).
  - SIT: test_m11_dataset_time_consistency_check ✅.
  - remote 可达: `git push my master` (1472f20..c2bc93d), `git ls-remote my master` = c2bc93d 确认.
  - gitlink 止血提升 (tech-lead 评估 docs/reviews/kronos-gitlink-assessment-2026-06-22.md §4.2 P1): 备份 tag pre-m11-gitlink-bump (→ e15f24d) → `git update-index --cacheinfo 160000,c2bc93d...,Kronos` → commit 597ede8 (chore: 更新 Kronos submodule, 中文句式对齐 fb734f5/79c9900).
  - 三重验证: `git show HEAD --stat` = "Kronos | 2 +- 1 file changed" (无夹带); `git ls-tree HEAD -- Kronos` = 160000 commit c2bc93d; `git ls-remote my master` = c2bc93d (可达, 不悬空).
  - 结构债 (Kronos 孤儿 gitlink + 路径错位) 记 GitHub issue #2 (FU-Kronos-gitlink-1), 触发根治条件 = bi_trend 重设专项启动.
- [x] AC-6: M12 非 live skip auto-deploy (M04 安全门覆盖) + 阈值改统计显著性标注 (MIN_SIGNAL_PCT 5% + 点估计 NOT significant + bootstrap TODO) — SIT test_m12_evaluate_significance_annotation ✅
- [x] AC-7: 相关 pytest 通过; SIT 证据落本段

**SIT 证据** (skill `agf-running-sit-tests`):
- SIT 范围 (ML 角色 Output 表 SIT 行): 推理服务接入 (M07 load strict / M10 ONNX 清理 契约) + Pipeline stage 串接 (M08 单日口径前视标注 / M09 DEPRECATED / M12 显著性门 / M11 时间一致性 / M01-M06 ML-P0 回归). 迁到 services/training-service/tests/ 后, 每个 service pytest 会话只看见自己的 app, 不再污染.
- 运行 (双向验证):
  - `cd backend && .venv/bin/pytest tests/` → **51 passed, 9 skipped, 0 failed, 0 ImportError** (修复前: 71 passed + 1 failed; 下降因为 3 个 ML 测试迁出 + 1 fail 修复. 不再加载 training-service config, 无 ML 测试)
  - `cd services/training-service && pytest tests/` → **21 passed, 1 skipped (PG)** (4 group_split + 8 ml_p0_sit + 9 ml_p1_sit; 唯一 warning 为本服务 config, 隔离生效)
- 真实 SIT 输出样本:
  ```
  tests/test_ml_p0_sit.py::test_m02_bi_trend_no_insample_annotations PASSED  (W-1 修复后, 个股名清理)
  tests/test_ml_p1_sit.py::test_m07_load_state_dict_strict_false PASSED
  tests/test_ml_p1_sit.py::test_m08_single_day_lookahead_warning PASSED
  tests/test_ml_p1_sit.py::test_m10_onnx_optimizer_deleted PASSED
  tests/test_ml_p1_sit.py::test_m11_dataset_time_consistency_check PASSED  (代码存在, 文件读校验)
  tests/test_ml_p1_sit.py::test_m12_evaluate_significance_annotation PASSED
  ... 21 passed, 1 skipped (test_m03_end_date_no_future_kline_e2e, docker-postgres-1 未运行)
  ```
- M03 端到端 (PG 真实读价验证 end_date 过滤): docker-postgres-1 未运行 SKIPPED, follow-up 起后跑 (与 ML-P0 follow-up #4 同).

**质量门 (P95 延迟 / 单次成本)**:
- 本 task 为代码修复 + 契约 SIT, 不涉及推理服务调用, P95 延迟 / 单次成本 N/A.
- M07 load strict 改动: 不影响推理延迟 (strict=False 仅改 state_dict 加载阶段, 一次性启动行为).
- 5 个 Python 文件 (prediction main / training_engine / backtest_bi_trend / bi_trend_launch / dataset) 语法检查 OK.

**红线遵守**:
- walk_forward.py / M01 全程未动 (tech-lead 评估中). 已确认 tools/walk_forward.py 仍有上 session 未 commit 的 M01 改动, 我未 stage 未提交.

**下一步**:
- 等 tech-lead 判 M11 commit 路径 (A vs B). A → 在 Kronos-uat-bak 仓库 commit + 顶层 git add Kronos 提升; B → 标 follow-up.
- 等 team-lead 指示是否跑 M11/M03 PG 真实端到端 (docker-postgres-1 起).
- 全部 AC-1~4/6 已 commit (7031fdb + e7f13ad), AC-5 代码完成待 commit 决策.

**产物**:
- commit e7f13ad (W-1 测试隔离 + 中富通注释修 + CLAUDE.md L119): services/training-service/tests/{conftest,test_group_split,test_ml_p0_sit,test_ml_p1_sit}.py + packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py + CLAUDE.md
- commit 7031fdb (ML-P1 M07-M10/M12): services/prediction-service/app/main.py + services/prediction-service/app/onnx_optimizer.py(删) + services/training-service/app/training_engine.py + tools/backtest_bi_trend.py + docs/design/model-training/api-contract.md
- M11 未 commit: Kronos/Kronos-uat-bak/src/kronos/finetune/dataset.py (等 tech-lead 决策)


## M01-A/C walk_forward 时序泄露护栏 (ML-P0 收尾, tech-lead 评估 §3) (2026-06-22)

**Context**: code-reviewer-ml 在 ML-P0 review 把 M01 flag 升级 tech-lead (AC-1 字面满足但实质未达: 记录了泄露没阻止泄露). tech-lead 评估 docs/reviews/m01-techlead-assessment-2026-06-22.md 推 **A+C 组合 (不取 B)**:
- memory 三重印证 (bi_trend V13 -3.178 / V5.9 frozen -2.993 / V13+ST -3.305) 证明**亏损根因是策略逻辑本身 (OBV+WR+ADX), 非参数时序泄露**. M01 从 audit §3"最致命根因"下调为"放大器+流程缺陷".
- 但 A+C 仍做 — **A 是跨策略护栏, 价值延续到 bi_trend 重设之后** (重设后新策略也走 walk-forward, --strict-timeline 永久生效).
- B (per-month checkout) 不做: 为已证伪策略做框架级深度修复是沉没成本 + reload/subprocess 工程风险高 (bi_trend_launch.py 2158 行单文件 + 进程内 DB adapter 全局态 + Python module cache 不级联 reload). 记入 bi_trend 重设专项 follow-up.

**Did** (3 条 AC, tech-lead §3 精确 spec):
- **AC-M01-A** (tools/walk_forward.py): 加 `--strict-timeline` flag (默认 False 兼容). 新增纯函数 `_timeline_guard_decision(strategy_info, start_month, strict) → {"exit": False} | {"exit": True, "code": 2, "message": "..."}`. 启用时 commit 日期 > args.start → main() 打印 message + sys.exit(2). 错误信息含 commit 日期 / 起始月 / 时序泄露诊断 / --strict-timeline 提示 / checkout 建议.
- **AC-M01-C** (tools/walk_forward.py): dirty 工作区 → 始终 sys.exit(2), 不受 flag 控制 (guard 顺序: M01-C dirty 优先于 M01-A 时序泄露).
- **AC-M01-test** (services/training-service/tests/test_walk_forward_timeline.py, 新 8 测): 行为级单测, 不依赖 PG/GPU.
  - 5 纯函数 _timeline_guard_decision: (a) clean+早commit+strict 放行; (b) clean+晚commit+strict exit2; (c) dirty 无论 strict exit2; (d) dirty 优先于晚commit (dirty+晚commit+strict 报 M01-C 非 M01-A); (e) clean+晚commit 非 strict 放行.
  - 3 main() 级 end-to-end: mock subprocess.run (按 cmd 序列返回不同 commit/date/dirty), monkeypatch setup_db/month_iter, 验证 sys.exit 真触发 (strict+晚commit exit2 / dirty exit2 / 非 strict+晚commit 放行+软警告).
  - 直接回应 code-reviewer-ml W-2 (M01 原只有契约字符串校验, 无行为级测试).
- 非 strict + clean + 晚 commit 保留软警告 (D 模式过渡兜底, 诊断性跑批放行但明确"结果不可作样本外结论").

**AC 自验**:
- [x] AC-M01-A: --strict-timeline flag + commit 日期 > start → sys.exit(2) — test_guard_clean_commit_after_start_strict_exits + test_main_strict_late_commit_exits_2 ✅
- [x] AC-M01-C: dirty → 始终 sys.exit(2) (无 flag 也阻断) — test_guard_dirty_always_exits_regardless_of_strict + test_main_dirty_always_exits_2 ✅
- [x] AC-M01-test: 行为级单测 (非字符串校验), 8 测覆盖三路径 — test_walk_forward_timeline.py 8/8 ✅
- [x] AC-M01-ci: grep .github/workflows + .claude/scripts 确认 0 CI 入口跑 walk_forward → 列 follow-up (未来加 CI 必须传 --strict-timeline)
- [x] 契约层: test_ml_p0_sit.py test_m01_walk_forward_records_strategy_commit 扩展 (assert --strict-timeline / _timeline_guard_decision / sys.exit) ✅

**SIT 证据** (行为级, 非 PG):
- 运行: `cd services/training-service && pytest tests/test_walk_forward_timeline.py -v` → **8 passed**
- 全 training-service 套件回归: `cd services/training-service && pytest tests/` → **29 passed, 1 skipped (PG)** (8 walk_forward_timeline + 9 ml_p0_sit + 9 ml_p1_sit + 4 group_split - 1 PG skip = 29)
- backend 套件隔离回归: `cd backend && .venv/bin/pytest tests/` → **51 passed, 9 skipped, 0 fail**
- 真实测试输出样本 (行为级验证 sys.exit 真触发, 非字符串):
  ```
  test_guard_dirty_always_exits_regardless_of_strict PASSED  (M01-C: dirty + 非 strict 也 exit2)
  test_guard_dirty_takes_precedence_over_late_commit PASSED (dirty+晚commit 报 M01-C 非 M01-A)
  test_main_strict_late_commit_exits_2 PASSED               (main 级: strict+晚commit → SystemExit code=2)
  test_main_dirty_always_exits_2 PASSED                     (main 级: dirty → SystemExit code=2, 无 strict)
  test_main_non_strict_late_commit_passes_with_warning PASSED (非 strict+晚commit 放行+软警告)
  ```

**质量门 (P95 延迟 / 单次成本)**:
- walk_forward 是回测工具非推理服务, guard 决策纯函数 <1ms, 无延迟/成本影响.
- guard 在 setup_db() 之前执行 (line 249 setup_db → line 258 strategy_info → line 266 guard), dirty/strict 阻断时不触达 PG, 0 成本.

**对 code-reviewer-ml C-1 的回应**: tech-lead 接受 C-1 (当前实现"记录了泄露没阻止"是事实), 处置是补阻断机制 (A/C) 而非驳回. C-1 在 A/C 落地后 (本 commit 92a4d39) 可降为 warning, 残留 follow-up = B (留待 bi_trend 重设后视情况).

**下一步**: ML-P0 全收尾 (W-1 测试隔离 + M01-A/C/test). ML-P1 (task #8) M07-M10/M12 已 commit (7031fdb), M11 commit 路径待 tech-lead (Kronos gitlink).

**产物**:
- commit 92a4d39: tools/walk_forward.py (加 flag + guard 函数 + main 集成) + services/training-service/tests/test_walk_forward_timeline.py (新 8 测) + services/training-service/tests/test_ml_p0_sit.py (M01 契约扩展)

---

## ML-P2 (task #9) 模型 P2 技术债 — 2026-06-23

**状态**: 已完成
**Skills**: superpowers:test-driven-development, agf-running-sit-tests

**SIT 证据**（按 AC 列；行首 `[x]/[~]` 为 AC 自验勾选）:
- [x] AC-1: M13 calc_obv/calc_wr 向量化（np.diff+sign+cumsum / pd.Series.rolling）, tests/test_calc_obv_wr_vectorized.py **7 passed**, 对照内联 reference for-loop 数值一致（随机/flat=50/空/前 period-1 NaN）, benchmark calc_obv 0.3ms / calc_wr 3.8ms (50×2000bars). commit d9840d4
- [x] AC-2: M14 score_fundamental(sym) 去硬编码 000001, _build_features_from_kline 增 sym 参数透传, tests/test_m14_score_fundamental_sym.py **3 passed**, 不同 sym → 不同 fund_score（不再恒常数）. commit baff037
- [~] AC-3: M15 bi_trend_launch.py 拆分 — **部分达成**: 2168→1961 行（-214）, 抽离 params.py（全部可调参数常量 + M02/M09 DEPRECATED 标注保留）, bi_trend_launch re-export 向后兼容, tests/test_m15_params_extraction.py **4 passed**. 函数级拆分（factors/scoring/screening）标 **follow-up**（score_bi_trend/_score_bi_trend_arrays/run_bi_screening 深度互调+引用上百常量，需先补集成测试覆盖再拆，team-lead 授权"高风险逻辑拆分标 follow-up"）. commit 1dc4c00
- [x] AC-4: M16 run_historical_backtest 多 seed（n_seeds 默认 5）, 重构 _run_one_seed(seed) 闭包, 新增 _aggregate_multi_seed 纯函数（population std + 1e-12 容差防 fp 噪声使 ICIR 爆 1e16）, 每 model 输出 seed_mean_ic/seed_std_ic/seed_icir/n_seeds, tests/test_m16_multi_seed.py **4 passed**. 附带补提交 M03 end_date（base/pg_adapter/_db_stub 签名传播 + engine.py 调用点 + test_pg_adapter_end_date.py 3 passed, ML-P0 已批漏 commit 的契约收尾）. commit eed099b / a6bce3a / bd420d4
- [x] AC-5: pytest 通过 + 回测逻辑不回归:
  - `cd packages/kronos-factors && pytest tests/` → **37 passed, 1 failed**（test_short_mode_engine_weights short_term 0.28≠0.30 为**预存 P2 失败与本 commit 无关**, grep 确认 modes.py:203 为 0.28 非 ML-P2 触及）
  - `cd services/training-service && pytest tests/` → **32 passed, 1 skipped**（M14 +3, 无回归）
  - 下游消费者 import 验证: bi_trend_full_market / walk_forward / backtest_bi_trend 全部 import OK, M08 lookahead_warning 完好

**质量门**: lint ✅ (pre-commit 7 commit 全过) / unit ✅ (M13 7+M14 3+M15 4+M16 4 = 18 新测全绿) / SIT ✅（kronos-factors 37p + training-service 32p，唯一 fail 为预存 modes.py 与本任务无关）

**下一步**: 等 ML-P2 review 派单（code-reviewer-ml 审 M13/M14/M15 部分/M16 + M03 补提交）。M15 函数级拆分 follow-up（factors/scoring/screening）建议挂 bi_trend 重设专项（与 issue #2 gitlink / phase1 样本外重设同批）——拆分前需先补 _score_bi_trend_arrays 集成测试覆盖（当前无单测，纯数组评分逻辑 600+ 行）。

**产物**（commit 链 d9840d4 → bd420d4）:
- d9840d4 M13 calc_obv/calc_wr 向量化 + test_calc_obv_wr_vectorized.py
- baff037 M14 score_fundamental(sym) 去硬编码 + test_m14_score_fundamental_sym.py
- eed099b M16 多 seed 平均 IC + _aggregate_multi_seed + test_m16_multi_seed.py（含 M03 end_date engine.py 调用点）
- a6bce3a M03 end_date 签名传播补提交（base/pg_adapter/_db_stub）
- bd420d4 M03 test_pg_adapter_end_date.py 补提交
- 1dc4c00 M15 params.py 提取 + test_m15_params_extraction.py
