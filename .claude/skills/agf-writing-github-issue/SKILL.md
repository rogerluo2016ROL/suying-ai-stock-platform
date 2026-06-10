---
name: agf-writing-github-issue
description: Use whenever a user, product-lead, or qa-engineer wants to create a GitHub issue in the project repo — including phrases like "提一个 issue / 写一个 issue / 报 bug / 把这个开成 issue / gh issue / 上 GitHub / track 一下 / 立个 ticket". Provides the required-field skeleton, locked label set (type / area / epic / priority / severity / phase), gh CLI heredoc template, and the QA-auto-issue exception path. Replaces ad-hoc `gh issue create` calls with inconsistent titles / missing labels / freestyle bodies.
---

# Writing a GitHub Issue

> Examples 段含具体项目（RolexOps）实例（image tag、cookie name、目录路径），保留以提高参考价值；使用时按你项目的实际值替换。

Use this skill when any of the following:

- 用户说 "写 issue / 提一个 issue / 报 bug / 上 GitHub / track 一下 / 立个 ticket"
- product-lead 把 PRD 里的 AC 拆成可分派的 issue
- dev 在 SIT 自跑中发现 P0 / P1 缺陷（**特殊路径，见下**）
- qa-engineer 在 E2E / UAT 中发现 P0 / P1 问题（**特殊路径，见下**）
- 主 Claude / 任意 agent 准备调用 `gh issue create`

## 最小输入模式（用户授权 / 2026-05-13）

> **默认行为**：用户只给"关键信息"，agent 智能补全其他字段，直接 `gh issue create`，不走草稿 gate。

### 用户必须给的最少信息

| 信息 | 说明 |
|---|---|
| **要解决什么 / 想做什么** | 一两句话描述问题或功能想法，bug 还是 feature 还是 chore 可推断 |

**就这一条**。其他字段都由 agent 推断 + 补全。

### Agent 必须自动补全的字段

| 字段 | 推断规则 |
|---|---|
| **Title** | 按用户描述拟动宾结构 + 加 type prefix。`feat(...)` / `fix(...)` / `chore(...)` / `docs(...)`。≤70 char |
| **Why / 背景** | 从用户原话扩写 1-2 段；若上下文有相关 PRD / ADR / 历史 issue，主动 grep `docs/prd/` `docs/adr/` 并 cite |
| **AC** | 按 feature/bug 分别套模板生成 2-4 条可验证条件；bug 必含 "修复后用什么验证" |
| **type label** | feat（新功能）/ bug（修缺陷）/ chore（重构/构建/文档）/ adr（架构决策）按关键词判 |
| **area label** | grep 用户描述里的关键词：`frontend`/`React`/`UI`/`组件` → area:frontend；`API`/`endpoint`/`后端`/`数据库`/`migration` → area:backend；`LLM`/`prompt`/`豆包`/`Qwen`/`embedding` → area:ai；`docker`/`compose`/`caddy`/`redis` → area:infra |
| **priority** | bug 默认 P1（核心流程影响）；feature 默认 P2（除非用户说"急/紧急/blocking"→ P1）；data loss / 安全 / 线上挂 → P0 |
| **severity**（bug 专用） | 与 priority 同步：P0/P1 |
| **epic 关联** | grep 当前 branch 名（`release/v1.6.0` etc.）+ 最近 commit + `docs/prd/`，能锁定 Epic N 才加；不确定**不加**，宁缺勿乱 |
| **phase** | 默认不加；除非用户在 SIT/E2E/UAT 上下文中报问题 |
| **复现步骤**（bug 专用） | 用户没给的话用合理推测填，并在末尾标 `<!-- TODO 用户补充实际复现 step -->` |
| **环境**（bug 专用） | grep `docker compose ps` 拿当前 image / commit hash，前端 bug 默认填 "Chrome 最新版（用户未指定）" |
| **关联 (Refs)** | 主动 grep 关联 PRD / ADR / 现有 issue（gh issue list -L 10 关键词）；找到的填，找不到填 N/A |

