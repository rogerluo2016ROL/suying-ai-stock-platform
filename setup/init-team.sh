#!/usr/bin/env bash
# init-team.sh — verify and prepare AppGenesisForge AI team scaffold
#
# 用法：bash setup/init-team.sh（在项目根运行；脚本自身会 cd 到项目根，任意 cwd 调用均可）
# 行为：自动验证 + 列出人工步骤；幂等可重复跑。
# 退出码：硬性失败时 1，否则 0（警告不退出）。

set -uo pipefail

# 本脚本位于 setup/，内部用相对路径（.claude/ 等）→ 先 cd 到项目根，无论从哪调用都对
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

# 颜色（仅当 stdout 是 terminal 时启用）
if [[ -t 1 ]]; then
  R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; B=$'\033[0;34m'; N=$'\033[0m'
else
  R= G= Y= B= N=
fi

PASS=0; WARN=0; FAIL=0
ok()   { echo "${G}✅${N} $1"; PASS=$((PASS+1)); }
warn() { echo "${Y}⚠️ ${N} $1"; WARN=$((WARN+1)); }
fail() { echo "${R}❌${N} $1"; FAIL=$((FAIL+1)); }
info() { echo "${B}→${N} $1"; }

echo "=== AppGenesisForge Project Init ==="
echo

# 1. Claude Code 版本
info "Checking Claude Code..."
if command -v claude >/dev/null 2>&1; then
  CC_VER=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)
  if [[ -n "${CC_VER:-}" ]]; then
    LOWEST=$(printf '%s\n2.1.154\n' "$CC_VER" | sort -V | head -1)
    if [[ "$LOWEST" == "2.1.154" ]]; then
      ok "claude v$CC_VER (≥ v2.1.154)"
    else
      warn "claude v$CC_VER 低于 v2.1.154 — Agent Team 实验功能不可用，subagent 路径仍可用"
    fi
  else
    warn "claude --version 输出无法解析"
  fi
else
  fail "claude CLI 未安装。安装：https://claude.com/claude-code"
fi

