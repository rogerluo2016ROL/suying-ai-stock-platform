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

