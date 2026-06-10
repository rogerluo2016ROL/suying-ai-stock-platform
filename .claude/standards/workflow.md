# Team Workflow

## Session Entry

主 Claude 收到用户请求后，按以下三路判断决定如何启动：

1. **直接执行**（无需组队）：明确指向单一文件 / 单一角色的小型修改（改一段文案、调整某个 agent 描述、修一处明显笔误）、纯查询解释、单步重构。
2. **派给 `product-lead` 单角色 subagent**：需求明确但要走完整 PRD/拆分/审查/测试链路、且核心实现只动一个执行层角色时使用。派单语法：`Agent({subagent_type: "product-lead", description: "...", prompt: "..."})`。
3. **建 Agent Team**（多角色并行）：命中 `CLAUDE.md` "Team Mode" 节启用条件——任务涉及 ≥2 执行层角色 / 跨完整交付链路 / 用户提示含「team / 团队 / 并行 / 同时 / 多角色」等词。由用户的 `/agf-team-start <feature>` 触发，或主 Claude 主动按 Team Mode 协议建立。

判断不清时按"更高路径"处理（subagent 优于直接执行；team 优于 subagent）——多一轮调度的成本远低于跳过编排导致的返工。

**Headless / CI 入口**：在 CI 或脚本里以 `claude -p --agent <name> "<prompt>"` 触发某个 agent 时，CLI 会同时尊重该 agent frontmatter 的 `tools:` / `disallowedTools:`（自 2.1.119）与 `permissionMode:`，工具白名单和模式不会因 headless 而失效。例如 `claude -p --agent code-reviewer "review HEAD"` 直接得到该角色的工具集与 `auto` 模式。

## Workflow

1. **Simple tasks**: 按上节"Session Entry"判定为可直接执行的请求，主 Claude 处理
2. **Complex tasks**（扁平 2 层结构）:

```
USER → [product-lead] ──技术咨询──→ [tech-lead]（顾问，按需介入）
             │
             ├──→ [uiux-designer]  ──设计标注──→ [frontend-dev]
             ├──→ [frontend-dev]   ←─API契约──→ [backend-dev]
             ├──→ [backend-dev]
             ├──→ [ai-agent-dev]
             └──→ [ml-engineer]
                       [所有执行层: 自跑 Unit + SIT 并写 progress/<role>.md]
                       ↓ 完成报告（含 SIT 证据）
             [product-lead] → [code-reviewer]（代码审查 + SIT Audit）→ [qa-engineer]（E2E / UAT）
                                                      ↓
                                             [product-lead] → USER
```

- **product-lead** 是唯一协调者：挖掘需求 → 输出 PRD（`docs/prd/`）→ 直接分配任务给执行层 → 触发 code review (含 SIT Audit) → 推进 E2E / UAT → 验收 → 汇报
- **tech-lead** 是条件触发的技术顾问：不在默认主链路上；仅在以下情况必须介入：项目或新模块尚无 ADR / Tech Stack 基线、发生新技术选型、code-reviewer 升级重大架构风险
- 执行层完成后**直接报告 product-lead**，不经过 tech-lead；执行层负责 Unit + SIT，SIT 证据写入 `progress/<role>.md`
- **code-reviewer** 负责代码审查 + SIT 证据 audit，不负责直接修复源码；发现重大架构问题时同步通知 product-lead 并升级到 tech-lead（本文件 ASCII 流程图省略此虚线以保持主链路简洁，完整虚线见 `docs/team-capability-map.md` 的 Mermaid 图）
  - **SIT Audit 4 项检查**：
    1. `progress/<role>.md` 是否含完整 `**SIT 证据**` 段
    2. AC 覆盖：是否覆盖 PRD 全部 AC（integration 层）
    3. 证据可信度：fail/blocked 内嵌的命令 + 真实输出是否可信（非 placeholder）
    4. 失败标记真实性：fail/blocked 是否如实标记
  - **3 档 verdict**：`✅ Pass / ⚠️ Pass with concerns / ❌ Redo SIT`

### Verdict 词表（4 套各管各，不互相替代）

