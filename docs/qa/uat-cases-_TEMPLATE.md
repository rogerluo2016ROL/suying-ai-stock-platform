---
# 结构化元数据（PL / 工具解析用；不要删，值可改）
feature: [feature-slug]
stage: uat-cases
status: Draft                         # Draft → Approved（用户审核确认后）→ Done（全部执行完）
date: YYYY-MM-DD
change: docs/changes/[change]/          # 需求来源主路径（tasks.md 含 AC↔Scenario 映射表）
prd: docs/prd/[feature]-[YYYY-MM-DD].md # 旧流程 fallback（弃用 v6.9.0，删 v7.0.0）
e2e_report: docs/qa/[feature]-e2e-[YYYY-MM-DD].md
approved_by: ""                       # 用户/业务方署名（status: Approved 时必填）
approved_date: ""
cases_total: 0
cases_p0: 0
ui_surfaces: 0                        # 用户可见界面数 = 界面渲染核查矩阵行数；纯后端 / CLI feature 为 0
---

# UAT 测试用例 — [Feature Name]

> **This is a template.** 路径命名：`docs/qa/[feature]-uat-cases-[YYYY-MM-DD].md`（全 feature 单份，pool 多实例共享）。
>
> **Gate**：本文档在 E2E 通过后、UAT 执行前生成；**frontmatter `status: Approved`（用户审核确认）之前不得开始 UAT 执行**——MAJOR / MINOR 强制，PATCH 级 hotfix 可由 product-lead 显式豁免（细则见 [`testing.md`](../../.claude/standards/testing.md)「UAT 用例文档」节）。每条用例独立执行、独立判定。删除本介绍段后再发布。

- **需求来源**: `docs/changes/[change]/`（`tasks.md` 含 AC↔Scenario 映射表；旧流程 fallback：`docs/prd/[feature]-[YYYY-MM-DD].md`）
- **E2E 报告**: `docs/qa/[feature]-e2e-[YYYY-MM-DD].md`
- **UAT 栈**: 取自 `docs/deploy/[feature]-uat-[YYYY-MM-DD].md`（无共享栈则 legacy 兜底）

## AC 覆盖矩阵（每条 AC ≥ 1 个用例，缺行即漏）

| AC（changes/tasks.md 映射表；PRD §4 fallback） | Priority | 用例 |
|---|---|---|
| AC-1 | P0 | UAT-1, UAT-2 |
| AC-2 | P1 | UAT-3 |

## 界面渲染核查矩阵（每个用户可见界面 ≥ 1 行，缺行即漏）

> 界面清单对照 `docs/design/[feature]/spec.md` + 变更文件夹 proposal/tasks 枚举（PRD fallback）。执行时每行必须**真渲染**（Web = chrome-devtools MCP 加载 UAT 栈 URL；小程序 = 开发者工具模拟器 + 真机；Apple = 模拟器 / 真机）+ 截图 + **读图四查**回填（截图必须用 `Read` 读回做视觉分析，**只截图不读图 = 未核查**）；**纯 API 断言不构成含界面用例的 Pass**。SSOT 见 [`testing.md`](../../.claude/standards/testing.md)「UAT 界面渲染核查」节。纯后端 / CLI feature 本节标"不适用"。

| 界面（页面/弹窗/浮层） | 覆盖用例 | 截图（执行后回填） | 导航 | 裁切 | 控件可点 | 视觉达标 |
|---|---|---|---|---|---|---|
| 如：列表页 `/items` | UAT-1 | `evidence/UAT-1-items.png` | 待执行 | 待执行 | 待执行 | 待执行 |

四查每格回填 `✅` / `❌ + 一句偏差`；导航 / 裁切 / 视觉达标的结论必须出自 `Read` 读图（对照 design spec + `index.html` 原型，视觉达标判准 = **截图敢不敢直接交付用户**），控件可点出自真实交互；`❌` 按所属用例 priority 走 Verdict 决策树。

## 用例

### UAT-1: [标题]（← AC-1，P0）

1. **前置条件**: [数据准备 / 环境状态，如"已有 approved 母本"、"api_keys 已配置"]
2. **触发条件**: 当 [触发动作 / 事件] 时
3. **操作步骤**:
   1. [可复现的具体动作：命令 / API 调用 / UI 操作]
   2. [...]
4. **预期结果**: [必须可观察：显示… / 返回… / 跳转至…；禁"功能正常"这类无法判定的描述]
5. **实际结果 + 证据**（执行后回填；真实跑过的命令 + 输出 / 截图，不允许只写"已通过"；**涉及用户可见界面：真渲染截图 + 读图四查结论必选，纯 API 输出不构成 Pass**）:
   - run 1: `待执行`
   - run 2（仅 P0，pass^2 检验）: `待执行`
6. **Verdict**: 待执行 <!-- ✅ Pass / ❌ Fail / ⚠️ Blocked / ⚠️ Flaky；P0 须 pass^2 = 2/2 -->

（按本骨架为每条用例复制一节；用例 ID 文档内自增）

## 用户审核确认（status → Approved 的依据）

- [ ] 用例覆盖全部 AC（来自 changes/tasks.md 映射表；PRD fallback）（对照上方矩阵无缺行）
- [ ] 每条用例字段 1–5 齐全；预期结果可观察（无"功能正常"式描述）
- [ ] 前置条件可准备、操作步骤可复现
- [ ] 界面渲染核查矩阵覆盖全部用户可见界面（对照 `docs/design/[feature]/spec.md` 无缺行；纯后端 feature 标"不适用"）
- **审核人**: ________　**日期**: ________　**结论**: 确认 / 需修改（列出条目）

审核通过后由 qa-engineer 将 frontmatter `status` 改为 `Approved` 并回填 `approved_by` / `approved_date`。

## 执行规则

- 每条用例独立执行、独立判定，**禁止合并写"全部通过"**
- **fail 的用例必须展开**：命令 + 真实输出 + 偏差（与预期差在哪）
- P0 用例 pass^2：连续 2 次都过才 Pass；两次不一致 = `⚠️ Flaky`，按 fail 处理
- **界面渲染核查**：矩阵每行必须真渲染（chrome-devtools / 对应轨模拟器）+ 截图 + 读图四查（导航 / 裁切 / 控件可点 / 视觉达标）后回填；任一行缺截图或缺读图结论 = 该界面未测，相关用例不得记 Pass（SSOT：`testing.md`「UAT 界面渲染核查」节）
- Pool 模式：本文档全 feature 单份；多 qa 实例分担执行时在该用例「实际结果」行末注 `tester: qa-engineer-<N>`
- 全部执行完：frontmatter `status: Done`；UAT 报告（skill `agf-writing-qa-report`）引用本文件用例 ID，**证据 SSOT 在本文档，报告不重复粘贴**
