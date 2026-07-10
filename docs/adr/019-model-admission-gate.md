# ADR-019: Model admission gate

模型晋级必须具备数据就绪、严格时间线、成本模型、样本外报告和回撤样本五类证据。production 还必须经过人工审批；缺证据或 MLflow 不可用时 fail closed。

## 决策

- 阶段固定为 `research → candidate → paper → production`，晋级证据必须带可追溯 `evidence_run_id`。
- paper 需要基线模型；无基线时不能用“无对手”方式晋级。
- PRD Q-3 尚未批准 production 数值阈值，因此 `production_thresholds_approved=false`，即使五门通过并人工批准也继续阻断。
- MLflow 使用注册模型 alias 表达阶段。alias 更新成功后才允许提交 PostgreSQL stage；MLflow 失败时 PostgreSQL 不发生变更。
- `MLFLOW_MODE=live` 时连接失败直接报错，禁止静默回退 mock 后伪称晋级成功。