### 兜底问号（只在以下情况问用户）

1. **priority 真拿不准 P0/P1/P2** — 比如用户说"挺重要"，bug 但没说阻塞与否
2. **area 完全猜不出** — 描述太抽象（"那个东西坏了"）
3. **是 bug 还是 feature 真分不清** — 比如"X 行为不太对，是不是应该 Y"

非这三种 → **不要问，直接补全 + 创建**。事后用户在 GitHub 上 edit 比中途问还快。

## 自动 issue 路径（已授权，跳过用户确认）

**路径 A — dev 在 SIT 中发现 P0 / P1**（SIT 由 dev 自跑）：

1. 直接 `gh issue create`（不需问用户、不需 product-lead 同意）
2. `--label "type:bug,priority:P0,severity:P0,phase:sit"`（或对应 P1）
3. 创建后通过 SendMessage 向 product-lead 报告 issue 号
4. **P2 问题不开 issue**，只在 `progress/<role>.md` 的 `**SIT 证据**` 段记 fail/blocked

**路径 B — qa-engineer 在 E2E / UAT 中发现 P0 / P1**：

1. 直接 `gh issue create`
2. `--label "type:bug,priority:P0,severity:P0,phase:e2e"`（或 `phase:uat`）
3. 创建后通过 SendMessage 向 product-lead 报告 issue 号
4. **P2 问题不开 issue**，只记录在 E2E / UAT 报告里

来源：用户 memory `feedback_qa_auto_gh_issue.md`；SIT 归属在 dev，QA 仅覆盖 E2E / UAT。

---

## 字段总览（最小输入模式下 agent 自动补全）

最终 issue 必有：

- Title（agent 拟）
- Why / 背景（agent 扩写）
- AC bullets（agent 套模板生成）
- Type label + Area label + Priority label（agent 推断）
- Refs（agent grep 后填）

最终 issue 选填（命中才加）：

- `epic:N`（关联 Epic 1-12，从 branch / commit / PRD 锁定）
- `phase:design/dev/review/sit/e2e/uat`（QA 上下文才加）
- `severity:P0/P1`（bug 专用）
- `v1.6`（release 关联）

## 优先级判定

| 级别 | 适用场景 |
|---|---|
| **P0** | 线上阻塞 / 数据损坏 / 安全漏洞 / UAT-block regression |
| **P1** | 核心流程影响 / UX regression / 性能 SLA 超标但非阻塞 |
| **P2** | 次要 / 体验优化 / nice-to-have |

判不准时 → 偏保守降一级（P0→P1），不要默认拔高。

## 本仓锁定 label 集合（不要自创）

`gh label list` 已固化的 label，**只能从下面选**：

```
type:feat | type:bug | type:chore | type:adr
area:frontend | area:backend | area:ai | area:infra
epic:1 | epic:2 | epic:3 | epic:4 | epic:5 | epic:6
epic:7 | epic:8 | epic:9 | epic:10 | epic:11 | epic:12
phase:design | phase:dev | phase:review | phase:sit | phase:e2e | phase:uat
priority:P0 | priority:P1 | priority:P2
severity:P0 | severity:P1
status:blocked | status:needs-info | status:wontfix
v1.6
```

新需求要新 label → **先停下问用户**，不要直接 `gh label create`。

## Body 模板

`gh issue create --body-file -` 喂下面这个模板（替换 `<...>`）：

```markdown
## 背景 / Why

<1-3 段说清楚要解决什么问题、用户痛点 / 业务驱动、为什么现在做>

## 验收标准 / AC

- [ ] AC-1: <具体可验证的条件>
- [ ] AC-2: <…>
- [ ] AC-3: <…>

## 关联

- PRD: <docs/prd/xxx.md 或 "N/A">
- ADR: <docs/adr/NNN-xxx.md 或 "N/A">
- Related issues: <#123 #456 或 "N/A">

## 备注

<可选：约束 / 性能预算 / 安全要求 / 截图 / log 片段>
```

