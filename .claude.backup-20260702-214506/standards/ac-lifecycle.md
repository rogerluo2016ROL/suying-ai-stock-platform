# AC Lifecycle and Delivery Definition

## AC 验收生命周期

```
product-lead 定义 AC（PRD）→ 任务分配时把具体 AC 写进 SendMessage
       ↓
开发者实现 + Unit + SIT（API+DB+external 单边集成）→ 逐条自验 AC → append 到 progress/<role>.md → SendMessage 完成报告
       ↓
product-lead 触发 code-reviewer 审查代码质量 + SIT 证据 audit
       ↓
code-review 通过（code verdict ∈ {`approve`, `approve with changes`}；`block` 不通过，回派 dev）后进入 E2E
       ↓
qa-engineer 执行 E2E → 通过后进入 UAT
       ↓
product-lead 对照 AC 最终判定 → 汇报用户（业务签字）→ 归档 progress/
```

**AC 可测试性标准**：每条 AC 必须有触发条件（"当…时"）+ 可观察结果（"显示…"/"返回…"/"跳转至…"）。**交互类 AC 写成可点击因果链**——"点击 X 控件 → 发出 `<method path>` → 成功后 UI 显示 Z"，把控件、API 调用、可观测后果串进一条 AC（防"按钮没事件 / 前后端接不上"在 AC 层就无法验收）。

## Self-Reporting Pattern（自报告模式）

**核心思想**：teammate 完成任务时，先把过程证据**追加写入 `progress/<role>.md`**（持久化），再 SendMessage 给 product-lead 一份摘要。这样 lead session 关闭、压缩、跨机器恢复后，仍能从文件系统读出"做到哪了 / 跑过什么 / 验过什么"。行业等价物：Anthropic Agent Teams 文档的 idle notification + SendMessage + shared task list 组合（官方未单独命名）。

**三要素**（缺一不可）：
1. **报告格式**：精简 5 段（见下文「完整条目格式」，pass 单行、fail/blocked 才展开）
2. **写入位置**：`progress/<role>.md`，append 到文件末尾（chronological）
3. **验证标准**：fail / blocked 必须含**实际跑过的命令 + 真实输出**，不允许只写"已通过"；pass 一句话即可

**强制约束**：
- 适用对象：所有执行层 teammate（`backend-dev` / `frontend-dev` / `ai-agent-dev` / `ml-engineer` / `miniapp-dev`）
- 强制时机：每完成一个 task 单（不论是否阻塞），先 append 到 `progress/<role>.md`，再 SendMessage
- Hook 兜底：`SubagentStop` 与 `TeammateIdle` 触发 [`check-progress-file.sh`](../hooks/check-progress-file.sh)；该 role 的 `progress/<role>.md` 不存在或空 → exit 2 阻断退出
- 豁免：当前 team 没有 pending/in_progress task 分给该 role 时（standby 角色）放行
- 其他角色（`product-lead` / `code-reviewer` / `qa-engineer` / `tech-lead` / `uiux-designer` / `content-writer` / `growth-analyst` / `miniapp-code-reviewer` / `miniapp-qa-engineer`）由各自产物（`docs/{prd,reviews,qa,design,content,growth}/`）兜底，不强制写 `progress/`，写了也不会被 hook 拦

### 完整条目格式（progress/<role>.md 内）

> **设计原则**：可读性优先——pass 单行扫读，fail/blocked 才展开。原 9 段（状态 / 任务类型 / Skills used / 验证命令 / 验证输出 / SIT 证据 / AC 自验 / 涉及文件 / 下一步）压缩为 5 段：状态 / Skills / SIT 证据（含 AC 自验勾选）/ 质量门 / 下一步。被砍字段说明见本节末。
>
> **Pool 模式**（[ADR-001](../../docs/adr/001-multi-instance-worker-pool.md)）：进度文件命名 `progress/<role>-<N>.md`（pool 实例 N）或 `progress/<role>.md`（单实例），格式相同。

每完成一个 task 单 append 一段，格式如下：

```markdown
## [任务名 / Task ID] - YYYY-MM-DD HH:MM
**状态**: 已完成 / 阻塞
**Skills**: superpowers:test-driven-development, agf-running-sit-tests, ...

**SIT 证据**（按 AC 列；行首 `[x]/[ ]` 同时表达 AC 自验勾选；pass ≤ 80 字单行，fail/blocked 展开命令 + 输出 + 偏差，整段 ≤ 5 行）:
- [x] AC-1 ✅ 用户注册 — POST /register 写库成功
- [x] AC-2 ✅ 邮箱校验
- [ ] AC-3 ❌ webhook 签名 — 实现 SHA1，PRD 要 HMAC-SHA256
    - 命令: $ pytest backend/tests/sit/test_webhook.py::test_signature -v
    - 输出: AssertionError: signature mismatch (expected HMAC-SHA256, got plain)

**质量门**: lint ✅ / typecheck ✅ / unit ✅ / SIT ⚠️（AC-3 fail）

**下一步**: 等待 review / 阻塞: <具体阻塞点 + 已尝试方案 + 需要什么解锁>
```

**字段约束**：
- **状态**：仅 `已完成` / `阻塞` 两值；不再写 `进行中`（idle 退出时进行中即视为阻塞）
- **Skills**：1 行内列完，逗号分隔；用于 retro 检视 skill 触发率
- **SIT 证据**：pass 单行结论即可（≤ 80 字），fail / blocked 才内嵌命令 + 输出 + 偏差三行（≤ 5 行）。code-reviewer 在 audit 时按 SIT Audit 4 项检查核对（定义见 [`workflow.md` SIT Audit](workflow.md) / `code-reviewer.md` SIT Audit 段）
- **质量门**：1 行内打 `lint / typecheck / unit / SIT` 4 项 ✅/⚠️/❌；任一非 ✅ 在括号内 ≤ 30 字简注
- **下一步**：阻塞场景必须写明阻塞点 + 已尝试 + 需要什么；**勿在阻塞状态下继续 SendMessage 假装在推进**

