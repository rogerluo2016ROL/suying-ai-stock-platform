# Task 5 实现报告

## 交付结果

- 新增 `tools/embodied_refresh/changes.py`，只允许 `success` 快照作为差异基线。
- 实现六维 0–100 重要性评分，权重为来源 25、商业化 25、映射变化 20、业务贡献 15、节点重要性 10、时效交叉验证 5，并保留因子明细。
- 实现 P0/P1/P2/P3 边界：85/70/50，分数强制截断到 0–100。
- 变动指纹不包含 run_id，同一变动跨 rerun 稳定；单批次重复行只产生一条变动。
- 中文摘要按 P0→P1→P2、同级按分数降序与公司代码稳定排序；P3-only 返回 `None`，不出站。
- 摘要包含截止时间、分级数量、状态/阶段前后变化、来源、证据日期、剩余风险、L1–L8 覆盖变化、Top3 进出原因及投资风险声明。

## TDD 与验证证据

- RED：`bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_changes.py -q`，收集阶段因 `ModuleNotFoundError: embodied_refresh.changes` 失败。
- GREEN：同命令通过全部 Task 5 用例。
- 前序回归：`bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_repository.py tools/tests/test_embodied_refresh_sources.py tools/tests/test_embodied_refresh_evidence.py tools/tests/test_embodied_refresh_mappings.py tools/tests/test_embodied_refresh_audit.py -q`，全部可运行用例通过，1 个 PostgreSQL 条件用例跳过。

## 范围说明

未修改工作树中已存在的 `.superpowers/sdd/.gitignore`、`progress.md`、`task-2-report.md`、`task-3-report.md` 变更；Task 5 提交只包含本任务的实现、测试和报告。
