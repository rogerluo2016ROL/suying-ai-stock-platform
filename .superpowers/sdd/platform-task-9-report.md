# Task 9 report

- 拆分 data-service 的 inventory、jobs、schedules、readiness 资源；`status` 保留兼容汇总。
- inventory 使用真实表 COUNT，不再复用 scheduler 的单次写入量。
- signal-service 兼容 `/api/v1/data/*` 路由移除 subprocess fallback，并标记 `Deprecation: true`。
- 验证：data status semantics 1 passed；data/signal Python 文件 py_compile 通过。
- 复审修复：readiness 复用完整组件判定（含 Tushare 配置、PG、runtime 详情）；未配置 Tushare 时 `ready=false`。
- 前端数据源状态补充 `pending` 语义并在 normalize 中保留。
