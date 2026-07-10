# ADR-017 数据 readiness 快照

不同执行模式使用 profile 声明必需数据源与允许延迟。执行前由 `ReadinessEvaluator` 检查覆盖率及截止时间；必需源过期则状态为 `blocked`。结果以不可变 `data_readiness_snapshots` 保存，并通过 data-service API 按 ID 查询，便于审计和重放。