bug 类 issue 额外要求：

```markdown
## 复现步骤

1. <step>
2. <step>
3. <step>

## 期望 vs 实际

- 期望: <…>
- 实际: <…>

## 环境

- Branch / commit: <…>
- Browser / OS: <…>（前端）
- 容器 / 后端版本: <docker compose logs ... 时间戳>
```

## gh CLI 命令模板

**正确做法（HEREDOC，避免 shell escape 出错）**：

```bash
gh issue create \
  --title "feat(auth): 加上 OAuth Google 登录" \
  --label "type:feat,area:backend,epic:3,priority:P1" \
  --body "$(cat <<'EOF'
## 背景 / Why

当前只支持用户名密码登录，团队反馈每次新员工都要找主理人手动 create-owner，体验差。

## 验收标准 / AC

- [ ] AC-1: POST /api/auth/oauth/google 接收 Google OAuth code，返回 httpOnly cookie
- [ ] AC-2: 前端 LoginPage 新增 "用 Google 登录" 按钮
- [ ] AC-3: 通过 SIT：含错误回调、过期 code、撤销授权三种 case

## 关联

- PRD: docs/prd/oauth-google-2026-05-13.md
- ADR: docs/adr/000-system-architecture.md §3.6
EOF
)"
```

**错误做法**（禁止）：
- ❌ `gh issue create --body "..."` 含换行 / 反引号 / 中文引号 —— shell 转义噩梦
- ❌ `--label "P0"` —— 不带 `priority:` 前缀
- ❌ `gh label create` 自创新 label —— 必须先问用户

## 执行流程（最小输入模式）

```
1. 接收用户「关键信息」（一两句话）
   ↓
2. Agent 推断字段：
   - title / type / area / priority / severity
   - grep 当前 branch / commit / docs/prd/ / docs/adr/ 拿 epic / refs
   - 按 type 套 body 模板（feature 或 bug）
   ↓
3. 若命中"兜底问号"三类（priority 真拿不准 / area 完全猜不出 / type 分不清）
   → 简短问一句；否则跳过
   ↓
4. 用 HEREDOC 拼 body + 锁定 label
   ↓
5. gh issue create（直接执行）
   ↓
6. 报告 issue URL + 已贴 label 清单
   ↓
7.（QA 路径）SendMessage product-lead 报 issue #
```

### 反模式：过度提问

❌ "你的优先级是 P0 还是 P1 还是 P2？area 选 frontend 还是 backend？要加哪些 epic label？"

→ 这违反用户授权。**只在兜底问号三类才问，且只问那一个不确定的字段。**

✅ 用户："发布按钮点了没反应"

→ agent 自动判定：type:bug, area:frontend, priority:P1, severity:P1，AC 套 bug 模板，复现步骤推测填 + 标 TODO，直接 create。

## 例子

**Example 1 — feature 请求**

User: "我想把仪表盘加一个本月成本曲线，能开个 issue 吗？"

```bash
gh issue create \
  --title "feat(dashboard): 仪表盘新增本月成本曲线视图" \
  --label "type:feat,area:frontend,priority:P2" \
  --body "$(cat <<'EOF'
## 背景 / Why

主理人每天看 docs/reviews/cost-YYYY-MM.md 才能知道当月花了多少，希望仪表盘直接出一条曲线一眼看趋势。

## 验收标准 / AC

- [ ] AC-1: 仪表盘新增 "本月成本" 卡片，含 sparkline + 总额
- [ ] AC-2: 数据源读 docs/reviews/cost-YYYY-MM.md（或 /api/admin/cost 端点）
- [ ] AC-3: 加载失败时 graceful degrade（卡片显示 "--"，不让整页 crash）

## 关联

- Refs: .claude/standards/cost-budget.md
EOF
)"
```

**Example 2 — bug 上报**

