---
name: repo-layout
description: Repository directory map for AppGenesisForge — what lives where. Loaded on demand when an agent is about to create/modify project structure or unsure where to put a new artifact.
paths:
  - "**/*.md"
  - ".claude/**"
  - "docs/**"
  - ".github/**"
---

# Repository Layout

> AppGenesisForge 的目录地图。新建文件 / 不确定某产物归属时查这里；修改本表后须同步 CLAUDE.md 里的指针。

## .claude/

| 路径 | 内容 |
|---|---|
| `.claude/agents/*.md` | 团队角色 agent 定义（通用 + `miniapp-*` + `apple-*` + post-launch；小程序 / Apple 设计由 `uiux-designer` 分别在 MiniApp Mode / Apple Mode 下覆盖；**计数以 `ls .claude/agents/*.md` 为准，不硬编码**）。**frontmatter（能力字段）是生成物**——见下行 `roles.yaml` |
| `.claude/agents/roles.yaml` | 角色能力机读 SSOT（model / color / tools / skills / pool / permission / focus / boundary）；`gen-roles.py` 从它生成本目录各 `.md` 的 frontmatter（逐字零 diff）+ `standards/team-roles.md` 两表（marker 注入）。改能力编辑此文件后重跑 `gen-roles.py`，`--check` 由 `lint-all.sh` 硬阻断 drift |
| `.claude/standards/*.md` | 团队通用规范（角色、工作流、测试、安全、观测、成本预算、轻量化 plan 格式等），跨项目复用 |
| `.claude/commands/*.md` | 项目级 slash commands：`agf-init`（装后由 Claude 接管初始化，替代手敲 `setup/init-team.sh`）`agf-team-start` `agf-team-stop` `agf-uat` `agf-board`（实时开发看板 HTML，任务视图唯一入口——原 `agf-tasks` 文本表 v6.26.0 退役，ADR-026 D7）`agf-release-retro` `agf-deploy-uat` `agf-apple-release`（Apple 发布门：签名分发包 + 冒烟）`agf-handoff`（给 Codex / opencode 交接执行层 → 隔离 worktree + stamped AGENTS.md + 出门/回门简报）`agf-code-map`（Deeply Understand / codemap 入口：代码图谱 / 变更影响分析 / 理解地图，ADR-021，替换已删的 agf-understand workflow） |
| `.claude/scripts/` | 项目工具脚本（非 hook；清单以 `ls` 为准）。一句话用途：`lint-all.sh` 全仓 lint+门+测试入口（pre-commit 链调）· `run-all-tests.sh` hermetic 测试 runner（被 lint-all 委托）· `gen-roles.py` 角色能力 SSOT 生成器（`--check` 硬阻断 drift）· `agf-verdict.py` verdict 守门（被 validate-verdict.sh 委托，ADR-010）· `agf-spec-validate.sh` / `agf-spec-archive.sh|.py` 行为规格校验 / 归档 merge（ADR-012）· `agf-advisory.sh` advisory 机筛统一入口（串跑 `agf-sit-precheck.sh` / `agf-design-precheck.sh`，永不阻断，dev 报告前跑一次；原 wiring-check 已退役——ADR-011/013/026 D2）· `agf-deny-baseline.sh` / `agf-claims-audit.sh` 诚实层门（lint-all 硬阻断，ADR-023）· `agf-board.sh` 任务看板（唯一任务视图）· `agf-matrix.sh` 多报告 fan-in · `agf-next-instance.sh` / `agf-check-ownership.sh` / `agf-worktree-gc.sh` Pool / worktree 辅助（ADR-001）· `archive-progress.sh` progress 归档 · `agf-handoff.sh` 外部工具交接 · `test-install.sh` 安装链路 E2E（MINOR+ release 前必跑）· `check-repo-layout.sh` / `check-superpowers-mapping.sh` lint advisory 。**参数 / 退出码 / 门属性以各脚本 header 注释为唯一来源，勿在本表复述**（参数级细节曾在此格漂移）；各门真实强度见 `known-limitations.md` |
| `.claude/skills/*/SKILL.md` | **项目自有 skill**（清单/计数以 `ls .claude/skills/` 为准，**勿在文档硬编码计数**——见 `verified-facts.md` 纪律）：需求入口 `agf-writing-change`（v6.9.0 取代 PRD）+ `agf-writing-prd`（弃用 fallback）/ 多 LLM 接入 `agf-wiring-multi-llm-sdk` / SIT（通用 `agf-running-sit-tests` + Apple `agf-running-apple-sit`）/ `agf-writing-adr` / `agf-writing-qa-report` / `agf-running-release-retro` / `agf-writing-github-issue` / `agf-deploying-uat` / `agf-releasing-apple` / `agf-wiring-apple-llm` 等；**office 技能组（选装，v6.25.0 起默认不随安装分发，`install-to-existing.sh --with-office-skills` 才装）**：`agf-writing-docx-reports` / `agf-writing-pptx-reports` + 2 个外部第三方低层 skill `docx`、`pptx`（Anthropic 提供，含 `scripts/office/soffice.py` PDF 预览闭环；两份 `scripts/office/` 内容相同，上游更新需双侧同步） |
| `.claude/hooks/*.sh` | 四层防御 + 工作流 hook + git pre-commit；详见本目录与 `.claude/standards/security.md` |
| `.claude/hooks/agf-hook-guard.sh` + `agf-hook-flags.lib.sh` | hook 运行时 profile 中央 guard + 判定库（ADR-014）；6 个团队协调类 hook 经 guard 包装（teammate-keepalive / check-progress-file / session-start-context / validate-task-schema / gate-deploy-release-auth / gate-redo-fuse），安全防御直连 |
| `.claude/hooks/agf-task-hook.lib.sh` | TaskCreated hook 公共提取/归因辅助库（`agf_task_desc` jq 4-路径 + `agf_has_attribution` sentinel grep）；被 validate-task-schema / gate-deploy-release-auth / gate-redo-fuse 三 hook source，去三处手抄重复（payload shape 变更改 1 处，ADR-023 F1） |
| `.claude/hooks/block-config-edit.sh` | PreToolUse `Edit\|Write` 配置保护——防 agent 改 lint/format 配置弱化规则（ADR-017），进 `AGF_HOOK_IMMUTABLE` |
| `.claude/hooks/enforce-write-scope.sh` | PreToolUse `Edit\|Write` 角色边界——按 `roles.yaml` `boundary.write_scope` 拦越界写（reviewer 只 `docs/reviews/`、qa 只 `docs/qa/`、deploy 只 `docs/deploy/`；主线程 + 无 boundary 角色放行；ADR-018），进 `AGF_HOOK_IMMUTABLE` |
| `.claude/hooks/gate-deploy-release-auth.sh` | TaskCreated 部署/发布门授权归因——deploy-engineer / apple-release-engineer 派单 task 描述必须含 `用户授权:` 归因行（缺 exit 2）；与 `validate-task-schema.sh` 同 matcher 并列；归因+审计+摩擦层非硬门（PL 主 session 与用户 slash 不可区分），ADR-019，进 `AGF_HOOK_PROFILEABLE`（可降级） |
| `.claude/hooks/gate-redo-fuse.sh` | TaskCreated 回派熔断——从 task 描述抽 feature slug，数 `docs/reviews/<slug>-*.md` 里 blocking 报告（`code_verdict: block` / `sit_audit_verdict: Redo SIT`），≥阈值（默认 3，`AGF_REDO_FUSE_LIMIT` 可调）强制升级 tech-lead 归因（`熔断豁免:` sentinel，缺 exit 2），堵无限回派循环；与 `validate-task-schema` / `gate-deploy-release-auth` 同 matcher 并列；loop 检测+升级归因层非硬门，ADR-020，进 `AGF_HOOK_PROFILEABLE`（可降级） |
| `.claude/hooks/tests/ci/` | CI 治理断言测试子目录（`lint-all.sh` 用 `find` 递归发现；首个 `test-no-hardcoded-paths.sh` 扫无 `/Users/`/`/home/` 硬编码）|
| `.claude/hooks/tests/*.sh` | hook 单测（`test-*.sh`，**非 hook、不计入 hook 数**，含 `ci/` 子目录）；`lint-all.sh`（`find` 递归）+ `run-all-tests.sh`（hermetic）+ `setup/init-team.sh` 自动跑全部 |
| `.claude/rules/*.md` | path-scoped 规则（本目录 3 文件：本文件 / `team-mode.md` / `verified-facts.md`），Claude Code 按文件路径自动加载 |
| `.claude/settings.json` | 项目配置：Agent Teams 启用、permissions allow/deny、hooks 注册、autoMemoryEnabled、worktree.baseRef |
| `.claude/security/deny-baseline.json` | `permissions.deny` 非回归 baseline（`{version, canonical_sha256, entries[]}`）；`agf-deny-baseline.sh --check`（`lint-all.sh` 硬阻断）对比子集，deny 条目被删 / baseline 篡改 → exit 2；有意变更 deny 后跑 `--update` 重签。对标 claude-code-harness selfaudit DenyBaseline |
| `.mcp.json` | 项目级 MCP server 注册（当前：`chrome-devtools-mcp@latest` 供 `qa-engineer` 跑 E2E；`@upstash/context7-mcp` 供 `tech-lead` 版本查证 / dev 拉第三方库最新文档防幻觉；`xcodebuildmcp@latest` 供 `apple-dev` / `apple-qa-engineer` 驱动 Xcode——build / 模拟器 / 真机 devicectl / XCUITest）；与 `.claude/settings.json` 分文件（前者是 MCP 协议规范文件，后者是 Claude Code 私有配置） |
| `.claude/agent-memory/<role>/` | agent 持久记忆（per-role 目录；被 `team-roles.md` frontmatter 能力表引用） |