# 2. Hook 可执行 + 回归测试
info "Verifying hooks..."
HOOK_DIR=".claude/hooks"
if [[ -d "$HOOK_DIR" ]]; then
  # 自动 chmod（幂等安全）
  chmod +x "$HOOK_DIR"/*.sh "$HOOK_DIR"/tests/*.sh 2>/dev/null || true

  # glob 遍历全部单测（曾因硬编码清单漏跑 test-secret-pattern-parity.sh，新增测试无需改这里）
  for TEST in "$HOOK_DIR"/tests/test-*.sh; do
    if [[ -f "$TEST" ]]; then
      if bash "$TEST" >/dev/null 2>&1; then
        ok "${TEST#"$HOOK_DIR"/} 通过"
      else
        fail "${TEST#"$HOOK_DIR"/} 失败 — 跑 \`bash $TEST\` 看详情"
      fi
    else
      warn "$HOOK_DIR/tests/ 下无 test-*.sh 单测"
    fi
  done
else
  fail "$HOOK_DIR 目录不存在"
fi

# 3. settings.json 合法性
info "Validating .claude/settings.json..."
if [[ -f ".claude/settings.json" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    if python3 -c "import json; json.load(open('.claude/settings.json'))" 2>/dev/null; then
      ok ".claude/settings.json 是合法 JSON"
    else
      fail ".claude/settings.json JSON 解析失败"
    fi
  else
    warn "python3 未安装，跳过 JSON 合法性校验"
  fi
else
  fail ".claude/settings.json 不存在"
fi

# 3b. git pre-commit hook（scan-commit 防 secret 通过 Edit/Write 落盘）
info "Checking git pre-commit hook (scan-commit)..."
if [[ -d ".git" ]]; then
  if [[ -e ".git/hooks/pre-commit" ]]; then
    if [[ -L ".git/hooks/pre-commit" ]] && [[ "$(readlink .git/hooks/pre-commit)" == *"scan-commit.sh" ]]; then
      ok "scan-commit pre-commit hook 已安装"
    else
      warn ".git/hooks/pre-commit 已存在但非 scan-commit.sh — 手动合并或：rm .git/hooks/pre-commit && ln -sf ../../.claude/hooks/scan-commit.sh .git/hooks/pre-commit"
    fi
  else
    if [[ -f ".claude/hooks/scan-commit.sh" ]]; then
      ln -sf "../../.claude/hooks/scan-commit.sh" ".git/hooks/pre-commit" && ok "已自动安装 scan-commit pre-commit hook" || warn "scan-commit hook 安装失败 — 手动跑：ln -sf ../../.claude/hooks/scan-commit.sh .git/hooks/pre-commit"
    else
      warn ".claude/hooks/scan-commit.sh 不存在 — 跳过 pre-commit 安装"
    fi
  fi
fi

# 3d. evals 静态校验
info "Validating evals/*.jsonl..."
if [[ -f "evals/run.sh" ]]; then
  chmod +x evals/run.sh 2>/dev/null || true
  if bash evals/run.sh validate >/dev/null 2>&1; then
    ok "evals/*.jsonl 全部合法"
  else
    warn "evals/*.jsonl 有问题 — 跑 \`bash evals/run.sh validate\` 看详情"
  fi
fi

# 4. CLAUDE.md
info "Checking CLAUDE.md..."
if [[ -f "CLAUDE.md" ]]; then
  ok "CLAUDE.md 存在"
else
  if [[ -f "CLAUDE.example.md" ]]; then
    warn "CLAUDE.md 未创建 — 跑 \`cp CLAUDE.example.md CLAUDE.md\` 后改内容"
  else
    fail "CLAUDE.md 和 CLAUDE.example.md 都不存在 — 模板可能复制不完整"
  fi
fi

# 5. ADR-000
info "Checking ADR-000..."
ADR000="docs/adr/000-system-architecture.md"
if [[ -f "$ADR000" ]]; then
  if head -10 "$ADR000" | grep -q "AppGenesisForge" 2>/dev/null; then
    if [[ -t 0 && -t 1 ]]; then
      echo "${Y}⚠️ ${N} $ADR000 还是模板示例。请选择处理方式（详见 docs/FIRST_RUN.md §4）："
      echo "  [A] 让 tech-lead 起新版（新项目推荐）"
      echo "  [B] 让 tech-lead 基于现有代码识别基线（接手老代码库）"
      echo "  [C] 直接删除该文件（首个 feature 启动时让 tech-lead 按需补）"
      echo "  [S] 跳过（保持原状，下次再处理 — 默认）"
      printf "选择 [A/B/C/S]: "
      read -r ADR_CHOICE
      ADR_CHOICE_UP=$(printf '%s' "${ADR_CHOICE:-S}" | tr '[:lower:]' '[:upper:]')
      case "$ADR_CHOICE_UP" in
        A)
          echo "  → 启动 Claude Code 后，把这条粘进对话："
          echo "    ${B}请启动 tech-lead，为本项目起 ADR-000 固化技术栈${N}"
          warn "ADR-000 仍是模板（已选 A 方案，待人工触发 tech-lead）"
          ;;
        B)
          echo "  → 启动 Claude Code 后，把这条粘进对话："
          echo "    ${B}请启动 tech-lead，本项目已有代码：1) 扫描仓库识别实际技术栈 2) 输出 ADR-000 固化「现状基线」而非「理想选型」 3) 同步更新 CLAUDE.md 的 Tech Stack 表${N}"
          warn "ADR-000 仍是模板（已选 B 方案，待人工触发 tech-lead）"
          ;;
        C)
          printf "  ${R}确认删除 $ADR000 ?${N} [y/N]: "
          read -r ADR_CONFIRM
          if [[ "$(printf '%s' "${ADR_CONFIRM:-N}" | tr '[:upper:]' '[:lower:]')" == "y" ]]; then
            if rm -f "$ADR000"; then
              ok "已删除 $ADR000（首个 feature 启动时由 tech-lead 按需补）"
            else
              fail "删除 $ADR000 失败"
            fi
          else
            warn "ADR-000 仍是模板（取消删除）"
          fi
          ;;
        *)
          warn "ADR-000 仍是模板（已跳过，下次再处理 — docs/FIRST_RUN.md §4）"
          ;;
      esac
    else
      warn "$ADR000 还是模板示例 — docs/FIRST_RUN.md §4 三选一（新写 / 改写 / 删除）"
    fi
  else
    ok "$ADR000 已定制"
  fi
else
  warn "$ADR000 不存在 — 首个 feature 启动时让 tech-lead 起草"
fi

# 6. Git
info "Checking git..."
if [[ -d ".git" ]]; then
  ok "git 仓库已初始化"
else
  warn "git 仓库未初始化 — 跑 \`git init && git add . && git commit -m 'initial'\`"
fi

# 7. permissions 白名单提醒（无法自动校验，只提示）
info "Permissions allowlist..."
warn ".claude/settings.json permissions.allow 需手动核对是否匹配项目实际命令"

# 总结
echo
echo "=== Summary ==="
echo "${G}通过${N}: $PASS  ${Y}警告${N}: $WARN  ${R}失败${N}: $FAIL"
echo

if [[ $FAIL -gt 0 ]]; then
  echo "${R}有 $FAIL 处硬性失败，先修这些再继续。${N}"
  exit 1
fi

if [[ $WARN -gt 0 ]]; then
  echo "${Y}有 $WARN 处人工步骤待处理。${N}详见 docs/FIRST_RUN.md。"
  echo
fi

echo "${B}Next:${N} 跑 \`/agf-team-start <你的第一个 feature>\` 启动团队"
exit 0
