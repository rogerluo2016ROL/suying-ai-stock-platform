---
name: repo-layout
description: Repository directory map for AppGenesisForge — what lives where. Loaded on demand when an agent is about to create/modify project structure or unsure where to put a new artifact.
paths:
  - "**/*.md"
  - ".claude/**"
  - "docs/**"
  - "evals/**"
  - ".github/**"
---

# Repository Layout

> AppGenesisForge 的目录地图。新建文件 / 不确定某产物归属时查这里；修改本表后须同步 CLAUDE.md 里的指针。

## .claude/

| 路径 | 内容 |
|---|---|
| `.claude/agents/*.md` | 19 个团队角色 agent 定义（10 通用 + 3 `miniapp-*` + 4 `apple-*` + 2 post-launch；小程序 / Apple 设计由 `uiux-designer` 分别在 MiniApp Mode / Apple Mode 下覆盖）。**frontmatter（能力字段）是生成物**——见下行 `roles.yaml` |
| `.claude/agents/roles.yaml` | 角色能力机读 SSOT（model / color / tools / skills / pool / permission / focus / boundary）；`gen-roles.py` 从它生成本目录各 `.md` 的 frontmatter（逐字零 diff）+ `standards/team-roles.md` 两表（marker 注入）。改能力编辑此文件后重跑 `gen-roles.py`，`--check` 由 `lint-all.sh` 硬阻断 drift |
| `.claude/standards/*.md` | 团队通用规范（角色、工作流、测试、安全、观测、成本预算、轻量化 plan 格式等），跨项目复用 |
| `.claude/commands/*.md` | 项目级 slash commands：`agf-init`（装后由 Claude 接管初始化，替代手敲 `setup/init-team.sh`）`agf-team-start` `agf-team-stop` `agf-uat` `agf-tasks` `agf-board`（实时开发看板 HTML）`agf-release-retro` `agf-deploy-uat` `agf-apple-release`（Apple 发布门：签名分发包 + 冒烟）`agf-handoff`（给 Codex / opencode 交接执行层 → 隔离 worktree + stamped AGENTS.md + 出门/回门简报） |
| `.claude/scripts/*.sh` | 项目工具脚本（非 hook，product-lead 等手动调用）：`agf-tasks.sh`（task list 表格视图）/ `agf-board.sh`（实时开发看板：task 卡片三列 kanban + 成员栏【◆lead/●工作中/○空闲 + `通信 X前` inbox 活跃徽标】+ 卡片相对时间 + 阶段门 chips → 自包含 `progress/board.html`【gitignored】，`--watch` 循环重生成 + 页面自刷新 ≈ 实时，pidfile 单实例后启接管；角色归属 task `owner` 直读优先【19 角色含 apple-*，pool 实例名保留】、UAT gate 排除 uat-cases 用例文档、team 缺省选择项目亲和【成员 cwd 命中本仓库优先，跨项目 fallback 时 header ⚠ 揭示】；数据源 `~/.claude/tasks` + `~/.claude/teams` config + docs 报告 frontmatter，零新状态）/ `archive-progress.sh`（UAT 后归档 `progress/<role>-*.md` 到 `docs/qa/<feature>-process-log.md`，支持 pool 多实例合并）/ `agf-matrix.sh --type=progress\|review\|qa`（PL 聚合 N 份报告为 1 张表）/ `lint-all.sh`（全仓 bash/JSON/YAML lint 入口，pre-commit hook 自动链调）/ `agf-next-instance.sh <type> [<feat>]`（Pool fan-out 前算下一个实例 N，stdout 只出整数）/ `agf-check-ownership.sh <allowed-glob>...`（Pool 并行派发后校验实例改动未越界）/ `agf-sit-precheck.sh <progress-file>`（SIT 证据机器预检：placeholder / 漏证据 / pass 含失败 token / 质量门矛盾 flag，advisory 不阻断，dev 自检 + reviewer SIT Audit step 0，ADR-011）/ `agf-handoff.sh <change> [role]`（给 Codex / opencode 交接执行层：建隔离 worktree【分支 `feat/<change>`】+ 本地忽略 `AGENTS.md`【per-handoff 产物不进版本库】+ 把 tasks.md 的 AC↔Scenario stamp 进 worktree 根 `AGENTS.md`【含只读 SSOT / DoD 指针 / progress 回填模板 / CLAUDE.md 仅作背景框定】；命令入口 `/agf-handoff`）/ `test-install.sh`（安装链路 E2E 自检：mktemp 临时 git 仓实跑 `setup/install-to-existing.sh`，动态对比安装清单 + JSON 可解析 + 幂等性 known-gap，MINOR+ release 前必跑）；另有 `agf-tui.sh`——被 `setup/agf-team-start.sh` `source` 的纯 bash 零依赖 TUI 库（非入口、非 hook、不手动调用，放此目录顶层仅为 `lint-all.sh` 的 `bash -n` 覆盖）；ADR-001 + Multi-instance Worker Pool 详 `workflow.md`/ `agf-spec-validate.sh <spec-or-delta.md>`（行为规格 / delta 机校：每 Requirement ≥1 Scenario / 段头合法 / REMOVED 带 Reason+Migration / scenario 恰好 4 个 #，advisory 不阻断，ADR-012）；**`.py` 脚本（共 3 个，非「唯一」）**：`gen-roles.py`（角色能力 SSOT 生成器，从 `.claude/agents/roles.yaml` 生成各 agent frontmatter + `team-roles.md` 两表，默认写 / `--check`（被 `lint-all.sh` 链调硬阻断 drift）/ `--extract` 三模式）、`agf-verdict.py`（verdict 守门，被 `validate-verdict.sh` 委托，ADR-010）、`agf-spec-archive.py`（delta 确定性 merge 进活规格 + 归档 change，薄包装 `agf-spec-archive.sh`，沿用 `validate-verdict.sh → agf-verdict.py` 先例，round-trip 测试 `hooks/tests/test-agf-spec-archive.sh`） |
| `.claude/workflows/*.js` | saved Dynamic Workflows（显式触发，成本走 cost-budget Workflow 门）：`agf-review-sweep.js`（高风险大 PR 对抗深审，ADR-002）/ `agf-understand.js`（PRD/ADR 前只读理解地图，ADR-005）；阶段嵌入边界与 workflow agent 卫生约束见 `workflow.md` §何时用 Workflow |
| `.claude/skills/*/SKILL.md` | **项目自有 skill**（清单/计数以 `ls .claude/skills/` 为准，**勿在文档硬编码计数**——见 `verified-facts.md` 纪律）：需求入口 `agf-writing-change`（v6.9.0 取代 PRD）+ `agf-writing-prd`（弃用 fallback）/ 多 LLM 接入 `agf-wiring-multi-llm-sdk` / SIT（通用 `agf-running-sit-tests` + Apple `agf-running-apple-sit`）/ `agf-writing-adr` / `agf-writing-qa-report` / `agf-running-release-retro` / docx+pptx 报告 / `agf-writing-github-issue` / `agf-deploying-uat` / `agf-releasing-apple` / `agf-wiring-apple-llm` 等；**2 个外部第三方 skill**：`docx`、`pptx`（Anthropic 提供的低层 .docx / .pptx 读写脚本与 schema，供上面两个 writing-* skill 依赖调用 `scripts/office/soffice.py`） |
| `.claude/hooks/*.sh` | 四层防御 + 工作流 hook + git pre-commit；详见本目录与 `.claude/standards/security.md` |
| `.claude/hooks/tests/*.sh` | hook 单测（`test-*.sh`，**非 hook、不计入 hook 数**）；`lint-all.sh` + `setup/init-team.sh` 自动跑全部 |
| `.claude/rules/*.md` | path-scoped 规则（本文件 + `team-mode.md`），Claude Code 按文件路径自动加载 |
| `.claude/settings.json` | 项目配置：Agent Teams 启用、permissions allow/deny、hooks 注册、autoMemoryEnabled、worktree.baseRef |
| `.mcp.json` | 项目级 MCP server 注册（当前：`chrome-devtools-mcp@latest` 供 `qa-engineer` 跑 E2E；`@upstash/context7-mcp` 供 `tech-lead` 版本查证 / dev 拉第三方库最新文档防幻觉；`xcodebuildmcp@latest` 供 `apple-dev` / `apple-qa-engineer` 驱动 Xcode——build / 模拟器 / 真机 devicectl / XCUITest）；与 `.claude/settings.json` 分文件（前者是 MCP 协议规范文件，后者是 Claude Code 私有配置） |

