#!/usr/bin/env bash
# test-agf-spec-archive.sh — 回归测试 agf-spec-archive.py（ADR-012 决策 3 + v6.9.0 评审加固）
# 跑法：bash .claude/hooks/tests/test-agf-spec-archive.sh
# 退出码：0 = 全过；1 = 至少一个 case 不符。由 lint-all.sh / init-team.sh 自动发现执行。

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PY="$REPO_ROOT/.claude/scripts/agf-spec-archive.py"
VALIDATE="$REPO_ROOT/.claude/scripts/agf-spec-validate.sh"

PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
have()    { grep -qF "$2" "$1" && ok "$3" || bad "$3 (缺: $2)"; }
havent()  { grep -qF "$2" "$1" && bad "$3 (不应有: $2)" || ok "$3"; }
# arc <args...> → 设全局 RC（exit code），吞输出
arc() { python3 "$PY" "$@" --specs-root "$TMP/specs" --changes-root "$TMP/changes" >/dev/null 2>&1; RC=$?; }

setup_dark() {
  rm -rf "$TMP/specs" "$TMP/changes"
  mkdir -p "$TMP/specs/theming" "$TMP/changes/dark/specs"
  cat > "$TMP/specs/theming/spec.md" <<'EOF'
# Spec: theming

## Purpose

主题与会话。

## Requirements

### Requirement: 默认浅色主题

The system MUST 默认使用浅色主题.

#### Scenario: 首次启动
- WHEN 用户首次打开
- THEN 显示浅色主题

### Requirement: 会话超时

The system MUST 在 30 分钟无操作后过期会话.

#### Scenario: 超时
- WHEN 30 分钟无操作
- THEN 会话过期

### Requirement: 记住我

The system MUST 提供记住我选项.

#### Scenario: 勾选
- WHEN 勾选记住我
- THEN 保持登录
EOF
  cat > "$TMP/changes/dark/specs/theming.md" <<'EOF'
# Delta: theming

## ADDED Requirements

### Requirement: 深色主题

The system MUST 支持深色主题切换.

#### Scenario: 切换
- WHEN 用户在设置切换深色
- THEN 立即应用深色主题

## MODIFIED Requirements

### Requirement: 会话超时

The system MUST 在 15 分钟无操作后过期会话.

#### Scenario: 超时
- WHEN 15 分钟无操作
- THEN 会话过期

## REMOVED Requirements

### Requirement: 记住我

**Reason**: 改用偏好持久化
**Migration**: 迁移到 settings

## RENAMED Requirements

- FROM: `### Requirement: 默认浅色主题`
- TO: `### Requirement: 默认主题`
EOF
}

echo "=== agf-spec-archive.py test ==="

# Case A: 完整 merge（clean，无 warning）+ 归档移动
setup_dark
arc dark 2026-06-26
[[ "$RC" -eq 0 ]] && ok "clean merge 退出 0" || bad "clean merge exit=$RC"
SPEC="$TMP/specs/theming/spec.md"
have   "$SPEC" "### Requirement: 默认主题"      "RENAMED: 默认浅色主题→默认主题"
havent "$SPEC" "### Requirement: 默认浅色主题"  "RENAMED: 旧 header 已消失"
have   "$SPEC" "15 分钟"                         "MODIFIED: 会话超时 改 15 分钟"
havent "$SPEC" "30 分钟"                         "MODIFIED: 旧 30 分钟 已消失"
havent "$SPEC" "### Requirement: 记住我"        "REMOVED: 记住我 已删"
have   "$SPEC" "### Requirement: 深色主题"      "ADDED: 深色主题 已加"
[[ -f "$TMP/changes/archive/2026-06-26-dark/specs/theming.md" ]] && ok "change 已移 archive" || bad "归档目录缺失"
[[ ! -d "$TMP/changes/dark" ]] && ok "原 change 已移走" || bad "原 change 仍在"
bash "$VALIDATE" "$SPEC" >/dev/null 2>&1 && grep -qF "MUST" "$SPEC" && ok "merge 产物 validate 仍合法" || bad "merge 产物 validate 失败"

