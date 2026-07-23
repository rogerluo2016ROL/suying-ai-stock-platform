#!/usr/bin/env bash
# test-gen-roles.sh — 回归测试 gen-roles.py 生成器核心
#
# 跑法：bash .claude/hooks/tests/test-gen-roles.sh
# 退出码：0 = 全部通过；1 = 至少一个 case 不符合预期
#
# 由 lint-all.sh / init-team.sh 自动发现并执行。
#
# 覆盖 spec §10 五项（docs/superpowers/specs/2026-06-15-agent-capability-yaml-ssot-design.md）：
#   1. write-path identity：committed roles.yaml 渲染 == committed .md/两表（--check 零 diff）
#   2. --check 抓篡改：改一处 frontmatter 后 --check 必 exit 1 且 diff 指向该文件
#   3. schema 拒非法：缺字段 / 非法 model / review-only 带 Edit 各自 exit 1
#   4. marker 缺失：删 marker 后生成器 exit 1
#   5. 两表渲染 + 镜像 --check 自洽（fixture 上闭环）
#
# 设计约束：对仓库真实文件**只读**。所有变异 case 在 mktemp 临时镜像里跑，
# 通过环境/参数把 gen-roles 的路径常量指向临时目录，绝不污染工作树。

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
GEN="$REPO_ROOT/.claude/scripts/gen-roles.py"
AGENTS_DIR="$REPO_ROOT/.claude/agents"
TEAM_ROLES_MD="$REPO_ROOT/.claude/standards/team-roles.md"

PASS=0
FAIL=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== gen-roles.py test ==="

# 前置：pyyaml 可用 + 脚本存在
if ! python3 -c "import yaml" 2>/dev/null; then
  echo "  ⚠️  跳过：环境无 PyYAML"; exit 0
fi
if [[ ! -f "$GEN" ]]; then
  bad "gen-roles.py 不存在"; echo "❌ 1 失败"; exit 1
fi

# ─────────────────────────────────────────────────────────────────────────
# §10.1 write-path identity：committed roles.yaml 渲染 == committed .md/两表（只读 --check）
# （extract→render round-trip 已随一次性迁移代码删除；roles.yaml 现为唯一 SSOT，
#  正确的不变量是"渲染 roles.yaml 逐字节复现 committed 产物"，即 --check。）
# ─────────────────────────────────────────────────────────────────────────
if python3 "$GEN" --check >/dev/null 2>&1; then
  ok "真实仓库 --check 一致（committed roles.yaml ↔ .md/两表 零 diff）"
else
  bad "真实仓库 --check 不一致（应 exit 0）"
fi