## docs/

| 路径 | 内容 |
|---|---|
| `docs/FIRST_RUN.md` | 接手模板的 Day-1 清单 + 前置知识 + 常见踩坑 |
| `docs/team-capability-map.md` | §1 端到端全景图（角色 + 阶段门 + hook + skill 叠加）+ 全角色协作 Mermaid + 能力对照表，改 agent 时必须同步 |
| `docs/product-workflow.md` | 产品交付工作流 + 全量术语词典；写 PRD / 拆 Task / 用术语前先查这里 |
| `docs/prd/*.md` | ⚠️ **弃用 v6.9.0 → 删 v7.0.0**（fallback）：旧 PRD 入口（skill `agf-writing-prd`）；新需求走变更文件夹 `docs/changes/`（见下，ADR-012） |
| `docs/design/DESIGN.md` | **项目级设计系统 SSOT**（设计 token：color/typography/spacing/radius/component + `on-*` 配对 + Do/Don't），uiux-designer 维护；各 feature spec 与前端样式引用其 token，禁内联重声明（纪律见 `coding.md` 设计 token 纪律） |
| `docs/design/[feature]/` | uiux-designer 产出（`spec.md` + `index.html`，资源放 `assets/`；视觉值引用 `docs/design/DESIGN.md` token） |
| `docs/reviews/*.md` | code-reviewer 产出 + release retro（`retro-vX.Y.Z-YYYY-MM-DD.md`）+ 季度 eval 漂移记录 |
| `docs/qa/*.md` | qa-engineer 产出（E2E / UAT 报告，写时用 skill `agf-writing-qa-report`；SIT 不再独立成 `docs/qa/*-sit-*.md`，证据写入 `progress/<role>.md` 由 code-reviewer 在 review 时 audit）+ `<feature>-process-log.md`（progress/ 归档，UAT 签字后由 product-lead 写入） |
| `docs/deploy/*.md` | deploy-engineer 产出（UAT 部署报告 `<feature>-uat-<YYYY-MM-DD>.md`，写时用 skill `agf-deploying-uat`；含 UAT 栈各服务 URL + 冒烟证据 + 迁移结果 + 部署 commit SHA + 二元 gate；qa-engineer 读它拿 E2E/UAT 测试目标地址）+ apple-release-engineer 产出（Apple 发布报告 `<feature>-apple-<YYYY-MM-DD>.md`，写时用 skill `agf-releasing-apple`；含分发包定位 + 冒烟证据 + 构建 commit SHA + 二元 gate；apple-qa-engineer 读它拿测试目标） |
| `docs/adr/*.md` | 架构决策记录（命名 `NNN-[slug].md`，写时用 skill `agf-writing-adr`；ADR-000 是基线；**索引见 `README.md`**——13 个 ADR 一句话 + 演进链 + 主题分组） |
| `docs/specs/<cap>/spec.md` | **活规格（行为需求 SSOT，永远当前）**：product-lead 维护，按能力 kebab-case 组织；功能变更走 delta + `agf-spec-archive` merge，不手改（ADR-012）；模板 `docs/specs/_TEMPLATE.md` + `README.md` |
| `docs/changes/<change>/` | **变更文件夹（需求入口，取代 PRD）**：四件套 proposal / specs delta / design / tasks（skill `agf-writing-change`）；`agf-spec-validate` 校验；UAT 签字后 `agf-spec-archive` 移 `archive/<date>-<change>/`；模板 `_TEMPLATE/` |

