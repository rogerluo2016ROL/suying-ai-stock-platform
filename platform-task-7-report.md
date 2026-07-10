# Task 7 报告

- Gateway `/api/v1/data` 已收敛到 `data-service:8010`，保留其他路由不变。
- signal-service 的 `/api/v1/dashboard/*`、`/api/v1/data/*` 兼容路由保留，并通过 `Deprecation: true`、`X-Deprecated-Route: true`、`X-Route-Owner` 显式标记弃用与 owner。
- screener-service 不再注册 training mock 路由，training owner 保持独立。
- 聚焦测试：gateway 7 passed；screener boundary 1 passed；signal contracts 15 passed、1 个既有日期敏感失败（测试固定 2026-06-21，在当前日期 2026-07-10 被判 stale）。
- `py_compile`：gateway、signal、screener 通过。
