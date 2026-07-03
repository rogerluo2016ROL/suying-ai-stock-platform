---
# 结构化元数据（matrix.sh / 自动化工具解析用；不要删，值可改）
# frontmatter 是 verdict 数据的唯一 SSOT（agf-verdict.py 解析；validate-verdict hook 重算守门、agf-matrix.sh fan-in 都读这里）
feature: [feature-slug]
date: YYYY-MM-DD
reviewer: code-reviewer        # pool 模式填实例名如 code-reviewer-2
code_verdict: approve          # approve | approve with changes | block
sit_audit_verdict: Pass        # Pass | Pass with concerns | Redo SIT
critical_count: 0
warning_count: 0
suggestion_count: 0
sit_checks:                    # SIT 4 检查的原子事实（推导 sit_audit_verdict；各 ∈ pass|concerns|fail）
  progress: pass
  ac_coverage: pass
  evidence: pass
  fail_marking: pass
---

# Code Review — [Feature Name]

> **This is a template.** Copy to `docs/reviews/[feature]-[YYYY-MM-DD].md`（单实例）或 `docs/reviews/[feature]-r<N>-[YYYY-MM-DD].md`（pool 模式实例 N）。**保留顶部 YAML frontmatter**——matrix.sh 等工具依赖它解析 verdict + 计数（详见 `ADR-001`）。删除本介绍段后发布。

- **Date**: YYYY-MM-DD
- **Reviewer**: code-reviewer ([model name])
- **Branch**: [branch + commit hash]
- **需求来源**: `docs/changes/[change]/`（`tasks.md` 含 AC↔Scenario 映射表；旧流程 fallback：`docs/prd/[feature]-[date].md`）
- **Files reviewed**: 列出本次变更涉及的所有文件路径

## Summary

- 代码 Verdict（3 档之一，与 `.claude/agents/code-reviewer.md` 一致）：`approve` / `approve with changes` / `block`
- 一句话理由

## Findings

### Severity 定义

- **Critical** — 上线前必须修，阻断合并（安全漏洞、数据丢失风险、生产 bug）
- **Warning** — 强烈建议修，不阻断但需工单跟进（性能问题、错误处理缺失、架构偏离、命名 / 注释 / 小重构）
- **Suggestion** — 可选优化 / 风格层面，dev 自行决定是否采纳

### Critical / Warning / Suggestion 列表

| ID | Severity | File:Line | Issue | Recommendation |
|---|---|---|---|---|
| C-1 | Critical | backend/app/api/auth.py:42 | SQL 字符串拼接，存在注入风险 | 改用 SQLAlchemy ORM 或参数化查询 |
| W-1 | Warning | backend/app/services/user.py:88 | 异常被 `except Exception: pass` 静默吞掉 | 至少打 structured log，必要时 re-raise |
| S-1 | Suggestion | frontend/src/Login.tsx:120 | 重复条件判断可抽函数 | 抽 `isValidEmail` |

## Security Checklist (per `.claude/standards/security.md`)

逐条核对，标 ✅ / ❌ / N/A：

- [ ] SQL 查询使用参数化或 ORM
- [ ] 输出编码 / CSP headers 配置
- [ ] shell 命令无未清理输入
- [ ] 受保护端点有认证/授权
- [ ] 无硬编码密钥
- [ ] 敏感数据不入日志
- [ ] 系统边界做输入验证
- [ ] 公共端点配置限流
- [ ] CORS 白名单正确
- [ ] 依赖无 critical CVE

## Equivalent-Bypass Check (per `security.md`)

- [ ] 检查代码是否绕过 hook 限制（如用 `shutil.rmtree` 替代 `rm -rf`、`metadata.drop_all()` 替代 `DROP TABLE`）

## 前后端对接审查项（含 `frontend/` 改动时必填；纯后端 / 文档 PR 整节标 N/A）

逐条核对（SSOT：`.claude/standards/testing.md` 前后端对接强制覆盖项 + `.claude/agents/code-reviewer.md` 同名节；手写绕过生成产物 / 控件无 handler → critical）：

- [ ] **契约走生成产物**：业务代码无手写 `fetch` / 手写请求响应类型 / 手写 MSW handler——API 调用必走 orval 生成产物（`frontend/src/api/generated/`）
- [ ] **交互完整性**：无空 handler / `TODO` handler / 仅 `console.log`；提交·数据类控件真调生成 client / mutation
- [ ] **交互测试在位**：每个交互控件有组件测试断言「触发 → 以正确参数调了正确 API」
- [ ] **endpoint 在契约内**：前端调用的 endpoint 均存在于后端 OpenAPI

## SIT Audit

> dev 在 code-review 前已按 skill `agf-running-sit-tests` 自跑 SIT，证据 append 到 `progress/<role>.md` 的 `**SIT 证据**` 段。本节是 reviewer 对证据的独立 audit（不重跑 SIT）。

### 4 项检查（参见 `.claude/agents/code-reviewer.md` "SIT Audit" 节）

- [ ] **progress 完整性**：`progress/<role>.md` 是否含本次 task 的完整 SIT 证据段（标题 `**SIT 证据**`，按 AC 列出条目）
- [ ] **AC 覆盖**：SIT 证据是否覆盖全部 AC（来自 changes/tasks.md 映射表；PRD fallback）在 integration 层的体现
- [ ] **证据可信度**：命令、输入、输出是否真实可重放（非伪造截图 / mock 替身）
- [ ] **失败/阻塞标记真实性**：fail / blocked 用例是否如实标记并详写（偏差说明 + 命令 + 输出片段；pass 可简写）——与 `workflow.md` §SIT Audit 4 项检查措辞对齐

### Verdict（3 档之一）

- ✅ **Pass** — 4 项全部通过
- ⚠️ **Pass with concerns** — progress 完整 + AC 覆盖通过，但证据可信度或否定结果有 minor gap（列出，不阻断）
- ❌ **Redo SIT** — 任一项 fail（证据缺失 / AC 漏覆盖 / 证据不可信 / 虚假 pass）

## Hand-off

- 代码 verdict `approve` 或 `approve with changes` + SIT Audit ✅/⚠️ → SendMessage product-lead 进入 **E2E**
- 代码 `block` 或 SIT Audit ❌ Redo SIT → SendMessage product-lead 列 critical 项 + Redo SIT 要求，由 product-lead 打包派回 dev

