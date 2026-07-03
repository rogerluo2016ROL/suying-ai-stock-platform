---
description: 启动 Agent Team 完成多角色产品/功能交付
argument-hint: <产品或功能描述> [--pool=auto|off|N] [--dry-run]
---

参考 `CLAUDE.md` "Team Mode" 节、`.claude/standards/workflow.md` 与 ADR-001 Multi-instance Worker Pool。

# 任务

$ARGUMENTS

# Pool 模式（ADR-001）

入口选项（解析 `$ARGUMENTS` 中可选的 `--pool=...` flag；缺省 = `auto`）：

| 选项 | 行为 |
|---|---|
| `--pool=auto`（**默认**）| product-lead 自动按"同 type ≥ 2 个 pending task → spawn N 实例"规则 fan-out；上限按 `.claude/standards/team-roles.md` "Pool 上限" 列 |
| `--pool=off` | 强制全程单实例（旧行为，向后兼容；适合 demo / debug / 单角色 feature） |
| `--pool=N`（N ∈ 2-7）| 全 type pool 上限统一覆盖为 N（高优先 feature 上限 7 / 资源紧张降到 3） |

Pool 决策时机：
- **拆 task 时**（Step 2）：识别同 type ≥ 2 → 触发 dev pool
- **dev 完成 SendMessage PL 时**（Step 3.1→3.2 衔接）：≥ 2 个 task 进 review 队列 → 触发 review pool
- **review 通过 ≥ 2 时**（Step 3.2 review → Step 3.3 部署门 → Step 3.4）：触发 qa pool

强制单实例例外（不论 `--pool` 选项）：同文件改动 / DB schema migration chain / Auth / LLM 切换 / cross-cutting concerns（详 `workflow.md` §Multi-instance Worker Pool §例外）。

### `--dry-run` 模式（预览，不真起）

加 `--dry-run` flag 时，**主 Claude 不调 Agent 工具 spawn**，只输出"将 spawn 的 teammate 清单 + 预估 token + Pool 触发的 type 与实例数"后停。用途：

- 调试 pool 上限配置是否合理
- 给用户预览资源消耗
- CI / 自动化测试场景（不真烧 token）

输出固定格式（markdown 表）：

```
## 预览：<TeamName>Team — pool=<选项>

| Teammate (拟 spawn 实例名) | Subagent type | Initial task 一句话 | Pool 触发理由 |
|---|---|---|---|
| product-lead | —（lead 本 session，--agent 启动） | 起 PRD | lead，不 spawn |
| frontend-dev-1 | frontend-dev | 实现 LoginForm 组件 | pool: 同 type 2 task |
| frontend-dev-2 | frontend-dev | 实现 LoginPage 路由 | pool: 同 type 2 task |
| backend-dev | backend-dev | 实现 /auth/login API | 单实例（同 type 仅 1 task） |
| ... | ... | ... | ... |

**预估 token**: 单实例 baseline ~50K → pool=auto 总 ~200K（4×，落 Medium 档）
**Worktree 数**: 4（含 PL 主 worktree）
**Docker 端口偏移**: qa pool 暂未触发（仅 dev/review pool 命中）
**强制单实例例外命中**: 无

下一步：去掉 `--dry-run` 真起。
```

不写文件、不写 task list、不调 SendMessage——只是产物预览。

# 执行指令

Create an agent team to deliver the task above. Team name 由你根据任务内容自动命名（驼峰式 + Team 后缀，例如 `LoginRevampTeam`）。

spawn 机制（按 type 名、不用 `@` 引用、本 session 即 PL 不重复 spawn、确认/报告 ID、worktree、teammateMode）一律按 `.claude/rules/team-mode.md` §启动协议，本文件不复述。下面只列本 command 独有的 teammate 选择 + 初始任务模板 + 派工契约。

**Teammate 选择规则**（本 session 已是 PL，只 spawn 其余角色）：
- 默认 spawn 下表 teammate（**不含 `product-lead`**——它是 `--agent` 主 session lead，不作为 teammate spawn）
- **若任务消息含 `[teammates: A,B,C]` 标记行**（脚本入口会带），则**仅** spawn 标记列出的 teammate；各自 initial task 按 feature 描述与 PRD 上下文推断（参考下表模板）

