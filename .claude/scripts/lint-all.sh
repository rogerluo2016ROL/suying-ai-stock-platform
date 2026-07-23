#!/usr/bin/env bash
# lint-all.sh — 项目级一键 lint 入口
#
# 用途: 跑所有可行的静态校验（不跑测试套，那是 dev 自己的事）：
#   1. Bash 脚本语法（bash -n）
#   2. JSON 文件解析（python3 -m json.tool）
#   3. YAML 文件解析（python3 yaml.safe_load）
#   4. Markdown 文件不强制 lint（项目无 markdownlint 依赖）但检查链接死链（可选 grep）
#
# 用法:
#   bash .claude/scripts/lint-all.sh             # 全跑
#   bash .claude/scripts/lint-all.sh --quick     # 跳过慢检查（暂同 default）
#   bash .claude/scripts/lint-all.sh --pre-commit # 仅检查 git staged 文件
#
# 退出码: 0 = 全过；1 = 任一失败
#
# pre-commit 集成: .git/hooks/pre-commit 串行调用本脚本（在 scan-commit.sh 之后）

set -uo pipefail

PRE_COMMIT_MODE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pre-commit) PRE_COMMIT_MODE=1; shift ;;
    --quick) shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

FAIL=0
PASS_COUNT=0

# run_gate <banner> <script> <fail-label> — 委托一个 gate 脚本：缺文件 → WARN 跳过；
# exit 0 → PASS++（透传 gate stderr）；非 0 → 打 fail-label + FAIL++。gate 自身负责 fail-open。
run_gate() {
  local banner="$1" script="$2" faillabel="$3" err
  echo ""; echo "=== $banner ==="
  if [[ ! -f "$script" ]]; then echo "  ⚠️ 跳过（缺 $script）"; return 0; fi
  err="$(mktemp)"
  if bash "$script" 2>"$err"; then
    cat "$err" >&2 2>/dev/null || true
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  ❌ $faillabel" >&2; cat "$err" >&2
    FAIL=$((FAIL + 1))
  fi
  rm -f "$err"
}

# === 文件列表 ===
if [[ "$PRE_COMMIT_MODE" -eq 1 ]]; then
  # 仅校验 staged 文件
  STAGED=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
  SHELL_FILES=$(echo "$STAGED" | grep -E '\.sh$' || true)
  JSON_FILES=$(echo "$STAGED" | grep -E '\.json$' || true)
  YAML_FILES=$(echo "$STAGED" | grep -E '\.(ya?ml)$' || true)
else
  # Shell: .claude 全深度 + setup/ 安装脚本 + 仓库根 maxdepth 1 的 *.sh（假设 cwd = 仓库根，合并去重）
  SHELL_FILES=$(
    { find .claude -type f -name '*.sh' 2>/dev/null
      find setup -type f -name '*.sh' 2>/dev/null
      find . -maxdepth 1 -type f -name '*.sh' 2>/dev/null
    } | grep -v node_modules | sed 's|^\./||' | sort -u
  )
  # JSON: 单根 . 跑（避免 .claude 和 . 双根重复扫同文件）
  JSON_FILES=$(find . -maxdepth 3 -type f -name '*.json' 2>/dev/null \
    | grep -v node_modules | grep -v '\.pytest_cache' \
    | sed 's|^\./||' | sort -u)
  YAML_FILES=$(find . -maxdepth 3 -type f \( -name '*.yaml' -o -name '*.yml' \) 2>/dev/null \
    | grep -v node_modules | grep -v '\.pytest_cache' \
    | sed 's|^\./||' | sort -u)
fi

# === Bash lint ===
echo "=== Bash 脚本语法 ==="
if [[ -n "${SHELL_FILES:-}" ]]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if bash -n "$f" 2>/dev/null; then
      echo "  ✅ $f"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "  ❌ $f" >&2
      bash -n "$f" 2>&1 | sed 's/^/     /' >&2
      FAIL=$((FAIL + 1))
    fi
  done <<< "$SHELL_FILES"
else
  echo "  （无 .sh 文件）"
fi

# === JSON lint ===
echo ""
echo "=== JSON 解析 ==="
if [[ -n "${JSON_FILES:-}" ]]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if python3 -m json.tool "$f" >/dev/null 2>&1; then
      echo "  ✅ $f"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "  ❌ $f" >&2
      python3 -m json.tool "$f" 2>&1 | sed 's/^/     /' >&2
      FAIL=$((FAIL + 1))
    fi
  done <<< "$JSON_FILES"
else
  echo "  （无 .json 文件）"
