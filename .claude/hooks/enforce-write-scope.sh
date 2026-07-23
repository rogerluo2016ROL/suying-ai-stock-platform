#!/usr/bin/env bash
# .claude/hooks/enforce-write-scope.sh
#
# PreToolUse(Edit|Write) —— 按 roles.yaml boundary.write_scope 拦截角色越界写。
# 补 A-F1（评审 P0）：AGF 自称"机制兜底而非 agent 自觉"，但 boundary.write_scope
# 原无运行时门（code-reviewer 可越界写源码无 hook 拦）。本 hook 用 PreToolUse payload
# 的 agent_type（仅 subagent/--agent 场景含，主线程不含）查 roles.yaml 的 write_scope。
#
# 行为：
#   - 主线程（无 agent_type）→ 放行（PL 编排者，全路径可写）
#   - 角色 无 boundary.write_scope（dev 等无边界角色）→ 放行
#   - file_path 在 write_scope 下 → 放行
#   - 越界 → exit 2
# fail-open：无 jq / 无 python3 / 无 roles.yaml / yaml 解析失败 → 放行（AGF 哲学一致）
#
# 进 AGF_HOOK_IMMUTABLE（不可降级）。依据 ADR-018（待开）。
# agent_type 字段依据：code.claude.com/docs/en/hooks（Common input fields，
# "When running with --agent or inside a subagent" 段）。

set -uo pipefail

INPUT="$(cat || true)"

command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# role（多路径防御，镜像 validate-verdict.sh:50-52）：Agent Teams teammate 形态可能填
# .teammate.name 而非 .agent_type；单取 .agent_type 会把 scoped-role teammate 误判为
# 主线程全放行 → 写边界在 team mode 形同虚设（C3）。6 字段取首个非空。
AGENT_TYPE=$(printf '%s' "$INPUT" | jq -r '
  [.agent_type, .subagent_type, .teammate.name, .agent.name, .name, .role]
  | map(select(. != null and . != "")) | .[0] // ""' 2>/dev/null)
FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

# 无 file_path（非 Edit/Write）→ 放行
[ -z "$FILE_PATH" ] && exit 0

# 主线程（无 agent_type）→ 放行（PL 编排者全路径可写）
[ -z "$AGENT_TYPE" ] && exit 0

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROLES_YAML="$HOOK_DIR/../agents/roles.yaml"
[ -f "$ROLES_YAML" ] || exit 0

# 查该角色 boundary.write_scope（python3 + PyYAML；fail-open）。
# Pool 实例名 <type>-<N>（ADR-001 fan-out 默认形态，如 code-reviewer-2）精确名查不到时
# 剥 -N 后缀重查——否则实例名 fail-open 放行，写边界在 Pool 模式整体失效；
# 先精确后剥离，防误伤真名恰含 -<数字> 的角色（镜像 validate-verdict.sh 剥后缀语义）。
WRITE_SCOPE=$(AGENT_TYPE="$AGENT_TYPE" ROLES_YAML="$ROLES_YAML" python3 -c '
import os, re, yaml
try:
    data = yaml.safe_load(open(os.environ["ROLES_YAML"]))
    agents = {a.get("name"): a for a in data.get("agents") or []}
    name = os.environ["AGENT_TYPE"]
    a = agents.get(name)
    if a is None:
        m = re.match(r"^(.+)-(\d+)$", name)
        if m:
            a = agents.get(m.group(1))
    if a is not None:
        print((a.get("boundary") or {}).get("write_scope") or "")
except Exception:
    pass
' 2>/dev/null)

# 无 write_scope（dev / 未知角色等无边界）→ 放行
[ -z "$WRITE_SCOPE" ] && exit 0

# 规范化 file_path 到「相对项目根的真实路径」——解析 .. 与 symlink（堵 C1 越界：
# docs/reviews/../../backend/x 原命中 docs/reviews/ 前缀放行；规范化后变 backend/x 被拦）。
# os.path.realpath 解析 .. + 现存组件 symlink，不要求路径已存在（Write 创建前）；fail-open。
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
REL="$(PROJECT_DIR="$PROJECT_DIR" FILE_PATH="$FILE_PATH" python3 -c '
import os
proj = os.path.realpath(os.environ["PROJECT_DIR"])
fp = os.environ["FILE_PATH"]
target = fp if os.path.isabs(fp) else os.path.join(proj, fp)
real = os.path.realpath(target)  # 解 .. + symlink
try:
    rel = os.path.relpath(real, proj)
except ValueError:
    rel = "__outside__"  # 不同盘符 → 视越界
if rel == ".." or rel.startswith(".." + os.sep):
    rel = "__outside__"  # realpath 落在项目根之外
print(rel)
' 2>/dev/null)"
[ -z "$REL" ] && exit 0  # python3 异常 → fail-open（与 yaml fail-open 一致）

# 规范化后逃出项目根 → 越界 block
case "$REL" in
  __outside__*)
    cat >&2 <<EOF
❌ [enforce-write-scope] 路径逃出项目根（规范化后拦截）
角色: ${AGENT_TYPE}（boundary.write_scope = ${WRITE_SCOPE}）
文件: $FILE_PATH → 规范化 $REL
EOF
    exit 2 ;;
esac

# 查规范化后 REL 是否在 write_scope 下（前缀匹配）
case "$REL" in
  "$WRITE_SCOPE"*) exit 0 ;;   # 在 write_scope 下 → 放行
  *)
    cat >&2 <<EOF
❌ [enforce-write-scope] 角色越界写被阻断

角色: ${AGENT_TYPE}（boundary.write_scope = ${WRITE_SCOPE}）
越界文件: $FILE_PATH → 规范化 $REL

该角色只能写 $WRITE_SCOPE 下（roles.yaml boundary + ADR-018）。
写源码/其他路径由 product-lead 重派给对应执行层角色，不绕 boundary。
EOF
    exit 2
    ;;
esac
