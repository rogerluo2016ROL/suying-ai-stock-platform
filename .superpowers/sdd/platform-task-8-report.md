# Task 8 报告

## 已完成

- 新增 `kronos-contracts` 健康契约包，提供 `ComponentCheck`、`ServiceHealth`、PostgreSQL 探针和统一构造函数。
- API Gateway 新增 `/api/v1/health/live`、`/api/v1/health/ready` 和 `/api/v1/runtime/readiness`，聚合服务探针并在单个服务超时时返回 200 与 `ready=false`。
- 新增健康契约测试。

## 验证

- `PYTHONPATH=packages/kronos-contracts:services/api-gateway bash tools/codex-lowio.sh py packages/kronos-contracts/tests -q`：2 passed
- `python3 -m py_compile packages/kronos-contracts/kronos_contracts/*.py services/api-gateway/app/main.py services/api-gateway/app/runtime.py`：通过

## 补齐

- 11 个业务服务新增 live/ready 路由并保留旧 health 路由。
- 业务 Dockerfile 安装本地 `kronos-contracts`。
- 增加 gateway readiness 聚合测试。