**已砍字段（不要回填）**：
- `任务类型` → commit message 的 `feat:` / `fix:` / `refactor:` 前缀已表达
- 顶层 `验证命令` + `验证输出` → 合并进 `质量门` 一行 + 失败的 AC 在 `SIT 证据` 内嵌
- 独立 `AC 自验` 段 → 用 `SIT 证据` 行首 `[x]/[ ]` 同时承担勾选职责
- `涉及文件` 列表 → `git diff --stat` / `git log --stat` 为权威，手抄列表会过时

### SendMessage 完成报告（写完 progress/ 之后发）

SendMessage 摘要保留 AC 行级显示（lead 在消息内即可扫到）；与 progress 5 段格式中 `**SIT 证据**` 行首 `[x]/[ ]` 等价，只是 SendMessage 是"提炼版"，让 lead 不打开 progress 文件就能决策。

```
SendMessage({to: "product-lead", message: "完成: [功能名]\n\nProgress 详情: progress/<role>.md (条目: <任务名> - <时间>)\n\nSIT 结论: ✅ 全部 AC integration 层覆盖 / ⚠️ 部分 fail [一行说明] / ❌ blocked [一行说明]\n\nAC 自验摘要:\n- [x] AC-1: ✅\n- [ ] AC-2: ⚠️ [一行说明]\n\nSkills used: superpowers:test-driven-development, superpowers:verification-before-completion, agf-running-sit-tests, ...\n\n下一步: <一行>", summary: "完成: [功能名]"})
```

`progress/<role>.md` 的条目是事实底稿；SendMessage 是给 lead 的摘要，**不能取代**底稿，偏差时 product-lead 以底稿为准。`AC 自验摘要` 与 progress 内联 `[x]/[ ]`、`Skills used:` 与 progress `**Skills**` 字段必须一致。涉及文件不再单列字段——以 `git diff --stat` / `git log --stat` 为权威，PR description 必带；上游 task 派单也用 PR 链接而非抄文件清单。

### 开发者 Definition of Done

报告完成前必须满足（适用于 frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev）：
- [ ] **TDD red-green-refactor 顺序**（核心纪律，新功能 / bugfix 强制；纯重构 / 文档可跳过）：
  - **red**：先写**失败的** Unit / SIT 测试（commit message 含 `test:` 前缀），跑 `pytest` / `vitest` 看到红
  - **green**：写**最少**实现让测试变绿（commit message 含 `feat:` / `fix:` 前缀，引用前一条 test commit hash）
  - **refactor**：保持绿的前提下整理代码（commit message 含 `refactor:` 前缀）
  - PR commit history **必须看得出 red → green 顺序**（first test commit 早于 first impl commit）
- [ ] Unit 测试已编写并通过（pytest / vitest 全绿 + lint + typecheck 全绿）
- [ ] 已跑 SIT (API+DB+external 单边集成) 并 append 证据到 `progress/<role>.md` SIT 段
- [ ] 每条 AC 已逐一本地验证（非"看起来像"，是真正跑过）
- [ ] 实现前已调用 `superpowers:test-driven-development`（与上面 red-green-refactor 顺序绑定）
- [ ] 完成前已调用 `superpowers:verification-before-completion`
- [ ] **已 append 一条完整条目到 `progress/<role>.md`**（5 段精简格式：状态 / Skills / SIT 证据（含 AC 自验勾选）/ 质量门 / 下一步）
- [ ] SendMessage 完成报告引用了 `progress/<role>.md` 对应条目
- [ ] 依次通过 code-review（含 SIT Audit）→ E2E → UAT 各阶段门才算交付完成（各档 verdict 取值 + 阶段门转换规则见 [`workflow.md` §Verdict 词表](workflow.md)，本条不重复）
- [ ] UAT 报告提交后，必须由 product-lead 对照 PRD AC 做最终业务签字才算交付完成

#### 通用 DoD（所有执行层 dev 必做）

以下三条对全部 dev 角色（frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev）完全一致，各 agent 文件的 `## Definition of Done` **不再重复罗列**，只列角色特有项 + 指向本节：

1. **已跑 SIT 并 append 证据**到 `progress/<role>.md` 的 `**SIT 证据**` 段（按 skill `agf-running-sit-tests`；pass 单行，fail/blocked 内嵌命令 + 真实输出）
2. **progress 已写完整 5 段条目**（状态 / Skills / SIT 证据 / 质量门 / 下一步，格式见上文"完整条目格式"）
3. **完成报告（SendMessage to product-lead）含 SIT 结论行**（`✅ 全部 AC integration 层覆盖` / `⚠️ 部分 fail [一行]` / `❌ blocked [一行]`）

各角色差异项见对应 agent 文件的 `## Definition of Done` 章节。

### 归档（UAT 签字后由 product-lead 执行）

UAT 业务签字 → product-lead 跑 `bash .claude/scripts/archive-progress.sh <feature>`，脚本自动按 base role 分组 + 组内按 N 升序合并 `progress/<role>{-<N>}.md` 到 `docs/qa/<feature>-process-log.md`（pool 多实例自动归组），再 `git rm progress/*.md` 留 `.gitkeep` + `README.md`。详见 [`product-lead.md` Step 5](../agents/product-lead.md) + [`archive-progress.sh`](../scripts/archive-progress.sh)。
