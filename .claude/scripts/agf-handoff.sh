#!/usr/bin/env bash
# agf-handoff.sh —— 给 Codex / opencode 等外部工具交接执行层。
# 做三件确定性的事：① 建隔离 worktree（分支 feat/<change>）；② 本地忽略 AGENTS.md
# （per-handoff 产物，永不进版本库）；③ 把 tasks.md 的 AC↔Scenario 表 stamp 进 worktree
# 根的 AGENTS.md（含只读 SSOT / DoD 指针 / progress 回填模板 / CLAUDE.md 仅作背景的框定）。
#
# 用法: bash .claude/scripts/agf-handoff.sh <change> [role]
# 治理（规格 / code review / 部署 / E2E / UAT 签字）一步不变，全留 Claude Code。
set -euo pipefail

CHANGE="${1:-}"
ROLE="${2:-backend-dev}"
[ -n "$CHANGE" ] || { echo "用法: agf-handoff.sh <change> [role]" >&2; exit 2; }

git rev-parse --git-dir >/dev/null 2>&1 || { echo "✗ 不在 git 仓库内" >&2; exit 2; }
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

TASKS="docs/changes/${CHANGE}/tasks.md"
[ -f "$TASKS" ] || { echo "✗ 找不到 ${TASKS}（先用 skill agf-writing-change 写变更文件夹四件套）" >&2; exit 2; }

REPO_NAME="$(basename "$REPO_ROOT")"
WT_PATH="../${REPO_NAME}-${CHANGE}"
BRANCH="feat/${CHANGE}"

# ① 隔离 worktree（baseRef=head，与 AGF settings.json 一致）；幂等复用
if [ -d "$WT_PATH" ]; then
  echo "• 复用已存在 worktree：${WT_PATH}"
elif git show-ref --quiet "refs/heads/${BRANCH}"; then
  git worktree add "$WT_PATH" "$BRANCH"
  echo "• 已建 worktree（复用分支 ${BRANCH}）：${WT_PATH}"
else
  git worktree add "$WT_PATH" -b "$BRANCH"
  echo "• 已建 worktree：${WT_PATH}（新分支 ${BRANCH}）"
fi
WT_ABS="$(cd "$WT_PATH" && pwd)"

# ② 本地忽略 AGENTS.md（不改 tracked .gitignore；per-handoff 产物每次重生成、不进版本库）
EXCLUDE="$(git rev-parse --git-common-dir)/info/exclude"
grep -qxF 'AGENTS.md' "$EXCLUDE" 2>/dev/null || echo 'AGENTS.md' >> "$EXCLUDE"

# ③ 抽 AC↔Scenario 表（抽不到则回退指向 tasks.md）
AC_TABLE="$(awk '/^## AC.*Scenario/{f=1;next} /^## /{f=0} f' "$TASKS" | sed '/^[[:space:]]*$/d' || true)"
[ -n "$AC_TABLE" ] || AC_TABLE="（tasks.md 里没解析到 AC↔Scenario 表，直接看 ${TASKS}）"

# 生成 stamped AGENTS.md：引号 heredoc（backtick/$ 全字面），再用 awk 注入占位符
TMP_AC="$(mktemp)"; printf '%s\n' "$AC_TABLE" > "$TMP_AC"
cat > "${WT_ABS}/AGENTS.md" <<'TPL'
# AGENTS.md —— 执行层交接（Codex / opencode 自动加载）

你是本仓库的「执行层」：**只写代码 + 测试**，不碰治理（规格 / 审查 / 部署 / 签字都在 Claude Code 那边）。

> 完整团队流程见仓库根 `CLAUDE.md`——**仅作背景**。里面的角色编排 / hooks / skills / slash 命令 / UAT / 部署 / 签字**都不是你的活，忽略它们**（那是 Claude Code 团队的职责，你也跑不了）。本文件就是你的工单。

## 本次任务：__CHANGE__（角色 __ROLE__）

实现下面这些 AC（逐字 AC / 场景见 `__TASKS__`）：

