#!/usr/bin/env bash
# agf-matrix.sh — PL 在 Multi-instance Worker Pool 模式下聚合 N 份报告为 1 张表
#
# 合并 progress-matrix.sh / review-matrix.sh / qa-matrix.sh 为单一入口。
# 参考: ADR-001 + .claude/standards/workflow.md §Multi-instance Worker Pool
#
# 用法:
#   bash .claude/scripts/agf-matrix.sh --type=progress [--role=<role>]
#   bash .claude/scripts/agf-matrix.sh --type=review --feature=<slug>
#   bash .claude/scripts/agf-matrix.sh --type=qa --feature=<slug>
#
# 解析策略:
#   - progress: 扫 progress/*.md，提 5 段格式的 `**字段**:` 标记
#   - review:   扫 docs/reviews/<feature>-*.md，解析 YAML frontmatter（结构化 verdict + 计数）
#   - qa:       扫 docs/qa/<feature>-*.md，解析 YAML frontmatter（stage / verdict / pass^2 计数）
#
# YAML frontmatter 解析: 简易 awk 实现，不需 yq 依赖（bash 3.2 + POSIX awk 兼容 macOS）

set -uo pipefail

TYPE=""
FEATURE=""
FILTER_ROLE=""

# === 参数解析 ===
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type=*) TYPE="${1#*=}"; shift ;;
    --type) TYPE="$2"; shift 2 ;;
    --feature=*) FEATURE="${1#*=}"; shift ;;
    --feature) FEATURE="$2"; shift 2 ;;
    --role=*) FILTER_ROLE="${1#*=}"; shift ;;
    --role) FILTER_ROLE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$TYPE" ]]; then
  echo "Usage: $0 --type=progress|review|qa [--feature=<slug>] [--role=<role>]" >&2
  exit 1
fi

