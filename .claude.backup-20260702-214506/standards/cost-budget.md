# Cost & Token Budget Baseline

Agent Team 是吞 token 最快的协作形态——多个 teammate 各持独立上下文 × 长会话 × 多轮对话，单功能消耗很容易冲到几百万 token；官方实测多 agent 系统均价消耗单 agent 的 **3–10×**（claude.com/blog «When to use multi-agent systems»，开销来自上下文复制 + 协调消息 + 交接摘要）——这是 [`workflow.md` Session Entry](workflow.md)「单 agent 优先 + 升级判据」的成本依据。本基线规定团队必须遵守的预算纪律与可验证的事后核账机制。

## 预算分级（默认值；项目可在 CLAUDE.md 覆盖）

| 任务规模 | 单次会话 token 上限（输入+输出合计） | 触发提示 | 触发硬停 |
|---|---|---|---|
| 小（单文件 / bugfix / 查询） | 100k | 80k | 150k |
| 中（功能开发 / 跨模块重构） | 500k | 400k | 800k |
| 大（完整 feature / 跨链路 PRD→UAT） | 2M | 1.6M | 3M |

> 这是**对话窗口**预算，不是 API 总账户预算。账户级预算由账单系统单独控制。

## 角色级纪律

- **product-lead**：每次拆任务前评估规模等级；规模超「中」必须在 PRD 顶部声明预估 token 与成本
- **tech-lead / 执行层**：发现自己即将超过单次「触发提示」阈值时主动 SendMessage product-lead 汇报进度并请示是否继续
- **任何 agent**：撞到「触发硬停」阈值时必须立即停下，不得擅自续跑

## Cache 利用率（必须 ≥ 60%）

