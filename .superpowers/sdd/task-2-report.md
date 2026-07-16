# 任务2报告：历史 regime 隔离

## 状态
- 已完成

## 文件
- `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py`
- `packages/kronos-factors/tests/test_bi_hardtech_v2.py`

## 提交号
- `1456deb6`

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

---

## 追加修复（审查回合）

### 审查问题
1. `run_bi_screening` 无前序交易日 early return 的 `market_info` 缺少 `global_regime_source`。
2. market crash 熔断 early return 的 `market_info` 缺少 `global_regime_source`。
3. 之前测试只覆盖 helper，没有直接校验 `run_bi_screening` 返回契约。

### 红灯
- 命令：
  - `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_bi_hardtech_v2.py packages/kronos-factors/tests/test_bi_trend_four_axis.py -q`
- 结果：
  - `2` 失败，分别是：
    - `test_run_bi_screening_no_prev_trade_date_keeps_return_contract`
    - `test_run_bi_screening_crash_return_keeps_return_contract`
- 失败原因：
  - 无前序交易日分支返回缺少 `global_regime_source`
  - 熔断分支返回缺少 `global_regime_source`

### 修复
- `packages/kronos-factors/tests/test_bi_hardtech_v2.py`
  - 新增直接调用 `run_bi_screening` 的契约测试。
  - 覆盖无前序交易日分支。
  - 覆盖熔断分支。
  - 两个测试都显式传入 `global_market_regime`，并用 patch 断言不会触发 runtime `get_market_regime`。
- `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py`
  - 仅给两个 early return 的 `market_info` 补上 `global_regime_source`。
  - 默认生产行为、正常主路径、主路径 market_info、选股与风控逻辑均未改动。

### 绿灯
- 命令：
  - `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_bi_hardtech_v2.py packages/kronos-factors/tests/test_bi_trend_four_axis.py -q`
- 结果：
  - `26/26` 通过
  - `packages/kronos-factors/tests/test_bi_hardtech_v2.py`: `16` 个
  - `packages/kronos-factors/tests/test_bi_trend_four_axis.py`: `10` 个

### 当前担忧
- 这次修的是返回契约完整性，不涉及扩大历史回放注入范围；如果后续要求把 breadth / sh_trend / regime 等市场环境也改成“完全由历史 runner 外部提供”，那会是另一轮接口设计，不适合夹带进这次窄修复。