# === 通用工具 ===
# 从 YAML frontmatter 提单值（仅支持顶层简单字段，不解析嵌套 / 数组）
# bash 3.2 + POSIX awk 兼容；不依赖 yq
extract_frontmatter_field() {
  local file="$1"
  local field="$2"
  awk -v field="$field" '
    BEGIN { in_fm=0 }
    NR==1 && /^---$/ { in_fm=1; next }
    in_fm && /^---$/ { exit }
    in_fm {
      # 用 split 拆 "field: value"
      idx = index($0, ":")
      if (idx == 0) next
      key = substr($0, 1, idx-1)
      # trim 前后空白
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
      if (key != field) next
      v = substr($0, idx+1)
      # 去尾部注释（# 之后）
      sub(/[[:space:]]+#.*$/, "", v)
      # trim 前后空白
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      # 去外层引号（双 / 单）
      sub(/^"/, "", v); sub(/"$/, "", v)
      sub(/^'\''/, "", v); sub(/'\''$/, "", v)
      print v
      exit
    }
  ' "$file" 2>/dev/null
}

# 列文件（bash 3.2 兼容；按字典序）
list_files() {
  local pattern="$1"
  local exclude="$2"
  FILES=()
  local dir
  dir=$(dirname "$pattern")
  local base
  base=$(basename "$pattern")
  while IFS= read -r f; do
    if [[ -n "$exclude" ]]; then
      [[ "$f" =~ $exclude ]] && continue
    fi
    FILES+=("$f")
  done < <(find "$dir" -maxdepth 1 -type f -name "$base" -print 2>/dev/null | sort)
}

# === Progress matrix ===
matrix_progress() {
  list_files "progress/*.md" "README\\.md"
  if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "（progress/ 暂无 task 条目）"; return 0
  fi

  echo "| Instance | 状态 | Skills | 质量门 | 下一步 |"
  echo "|---|---|---|---|---|"

  local FILE INSTANCE LAST_LINE BLOCK STATUS SKILLS GATE NEXT
  for FILE in "${FILES[@]}"; do
    INSTANCE=$(basename "$FILE" .md)
    if [[ -n "$FILTER_ROLE" ]]; then
      [[ "$INSTANCE" == "$FILTER_ROLE" || "$INSTANCE" =~ ^${FILTER_ROLE}-[0-9]+$ ]] || continue
    fi

    LAST_LINE=$(grep -n '^## ' "$FILE" 2>/dev/null | tail -1 | cut -d: -f1)
    if [[ -z "$LAST_LINE" ]]; then
      echo "| $INSTANCE | （无条目）| - | - | - |"; continue
    fi
    BLOCK=$(tail -n +"$LAST_LINE" "$FILE")

    STATUS=$(printf '%s' "$BLOCK" | grep -m1 '^\*\*状态\*\*' | sed -E 's/.*状态\*\*[:：][[:space:]]*(.+)$/\1/' || echo "-")
    SKILLS=$(printf '%s' "$BLOCK" | grep -m1 '^\*\*Skills\*\*' | sed -E 's/.*Skills\*\*[:：][[:space:]]*(.+)$/\1/' | cut -c1-50 || echo "-")
    GATE=$(printf '%s' "$BLOCK" | grep -m1 '^\*\*质量门\*\*' | sed -E 's/.*质量门\*\*[:：][[:space:]]*(.+)$/\1/' | cut -c1-60 || echo "-")
    NEXT=$(printf '%s' "$BLOCK" | grep -m1 '^\*\*下一步\*\*' | sed -E 's/.*下一步\*\*[:：][[:space:]]*(.+)$/\1/' | cut -c1-40 || echo "-")

    STATUS="${STATUS:--}"; SKILLS="${SKILLS:--}"; GATE="${GATE:--}"; NEXT="${NEXT:--}"
    echo "| $INSTANCE | ${STATUS//|/\\|} | ${SKILLS//|/\\|} | ${GATE//|/\\|} | ${NEXT//|/\\|} |"
  done
}

# === Review matrix（解析 frontmatter）===
matrix_review() {
  if [[ -z "$FEATURE" ]]; then
    echo "需要 --feature=<slug>" >&2; return 1
  fi
  list_files "docs/reviews/${FEATURE}-*.md" "_TEMPLATE|retro-"
  if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "（docs/reviews/${FEATURE}-*.md 暂无 review 报告）"; return 0
  fi

  echo "| Reviewer 实例 | 代码 Verdict | SIT Audit | Critical | Warning | 报告路径 |"
  echo "|---|---|---|---|---|---|"

  local FILE REVIEWER CODE_VERDICT SIT_VERDICT CRIT WARN
  for FILE in "${FILES[@]}"; do
    REVIEWER=$(extract_frontmatter_field "$FILE" "reviewer")
    CODE_VERDICT=$(extract_frontmatter_field "$FILE" "code_verdict")
    SIT_VERDICT=$(extract_frontmatter_field "$FILE" "sit_audit_verdict")
    CRIT=$(extract_frontmatter_field "$FILE" "critical_count")
    WARN=$(extract_frontmatter_field "$FILE" "warning_count")

    REVIEWER="${REVIEWER:-code-reviewer}"
    CODE_VERDICT="${CODE_VERDICT:--}"
    SIT_VERDICT="${SIT_VERDICT:--}"
    CRIT="${CRIT:-0}"
    WARN="${WARN:-0}"

    echo "| $REVIEWER | ${CODE_VERDICT//|/\\|} | ${SIT_VERDICT//|/\\|} | $CRIT | $WARN | $FILE |"
  done
}

# === QA matrix（解析 frontmatter）===
matrix_qa() {
  if [[ -z "$FEATURE" ]]; then
    echo "需要 --feature=<slug>" >&2; return 1
  fi
  list_files "docs/qa/${FEATURE}-*.md" "_TEMPLATE|process-log"
  if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "（docs/qa/${FEATURE}-*.md 暂无 E2E/UAT 报告）"; return 0
  fi

  echo "| QA 实例 | 阶段 | 报告级 Verdict | UAT 业务签字 | pass^2 (P0) | 报告路径 |"
  echo "|---|---|---|---|---|---|"

  local FILE TESTER STAGE REPORT_V UAT_SIGN P0_TOTAL P0_OK PASS2
  for FILE in "${FILES[@]}"; do
    TESTER=$(extract_frontmatter_field "$FILE" "tester")
    STAGE=$(extract_frontmatter_field "$FILE" "stage")
    REPORT_V=$(extract_frontmatter_field "$FILE" "report_verdict")
    UAT_SIGN=$(extract_frontmatter_field "$FILE" "uat_signoff_verdict")
    P0_TOTAL=$(extract_frontmatter_field "$FILE" "p0_pass2_total")
    P0_OK=$(extract_frontmatter_field "$FILE" "p0_pass2_ok")

    TESTER="${TESTER:-qa-engineer}"
    STAGE="${STAGE:--}"
    REPORT_V="${REPORT_V:--}"
    UAT_SIGN="${UAT_SIGN:-N/A}"
    if [[ -n "${P0_TOTAL:-}" && "$P0_TOTAL" != "0" ]]; then
      PASS2="${P0_OK:-0}/${P0_TOTAL}"
    else
      PASS2="-"
    fi

    echo "| $TESTER | $STAGE | ${REPORT_V//|/\\|} | ${UAT_SIGN//|/\\|} | $PASS2 | $FILE |"
  done
}

# === 主分发 ===
case "$TYPE" in
  progress) matrix_progress ;;
  review)   matrix_review ;;
  qa)       matrix_qa ;;
  *) echo "Unknown --type=$TYPE (need: progress|review|qa)" >&2; exit 1 ;;
esac
