# Task 3：网关预览数字和伪 lineage

## RED

命令：`/Users/rogerluo/程序目录/K线大模型/.venv/bin/python -m pytest tests/test_workbench_contract.py -q`（目录 `services/api-gateway`）

结果：`2 failed`。失败原因是响应仍包含 `CTX-preview` / `CAND-preview`，且状态仍为 `ok`。

## GREEN

移除网关内置的 `_WORKBENCH_MODULES` 固定业务数据；工作台接口统一返回 `status=unavailable`、空 `sections/actions/lineage`、`freshness.status=missing`、`as_of=None`，并保留请求上下文。

命令：`/Users/rogerluo/程序目录/K线大模型/.venv/bin/python -m pytest tests -q`（目录 `services/api-gateway`）

结果：`9 passed, 1 warning`。

## SHA

提交后填写实际 commit SHA。

## 遗留问题

真实聚合由 Task 7 接入前，工作台数据不可用；网关不会展示候选数、表数量、在线数或伪 lineage。