## progress/（Self-Reporting Pattern 持久化）

| 路径 | 内容 |
|---|---|
| `progress/<role>.md` | 执行层 teammate 完成任务的底稿（5 段格式：状态 / Skills / SIT 证据 [含 AC `[x]/[ ]` 内联] / 质量门 / 下一步）；feature 期间进 git，UAT 签字后由 product-lead 归档到 `docs/qa/<feature>-process-log.md` 并从 main 移除 |
| `progress/README.md` | 写入规则、Hook 兜底、Git 策略说明 |
| `progress/.gitkeep` | 保持空目录在 git 中存在 |

强制对象、写入格式与归档流程见 `.claude/standards/ac-lifecycle.md` "Self-Reporting Pattern" 节；hook 兜底由 `.claude/hooks/check-progress-file.sh` 在 `SubagentStop` / `TeammateIdle` 触发。

## 应用代码（首个 feature 启动时由执行层创建）

| 路径 | 内容 |
|---|---|
| `backend/` | FastAPI 应用（按 ADR-000）；agents 在 `backend/app/agents/` |
| `frontend/` | React + Vite 应用（按 ADR-000） |
| `miniapp/` | 微信小程序（按 `.claude/standards/miniapp.md`） |
| `apple/` | macOS / iOS 原生 app（单一多平台 Xcode 工程 + 内嵌 `AppCore` SPM package + `AppUITests/` + `fastlane/`，按 ADR-007/008/009 + `.claude/standards/apple-native.md` §1） |
| `docker-compose.yml` | 仅编排 Postgres |