# ─────────────────────────────────────────────────────────────────────────
# 构造临时镜像（含 roles.yaml + 真实 .md + 带 marker 的 team-roles.md）
# 用于 --check / marker / 篡改 case。镜像 roles.yaml 复制 committed SSOT 保证自洽。
# ─────────────────────────────────────────────────────────────────────────
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/.claude/agents" "$TMP/.claude/scripts" "$TMP/.claude/standards"
cp "$GEN" "$TMP/.claude/scripts/gen-roles.py"
cp "$AGENTS_DIR"/*.md "$TMP/.claude/agents/" 2>/dev/null

# 镜像 roles.yaml = 直接复制 committed SSOT（extract 一次性迁移已删，roles.yaml 是唯一来源）
cp "$AGENTS_DIR/roles.yaml" "$TMP/.claude/agents/roles.yaml"
if [[ ! -s "$TMP/.claude/agents/roles.yaml" ]]; then
  bad "镜像 roles.yaml 未就位"
else
  ok "镜像 roles.yaml 就位（复制 committed SSOT）"
fi

# 造一个带 marker 的 team-roles.md（用生成器自渲两表填入），保证镜像 --check 自洽
python3 - "$TMP" <<'PY'
import importlib.util, os, sys
tmp = sys.argv[1]
gen = os.path.join(tmp, ".claude/scripts/gen-roles.py")
spec = importlib.util.spec_from_file_location("genroles", gen)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
data = g.load_roles_yaml(os.path.join(tmp, ".claude/agents/roles.yaml"))
trt = g.render_team_roles_table(data)
att = g.render_agent_tools_table(data)
md = (
    "# Team Roles (fixture)\n\n"
    "## Team Roles\n\n"
    "<!-- BEGIN GENERATED:team-roles-table -->\n\n" + trt + "\n\n"
    "<!-- END GENERATED:team-roles-table -->\n\n"
    "### Agent Tools\n\n"
    "<!-- BEGIN GENERATED:agent-tools-table -->\n\n" + att + "\n\n"
    "<!-- END GENERATED:agent-tools-table -->\n"
)
open(os.path.join(tmp, ".claude/standards/team-roles.md"), "w", encoding="utf-8").write(md)
PY

run_check() {
  # 在镜像里跑 gen-roles.py --check（脚本自带相对路径，cwd 无关，靠脚本位置定位仓库根）
  python3 "$TMP/.claude/scripts/gen-roles.py" --check >/dev/null 2>&1
}

# ─────────────────────────────────────────────────────────────────────────
# §10.5 闭环：镜像 roles.yaml(复制) + 回填两表 → --check 应一致（exit 0）
# ─────────────────────────────────────────────────────────────────────────
if run_check; then
  ok "干净镜像 --check 一致（exit 0）"
else
  bad "干净镜像 --check 不一致（应 exit 0）"
fi

# ─────────────────────────────────────────────────────────────────────────
# §10.2 --check 抓篡改：改某 .md frontmatter 一处 → exit 1 且 diff 指向该文件
# ─────────────────────────────────────────────────────────────────────────
VICTIM="$TMP/.claude/agents/backend-dev.md"
python3 - "$VICTIM" <<'PY'
import sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
# 篡改 color: green → blue（frontmatter 内，body 不动）
t = t.replace("color: green", "color: blue", 1)
open(p, "w", encoding="utf-8").write(t)
PY
CHECK_OUT=$(python3 "$TMP/.claude/scripts/gen-roles.py" --check 2>&1)
CHECK_RC=$?
if [[ $CHECK_RC -eq 1 ]]; then
  ok "篡改 frontmatter 后 --check exit 1"
else
  bad "篡改后 --check 应 exit 1（实际 $CHECK_RC）"
fi
if echo "$CHECK_OUT" | grep -q "backend-dev.md"; then
  ok "--check diff 指向被篡改文件 backend-dev.md"
else
  bad "--check diff 未指向 backend-dev.md"
fi
# 还原 victim 供后续 case
cp "$AGENTS_DIR/backend-dev.md" "$VICTIM"

# ─────────────────────────────────────────────────────────────────────────
# §10.3 schema 拒非法：缺字段 / 非法 model / review-only 带 Edit
# 直接构造内存 roles.yaml dict 喂 validate_schema（check_file_set=False 隔离文件集合校验）
# ─────────────────────────────────────────────────────────────────────────
schema_case() {
  local name="$1" mutator="$2"
  local rc
  rc=$(python3 - "$TMP" "$mutator" <<'PY'
import importlib.util, os, sys, copy
tmp, mut = sys.argv[1], sys.argv[2]
gen = os.path.join(tmp, ".claude/scripts/gen-roles.py")
spec = importlib.util.spec_from_file_location("genroles", gen)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
data = g.load_roles_yaml(os.path.join(tmp, ".claude/agents/roles.yaml"))
a = data["agents"][0]
if mut == "missing":
    del a["focus"]
elif mut == "bad_model":
    a["model"] = "gpt4"
elif mut == "review_edit":
    a["boundary"] = {"kind": "review-only", "write_scope": "docs/reviews/"}
    if "Edit" not in a["tools"]:
        a["tools"].append("Edit")
elif mut == "bad_color":
    a["color"] = "slate"
elif mut == "bad_extra":
    a["extra"] = [["bogusField", "x"]]
try:
    g.validate_schema(data, check_file_set=False)
    print("0")  # 未拒 = bug
except g.SchemaError:
    print("1")  # 正确拒绝
PY
)
  if [[ "$rc" == "1" ]]; then ok "schema 拒绝：$name"; else bad "schema 未拒绝：$name"; fi
}
schema_case "缺必填字段(focus)" "missing"
schema_case "非法 model(gpt4)" "bad_model"
schema_case "review-only 带 Edit" "review_edit"
schema_case "非法 color(slate)" "bad_color"
schema_case "extra 非官方字段" "bad_extra"

# 反向：合法 dict 应通过（check_file_set=False）
LEGAL_RC=$(python3 - "$TMP" <<'PY'
import importlib.util, os, sys
tmp = sys.argv[1]
gen = os.path.join(tmp, ".claude/scripts/gen-roles.py")
spec = importlib.util.spec_from_file_location("genroles", gen)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
data = g.load_roles_yaml(os.path.join(tmp, ".claude/agents/roles.yaml"))
try:
    g.validate_schema(data, check_file_set=False); print("0")
except g.SchemaError: print("1")
PY
)
if [[ "$LEGAL_RC" == "0" ]]; then ok "schema 放行合法 roles.yaml"; else bad "schema 误杀合法 roles.yaml"; fi

# ─────────────────────────────────────────────────────────────────────────
# §10.4 marker 缺失：删掉一个 marker → --check exit 1
# ─────────────────────────────────────────────────────────────────────────
TR="$TMP/.claude/standards/team-roles.md"
python3 - "$TR" <<'PY'
import sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
t = t.replace("<!-- END GENERATED:agent-tools-table -->", "", 1)
open(p, "w", encoding="utf-8").write(t)
PY
if python3 "$TMP/.claude/scripts/gen-roles.py" --check >/dev/null 2>&1; then
  bad "marker 缺失时 --check 仍 exit 0（应 exit 1）"
else
  ok "marker 缺失时 --check exit 1"
fi

echo
# 注意：汇总行刻意不带 ✅ —— lint-all.sh 用 `grep -c '✅'` 数用例，带 ✅ 会把
# 汇总行自身也算进去（off-by-one）。不带 ✅ 时 grep 计数 == 真实 ok 数（$PASS）。
if [[ $FAIL -eq 0 ]]; then
  echo "=> 全部 $PASS 个用例通过"
  exit 0
else
  echo "=> $FAIL 个用例失败 / $PASS 个通过"
  exit 1
fi