User: "/api/materials/upload 上传大于 10MB 的图就 500，你帮我开 issue"

```bash
gh issue create \
  --title "bug(materials): 上传 >10MB 图片返回 500" \
  --label "type:bug,area:backend,priority:P1,severity:P1" \
  --body "$(cat <<'EOF'
## 背景 / Why

主理人上传素材是核心流程，10MB+ 的相机原图直接 500 → blocking 用户基础使用。

## 复现步骤

1. 登录系统
2. 进入素材库
3. 点击上传，选择 >10MB jpg/png
4. 请求 5s 后返回 500

## 期望 vs 实际

- 期望: 上传成功，或返回 413 + 友好提示 "超过 10MB 限制"
- 实际: 500 Internal Server Error，前端只看到 "上传失败"

## 验收标准 / AC

- [ ] AC-1: 后端检测到 >10MB 返回 413 + JSON `{"error": "max_size_10mb"}`
- [ ] AC-2: 前端识别 413，toast "图片不能大于 10MB"
- [ ] AC-3: 增加 integration test 覆盖 9.9MB / 10.1MB 边界

## 环境

- Branch / commit: release/v1.6.0 @ <hash>
- Backend: docker compose backend-1, image rolexops-backend:latest
EOF
)"
```

**Example 3 — dev SIT 自动路径**（Path A，dev-owned SIT）

backend-dev 跑 SIT 时发现 P0：

```bash
# 不问用户，直接创建
gh issue create \
  --title "bug(auth): SIT 发现 logout 后 cookie 未清除" \
  --label "type:bug,area:backend,priority:P0,severity:P0,phase:sit" \
  --body-file - <<'EOF'
## 背景 / Why

SIT 跑 v1.6.0 Epic 3 case 4 时发现：POST /api/auth/logout 返回 200，但 httpOnly cookie 没被 Set-Cookie 清空 → 用户登出后仍可访问 /api/me，权限泄漏。

## 复现步骤
1. 登录拿到 cookie
2. POST /api/auth/logout → 200
3. GET /api/me → 200（应为 401）

## 验收标准 / AC

- [ ] AC-1: logout 响应含 `Set-Cookie: rolex_session=; Max-Age=0; HttpOnly`
- [ ] AC-2: logout 后 GET /api/me → 401

## 关联

- SIT 证据: progress/backend-dev.md（条目 v1.6.0 logout - 2026-05-13；`**SIT 证据**` 段 AC-2 fail）
EOF

# 然后
# SendMessage product-lead "已创建 P0 issue #NN，blocking UAT"
```

## 验证 gate（issue 创建后）

每次 `gh issue create` 成功后，最后一条 user-facing 消息**必须包含**：

- ✅ Issue URL（gh 命令的 stdout 第一行）
- ✅ 已贴的 label 清单
- ✅（若 QA 路径）已发给 product-lead 的 SendMessage 确认

让用户能立刻点链接 + 知道分类对不对。

## Anti-patterns

| 反模式 | 为什么不行 |
|---|---|
| Title 用句号结尾 / 含特殊字符 | gh search / 看板列表不易扫读 |
| AC 写 "正常工作" / "符合预期" | 不可验证 → code-reviewer / qa-engineer 没法逐条核 |
| Body 大段无结构 | 后续被分派的 dev 找不到关键信息 |
| 不标 priority | 看板按 priority 排序 / 触发不了 P0 通知机制 |
| 既不标 type 也不标 area | 责任田不清 → 没人接 |
| Mock / fake 描述 | v1.6+ 禁 mock 描述，issue 必须真实场景 |

## Related skills

- `agf-writing-prd` — issue 通常源于 PRD AC，反向链回 PRD 路径
- `agf-writing-adr` — 涉及架构变更时先开 ADR，再开 issue 引用
- `agf-running-sit-tests`（dev-owned SIT）/ `agf-writing-qa-report`（E2E/UAT 报告，SIT 不在范围内） — QA 与 dev SIT 路径上下文
