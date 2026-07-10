# Task 4 证据闸门报告

## RED

- 修复前简报要求的两组 truthfulness 测试尚未创建，因此当时无法执行聚焦测试。
- 修复前 `factor_calibration._compute_ic_fallback` 使用固定随机数生成 IC/ICIR；backtest `/run` 与 `/calibrate` 使用 proxy/默认权重。

## GREEN

- `factor_calibration` 不再生成随机指标；无真实因子快照/未来复权收益时返回 `status=insufficient_data`、空 factors，并跳过权重 apply。
- scheduler 仅在 calibration 状态为 `ready` 时允许 apply。
- backtest `/run`、`/calibrate` 在真实 adapter 完成前返回 HTTP 409；新增只读 `/factor-evidence`，返回 `unsupported` 与缺失要求。
- 命令：`python3 -m py_compile services/backtest-service/app/routes.py services/training-service/app/factor_calibration.py services/training-service/app/scheduler.py`（通过）。
- 提交钩子 lint 通过；SHA：`cfe80532`。

## GREEN（补齐）

- 删除 backtest routes 中三引号包裹的旧 calibrate/proxy 死代码，恢复 compare 合法路由并在证据缺失时返回 422 `INSUFFICIENT_EVIDENCE`。
- 新增 training/backtest truthfulness 聚焦测试；两组测试均通过（各 2 passed）。
- `python3 -m py_compile` 通过。当前环境无项目 `.venv`，因此使用系统 `python3` 验证。

## 复验结果

- training 聚焦测试：2 passed；backtest 聚焦测试：2 passed。
- backtest-service 全量测试：2 passed。
- training-service 全量测试：36 passed、1 skipped、1 failed。
- 唯一失败为既有路径依赖缺失：`Kronos/Kronos-uat-bak/dataset.py`，不属于任务 4 改动。

## 遗留问题

- training-service 全量测试仍受既有 `Kronos/Kronos-uat-bak/dataset.py` 缺失影响；任务 4 新增测试与 backtest 全量测试均已通过。
