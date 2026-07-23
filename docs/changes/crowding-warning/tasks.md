# Tasks: 拥挤度→回撤预警

## 已完成 (v1, 2026-07-20)

- [x] 因子 `packages/kronos-factors/kronos_factors/scorer/crowding_drawdown.py` — `compute_crowding_risk` (6 成分时序分位) + `scan_crowding` (批量向量化), 17 单测全过
- [x] 选股接入 — `leader_afternoon.apply_afternoon_optimization(score, db, trade_date)` 调因子, 写 `crowding_level`/`risk_flags`; service.py 零改动 (sanitize/normalize 透传); 23 测试过
- [x] alert-service `POST /api/v1/alert/crowding-scan` — 批量扫描 + store.create + 飞书推送 + 科创板⭐; 实跑科创板扫出 33 只 high 拥挤
- [x] 回测 `tools/backtest_crowding_warning.py` — 向量化, train/test 切分, future_drawdown/命中率/IC, 接 walk_forward M01 时序护栏 (dirty 拦截实测生效); 4 单测过
- [x] scheduler `_crowding_watch_loop` — `CROWDING_WATCH_ENABLED=1` 启用, urllib 调 alert-service

## 待办

- [ ] git commit 策略文件 (`crowding_drawdown.py` 等) → 解除 M01-C dirty 拦截, 方可跑样本外
- [ ] 实跑样本外: `python tools/backtest_crowding_warning.py --start 2024-01 --end 2026-07 --train-cutoff 2025-12 --board 688 --strict-timeline`, 据命中率/IC 校准阈值与权重
- [ ] 生产服务恢复后: crontab 加 `40 15 * * 1-5 curl .../crowding-scan` (当前 crontab 2026-07-18 全停用)
- [ ] 前端 E2E: 确认 Screener.tsx 的 risk_flags chip 正确显示拥挤度标签 (代码零改动, 待服务起来验证)
- [ ] `agf-spec-validate` 校验本 change → UAT 签字 → `agf-spec-archive` 归档
