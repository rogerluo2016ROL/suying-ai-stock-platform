# 任务2报告：历史 regime 隔离

## 状态
- 已完成

## 文件
- `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py`
- `packages/kronos-factors/tests/test_bi_hardtech_v2.py`

## 提交号
- `c9af74f2`

## 红灯 / 绿灯
- 红灯命令：
  - `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_bi_hardtech_v2.py::test_explicit_historical_regime_skips_current_regime_lookup -q`
  - 结果：1 失败
  - 关键信息：`AttributeError: module 'kronos_factors.engine.bi_trend_launch' has no attribute '_resolve_global_market_regime'`
- 绿灯命令：
  - `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_bi_hardtech_v2.py packages/kronos-factors/tests/test_bi_trend_four_axis.py -q`
  - 结果：24/24 通过（`test_bi_hardtech_v2.py` 14 个，`test_bi_trend_four_axis.py` 10 个）

## 自审
- 新增 `_resolve_global_market_regime(explicit=None)`，显式传入字典时直接返回副本并标记 `explicit`，不会读取当前 runtime regime。
- `run_bi_screening(...)` 新增兼容参数 `global_market_regime=None`，默认不传时仍走原来的当前 runtime 查询路径，保持生产行为。
- 仅在 `market_info` 增加 `global_regime_source` 溯源字段，没有改动原有选股、打分、风控和调用逻辑。
- 保留了任务1现有接口：原有调用方不传新参数时无需改动。

## 担忧
- 本次只隔离了全局 regime 来源；函数内其余市场环境计算（例如 breadth / breadth_10d / regime）仍按 `trade_date` 对应数据执行，这是 brief 要求的最小改动，但如果后续历史回放还要求“全部市场环境都外部注入”，需要另开任务处理。