## docs/

| 路径 | 内容 |
|---|---|
| `docs/FIRST_RUN.md` | 接手模板的 Day-1 清单 + 前置知识 + 常见踩坑 |
| `docs/known-limitations.md` | **AGF 模板本体能力诚实 SSOT**（ADR-023）：两把尺子（强制强度 hard-block/advisory/model-dependent/process-dependent + 证据三态 executed/not-observed/absent）+ 声称审计表（各控制 CLAUDE.md 措辞 vs 实际强度）；tech-lead 每 MINOR retro 刷新；机判部分（脚本存在+注册）由 `agf-claims-audit.sh` 硬阻断 |
| `docs/team-capability-map.md` | §1 端到端全景图（角色 + 阶段门 + hook + skill 叠加）+ 全角色协作 Mermaid + 能力对照表，改 agent 时必须同步 |
| `docs/product-workflow.md` | 产品交付工作流 + 全量术语词典；写 PRD / 拆 Task / 用术语前先查这里 |
| `docs/prd/*.md` | ⚠️ **弃用 v6.9.0 → 删 v7.0.0**（fallback）：旧 PRD 入口（skill `agf-writing-prd`）；新需求走变更文件夹 `docs/changes/`（见下，ADR-012） |
| `docs/design/DESIGN.md` | **项目级设计系统 SSOT**（设计 token：color/typography/spacing/radius/component + `on-*` 配对 + Do/Don't），uiux-designer 维护；各 feature spec 与前端样式引用其 token，禁内联重声明（纪律见 `coding.md` 设计 token 纪律） |
| `docs/design/[feature]/` | uiux-designer 产出（`spec.md` + `index.html`，资源放 `assets/`；视觉值引用 `docs/design/DESIGN.md` token） |
| `docs/reviews/*.md` | code-reviewer 产出 + release retro（`retro-vX.Y.Z-YYYY-MM-DD.md`）+ 季度 eval 漂移记录 |
| `docs/qa/*.md` | qa-engineer 产出（E2E / UAT 报告，写时用 skill `agf-writing-qa-report`；SIT 不再独立成 `docs/qa/*-sit-*.md`，证据写入 `progress/<role>.md` 由 code-reviewer 在 review 时 audit）+ `<feature>-process-log.md`（progress/ 归档，UAT 签字后由 product-lead 写入） |
| `docs/deploy/*.md` | deploy-engineer 产出（UAT 部署报告 `<feature>-uat-<YYYY-MM-DD>.md`，写时用 skill `agf-deploying-uat`；含 UAT 栈各服务 URL + 冒烟证据 + 迁移结果 + 部署 commit SHA + 二元 gate；qa-engineer 读它拿 E2E/UAT 测试目标地址）+ apple-release-engineer 产出（Apple 发布报告 `<feature>-apple-<YYYY-MM-DD>.md`，写时用 skill `agf-releasing-apple`；含分发包定位 + 冒烟证据 + 构建 commit SHA + 二元 gate；apple-qa-engineer 读它拿测试目标） |
| `docs/adr/*.md` | 架构决策记录（命名 `NNN-[slug].md`，写时用 skill `agf-writing-adr`；ADR-000 是基线；**索引见 `README.md`**——索引表（一句话/枚举）+ 演进链 + 主题分组；计数以目录为准不在文档声明） |
| `docs/specs/<cap>/spec.md` | **活规格（行为需求 SSOT，永远当前）**：product-lead 维护，按能力 kebab-case 组织；功能变更走 delta + `agf-spec-archive` merge，不手改（ADR-012）；模板 `docs/specs/_TEMPLATE.md` + `README.md` |
| `docs/changes/<change>/` | **变更文件夹（需求入口，取代 PRD）**：四件套 proposal / specs delta / design / tasks（skill `agf-writing-change`）；`agf-spec-validate` 校验；UAT 签字后 `agf-spec-archive` 移 `archive/<date>-<change>/`；模板 `_TEMPLATE/` |
| `docs/superpowers/` | superpowers 工作流产物（`specs/` 设计 spec + `plans/` 轻量实施计划）。**历史一次性产物已归档 untrack**（v6.27.1，留工作树不进 git）；仅保留仍被脚本引用的 2 份 spec（yaml-ssot / structured-verdict）。新产物默认不入库（gitignore），确需长期留档的加 `!` 例外 |
| `docs/assets/` | 截图与图片资源（`agf-board.png` 等） |
| `docs/content/release-notes/` | content-writer 产出（发布说明等面向用户内容） |

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
| `.github/workflows/claude-code.yml.template` | Claude Code GitHub Action 模板（`.template` 后缀 = 真未启用；启用按文件头注释改名为 `claude-code.yml` + 配 secret） |
| `setup/` | 安装 / 启动脚本目录（仓库根零 `.sh`，3 个脚本全在此目录，下表逐个说明；原 TUI 层 `agf-install.sh` / `agf-team-start.sh` 已按 ADR-026 D3 退役） |
| `setup/init-team.sh` | 接手模板 Day-1 验证脚本（hook 测试 + JSON 语法 + 必备文件存在性 + 第三方 plugin skill 依赖核对：superpowers 版本校验 + roles.yaml 预载的其余 plugin skill 数据驱动核对，缺失 warn 附精确 `/plugin install` 命令） |
| `setup/install-to-existing.sh` | **用户安装入口**（非交互：拷 `.claude/` + `docs/` + `tools/codemap` + `uv sync` 装依赖 + 签 deny-baseline；`--refresh-docs` 升级 / `--with-office-skills` 选装 office 技能组）；装完进 Claude Code 跑 `/agf-init` 接管初始化（ADR-026 D3 入口统一） |
| `setup/customize.sh` | preset 裁剪（`--preset web-only\|minimal\|miniapp-only` + `--drop-postlaunch`，按项目类型去多余角色 + 按轨联删 skills/commands/standards + 同步 roles.yaml，ADR-026 D4） |
| `tools/codemap/` | **Deeply Understand (codemap)** — Python 原生代码理解引擎（ADR-021，替换 `agf-understand`）：tree-sitter 多语言 + SQLite 图谱 + 影响分析 + dashboard；uv 包，`uv run codemap build/update/diff/explain/orphans/...`（`orphans`=模块级"写了没接线"检测，ADR-024；原编排脚本 `agf-wiring-check.sh` 已按 ADR-026 D2 退役，`orphans` 手动走 `/agf-code-map`）；入口 skill `agf-code-map` / command `/agf-code-map` |
| `.agf/` | DU 派生产物（`code-map.db` 图谱 / `dashboard.html` / `meta.json` / `diff-overlay.json`，gitignored 可重建；`config.json` 项目配置入库）；详见 08 §1 |
| `template/Template.pptx` | pptx 母版模板（`agf-writing-pptx-reports` skill 引用，见 `template-team-guide.md` / `references/template-based-generation.md`） |

## 单一来源原则

每类内容**只在一个地方维护**，其他地方只放指针：

- 技术栈唯一来源：`docs/adr/000-system-architecture.md`（CLAUDE.md 只放一句"详见 ADR-000"）
- 角色清单 / 正文职责来源：`.claude/agents/*.md`；**角色能力唯一来源**（model / tools / skills / pool / permission 等）是 `.claude/agents/roles.yaml`——`gen-roles.py` 从它生成各 `.md` frontmatter（逐字零 diff）+ `.claude/standards/team-roles.md` 两表（marker 注入），`team-roles.md` 与 frontmatter 是**生成视图、勿手改**，drift 由 `lint-all.sh` 硬阻断；`docs/team-capability-map.md` 是视图，需同步
- 工作流唯一来源：`.claude/standards/workflow.md`（CLAUDE.md 不重复；`.claude/rules/` 三文件按场景指针：本文件 / `team-mode.md` / `verified-facts.md`）