# Case B: --dry-run 不改活规格、不移动
setup_dark
BEFORE="$(cat "$TMP/specs/theming/spec.md")"
arc dark 2026-06-26 --dry-run
[[ "$RC" -eq 0 ]] && ok "dry-run 退出 0" || bad "dry-run exit=$RC"
[[ "$BEFORE" == "$(cat "$TMP/specs/theming/spec.md")" ]] && ok "dry-run 不改活规格" || bad "dry-run 改了活规格"
[[ -d "$TMP/changes/dark" ]] && ok "dry-run 不移动 change" || bad "dry-run 移动了 change"

# Case C: 新能力（活规格不存在）→ 创建
rm -rf "$TMP/specs" "$TMP/changes"; mkdir -p "$TMP/specs" "$TMP/changes/feat/specs"
cat > "$TMP/changes/feat/specs/newcap.md" <<'EOF'
# Delta: newcap
## ADDED Requirements
### Requirement: 全新能力
The system MUST 提供全新能力.
#### Scenario: 用
- WHEN 触发
- THEN 生效
EOF
arc feat 2026-06-26
[[ "$RC" -eq 0 ]] && ok "新能力 merge 退出 0" || bad "新能力 exit=$RC"
NEW="$TMP/specs/newcap/spec.md"
have "$NEW" "### Requirement: 全新能力" "新能力含 ADDED requirement"
have "$NEW" "# Spec: newcap"           "新能力含标准 header"

# Case D: 用法错误
arc dark 2026/06/26;   [[ "$RC" -ne 0 ]] && ok "坏日期非零退出" || bad "坏日期未拦"
arc nonexist 2026-06-26; [[ "$RC" -ne 0 ]] && ok "不存在 change 非零退出" || bad "不存在 change 未拦"

# === 负向 / 加固用例（v6.9.0 评审 #6/#7/#8/#14）===

# N1: 活规格 Requirement 间夹 ## 小节 → MODIFIED 后者必须命中（不退化为 ADDED），## 小节保留
rm -rf "$TMP/specs" "$TMP/changes"; mkdir -p "$TMP/specs/inter" "$TMP/changes/m/specs"
cat > "$TMP/specs/inter/spec.md" <<'EOF'
# Spec: inter

## Requirements

### Requirement: A
The system MUST 行为甲.
#### Scenario: sa
- WHEN x
- THEN y

## Notes

保留我这段说明。

### Requirement: B
The system MUST 行为乙原始.
#### Scenario: sb
- WHEN x
- THEN y
EOF
cat > "$TMP/changes/m/specs/inter.md" <<'EOF'
# Delta: inter
## MODIFIED Requirements
### Requirement: B
The system MUST 行为乙改后.
#### Scenario: sb
- WHEN x2
- THEN y2
EOF
arc m 2026-06-26
[[ "$RC" -eq 0 ]] && ok "N1 交错小节 MODIFIED clean 退出 0" || bad "N1 exit=$RC（footer 吞并→警告门控？）"
IS="$TMP/specs/inter/spec.md"
have   "$IS" "行为乙改后"  "N1 MODIFIED B 命中改写"
havent "$IS" "行为乙原始"  "N1 旧 B 已替换"
have   "$IS" "保留我这段说明" "N1 中间 ## Notes 保留"
have   "$IS" "行为甲"       "N1 A 未受损"
[[ "$(grep -c '### Requirement: B' "$IS")" -eq 1 ]] && ok "N1 B 未被重复（无 ADDED 退化）" || bad "N1 B 重复了"

# N2: 活规格重名 Requirement → 任何触及它的 delta 触发 warning → 门控 exit 2（无 --force）
rm -rf "$TMP/specs" "$TMP/changes"; mkdir -p "$TMP/specs/dup" "$TMP/changes/c/specs"
cat > "$TMP/specs/dup/spec.md" <<'EOF'
# Spec: dup
## Requirements
### Requirement: 重名
The system MUST 甲.
#### Scenario: s1
- WHEN x
- THEN y
### Requirement: 重名
The system MUST 乙.
#### Scenario: s2
- WHEN x
- THEN y
EOF
cat > "$TMP/changes/c/specs/dup.md" <<'EOF'
# Delta: dup
## MODIFIED Requirements
### Requirement: 重名
The system MUST 丙.
#### Scenario: s3
- WHEN x
- THEN y
EOF
arc c 2026-06-26
[[ "$RC" -eq 2 ]] && ok "N2 重名触发 pre-flight 门控 exit 2" || bad "N2 exit=$RC（应 2）"
[[ -d "$TMP/changes/c" ]] && ok "N2 门控未归档（change 仍在）" || bad "N2 门控却归档了"
arc c 2026-06-26 --force
[[ "$RC" -eq 0 ]] && ok "N2 --force 放行 exit 0" || bad "N2 --force exit=$RC"

