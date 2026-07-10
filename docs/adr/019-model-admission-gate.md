# ADR-019: Model admission gate

模型晋级必须具备数据就绪、严格时间线、成本模型、样本外报告和回撤样本五类证据。production 还必须经过人工审批；缺证据或 MLflow 不可用时 fail closed。
