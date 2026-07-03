#!/usr/bin/env bash
# agf-spec-validate.sh — 行为规格 / delta 机器校验（advisory，ADR-012）
#
# 对活规格（docs/specs/<cap>/spec.md）或 delta（docs/changes/<change>/specs/<cap>.md）检查：
#   ① 每个 ### Requirement: 下至少 1 个 #### Scenario:（REMOVED/RENAMED 段豁免）
#   ② Requirement 正文含规范性语言 MUST/SHALL（REMOVED/RENAMED 豁免；advisory）
#   ③ Scenario 必须恰好 4 个 #（### / ##### / 等错级别 flag）
#   ③b 每个 #### Scenario 正文含 WHEN + THEN（否则不可测，advisory）
#   ④ delta 段头合法（^## (ADDED|MODIFIED|REMOVED|RENAMED) Requirements$）且段非空
#   ⑤ REMOVED Requirement 含 **Reason** + **Migration**；RENAMED 含 FROM:/TO:
#   ⑥ Requirement 正文疑似模糊词（快速/高效/scalable… 无量化；借鉴 GitHub Spec Kit /analyze 的 ambiguity 检测，advisory）
#
# **advisory，不阻断**：格式 flag 一律 exit 0（与 agf-sit-precheck.sh 同 fail-open 取向）；
# 仅用法 / 文件不存在 exit 1。reviewer / PL 看 flag 自行裁决，本脚本不替代判断。
#
# 用法: bash .claude/scripts/agf-spec-validate.sh <spec-or-delta.md> [更多文件...]
# 格式权威: docs/specs/README.md + ADR-012 决策 1/2。

set -uo pipefail

if [[ $# -lt 1 ]]; then
  echo "用法: agf-spec-validate.sh <spec-or-delta.md> [...]" >&2
  exit 1
fi

rc=0
for FILE in "$@"; do
  if [[ ! -f "$FILE" ]]; then
    echo "✗ 文件不存在: $FILE" >&2
    rc=1
    continue
  fi
  awk -v fname="$FILE" '
  function flush_req() {
    finalize_scen()
    if (req_line > 0) {
      if (section != "REMOVED" && section != "RENAMED") {
        if (scen == 0) {
          printf("⚠️  [SPEC] %s:L%d Requirement 无 #### Scenario: %s\n", fname, req_line, req_name) > "/dev/stderr"; flags++
        }
        if (req_norm == 0) {
          printf("⚠️  [SPEC] %s:L%d Requirement 正文缺 MUST/SHALL（规范性语言）: %s\n", fname, req_line, req_name) > "/dev/stderr"; flags++
        }
      }
      if (section == "REMOVED" && (reason == 0 || migration == 0)) {
        printf("⚠️  [SPEC] %s:L%d REMOVED Requirement 缺 **Reason**/**Migration**: %s\n", fname, req_line, req_name) > "/dev/stderr"; flags++
      }
      if (section != "REMOVED" && section != "RENAMED" && amb == 1) {
        printf("⚠️  [SPEC] %s:L%d Requirement 含疑似模糊词「%s」（建议量化 / 明确，如「快」→具体阈值）: %s\n", fname, amb_line, amb_word, req_name) > "/dev/stderr"; flags++
      }
    }
    req_line = 0; req_name = ""; scen = 0; req_norm = 0; reason = 0; migration = 0; amb = 0; amb_word = ""
  }
  function close_section() {
    if (is_delta && section != "") {
      if (section == "RENAMED") {
        if (ren_from == 0 || ren_to == 0) {
          printf("⚠️  [SPEC] %s:L%d RENAMED 段缺 FROM:/TO:\n", fname, sec_line) > "/dev/stderr"; flags++
        }
      } else if (sec_count == 0) {
        printf("⚠️  [SPEC] %s:L%d %s Requirements 段为空\n", fname, sec_line, section) > "/dev/stderr"; flags++
      }
    }
    sec_count = 0; ren_from = 0; ren_to = 0
  }
  function finalize_scen() {
    if (scen_open && (scen_when == 0 || scen_then == 0)) {
      printf("⚠️  [SPEC] %s:L%d Scenario 正文缺 WHEN/THEN（不可测）: %s\n", fname, scen_line, scen_name) > "/dev/stderr"; flags++
    }
    scen_open = 0; scen_when = 0; scen_then = 0
  }
  /^##[[:space:]]+(ADDED|MODIFIED|REMOVED|RENAMED)[[:space:]]+Requirements[[:space:]]*$/ {
    flush_req(); close_section()
    is_delta = 1
    match($0, /(ADDED|MODIFIED|REMOVED|RENAMED)/)
    section = substr($0, RSTART, RLENGTH)
    sec_line = NR
    next
  }
  /^##[[:space:]]/ { flush_req(); close_section(); section = ""; next }
  /^###[[:space:]]+Requirement:/ {
    flush_req()
    req_line = NR; req_name = $0
    sub(/^###[[:space:]]+Requirement:[[:space:]]*/, "", req_name)
    sec_count++
    next
  }
  /^####[[:space:]]+Scenario:/ {
    finalize_scen()
    if (req_line > 0) scen++
    scen_open = 1; scen_line = NR; scen_name = $0
    sub(/^####[[:space:]]+Scenario:[[:space:]]*/, "", scen_name)
    next
  }
  /Scenario:/ {
    if ($0 ~ /^#{1,3}[[:space:]]+Scenario:/ || $0 ~ /^#{5,}[[:space:]]+Scenario:/) {
      printf("⚠️  [SPEC] %s:L%d Scenario 必须恰好 4 个 #（#### Scenario:）: %s\n", fname, NR, $0) > "/dev/stderr"; flags++
    }
  }
  {
    if (req_line > 0) {
      if ($0 ~ /MUST|SHALL/) req_norm = 1
      if ($0 ~ /\*\*Reason\*\*/) reason = 1
      if ($0 ~ /\*\*Migration\*\*/) migration = 1
      if (amb == 0 && $0 !~ /^#/ && match($0, /快速|快捷|迅速|高效|流畅|无缝|友好|易用|简洁|灵活|健壮|稳定|可靠|直观|良好|海量|尽快|及时|fast|quickly|scalable|seamless|intuitive|performant|robust|user-friendly/)) {
        amb = 1; amb_line = NR; amb_word = substr($0, RSTART, RLENGTH)
      }
    }
    if (scen_open) {
      if ($0 ~ /WHEN/) scen_when = 1
      if ($0 ~ /THEN/) scen_then = 1
    }
    if (section == "RENAMED") {
      if ($0 ~ /FROM:/) ren_from = 1
      if ($0 ~ /TO:/) ren_to = 1
    }
  }
  END {
    flush_req(); close_section()
    if (flags == 0) printf("✅ [SPEC] %s 格式合法\n", fname)
    else printf("— %s: %d 个 flag（advisory 非阻断）\n", fname, flags) > "/dev/stderr"
  }
  ' "$FILE"
done

exit "$rc"