| 维度 | 角色 | 词表 |
|---|---|---|
| **代码 Verdict** | code-reviewer / miniapp-code-reviewer | `approve` / `approve with changes` / `block` |
| **SIT Audit Verdict** | code-reviewer / miniapp-code-reviewer | `✅ Pass` / `⚠️ Pass with concerns` / `❌ Redo SIT` |
| **QA 报告级 Verdict** | qa-engineer / miniapp-qa-engineer（自有词表）| `✅ Promote to next stage` / `❌ Block` / `⚠️ Conditional promote` |
| **UAT 业务签字 Verdict** | product-lead（最终业务判定）| `approve` / `request changes` |

阶段门转换规则：
- code-review → E2E：代码 verdict ∈ {`approve`, `approve with changes`} ∧ SIT Audit verdict ∈ {`✅ Pass`, `⚠️ Pass with concerns`}
- E2E → UAT：QA 报告级 verdict ∈ {`✅ Promote`, `⚠️ Conditional promote`}
- UAT → release：UAT 业务签字 verdict = `approve`

任一回退路径：`block` / `❌ Redo SIT` / `❌ Block` / `request changes` 中任一命中 → product-lead 重派 dev 修复。Pool 模式下"verdict 通过" = `agf-matrix.sh` 输出**全部** ≥ ⚠️（即任一实例 ❌ 即整个 batch fail）。
- **qa-engineer** 只执行 E2E / UAT；不替代开发者做 Unit 与集成自验（已由 dev 在实现阶段完成），不替代 product-lead 做最终业务验收
- 阶段门槛固定为：实现 + SIT 完成 → code review (含 SIT Audit) → E2E → UAT → product-lead 签字
- 任一阶段失败，均回到 **product-lead** 重新分派执行层修复（SIT Audit `❌ Redo SIT` 与 code verdict `block` 合并为一次回派）
- **小程序交付链路**：`uiux-designer（MiniApp Mode）→ miniapp-dev → miniapp-code-reviewer → miniapp-qa-engineer → product-lead`。设计阶段由 `uiux-designer` 在 MiniApp Mode 下完成（见 `agents/uiux-designer.md`）；开发、审查、QA 由 3 个 `miniapp-*` 专项角色负责。`backend-dev` / `ai-agent-dev` / `ml-engineer` 跨链路共用。详见 `.claude/standards/miniapp.md`

**Skills 触发点速查**：
- product-lead 接需求 → `brainstorming`；分配前 → `writing-plans`；并行派 ≥2 execution teammate → `using-git-worktrees`（强制）
- 开发者实现前 → `test-driven-development`；开发者完成 Unit 后、code-review 前 → `agf-running-sit-tests`（dev 自跑集成测试，与 TDD 并列触发）
- 写 PRD → `agf-writing-prd`；写 ADR → `agf-writing-adr`
- 测试报告（E2E / UAT）→ `agf-writing-qa-report`（SIT 证据由 dev 自写到 `progress/<role>.md`，无独立 SIT 报告）
- 完成前 → `verification-before-completion`；遇 bug → `systematic-debugging`；送审前 → `requesting-code-review`；收到审查/打回 → `receiving-code-review`

详见 `.claude/standards/superpowers.md`。

## Parallel Dispatch（执行层并行派发）

当单个执行层角色（尤其是 `backend-dev`）成为关键路径瓶颈时，`product-lead` 可在拆任务时**按模块/资源边界**并行派发多个同类型实例。

### 适用条件（同时满足才并行）

- 任务可按**资源/模块/目录前缀**自然切分（例：用户 / 订单 / 支付）。
- 各子任务**不写同一份文件**。
- 各子任务之间**无强顺序依赖**（A 不依赖 B 的代码已存在）。

### 不要并行的场景

- 同一资源 CRUD 的 API 层 / Service 层 / DAO 层（强依赖、必踩冲突）。
- 仅有一个共享文件需要改动（例：只是加一个新路由）。
- 紧耦合业务流（例：登录中间件 + 登录接口必须一致演进）。

### 派发协议

并行派任务消息中，除 [`product-lead.md` Step 2 的 6 段 Task description schema](../agents/product-lead.md)（任务描述 / 任务类型 / 上下文 / 上游产物 / 验收标准 / 预期产物；hook `validate-task-schema.sh` 强制）外，**必须额外声明**：

- **文件归属**：列出本实例**唯一拥有**的目录前缀或文件路径，例如：
  - 实例 1：`backend/app/users/**`
  - 实例 2：`backend/app/orders/**`