- 高 cache miss 源于模板化文档过长 / agent 频繁切换；连续两次会话 cache hit < 50% 应触发优化
- 优化路径：把不常变的内容下沉到 skill / `.claude/standards/`、避免在 CLAUDE.md 反复改大段
- **测量闭环**：cache 利用率没有独立查询工具，统一在 release retro 时由用户跑 `/usage` 贴 4 类 token 实数核账（见 skill `agf-running-release-retro` 的 /usage 强制段）——目标不再悬空
- Sub-agent progress summaries 走 prompt cache（`cache_creation` ~3× 减少），且 idle subagent 不重复触发——Parallel Dispatch 多 teammate 场景的成本基线因此偏低，历史账单中 sub-agent 占比下降属正常
- 参考：[Anthropic Prompt Caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)、[Reduce Token Usage](https://code.claude.com/docs/en/costs#reduce-token-usage)

## 模型降级路径（建议）

不是所有任务都需要 Opus。product-lead 判断任务足够明确、不涉及架构权衡时，鼓励 teammate 主动降级到 Sonnet 甚至 Haiku：

| 任务特征 | 推荐模型 |
|---|---|
| 架构决策 / 复杂权衡 / brainstorm | Opus |
| 标准 CRUD / 文档撰写 / 代码评审 | Sonnet |
| 文本提取 / 简单格式化 / 测试样板 | Haiku |

降级是工具，不是义务——若 Sonnet 多次产出不达预期，立即升回 Opus 别硬撑。

## Agent 默认 Model 路由（基线）

下表是各 agent 的默认 model 选型与理由。任意调整需在 PRD 顶部备注复核效果：

| Agent | Model | 选型理由 |
|---|---|---|
| product-lead | opus | 编排者，需求理解 + 多 agent 协调 + UAT 业务判断 |
| tech-lead | opus | 架构权衡 + ADR 撰写 + 版本查证决策 |
| ai-agent-dev | opus | LLM/prompt 设计风险高，guardrail 与 jailbreak 防御需深度推理 |
| backend-dev | sonnet | 标准 API/迁移/认证开发 |
| frontend-dev | sonnet | 标准 UI/状态/对接开发 |
| ml-engineer | sonnet | 推理服务接入 + Pipeline 编排（架构权衡升级到 tech-lead） |
| uiux-designer | sonnet | HTML 原型 + 视觉判断；haiku 视觉表达力不足 |
| qa-engineer | sonnet | 测试判断与失败诊断需推理深度 |
| deploy-engineer | sonnet | 部署流程性强、需冒烟 / 故障调试，但无需深推理；对齐 qa / backend 档 |
| code-reviewer | sonnet | 缺陷判断 + 安全审计，下沉 haiku 风险高 |
| miniapp-dev | sonnet | 与 frontend-dev 同档 |
| miniapp-qa-engineer | sonnet | 与 qa-engineer 同档 |
| miniapp-code-reviewer | **haiku** | 小程序审查规则结构化（参考 `.claude/standards/miniapp.md`），输出短报告，已由 code-reviewer 兜底深度判断 |
| content-writer | sonnet | 文案产出 + 单一来源核对，sonnet 表达力够；haiku 易把"全新"等敏感词写飞 |
| growth-analyst | sonnet | 实验设计 + 统计判断需推理深度，不下沉 haiku |

**调整原则**：
- 同类型任务跨多 agent 时优先用 sonnet 保一致性
- 仅当任务**有明确规则可循且失误成本由其他角色兜底**时才考虑 haiku
- 升降级触发：连续 2 次产出不达预期升档；连续 5 次任务空跑（输入不足 1k token）降档

## Effort 维度（与 model 正交；Opus 4.8 起）

`model` 决定**能力档**（opus/sonnet/haiku），`effort` 决定**思考深度**（`low / medium / high / xhigh / max`，可用档取决于 model）。二者正交：同一个 opus 可低 effort 快答、也可 xhigh 深推。合理用 effort 能在不换 model 的前提下省钱（降 effort）或提质（升 effort）。

### 推荐 effort（按任务性质）

| 任务性质 | 推荐 effort | 典型角色 / 场景 |
|---|---|---|
| 架构决策 / ADR / 复杂权衡 / 疑难 debug | `high`～`xhigh` | tech-lead 架构评审、ai-agent-dev guardrail 设计、PL 拆复杂 PRD |
| 常规实现 / 标准 review / 文档 | 默认（medium） | dev 日常 CRUD、code-reviewer 常规审、content-writer |
| 样板 / 格式化 / 文本提取 | `low` | 测试样板、简单转换 |

### ⚠️ effort 在各路径的生效情况

路径生效矩阵唯一来源是 [`team-roles.md`](team-roles.md) frontmatter 能力表（`effort` / `model` 行），此处不重复。effort 特有的操作结论：

- **Agent Team teammate 路径不 honor frontmatter `effort`**，且当前无 per-role 设置手段——**不要给 teammate 角色文件加 `effort:`**（会重蹈 A2 死字段）。某子任务需深推时，由 PL 自己接（高 effort）或拆成更小的明确步骤交 teammate。
- effort 路由现阶段主要落在 **PL（lead）** 与 **sub-agent / headless** 两条路径；teammate 的成本/质量控制仍以 **model 档**（上表）为主。
- 建议 PL **不硬编码** `effort:`（routine 编排会被一并抬到高 effort 浪费 token），改用 `/effort` 按环节临时调。

### Fast mode（成本/速度杠杆）

Opus 4.8 的 Fast mode：**2× 费率换 2.5× 速度**。适合 PL 在赶工的编排/澄清环节临时 `/fast`，不宜长期挂着（费率翻倍）。

## Pool 模式下成本预算（ADR-001 落地）

[ADR-001](../../docs/adr/001-multi-instance-worker-pool.md) + [`workflow.md` §Multi-instance Worker Pool](workflow.md) 引入同 type 多实例并发；本节定义 pool 模式的成本约束。

### Token 倍数预期（Anthropic 实证）

| Pool 模式 | 同时活跃 teammate 上限 | Token 倍数（vs 单实例）| wall-time 倍数 |
|---|---|---|---|
| pool=off（单实例）| 5 | 1×（基线）| 1× |
| pool=auto / 默认 cap=5 | 15（5 dev + 5 reviewer + 5 qa）| 3-5× | 0.3-0.5×（节省 50-70%）|
| pool=auto / 高峰 cap=7 | 21 | 6-8× | 0.2-0.3×（节省 70-80%）|

参考 Anthropic [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)：multi-agent ≈ 15× chat × 4× single-agent；并行加速最多 90%。

### Pool 上限按预算分档自动调

| 预算档 | Token 实测倍数 | Pool 上限（覆盖 [`team-roles.md`](team-roles.md) 默认）|
|---|---|---|
| **Small** (≤ 100K token / feature) | ≤ 3× | 上限 3 |
| **Medium** (> 100K, ≤ 500K / feature) | ≤ 5× | 上限 5（默认）|
| **Large** (> 500K / feature) | ≤ 8× | 上限 7 |

PL 在 Step 3 派单时按 PRD 复杂度选档。**判定规则（单一决策树，表中倍数即该档上限 cap）**：feature 收口时 `实测倍数 ≤ 所选档 cap` → 正常；`> cap` → 超档，retro §3 token 段必须记录原因；`> 8×`（绝对上限，与选档无关）→ 强制 retro 复盘是否过度并发。不存在"区间内自行判断"的模糊地带。

### 触发审查的硬阈值

- **Pool 实际倍数 > 8×** → retro 复盘是否过度并发（在 retro skill §3 token 段记录）
- **单 feature 总 cost > Large 档 1.5×** → tech-lead 评估是否架构问题（如多实例 review 重复读相同 PRD 导致 token 重复）；用 `/usage` **分类成本**（skills / subagents / per-MCP）定位是哪类在重复烧
- **Cache hit ratio < 50%**（pool 模式下下限比单实例 60% 放宽，因多实例首次 spawn 必有 cache miss）→ 提示 PL 检查实例是否短时间内 reap 太多

### Dynamic Workflow 成本门（ADR-002 基底；用途边界已扩展至 ADR-005 阶段嵌入）

`/agf-review-sweep` 等 Dynamic Workflow 单 run 扇出几十～上百 agent，**比 Pool 还烧**。门控：

- **显式触发 + PL 批**：禁默认开 `ultracode`（会把每个任务都编排成 workflow）；只在大 PR / 审计由 PL 按规模批准后调。
- **预算档**：≥ Medium 档（> 100k）的 workflow run **必须** PL 事前批 + 进 retro §3 记录实测倍数。
- **看成本**：`/workflows` 进度视图每 phase 带 token total；`/usage` 的 subagents 分类含 workflow agent。
- **降级**：研究预览期，`disableWorkflows` / `/config` 一键停 → 回 Pool（详 [ADR-002](../../docs/adr/002-dynamic-workflows-adoption.md)）。

### Spawn 成本可控的实践

- **同 batch 内复用实例**：1 个 reviewer-1 审 ≥ 2 个 task 时仍走单实例（不为每 task spawn），仅当 batch 内 ≥ 2 task **同时 pending** 才 fan-out
- **reap 时机**：实例完成立即 idle，下个 batch 重 spawn（避免长期占 context window）
- **共享 SSOT**：所有实例加载相同 `.claude/agents/<type>.md`（cache hit 友好）

## 反模式

- ❌ "为了让 agent 想得更全面，把所有 standards 都贴进 prompt" → cache 失效，token 翻倍
- ❌ "让 teammate 互相校对每一步" → 多轮往返爆量
- ❌ "等 agent 自己撞硬停" → 浪费已消耗的 token 没产出
- ❌ "Pool 模式 spawn N=10 实例求快" → 超本 §硬阈值，触发 retro 强制复盘

## 参考

- [Claude Code Costs](https://code.claude.com/docs/en/costs)
- [Agent Team Token Costs](https://code.claude.com/docs/en/costs#agent-team-token-costs)
- [Datadog Claude Code Monitoring](https://www.datadoghq.com/blog/claude-code-monitoring/)
