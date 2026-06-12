# Plans 轻量化格式规范

> 本规范约束 **派工前** `product-lead` 用 `superpowers:writing-plans` 生成的实施计划。
> plan 的目标读者是"有上下文但没看完 spec"的执行层 agent，轻量化即可。

## 格式 vs 默认模板的差异

| 维度 | 默认模板 | 本规范（轻量化） |
|---|---|---|
| **Step 粒度** | 每个 task 3-6 个 step（含 test/impl/commit 分离） | 每个 task 1-3 个 step |
| **代码块** | 每 step 都有完整代码 | 无 inline 代码；用"做什么"描述替代 |
| **文件映射** | Modify: `path:123-145`（行号） | Modify: `path`（文件名即可） |
| **测试命令** | 每 step 有 `Run: pytest ...` | 只在关键验证点标一句 |
| **Commit** | 每 task 有 commit step | 合并到完成报告里，不在 plan 里逐条写 |

## 轻量化 Header

```markdown
# [Feature] 实施计划

**Goal:** 一句话目标
**架构:** 1-2 句方案概述
**文件:** 列出涉及的核心文件（新增 + 修改）

---
```

## 轻量化 Task 格式

```markdown
### Task N: [模块名]

**涉及文件:** `backend/app/foo.py` / `frontend/src/bar.tsx`

- [ ] **Step 1: [做什么]**
  - 参考：[设计文档路径或上一 task]
  - 验收：如何验证完成（命令 / 行为描述）

- [ ] **Step 2: [做什么]（如有）**
  - 参考：[相关 doc 或 Step 1]
  - 验收：[验证方式]
```

**禁止出现**：
- `TBD` / `TODO` / `待实现`
- inline 代码块（除非是极端复杂的单行正则或配置）
- `git commit` 步骤（移到完成报告里）

**允许出现**：
- 关键 CLI 命令（如 `pnpm dev`、`pytest`）作为验收提示
- 文件路径引用（指向 `docs/design/` / `docs/adr/`）
- 与其他 Task 的依赖关系说明

## 长度约束

- 单个 Task ≤ 200 字（含 markdown）
- 整个 Plan ≤ 1 页（~500 字）
- 超过即拆分 — 拆分信号：超过 4 个 Task 或涉及 ≥2 个独立子系统

## 质量自检

- [ ] 每条 Step 都能用一句话描述"做什么 + 如何验"
- [ ] 没有 `TBD` / `TODO` / 引用未创建的函数
- [ ] Task 之间依赖关系清晰（谁先谁后）
- [ ] Plan 总字数 < 500

## 与默认模板的关系

本规范是 `superpowers:writing-plans` 的**项目级输出约束**，不替换 skill 本身。
`product-lead` 调用 skill 时按 skill 流程走，但保存 plan 前对照本规范做简化压缩。

执行层 agent（`frontend-dev` / `backend-dev` 等）收到轻量化 plan，具体实现细节由他们在 sub-task 内用 `superpowers:executing-plans` 或 `subagent-driven-development` 补充。