__AC_TABLE__

## 只读（禁改）

- `docs/specs/<cap>/spec.md`        行为契约 WHEN/THEN（你实现的 cap 见上表）
- `docs/adr/000-system-architecture.md`   技术栈 / 版本约束
- `docs/design/<feature>/spec.md` + `docs/design/DESIGN.md`   设计规范 / token
- OpenAPI 契约                     前后端走生成 client，禁手写 fetch
- 细则：契约 / 设计 token 纪律见 `.claude/standards/coding.md`；SIT / 覆盖见 `.claude/standards/testing.md`

**禁止修改 `docs/specs`、`docs/adr`、`docs/design` 下任何文件。需要改 = 越界，停下回 Claude Code。**

## 完成定义（DoD，缺一不算完成；权威源 `.claude/standards/ac-lifecycle.md`）

- test-first（先写测试再写实现）
- Unit + SIT 全绿；SIT 真连 DB / 外部服务，不全 mock
- 逐条自验 AC，贴真实命令 + 输出（不许只说「已完成」）
- lint + typecheck 全绿；无硬编码密钥
- 前后端走生成的 client / 类型，禁手写 fetch

## 环境 / 密钥

SIT 要真连 DB / 外部服务——env 与密钥由**人**在本 worktree 准备（如 docker compose postgres、`.env`）。**别把密钥写进代码或 commit**（仓库 pre-commit 会扫，但途中其它密钥 hook 在外部工具里不生效）。

## 完成后回填

按下面格式写 `progress/__ROLE__.md`（机器会用 `agf-sit-precheck.sh` 检这个格式），然后 `git commit`（触发仓库 pre-commit 密钥扫描）：

```markdown
**状态**：实现 __CHANGE__ 的 AC，全部完成
**用到的工具/方法**：（外部工具填实际用的；此段不参与 sit-precheck，可留空）
**SIT 证据**
- [x] AC-1 ✅  $ pytest tests/...        → 1 passed
- [x] AC-2 ✅  $ curl -s localhost:8000/... → 200 {...}
**质量门**：lint ✅ / typecheck ✅ / unit ✅ / SIT ✅
**下一步**：交 Claude Code code review（门 1）
```

> 越界、歧义、要改规格 / 架构 → 停下，回 Claude Code 问，别自己猜着改。
TPL

awk -v change="$CHANGE" -v role="$ROLE" -v tasks="$TASKS" -v acfile="$TMP_AC" '
  /__AC_TABLE__/ { while ((getline l < acfile) > 0) print l; close(acfile); next }
  { gsub(/__CHANGE__/, change); gsub(/__ROLE__/, role); gsub(/__TASKS__/, tasks); print }
' "${WT_ABS}/AGENTS.md" > "${WT_ABS}/AGENTS.md.tmp" && mv "${WT_ABS}/AGENTS.md.tmp" "${WT_ABS}/AGENTS.md"
rm -f "$TMP_AC"

echo "• 已生成 stamped AGENTS.md：${WT_ABS}/AGENTS.md"
echo ""
echo "── 出门（人工切到外部工具）─────────────────"
echo "  cd ${WT_PATH} && codex            # 或 opencode；启动即自动读 AGENTS.md"
echo ""
echo "── 回门（work 回来时）──────────────────────"
echo "  git fetch ${WT_PATH} ${BRANCH}"
echo "  git diff --name-only main...${BRANCH} | grep -E 'docs/(specs|adr|design)'   # 应为空，非空=越界打回"
echo "  bash .claude/scripts/agf-sit-precheck.sh progress/${ROLE}.md                 # 强制入口检查"
echo "  → 通过后派 code-reviewer 做 code review + SIT Audit（门 1），再 /agf-deploy-uat、/agf-uat"
echo ""
echo "── 完事清理 ────────────────────────────────"
echo "  git worktree remove ${WT_PATH}    # 合并后清理（分支 ${BRANCH} 视情况保留/删除）"
