---
name: verified-facts
description: AGF 模板本体硬事实（Pool 上限 / progress 5 段格式 / Verdict 词表 / Worktree baseRef / scan-secrets 厂商数 / 角色能力 SSOT / 行为规格 delta），跨 session 复用避免重 grep。仅在编辑模板内部（agents / standards / hooks / scripts / commands / docs/adr）时加载。
paths:
  - ".claude/agents/**"
  - ".claude/standards/**"
  - ".claude/hooks/**"
  - ".claude/scripts/**"
  - ".claude/commands/**"
  - "docs/adr/**"
---

# Verified Facts（AGF 模板本体硬事实）

> 组件清单 / 计数以实际目录为准（`ls .claude/agents|standards|skills|hooks|scripts|commands`），不在文档里重复声明。本文件由 `CLAUDE.md` 指针引入；仅编辑模板内部文件时按 path 自动加载，避免常驻 context（v6.6.2 从 CLAUDE.md 下沉）。

- **Pool 上限**（ADR-001 + `team-roles.md` `Pool 上限` 列）：
  - product-lead / tech-lead / uiux-designer / content-writer / growth-analyst / deploy-engineer / apple-release-engineer = **1**（禁 pool）
  - frontend-dev / backend-dev / code-reviewer / qa-engineer = **5**（Small=3 / Med=5 / Large=7）
  - ai-agent-dev / ml-engineer / miniapp-dev / miniapp-code-reviewer / miniapp-qa-engineer / apple-dev / apple-code-reviewer / apple-qa-engineer = **3**
- **Pool 模式 文件命名**：`progress/<role>-<N>.md` / `docs/reviews/<feat>-r<N>-<date>.md` / `docs/qa/<feat>-{e2e,uat}-q<N>-<date>.md`
- **progress 5 段格式**（`ac-lifecycle.md` "完整条目格式"）：状态 / Skills / SIT 证据 / 质量门 / 下一步（hook `check-progress-file.sh` 强制校验）
- **Verdict 词表** 4 套（`workflow.md` §Verdict 词表）：code-review `approve / approve with changes / block`；SIT Audit `Pass / Pass with concerns / Redo SIT`；QA 报告级 `Promote / Block / Conditional promote`；UAT 业务签字 `approve / request changes`
- **P0 case 必须 pass^2**：UAT 阶段 P0 case 连续跑 2 次都过才签字
- **Worktree baseRef**：`head`（`.claude/settings.json` pin）
- **Hook 运行时 profile（ADR-014）**：`AGF_HOOK_PROFILE=minimal|standard`（默认 standard，未设=零回归）；**永不响应 profile**：四层防御（block-dangerous-bash / scan-secrets / sanitize-tool-output / scan-commit）+ `block-config-edit` + `enforce-write-scope` + `validate-verdict`；**可降级**：`teammate-keepalive` / `check-progress-file` / `session-start-context` / `validate-task-schema` / `gate-deploy-release-auth` / `gate-redo-fuse`；env 须 `export`（shell 变量不传 hook 子进程）。原 opt-in 遥测（`AGF_OBSERVE` / `AGF_GOVERNANCE_LOG`）已按 ADR-026 D6 退役（v6.26.0）
- **scan-secrets 厂商数 = 11**：AWS / GitHub / OpenAI / Anthropic / Google / Slack / DeepSeek / Doubao / Qwen / MiniMax / Apple 签名材料（ASC API key / match 密码 / fastlane session）+ PEM/SSH/PuTTY/BIP39
- **行为规格 / delta（ADR-012，v6.9.0）**：需求入口 = 变更文件夹 `docs/changes/<change>/`（proposal / specs delta / design / tasks，取代 PRD；PRD 弃用 v6.9.0 → 删 v7.0.0）；活规格 `docs/specs/<cap>/spec.md`（行为 SSOT，永远当前）；delta 段头 `## (ADDED|MODIFIED|REMOVED|RENAMED) Requirements`，archive 应用顺序 **RENAMED → REMOVED → MODIFIED → ADDED**；每 Requirement ≥1 `#### Scenario`（恰好 4 个 #）；`agf-spec-validate.sh` 校验（advisory，含 scenario 须含 WHEN/THEN）+ `agf-spec-archive.py` 确定性 merge（段模型解析 + **pre-flight 门控**：名称失配/重名等异常 → 非零退出不归档，`--force`/`--dry-run`）；同一 capability 同时只允许一个在途 change（防 lost-update）；AC 仍 `AC-N` 编号、语义源自 delta scenario（progress / SIT 机器全不变）
- **角色能力 SSOT**：`.claude/agents/roles.yaml`（机读单一来源）；`gen-roles.py` 反向生成各 agent `.md` frontmatter（逐字零 diff）+ team-roles 两表（marker 注入），drift 由 `lint-all.sh` 硬阻断
- **color 枚举**：官方 sub-agent frontmatter `color` 仅 8 值（red/blue/green/yellow/purple/orange/pink/cyan）；`gen-roles.py` `COLOR_ENUM` 守门，越界 schema fail（v6.6.2 加固）