| Teammate | Initial task 模板（默认 / 推断参考） |
|---|---|
| `product-lead`（lead 本 session，**不 spawn**）| lead 自身首个动作：调用 `superpowers:brainstorming` 澄清需求，输出 PRD 草稿到 `docs/prd/<feature>-<YYYY-MM-DD>.md`，列出至少 3 个开放问题 |
| `tech-lead` | 检查 `docs/adr/` 是否覆盖本任务所需技术基线；已覆盖则合规检查并回报，未覆盖则**用 `agf-writing-adr`** 起草新 ADR 大纲 |
| `frontend-dev` | 阅读 `src/` / `frontend/`（如存在）后输出页面骨架与状态管理切分计划（实现阶段：`superpowers:test-driven-development` 写测试、`agf-running-sit-tests` 跑 SIT） |
| `backend-dev` | 阅读 `backend/`（如存在）后输出 API 契约草案（路径、请求/响应 schema）（实现阶段：LLM 接入用 `agf-wiring-multi-llm-sdk`、`superpowers:test-driven-development` + `agf-running-sit-tests`） |
| `qa-engineer` | 阅读 PRD 草稿后准备 E2E/UAT 测试策略框架（先不执行；执行阶段用 chrome-devtools 跑真机、`agf-writing-qa-report` 写报告；SIT 由 dev 自跑，不在 qa 范围） |
| 其它 teammate | 按角色 description 与 PRD 推断一个可立即执行的初始任务 |

**Initial task 沉默契约（追加到每条初始任务消息末尾）**：

> 完成后只回 **1 句话**给 lead：`<状态> + <产物路径>`（例：`PRD 草稿已落 docs/prd/login-2026-05-18.md，3 个开放问题在 §8`）。不要在聊天区复述任务内容、不要列 next steps、不要贴 diff —— 细节落产物文件 / `progress/<role>.md`。

**Skill 点名契约（teammate 不预加载 skill，PL 派工时必带）**：

> teammate 走 Agent Team 路径**不会预加载 frontmatter 的 `skills`**——PL 在派**每一条**任务（不止初始任务）时，必须在任务文字里**点名该角色要用的 skill**（如"用 `agf-wiring-multi-llm-sdk` 接入 DeepSeek"）。各角色 skill 清单见 `.claude/standards/team-roles.md` 的「Plugin Skills」列。

# 约束

> 「是 agent team 非 subagent」「lead = 本 session / 不重复 spawn PL」「确认句 + 报告 ID」「teammateMode 控显示」等通用协议见 `.claude/rules/team-mode.md` §启动协议。本节只补 command 独有约束：

1. spawn 汇报格式：每个 teammate 用 **markdown 表格 1 行**，列 = `name | agent ID | initial task 一句话`；**禁止**散文式介绍 / 复述 initial task 全文 / 预告"接下来 X 会 Y"。整段汇报（确认句 + 表格）≤ 15 行。
2. Spawn 之后由 `product-lead` 接管协调，按 `.claude/standards/workflow.md` 推进交付链路（dev 自跑 Unit + SIT → code review（含 SIT Audit）→ UAT 部署（deploy-engineer 起隔离栈）→ E2E → UAT）。
3. 多个同类型实例并行时遵守 `.claude/standards/workflow.md` "Parallel Dispatch" 节（文件归属 + 临界区 + 完成报告列全文件）+ §"Multi-instance Worker Pool"（实例命名 `<type>-<N>` / worktree 隔离 / Docker 端口偏移 / 失败处理）。

# 任务规模过小怎么办

如果任务明显单角色就能完成（仅文案改动 / 单点 bugfix / 纯查询），不要建 team——告诉用户："本任务规模过小，建议改用 `请启动 <角色>` 的单角色 subagent 路径，无需 agent team。"

# 另一种路径：Agent View（独立并行执行）

> 本节不走 `.claude/rules/team-mode.md` 的 Agent Team 协议，因为没有 lead / mailbox / 共享 task list。

## 何时选这条路（而不是 Agent Team）