# N3: RENAMED 的 TO 含反斜杠 → 不崩溃、字面保留（旧 re.sub 模板注入会崩/劈裂）
rm -rf "$TMP/specs" "$TMP/changes"; mkdir -p "$TMP/specs/esc" "$TMP/changes/r/specs"
cat > "$TMP/specs/esc/spec.md" <<'EOF'
# Spec: esc
## Requirements
### Requirement: 旧名
The system MUST x.
#### Scenario: s
- WHEN x
- THEN y
EOF
cat > "$TMP/changes/r/specs/esc.md" <<'EOF'
# Delta: esc
## RENAMED Requirements
- FROM: `### Requirement: 旧名`
- TO: `### Requirement: 新名\npath`
EOF
arc r 2026-06-26
[[ "$RC" -eq 0 ]] && ok "N3 特殊字符 RENAMED 不崩溃 exit 0" || bad "N3 exit=$RC（re.sub 模板注入？）"
have "$TMP/specs/esc/spec.md" '### Requirement: 新名\npath' "N3 反斜杠字面保留、未被解释成换行"

# N4: REMOVED 不存在名 → warning → 门控 exit 2 不改不移；--force 放行
rm -rf "$TMP/specs" "$TMP/changes"; mkdir -p "$TMP/specs/g" "$TMP/changes/g/specs"
cat > "$TMP/specs/g/spec.md" <<'EOF'
# Spec: g
## Requirements
### Requirement: 存在
The system MUST x.
#### Scenario: s
- WHEN x
- THEN y
EOF
cat > "$TMP/changes/g/specs/g.md" <<'EOF'
# Delta: g
## REMOVED Requirements
### Requirement: 不存在
**Reason**: r
**Migration**: m
EOF
SNAP="$(cat "$TMP/specs/g/spec.md")"
arc g 2026-06-26
[[ "$RC" -eq 2 ]] && ok "N4 不存在名 REMOVED 门控 exit 2" || bad "N4 exit=$RC（应 2）"
[[ "$SNAP" == "$(cat "$TMP/specs/g/spec.md")" ]] && ok "N4 门控未改活规格" || bad "N4 门控却改了活规格"
[[ -d "$TMP/changes/g" ]] && ok "N4 门控未归档" || bad "N4 门控却归档了"
arc g 2026-06-26 --force
[[ "$RC" -eq 0 ]] && ok "N4 --force 放行 exit 0" || bad "N4 --force exit=$RC"

# N5: 多 capability（2 个 delta 文件）→ 都 merge
rm -rf "$TMP/specs" "$TMP/changes"; mkdir -p "$TMP/specs" "$TMP/changes/multi/specs"
for c in capx capy; do
cat > "$TMP/changes/multi/specs/$c.md" <<EOF
# Delta: $c
## ADDED Requirements
### Requirement: $c 行为
The system MUST 做 $c.
#### Scenario: s
- WHEN x
- THEN y
EOF
done
arc multi 2026-06-26
[[ "$RC" -eq 0 ]] && ok "N5 多 capability 退出 0" || bad "N5 exit=$RC"
[[ -f "$TMP/specs/capx/spec.md" && -f "$TMP/specs/capy/spec.md" ]] && ok "N5 两 capability 活规格都创建" || bad "N5 漏 capability"

echo
if [[ $FAIL -eq 0 ]]; then
  echo "=> 全部 $PASS 个用例通过"
  exit 0
else
  echo "=> $FAIL 个用例失败 / $PASS 个通过"
  exit 1
fi
