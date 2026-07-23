# Design: 拥挤度→回撤预警

## 因子 (crowding_drawdown.py)

6 成分**时序滚动分位** (窗口 250 交易日, 口径 (rank-1)/(N-1) 对齐 bi_alpha_v15):
`turnover_rate_f` / `amount` / `volume_ratio` / `pb` / `ret20`(close 自算) / `net_mf_amount`(主力资金)

等权合成 CI (至少 3 成分有效, 缺失剔除)。level: high(>0.90) / medium(>0.80) / low; `ret20` 分位 > 0.95 直接升 high (对齐 screening_scorers 超买规则)。

## 数据坑 (已规避, 见 cerebrum)

- 换手率: `daily_basic.turnover_rate_f` (不用 `daily_kline.turnover_rate`, 688 有 36% NULL)
- 涨幅: close 自算 (不用 `change_pct`, 688 仅 64% 有效)
- **北向个股: 不用** (hk_holdings 2024-08 交易所停止披露)
- 主力资金: `moneyflow.net_mf_amount` (同步可用); 融资融券/股东户数滞后 ~3 周, 暂不进主公式

## 方向纪律

拥挤度是"极端反转"型因子: 高拥挤 → 预警回撤 (**回避/减仓方向, 非做多**)。回测判定看 IC(crowding, 未来回撤) < 0 且高拥挤组回撤 > 低拥挤组, 不能只看命中率 (对齐 cerebrum 机构活跃度 Top 组年化 -52% 的同源教训)。

## 时序纪律

回测脚本 `_timeline_guard` 复用 `walk_forward._git_strategy_commit + _timeline_guard_decision` (M01: 策略文件 commit 日期 guard; dirty 始终拦截)。

## 关键文件

- `packages/kronos-factors/kronos_factors/scorer/crowding_drawdown.py` — 因子 + scan_crowding
- `packages/kronos-factors/kronos_factors/engine/leader_afternoon.py` — 选股接入 (apply_afternoon_optimization)
- `services/alert-service/app/routes.py` — `/crowding-scan`
- `tools/backtest_crowding_warning.py` — 回测
- `services/screener-service/app/scheduler.py` — `_crowding_watch_loop`
- 单测: `tests/test_crowding_drawdown.py` (17) + `tests/test_backtest_crowding_warning.py` (4)