- **临界区清单**：明确告知本实例**不得直接修改**的共享文件，统一回 product-lead 排队。各角色的具体清单由其自身 agent 文件维护（见 `.claude/agents/backend-dev.md`、`.claude/agents/frontend-dev.md`），通用类别包括：
  - 全局入口（`main.*` / `App.*`）与路由注册表
  - 全局状态/依赖容器入口（store、DI container）
  - 数据库迁移（后端）、全局样式与主题配置（前端）
  - barrel exports / `__init__.py` 等模块出口
  - 包管理 manifest 与 lockfile（`package.json` / `pnpm-lock.yaml` / `pyproject.toml` / `requirements.txt`）
- **完成报告**：执行层在完成报告里**列出实际改动的所有文件**，便于 product-lead 跨实例检测冲突。

### 规模与隔离

- 推荐并行规模 **2–3 个实例**；超过 3 个时协调成本显著上升，需先评估是否值得。
- **worktree 强制**：≥2 个 execution-layer teammate 并行时**必须**每个实例运行在独立的 `git worktree` 中（在 git 层兜底意外撞写，最后由 `product-lead` `git merge` 收口）。
  - 启动协议：`product-lead` 调用 skill `superpowers:using-git-worktrees`，按其引导为每个实例分配独立 worktree
  - **worktree 基线**：`.claude/settings.json` 已 pin `worktree.baseRef: "head"`——新 worktree 从本地 `HEAD` 派生，保留 lead 的未推送 progress / migration 进度。Claude Code 2.1.128 起默认行为多次翻动（128: head；133: fresh），项目级显式 pin 防回归。如需切回 `fresh`（从 `origin/<default>` 派生），必须更新本节并改 settings.json
  - 单实例不强制（无并行风险），但鼓励用 worktree 隔离 long-running feature
  - 例外：仅做查询 / 不写文件的并行 teammate（如多个 code-reviewer 在不同模块 read-only 审查）可同主 worktree
- 共享文件（migration、路由注册、依赖容器出口）的修改一律由 `product-lead` **串行收口**，不分配给并行实例。

### Code Review 阶段（含 SIT Audit）

- 各并行实例**已自跑 SIT** 并将证据写入各自 `progress/<role>.md`；review 阶段按 §"Multi-instance Worker Pool" 决定走单实例 review（合并后审）或 Review pool（每实例对应一个 task 并发审）。worktree 模式下，合并由 `product-lead` 在主 worktree 跑 `git merge <feature-worktree-branch>` 完成。
- `code-reviewer`（单实例或 pool 中任一实例）在审查代码同时 audit 对应实例 progress 中的 SIT 证据段（4 项检查 + 3 档 verdict，见上）；pool 模式下跨实例的接口与命名一致性由 PL 用 `agf-matrix.sh --type=review` 输出的对比表统一审，发现实例间冲突或 SIT 证据不可信时升级回 `product-lead`。
- 合并冲突由 `product-lead` 协调对应实例修复，不直接 force-push 覆盖。

## Multi-instance Worker Pool（Dev / Reviewer / QA 三层 pool）

> **决策依据**：[ADR-001 multi-instance-worker-pool](../../docs/adr/001-multi-instance-worker-pool.md)。
>
> §"Parallel Dispatch" 是 **Dev pool 的具体规则**（按模块切分 / 文件归属 / 临界区清单）；本节是覆盖 Dev / Reviewer / QA **三层 pool 的通用规则**，与 Parallel Dispatch 协同（dev 层兼用两节）。

### 通用规则（一条覆盖三层）

`product-lead` 检测到**同 type ≥ 2 个 pending task** → 按需 spawn N 个该 type 实例。三类触发场景：

| Pool | 触发时机 | 实例命名 | 典型 N |
|---|---|---|---|
| **Dev pool** | PRD 拆出 ≥ 2 个同 type dev task（如 3 个 fe 组件）| `frontend-dev-1` / `backend-dev-2` / `ai-agent-dev-1` ... | 2-5 |
| **Review pool** | ≥ 2 个 dev task 完成、SendMessage PL 报告排队 | `code-reviewer-1` / `miniapp-code-reviewer-1` ... | 2-5 |
| **QA pool** | ≥ 2 个 task 通过 code review、进入 E2E/UAT 队列 | `qa-engineer-1` / `miniapp-qa-engineer-1` ... | 2-5 |

### 命名与寻址

