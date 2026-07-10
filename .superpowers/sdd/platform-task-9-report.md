# Task 9 report

- 拆分 data-service 的 inventory、jobs、schedules、readiness 资源；`status` 保留兼容汇总。
- inventory 使用真实表 COUNT，不再复用 scheduler 的单次写入量。
- signal-service 兼容 `/api/v1/data/*` 路由移除 subprocess fallback，并标记 `Deprecation: true`。
- 验证：data status semantics 1 passed；data/signal Python 文件 py_compile 通过。
