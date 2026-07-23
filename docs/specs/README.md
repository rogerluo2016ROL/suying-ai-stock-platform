# docs/specs/ —— 行为规格（活规格）

> 系统**当前行为**的真相，按**能力（capability）**组织，永远反映现状。AGF 第三类「永远当前」的 SSOT（另两类：`docs/design/DESIGN.md` 设计 token、`docs/adr/000` 技术栈）。决策见 [ADR-012](../adr/012-spec-driven-change-folders.md)。

## 是什么

- 每个能力一份 `docs/specs/<capability>/spec.md`（capability 用 kebab-case，如 `user-auth/spec.md`、`theming/spec.md`）。
- 内容是**行为需求**（`### Requirement:` 规范性 MUST/SHALL 契约）+ **可测试场景**（`#### Scenario:` WHEN/THEN，可选 AND）。
- **维护者：product-lead**。不手改——通过变更文件夹的 delta + archive-merge 演进（见下）。

## 怎么演进（事件溯源）

活规格 = 所有已归档 delta 的左折叠：

```
docs/changes/<change>/specs/<cap>.md (delta: ADDED/MODIFIED/REMOVED/RENAMED)
        │  UAT 业务签字后
        ▼  agf-spec-archive.py <change> <date>  （顺序 RENAMED→REMOVED→MODIFIED→ADDED）
docs/specs/<cap>/spec.md  ← 永远是当前真相
```

- **不要手工编辑活规格做功能变更**——功能变更一律走 `docs/changes/<change>/` 的 delta，archive 时自动 merge 进来。
- 纯笔误 / 链接修复可直接改活规格（与 ADR 同政策）。

## 格式纪律（被 `agf-spec-validate.sh` 机校）

- 每个 `### Requirement:` 下**至少 1 个 `#### Scenario:`**（scenario 恰好 4 个 `#`；3 个或纯 bullet 视为缺失）。
- Requirement 正文用 **MUST / SHALL**（缺则 advisory warn）。
- 模板见 [`_TEMPLATE.md`](_TEMPLATE.md)。新建能力：`cp _TEMPLATE.md <capability>/spec.md` 后填写。

## 校验

```bash
bash .claude/scripts/agf-spec-validate.sh docs/specs/<capability>/spec.md
```

advisory（不阻断）；product-lead propose 后自检、code-reviewer 在 review 时跑。
