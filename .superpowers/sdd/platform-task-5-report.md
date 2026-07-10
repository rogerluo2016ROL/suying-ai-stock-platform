# Task 5 实施报告

## RED

- `test_missing_kronos_is_unavailable_not_neutral` 首次运行失败：`AttributeError: module 'app.routes' has no attribute '_combine_signal_dimensions'`。
- xtquant 能力测试文件首次运行因 worktree 没有 `.venv` 未能启动；改用共享解释器后进入测试。

## GREEN

- 信号维度只对实际可用分数归一化；缺失维度为 `None`，返回 `coverage`、`unavailable_dimensions` 和 `result_status=insufficient_data`，Kronos 不再固定 50。
- xtquant SDK 可用但真实能力未接入时抛出 `BrokerCapabilityError`，不调用 stub；SDK 缺失仍保留明确的开发 stub 模式，并通过 `live_readiness()` 返回 blocked。

## 验证

- `/Users/rogerluo/程序目录/K线大模型/.venv/bin/python -m pytest services/trade-service/tests/test_xtquant_capabilities.py -q`：2 passed。
- `/Users/rogerluo/程序目录/K线大模型/.venv/bin/python -m py_compile services/trade-service/app/routes.py services/trade-service/app/xtquant_broker.py`：通过。
- signal 全文件：14 passed, 1 failed；失败是既有日期敏感断言（固定 `2026-06-21`，当前日期为 `2026-07-10`，期望 fresh 实际 stale），与本任务改动无关。

## SHA

`d0bb2ec21725b42e66af5464edff907b9ef84e61`

## 遗留问题

- xtquant 的真实下单、撤单、持仓、资产查询和回调仍需在 Windows/QMT 环境接入；当前 live readiness 保持 blocked。

## 审查修复

- SDK 缺失或能力未实现时，connect、下单、撤单、持仓、资产及 sync 全部抛 `BrokerCapabilityError`，不再调用成功 stub。
- fundamental、event risk、market 缺失时保持 `None`；insufficient_data 返回 `signal=None`、`decision=unavailable`，不写入历史分数。
- 修复后：trade capability `3 passed`；signal 定向测试 `1 passed`；两服务 py_compile 均通过。