## 工程配套

| 路径 | 内容 |
|---|---|
| `Makefile` | 本地开发一键入口（`make help` 列全部 target）：`dev` 包装 ADR-000 §本地开发流程（uv + pnpm + postgres），`install`/`test`/`lint`/`migrate` 走 uv。**不含 UAT**——隔离 UAT 栈走 deploy-engineer 受治理门 `/agf-deploy-uat`（契约 `deployment.md` §6.2，含迁移 + 冒烟 + gate + 报告），不收进 Makefile 以免复刻其起栈命令、产生 SSOT 漂移 |
| `evals/*.jsonl` | 角色漂移检测用例（按 role 分文件 JSONL）；`evals/run.sh` 是 runner |
| `.github/workflows/claude-code.yml` | Claude Code GitHub Action 模板（默认未启用） |
| `setup/` | 安装 / 启动脚本目录（仓库根零 `.sh`，5 个脚本全在此目录，下表逐个说明） |
| `setup/init-team.sh` | 接手模板 Day-1 验证脚本（hook 测试 + JSON 语法 + 必备文件存在性） |
| `setup/agf-team-start.sh` | 交互式 Agent Team 启动器（预检 + teammate 多选菜单），等价 slash command `/agf-team-start`；不复述启动协议，只做 UX + 调用 slash 命令保 SSOT |
| `setup/agf-install.sh` | TUI 安装程序（把 AGF 模板注入新 / 旧项目的一条龙交互入口）；薄 TUI 外壳——source `.claude/scripts/agf-tui.sh`，编排 `setup/install-to-existing.sh`（核心安装）+ `setup/customize.sh`（preset 裁剪）+ `setup/init-team.sh`（Day-1 体检），被调脚本非交互契约不变 |
| `setup/install-to-existing.sh` | 非交互核心安装（把 `.claude/` + `docs/` 规范注入已有 git 仓，`setup/agf-install.sh` 编排调用，也可独立使用） |
| `setup/customize.sh` | preset 裁剪（`--preset minimal\|miniapp-only`，按项目类型去多余角色） |

## 单一来源原则

每类内容**只在一个地方维护**，其他地方只放指针：

- 技术栈唯一来源：`docs/adr/000-system-architecture.md`（CLAUDE.md 只放一句"详见 ADR-000"）
- 角色清单 / 正文职责来源：`.claude/agents/*.md`；**角色能力唯一来源**（model / tools / skills / pool / permission 等）是 `.claude/agents/roles.yaml`——`gen-roles.py` 从它生成各 `.md` frontmatter（逐字零 diff）+ `.claude/standards/team-roles.md` 两表（marker 注入），`team-roles.md` 与 frontmatter 是**生成视图、勿手改**，drift 由 `lint-all.sh` 硬阻断；`docs/team-capability-map.md` 是视图，需同步
- 工作流唯一来源：`.claude/standards/workflow.md`（CLAUDE.md 不重复；本文件 + `.claude/rules/team-mode.md` 按场景指针）