- 实例名 `<type>-<N>`，N 从 1 单调递增**在同 release 内不重置**（避免新旧实例同名 → SendMessage 路由错）
- **N 分配算法**（PL Step 3 fan-out 时执行）：

  ```bash
  # 查当前同 type 已存在的最大 N，加 1。3 路扫描（progress / review / qa pool 文件名 pattern 各异）
  # - progress/<type>-<N>.md：N 在文件名末尾
  # - docs/reviews/<feat>-r<N>-<date>.md：N 在 'r' 后跟 mid-string（不是末尾）
  # - docs/qa/<feat>-{e2e,uat}-q<N>-<date>.md：N 在 'q' 后跟 mid-string
  N_PROGRESS=$(ls progress/<type>-*.md 2>/dev/null | grep -oE '-[0-9]+\.md$' | grep -oE '[0-9]+' | sort -n | tail -1)
  N_REVIEW=$(ls docs/reviews/<feat>-r*-*.md 2>/dev/null | grep -oE '-r[0-9]+-' | grep -oE '[0-9]+' | sort -n | tail -1)
  N_QA=$(ls docs/qa/<feat>-{e2e,uat}-q*-*.md 2>/dev/null | grep -oE '-q[0-9]+-' | grep -oE '[0-9]+' | sort -n | tail -1)
  MAX_N=$(printf '%s\n' "${N_PROGRESS:-0}" "${N_REVIEW:-0}" "${N_QA:-0}" | sort -n | tail -1)
  NEXT_N=$((${MAX_N:-0} + 1))
  ```

  - 首次 spawn：`NEXT_N = 1`
  - 后续 spawn：取所有相关产物（progress / review / qa）的最大 N + 1
  - 同 batch 内连续 spawn N 个实例：使用 `NEXT_N`, `NEXT_N+1`, ..., `NEXT_N+N-1`
  - **重 spawn 失败实例**：用更大的 N（如 fail 的是 `<type>-2`，重 spawn 为 `<type>-3`，不复用 -2 避免文件冲突）

- SendMessage 按实例名寻址（`to: "code-reviewer-3"` 而非 `to: "code-reviewer"`）
- 所有实例共享 `.claude/agents/<type>.md` 同一 frontmatter（**SSOT 不变**），只是同 definition 加载 N 次
- 实例完成后 idle 不复用，下个 batch 重新 spawn（避免 context bleed + 简化资源回收）

### 池上限（per type）

- 默认 **5 / type**；按 `cost-budget.md` 分档调整：Small bucket ≤ 3 / Medium bucket = 5 / Large bucket ≤ 7
- 具体上限按 type 在 [`team-roles.md`](team-roles.md) "Pool 上限" 列覆盖
- 超上限的 task 进入 PL 的 pending queue，前序实例完成后下个 batch 处理

### 例外（强制单实例，不进 pool）

任一命中即必须单实例顺序处理：

- **同文件改动**：多个 task 改同一份代码文件（worktree 合并冲突）
- **DB schema migration chain**：必须按 migration 顺序 review，并发会跳号
- **Auth / 鉴权链路** 修改
- **LLM 切换 / prompt 重构** 类高风险变更（详见 [`coding.md`](coding.md) 高风险变更定义）
- **Cross-cutting concerns**：影响多模块的横切关注点（日志框架 / error handler 等）

PL 在 Step 3 派单时识别上述场景，明确写入 task description 的"上下文"段："**本 task 强制单实例处理，理由：...**"。

### Worktree 与 Docker 隔离

