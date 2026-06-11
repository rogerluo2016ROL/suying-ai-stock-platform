# Body 模板 + gh CLI heredoc 模板 + 完整例子

> 从 `SKILL.md` 下沉的完整参考。**拼 body / 写 `gh issue create` 命令前必读本文**，按模板替换 `<...>`。
> Examples 段含具体项目（RolexOps）实例（image tag、cookie name、目录路径），保留以提高参考价值；使用时按你项目的实际值替换。

## Body 模板

`gh issue create --body-file -` 喂下面模板（替换 `<...>`）：

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

**正确做法（HEREDOC，避免 shell escape 出错）**

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