fi

# === YAML lint ===
echo ""
echo "=== YAML 解析 ==="
if [[ -n "${YAML_FILES:-}" ]]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" "$f" 2>/dev/null; then
      echo "  ✅ $f"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "  ❌ $f" >&2
      python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" "$f" 2>&1 | sed 's/^/     /' >&2
      FAIL=$((FAIL + 1))
    fi
  done <<< "$YAML_FILES"
else
  echo "  （无 .yaml/.yml 文件）"
fi

# === roles SSOT drift 检查 ===
# 跑 gen-roles.py --check（check-only，绝不改文件 / git add）。drift 时生成器自己
# 打印 spec §8 提示语（"✗ roles drift: <file> 与 roles.yaml 不一致" + 同步 hint），
# 这里只起 banner + 传播 exit。生成器 / roles.yaml 缺失时优雅降级（不崩溃整条 lint）。
echo ""
echo "=== roles SSOT drift 检查 ==="
GEN_ROLES=".claude/scripts/gen-roles.py"
ROLES_YAML=".claude/agents/roles.yaml"
if [[ ! -f "$GEN_ROLES" ]]; then
  echo "  ⚠️ 跳过（缺 ${GEN_ROLES}）"
elif [[ ! -f "$ROLES_YAML" ]]; then
  echo "  ⚠️ 跳过（缺 ${ROLES_YAML}）"
elif ! command -v python3 >/dev/null 2>&1; then
  echo "  ⚠️ 跳过（无 python3）"
else
  if python3 "$GEN_ROLES" --check >/dev/null 2>/tmp/_genroles.err; then
    echo "  ✅ roles 一致（无 drift）"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  ❌ roles drift" >&2
    cat /tmp/_genroles.err >&2
    FAIL=$((FAIL + 1))
  fi
  rm -f /tmp/_genroles.err
fi

# deny-baseline 非回归门：硬阻断 settings.json permissions.deny 被悄悄改小 / baseline 篡改。
# claims-audit 门：CLAUDE.md 治理声称 ↔ 现实（A 幽灵注册 + B 幽灵声称硬阻断，C advisory）。
# 两者 fail-open 由各脚本自负（缺 jq/文件 → 自 exit 0 + WARN）。
run_gate "deny-baseline 非回归门" ".claude/scripts/agf-deny-baseline.sh" "deny-baseline 回归 / 篡改"
run_gate "claims-audit 门" ".claude/scripts/agf-claims-audit.sh" "claims-audit 失败（声称与现实不符）"

# === Hook 测试套（委托 run-all-tests.sh，v6.25.0 去重）===
# 原地内联过一份「find test-*.sh 循环」与 run-all-tests.sh 重复、且执行语义分叉
# （本处非 hermetic，会被 git hook 环境的 GIT_DIR/GIT_WORK_TREE 污染）——统一委托
# hermetic runner，两处只维护一份循环。
if [[ "$PRE_COMMIT_MODE" -eq 0 ]]; then
  echo ""
  echo "=== Hook 测试套（run-all-tests.sh hermetic）==="
  if bash "$(dirname "${BASH_SOURCE[0]}")/run-all-tests.sh" > /tmp/_hooktest.out 2>&1; then
    grep -E '  ✅ ' /tmp/_hooktest.out || true
    SUITE_N=$(grep -cE '  ✅ ' /tmp/_hooktest.out || true)
    PASS_COUNT=$((PASS_COUNT + SUITE_N))
  else
    cat /tmp/_hooktest.out >&2
    FAIL=$((FAIL + 1))
  fi
  rm -f /tmp/_hooktest.out
fi

# === repo-layout SSOT advisory（advisory，不计入 FAIL；防 I8 类型漏列 drift）===
echo ""
echo "=== repo-layout SSOT advisory ==="
bash "$(dirname "${BASH_SOURCE[0]}")/check-repo-layout.sh" || true

# === superpowers-mapping advisory（W1 drift 守门：hook advisory 字面量必须在 superpowers.md）===
echo ""
echo "=== superpowers-mapping advisory ==="
bash "$(dirname "${BASH_SOURCE[0]}")/check-superpowers-mapping.sh" || true

# === 总结 ===
echo ""
echo "─────────"
if [[ "$FAIL" -gt 0 ]]; then
  echo "❌ Lint 失败：$FAIL 个文件 / 测试套未过；$PASS_COUNT 个通过" >&2
  exit 1
else
  echo "✅ Lint 全过：$PASS_COUNT 个文件 / 测试套"
  exit 0
fi