任务可拆成 **≥2 个互相独立的执行单元**、且满足**全部**条件：

- 子任务间不需中途讨论 / 互相质疑 / 共享发现（每个 worker 拿 spec 即可独立完工）
- 已有 PRD 或明确 spec（不需 product-lead 现场澄清）
- 每个子任务有清晰交付物边界（独立 PR / feature 子目录 / 报告）

**典型场景**：基于已签字 PRD 的并行实现（backend API + frontend 页面 + SIT 用例）、批量代码审查（同时审 N 个 PR）、跨 repo 的同形修改（monorepo 多包同步升级）。

**反例**（继续走 Agent Team）：需求还在演化、需要 devil's advocate、teammate 间要交换中间结果、有跨 worker 的依赖等待。

## 启动方式

```bash
# 1. 派工（每条命令开一个独立 background session，自动 worktree 隔离）
claude --agent backend-dev    --bg "实现 <feature> 的 API：契约见 docs/prd/<feature>.md §3"
claude --agent frontend-dev   --bg "实现 <feature> 的页面：原型见 docs/design/<feature>/index.html"
claude --agent qa-engineer    --bg "为 <feature> 写 E2E 用例：AC 见 docs/prd/<feature>.md §4（SIT 由 dev 自跑，不在 qa 范围）"

# 2. 一屏看全局（PR 状态点自动追踪：黄=等审 / 绿=通过 / 紫=已 merge）
claude agents
```

面板里：`Space` peek、`Enter` attach、`Ctrl+X` 停 session（再按一次删除并清 worktree）、`←` 在空 prompt 上一键 background + 切回面板；跑并行子项（subagent / 后台命令）的行还显示 `done/total` 计数（如 `2/5`，v2.1.161+），peek 面板列出最长运行的子项。

## 注意事项

- **配额按 session 算**：N 个并行 session = N 倍订阅消耗，跑前先掂量
- **机器睡眠会停**：醒来后 `claude respawn --all` 恢复
- **worktree 自动建在 `.claude/worktrees/`**：删 session 时一并清理，未提交改动会丢——重要工作先 `git push` 或 `git commit` 再删
- **Sub-agent / teammate 不在面板里列**：只列 top-level background session
- **不能替代 product-lead 协调**：本路径**不做** PRD 演化 / UAT 签字 / 跨 worker 冲突仲裁；这些仍需 `/agf-team-start` 走 Agent Team 路径
- **本路径不写 progress/<role>.md**：Self-Reporting Pattern（`.claude/standards/ac-lifecycle.md`）默认绑定 Agent Team；如需底稿，在各 `--bg` prompt 里显式要求 worker 完成时 append 到 `progress/<role>.md`
- **`permissionMode: auto` / `bypassPermissions` 的 agent 不能直接 `--bg`**：Claude Code 安全门规定，未在交互模式接受过该 mode 前 `--bg` 启动这两类 agent 会被拒。名单以 `.claude/standards/team-roles.md` "Team Roles" 表 `Permission` 列为准（不在此复述，避免双写）。规避：先 `claude --agent <name>` 交互跑一次接受弹窗，之后即可 `--bg` 派工
- **`--bg` 启动的是 sub-agent 形态**：frontmatter 行为与 Agent Team 路径不同，详见 `.claude/standards/team-roles.md` 能力对照表

## 选哪条路：一句话决策表

| 场景信号 | 选 |
|---|---|
| 多 worker 要互相讨论 / 质疑 / 共享中间发现 | **Agent Team**（默认） |
| 需要 lead 实时协调 / 仲裁文件冲突 / 推进 UAT 签字 | **Agent Team** |
| 已有 spec，子任务独立可并行，只想看进度 + 自动收 PR | **Agent View** |
| 单角色任务 | 直接 `请启动 <角色>` 走 subagent，两条路径都不用 |

## 进度可视化（可选）

Team 跑起来后，提示用户可开实时看板：`/agf-board --watch`（或 `bash .claude/scripts/agf-board.sh --watch`）→ `open progress/board.html`——task 卡片三列 kanban，teammate 每次 TaskUpdate ≈3s 内上板；详见 `.claude/commands/agf-board.md`。