| Pool | Worktree | Docker / Env |
|---|---|---|
| Dev pool | 必须独立（按 [§Parallel Dispatch §规模与隔离](#规模与隔离)）| 可选（看 task 是否启服务）|
| Review pool | **可共享**（read-only 操作），review 报告独立 commit | 不需要 |
| QA pool | 必须独立 | **强制**端口偏移 —— 通过 `POOL_INSTANCE=N` env，docker-compose 端口 = base + N×100（详 `docker-compose.yml`）|

### Fan-out / Fan-in 派单流程（PL Step 3 落地点）

```
1. Fan-out：
   PL 跑 task list → 识别同 type ≥ 2 → spawn N 实例 → SendMessage 分配
   （每个实例分配恰好 1 个 task；不要 1 个实例接多个 task，否则失去并行意义）

2. 并发执行：
   N 个实例独立工作（独立 worktree / 独立 progress 文件 / 独立 review-or-qa 报告）

3. Fan-in：
   实例完成 SendMessage PL → PL 跑 matrix 脚本（见下）聚合 → 看 1 张表
   - `agf-matrix.sh --type=progress`：扫 progress/<role>-*.md
   - `agf-matrix.sh --type=review --feature=<slug>`：扫 docs/reviews/<feat>-r*.md（解析 YAML frontmatter）
   - `agf-matrix.sh --type=qa --feature=<slug>`：扫 docs/qa/<feat>-{e2e,uat}-*.md（解析 YAML frontmatter）

4. PL 决策：
   全 ✅ → 进入下一阶段
   任一 ⚠️/❌ → 下钻打开单份报告 → 决定回派 / 升级 / 中止
```

### 失败处理

- **单实例 fail**：PL 决定 ① 重 spawn 同 type 新实例（`<type>-<N+1>`）继续 / ② 降级单实例 fallback / ③ 整 batch abort 复盘
- **≥ 50% 实例 fail**：默认 abort 整 batch + 触发 retro
- **Worktree 资源紧张**（disk / RAM）：PL 在 team-start 前跑 `df -h` 检查，不足则自动降 pool size
- **PL 等待超时**：单实例 idle > 设定值（默认 30 min 无 SendMessage 反馈）→ PL 主动 query 实例状态，必要时 kill 重 spawn

### 跨实例一致性（漂移防御）

- **SSOT 防漂移**：所有实例加载同一 `.md` 是基线保障；任何实例 fork 出新约定（不查 SSOT 自定义）由 PL 在 review 报告里抓
- **PL 抽检**：每 batch 完成后 PL 选 1 个 task 交叉对比另一 reviewer 的 review 结果（10% 抽检率，写进 retro §4 流程协作段）
- **Retro Cohen's κ**：连续 ≥ 3 个 release 跑实例间 verdict 一致性，κ < 0.6 触发新 ADR

### 实例不复用，但 archive-progress 必须合并

- 各实例的 `progress/<role>-<N>.md` 在 feature 结束、UAT 通过后由 `archive-progress.sh` 自动合并到 `docs/qa/<feat>-process-log.md` 的对应 role 段（按时间顺序 cat 即可）
- 合并完成后所有 `progress/<role>-*.md` 一起 `git rm` 离开 main 分支

## Issue Close DoD（Definition of Done for `gh issue close`）

> 触发来源：`docs/reviews/issue-audit-2026-05-16.md` Systemic Pattern 1 — 33 issues 审查中 4 例 Deferred-without-tracker（#18 / #19 / #22 Phase 2/3 / #23 umbrella），形成"问题假装消失"通道。本节是 close issue 动作的强制前置门。

**主要执行者**：`product-lead`（close 动作前必须自检本节 4 条 + 4 + 5 条；hook 不强制，靠 DoD 自觉 + code-reviewer / tech-lead 抽审）。

### 1. Close 类型分类

| Close 类型 | 触发场景 | 强制要求 |
|---|---|---|
| **Shipped close** | 功能/修复已 ship + UAT 通过 | ① close 公告附 commit SHA / PR / UAT 报告链接；② 容器化部署的修复必须满足下文 §3 "容器/服务重建实证生效"（见 `.claude/standards/deployment.md`）；③ 公告里写明 SIT/E2E/UAT 覆盖范围 + **未覆盖的 scope gap**（防 #16 类"BE schema ship 但端到端不通"误报 SHIPPED） |
| **Deferred close (`not-planned`)** | 功能延期 / 当前 sprint 不做 | 必须同步起 follow-up tracker（见 §2 Deferred 红线） |
| **Duplicate / invalid close** | 重复 / 误报 / 范围外 | close 公告引用原始 issue 编号或说明"非本系统范围"原因，无需 follow-up |
| **Umbrella close** | epic / umbrella issue 整合关闭 | 必须按 §4 显式 carry-forward 所有 deferred children |

### 2. Deferred 红线（强制 follow-up tracker）

`gh issue close --reason "not-planned"` **不允许裸关**。close 时必须同步落地以下任一锚点（推荐前两项，与 #22 模式对齐）：

1. **新 gh issue tracker**：开一个 v1.X+ 范围的新 issue（label `epic:v1.X+` 或 `needs-info`），body 引用被 close 的原 issue 编号 + 触发再实施的条件
2. **ADR + research note 双锚点**（重量级 / 已有 design / spike sunk cost）：
   - `docs/adr/NNN-[feature]-deferred.md`（状态 `Proposed (deferred)`，列 v1.X+ 启动门）
   - `docs/reviews/<issue>-[topic]-research-YYYY-MM-DD.md`（既有 design / POC / spike 沉淀状态登记）
   - 参考样本：**ADR-019 + `docs/reviews/22-phase23-research-2026-05-14.md`**（#22 Phase 2/3 的双锚点）；**ADR-020 + `docs/reviews/19-folder-dnd-research-2026-05-16.md`**（#19 文件夹拖拽 v1.12+ tracker，本次落地）
3. **轻量 research note**（仅探索结论 / 无实施意图）：`docs/reviews/<issue>-research-YYYY-MM-DD.md` 单文件，说明"已评估，结论是 X，目前无计划"

**反例（本次 audit 暴露）**：
- ❌ **#18** AI 全自动化模块用途 — close 无任何 tracker，依赖"主理人 daily-use 触发 re-open"被动机制
- ❌ **#19** 文件夹拖拽 — 已有 designer spec + dnd-kit POC PASS sunk cost，但 close 时零 tracker（**本次补 ADR-020 + research note**）
- ❌ **#23** Materials umbrella — close comment "未来按需 re-open umbrella 或起新 epic" 是被动等待，无显式 carry-forward

**正面模板**：
- ✅ **#22 Phase 2/3 deferred** — 唯一带 ADR-019 + research note 的 deferred，**未来 Deferred 模板**

### 3. Close 前 verify checklist（product-lead 自检）

close issue 前对照逐条自检（推荐 close 公告里 `## Verify Checklist` 段直接抄录已勾选项）：

- [ ] **代码状态实证**：`git log --grep "#<issue>"` 或 PR 链接 ≥ 1 条，commit SHA 写入公告
- [ ] **容器化部署修复**：若涉及容器化路径（FE / BE / worker），已 `docker compose up -d --build` 后 curl AC 边界实证（见 `.claude/standards/deployment.md`）
- [ ] **测试覆盖声明**：close 公告写明 SIT/E2E/UAT 各覆盖了什么 + **明确没覆盖的 scope gap**（防 #16 "BE schema 通过 SIT，但 cron tick + 消费链路 + FE 端到端零覆盖"）
- [ ] **Deferred follow-up tracker**：若 `--reason not-planned`，§2 三种锚点至少 1 项已落盘 + close 公告引用其路径
- [ ] **Umbrella carry-forward**（如适用）：见 §4
- [ ] **Label housekeeping**：`needs-info` / `blocked` 等过程标签已清；最终 verdict label（如 `wontfix` / `done`）已加

### 4. Umbrella close 子条款（carry-forward 强制）

umbrella / epic issue close 时，若存在**任何 deferred children**（child 任务 / 子需求 / sub-feature），必须满足：

1. **逐条列出 deferred children**：close 公告里以列表形式列出每个被推迟的 sub-feature 标题
2. **每个 deferred child 显式分配 carry-forward tracker**：参照 §2 三种锚点，逐 child 落 follow-up（不可全部塞进一句"未来按需 re-open"）
3. **不允许"被动等待 re-open umbrella"**：umbrella close 的语义是"这个聚合容器已经被 epic-roadmap / 新 issue 取代"，原 umbrella 不应被 re-open；新 epic-tracker 必须以新 issue / 新 epic-label 存在

**反例**：
- ❌ **#23** Materials umbrella close comment "未来新需求按需 re-open umbrella 或起新 epic" — 被动等待，零 tracker
- ❌ **#23** 同步继承 #19 / #22 Phase 2/3 deferred-without-tracker 风险

**正面模板**：暂无（本节是新立 baseline）；下次出现 umbrella close 时此处补样本路径。

### 5. close 后 audit 抽审

- `code-reviewer` / `tech-lead` 可在季度复盘或 issue audit 时抽审本节执行情况（参考 2026-05-16 issue audit 流程）
- 抽审发现 §2 / §3 / §4 违规 → 升级 product-lead，作为流程改进案例记入 `docs/reviews/issue-audit-YYYY-MM-DD.md`
- 违规不强制 reopen 原 issue，但必须**追溯补 tracker**（不能既不 reopen 又不补 tracker）
