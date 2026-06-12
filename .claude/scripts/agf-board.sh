#!/usr/bin/env bash
# agf-board.sh — AGF 实时开发看板（task 卡片 → 自包含 HTML，浏览器 open 即用）
#
# 用法:
#   bash .claude/scripts/agf-board.sh                          # 一次性生成（最近活跃 team）
#   bash .claude/scripts/agf-board.sh <team> --feature <slug>  # 指定 team + 阶段门(按 feature 扫 docs)
#   bash .claude/scripts/agf-board.sh --watch                  # 循环重生成(默认 3s)，配合页面自刷新≈实时
#   bash .claude/scripts/agf-board.sh --watch --interval 5
#   bash .claude/scripts/agf-board.sh --out /tmp/board.html
#
# 数据源（全部现成，零新状态）:
#   ~/.claude/tasks/<team>/*.json   task 卡片（id/subject/status/activeForm/blockedBy；无 owner 字段，
#                                   角色从 description 匹配 15 角色名 best-effort 提取）
#   docs/reviews|deploy|qa/<feature>-*  阶段门 chips（frontmatter / gate 行，--feature 时启用）
# 输出: progress/board.html（默认；已 gitignore，运行时产物不入库）
# 实时机制: file:// 下 fetch 受 CORS 限制 → 不起 server，--watch 循环重生成 + 页面 <meta refresh>
# 依赖: jq；bash 3.2 兼容（无 mapfile / declare -A）

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TASKS_BASE="${AGF_TASKS_DIR:-$HOME/.claude/tasks}"          # 测试/演示可覆盖
TEAMS_BASE="${AGF_TEAMS_DIR:-$HOME/.claude/teams}"          # 成员栏数据源（team config.json）
DOCS_ROOT="${AGF_BOARD_DOCS_ROOT:-$ROOT}"                   # 阶段门扫描根（测试可覆盖）

TEAM=""; TEAM_EXPLICIT=0; FEATURE=""; WATCH=0; INTERVAL=3; OUT="$ROOT/progress/board.html"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --feature)  FEATURE="${2:-}"; shift 2 ;;
    --watch)    WATCH=1; shift ;;
    --interval) INTERVAL="${2:-3}"; shift 2 ;;
    --out)      OUT="${2:-$OUT}"; shift 2 ;;
    -h|--help)  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)          TEAM="$1"; TEAM_EXPLICIT=1; shift ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "error: 需要 jq（brew install jq）" >&2; exit 1; }

# 默认 team = 最近修改的 task 目录（不跳过空目录：新 team 总是先建目录、后派单，
# 宁可显示"等待派单"的诚实空板，也不回退到陈旧 team）；watch 每轮重解析，
# 且连续 2 轮指向同一新 team 才切换（防目录 mtime 抖动来回横跳）；显式传 team 则固定不切
PENDING_TEAM=""
resolve_team() {
  [[ "$TEAM_EXPLICIT" -eq 1 ]] && return 0
  local d cand=""
  for d in $(ls -t "$TASKS_BASE" 2>/dev/null); do
    [[ -d "$TASKS_BASE/$d" ]] && { cand="$d"; break; }
  done
  if [[ -z "$cand" || "$cand" == "$TEAM" ]]; then PENDING_TEAM=""; return 0; fi
  if [[ -z "$TEAM" || "$cand" == "$PENDING_TEAM" ]]; then  # 首轮直选；其后需连续两轮确认
    [[ -n "$TEAM" ]] && echo "board: team 切换 → $cand" >&2
    TEAM="$cand"; PENDING_TEAM=""
  else
    PENDING_TEAM="$cand"
  fi
  return 0
}

resolve_team
TASK_DIR="$TASKS_BASE/$TEAM"
[[ -d "$TASK_DIR" ]] || { echo "error: 无 task 目录: $TASK_DIR" >&2; exit 1; }

# watch 单实例：同一输出文件只允许一个 watch，后启动者接管（自动停掉旧进程，
# 防多个 watch 互相覆盖 board.html 导致页面闪烁/内容横跳）
PIDFILE="$OUT.pid"
if [[ "$WATCH" -eq 1 ]]; then
  mkdir -p "$(dirname "$OUT")"
  if [[ -f "$PIDFILE" ]]; then
    OLDPID="$(cat "$PIDFILE" 2>/dev/null)"
    if [[ -n "$OLDPID" ]] && ps -p "$OLDPID" -o command= 2>/dev/null | grep -q 'agf-board'; then
      kill "$OLDPID" 2>/dev/null && echo "board: 接管 watch（已停掉旧进程 ${OLDPID}）" >&2
    fi
  fi
  echo $$ > "$PIDFILE"
fi

html_escape() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
attr_escape() { html_escape | sed 's/"/\&quot;/g'; }   # 用于 HTML 属性值（title tooltip）

# 15 角色 → 品牌色（与 team-capability-map 一致）；未匹配 → 灰
role_color() {
  case "$1" in
    product-lead) echo "#f97316" ;;  tech-lead) echo "#3b82f6" ;;
    uiux-designer) echo "#a855f7" ;; frontend-dev) echo "#06b6d4" ;;
    backend-dev) echo "#22c55e" ;;   ai-agent-dev) echo "#ec4899" ;;
    ml-engineer) echo "#84cc16" ;;   miniapp-dev) echo "#14b8a6" ;;
    code-reviewer) echo "#eab308" ;; miniapp-code-reviewer) echo "#f59e0b" ;;
    qa-engineer) echo "#ef4444" ;;   miniapp-qa-engineer) echo "#f43f5e" ;;
    deploy-engineer) echo "#64748b" ;; content-writer) echo "#a78bfa" ;;
    growth-analyst) echo "#6366f1" ;; *) echo "#8b949e" ;;
  esac
}

detect_role() {  # $1=description → 首个命中的角色名（保留 -N 实例号显示；配色按 base）
  printf '%s' "$1" | grep -oE '(product-lead|tech-lead|uiux-designer|frontend-dev|backend-dev|ai-agent-dev|ml-engineer|miniapp-dev|miniapp-code-reviewer|miniapp-qa-engineer|code-reviewer|qa-engineer|deploy-engineer|content-writer|growth-analyst)(-[0-9]+)?' | head -1
}
role_base() { printf '%s' "$1" | sed 's/-[0-9]*$//'; }

card_age() {  # $1=task json 文件 → 相对时间（文件 mtime 即该卡最后一次状态更新）
  local m now d
  m="$(stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null)" || { echo ""; return 0; }
  now="$(date +%s)"; d=$(( now - m ))
  if   (( d < 60 ));    then echo "刚刚"
  elif (( d < 3600 ));  then echo "$((d/60)) 分钟前"
  elif (( d < 86400 )); then echo "$((d/3600)) 小时前"
  else                       echo "$((d/86400)) 天前"; fi
}

# ---- 成员栏（读 team config.json；solo session 无 config 则整栏隐藏）----
build_members() {  # 入参经全局 DOING_MAP（"id|role_base" 行）关联"谁在干哪张卡"
  MEMBERS_HTML=""
  local conf="$TEAMS_BASE/$TEAM/config.json"
  [[ -f "$conf" ]] || return 0
  local name atype state hint color dot cls cur curid
  while IFS='|' read -r name atype state hint; do
    [[ -z "$name" ]] && continue
    color="$(role_color "$(role_base "$atype")")"
    curid=""
    if [[ "$state" == "lead" ]]; then dot="◆"; cls="on"
    elif [[ "$state" == "true" ]]; then
      dot="●"; cls="on"
      curid="$(printf '%s\n' "$DOING_MAP" | awk -F'|' -v r="$atype" '$2==r{print $1; exit}')"
    else dot="○"; cls="off"; fi
    if [[ -n "$curid" ]]; then
      cur=" <em>→ #${curid}</em>"                       # 有进行中的卡 → 卡号是当下事实
    elif [[ "$cls" == "on" && "$state" == "true" && -n "$hint" ]]; then
      # 工作中但无卡片（review / 临时指派等不走 task 的工作）→ 退而显示 spawn prompt 摘要
      cur=" <em class=\"hint\" title=\"初始任务: $(printf '%s' "$hint" | attr_escape)\">· $(printf '%s' "$hint" | cut -c1-42 | html_escape)…</em>"
    else cur=""; fi
    MEMBERS_HTML="$MEMBERS_HTML<span class=\"mem $cls\"><i style=\"background:$color\"></i>$dot $name$cur</span>"
  done < <(jq -r '.leadAgentId as $l | .members[] | "\(.name)|\(.agentType // "?")|\(if .agentId == $l then "lead" else ((.isActive // false) | tostring) end)|\(.prompt // "" | gsub("[\n\r|]"; " ") | .[0:160])"' "$conf" 2>/dev/null)
  return 0
}

# ---- 阶段门 chips（--feature 时启用；全部 best-effort，缺文件显示 —）----
gate_chip() {  # $1=label $2=state(ok|run|bad|none)
  local cls="none" icon="—"
  case "$2" in ok) cls="ok"; icon="✓" ;; run) cls="run"; icon="●" ;; bad) cls="bad"; icon="✗" ;; esac
  printf '<span class="gate %s">%s %s</span>' "$cls" "$icon" "$1"
}
fm_val() { sed -n '/^---$/,/^---$/p' "$1" 2>/dev/null | grep "^$2:" | head -1 | sed "s/^$2:[[:space:]]*//; s/[\"']//g"; }
latest_doc() { ls -t $1 2>/dev/null | grep -v '_TEMPLATE' | head -1; }

build_gates() {
  local impl="run" cr="none" dep="none" e2e="none" uat="none"
  [[ "$N_TOTAL" -gt 0 && "$N_DONE" -eq "$N_TOTAL" ]] && impl="ok"
  if [[ -n "$FEATURE" ]]; then
    local f v s
    f="$(latest_doc "$DOCS_ROOT/docs/reviews/${FEATURE}*-20*.md")"
    if [[ -n "$f" ]]; then
      v="$(fm_val "$f" code_verdict)"; s="$(fm_val "$f" sit_audit_verdict)"
      case "$v" in approve*) cr="ok" ;; block) cr="bad" ;; *) cr="run" ;; esac
      [[ "$s" == *Redo* ]] && cr="bad"
    fi
    f="$(latest_doc "$DOCS_ROOT/docs/deploy/${FEATURE}-uat-*.md")"
    if [[ -n "$f" ]]; then
      grep -q '✅ 部署成功' "$f" 2>/dev/null && dep="ok" || dep="bad"
    fi
    f="$(latest_doc "$DOCS_ROOT/docs/qa/${FEATURE}-e2e*-20*.md")"
    if [[ -n "$f" ]]; then
      v="$(fm_val "$f" report_verdict)"
      case "$v" in Promote*) e2e="ok" ;; Block*) e2e="bad" ;; *) e2e="run" ;; esac
    fi
    f="$(latest_doc "$DOCS_ROOT/docs/qa/${FEATURE}-uat*-20*.md")"
    if [[ -n "$f" ]]; then
      v="$(fm_val "$f" uat_signoff_verdict)"
      case "$v" in approve) uat="ok" ;; "request changes") uat="bad" ;; *) uat="run" ;; esac
    fi
  fi
  GATES_HTML="$(gate_chip 实现 "$impl")$(gate_chip 'Code Review' "$cr")$(gate_chip 'UAT 部署' "$dep")$(gate_chip E2E "$e2e")$(gate_chip UAT "$uat")"
}

# ---- 生成一次 ----
generate() {
  resolve_team; TASK_DIR="$TASKS_BASE/$TEAM"
  local PEND="" DOING="" DONE_C="" f id status subject desc active blocked role color summary chips age
  N_TOTAL=0; N_DONE=0; N_DOING=0; N_PEND=0; DOING_MAP=""

  local names
  names="$(ls "$TASK_DIR" 2>/dev/null | grep '\.json$' | sort -n)"
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    f="$TASK_DIR/$name"
    id="$(jq -r '.id // ""' "$f")"
    status="$(jq -r '.status // "pending"' "$f")"
    subject="$(jq -r '.subject // (.description | split("\n")[0]) // ""' "$f" | html_escape)"
    desc="$(jq -r '.description // ""' "$f")"
    active="$(jq -r '.activeForm // ""' "$f" | html_escape)"
    blocked="$(jq -r '.blockedBy // [] | join(" ")' "$f")"
    role="$(detect_role "$desc $subject $active")"
    color="$(role_color "$(role_base "$role")")"
    [[ -z "$role" ]] && role="unassigned"
    age="$(card_age "$f")"
    [[ "$status" == "in_progress" && "$role" != "unassigned" ]] && DOING_MAP="$DOING_MAP$id|$(role_base "$role")
"
    summary="$(printf '%s' "$desc" | sed -n '2,3p' | tr '\n' ' ' | cut -c1-140 | html_escape)"

    chips=""
    if [[ -n "$blocked" ]]; then
      local b; for b in $blocked; do chips="$chips<span class=\"chip blk\">⛓ #$b</span>"; done
    fi

    N_TOTAL=$((N_TOTAL+1))
    local card="<div class=\"card s-$status\" style=\"border-left-color:$color\">
  <div class=\"row\"><span class=\"tid\">#$id${age:+ <span class=\"age\">· $age</span>}</span><span class=\"role\" style=\"color:$color\">●&nbsp;$role</span></div>
  <div class=\"subj\">$subject</div>"
    [[ "$status" == "in_progress" && -n "$active" ]] && card="$card
  <div class=\"act\">⟳ $active</div>"
    [[ -n "$summary" ]] && card="$card
  <div class=\"sum\">$summary</div>"
    [[ -n "$chips" ]] && card="$card
  <div class=\"chips\">$chips</div>"
    card="$card
</div>"

    case "$status" in
      completed)   N_DONE=$((N_DONE+1));  DONE_C="$DONE_C$card" ;;
      in_progress) N_DOING=$((N_DOING+1)); DOING="$DOING$card" ;;
      *)           N_PEND=$((N_PEND+1));  PEND="$PEND$card" ;;
    esac
  done <<< "$names"

  build_gates
  build_members
  local META="" TS
  TS="$(date '+%H:%M:%S')"
  [[ "$WATCH" -eq 1 ]] && META="<meta http-equiv=\"refresh\" content=\"$INTERVAL\">"

  mkdir -p "$(dirname "$OUT")"
  local TMP="$OUT.tmp.$$"
  cat > "$TMP" <<EOF
<!doctype html><html lang="zh"><head><meta charset="utf-8">$META
<title>AGF Board · $TEAM</title>
<style>
 :root{color-scheme:dark}
 body{background:#0d1117;color:#e6edf3;font:14px/1.5 -apple-system,"PingFang SC",sans-serif;margin:0;padding:24px}
 header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:6px}
 h1{font-size:18px;margin:0}.dim{color:#8b949e;font-size:12px}
 .gates{margin:10px 0 18px;display:flex;gap:8px;flex-wrap:wrap}
 .gate{font-size:12px;padding:3px 10px;border-radius:99px;border:1px solid #30363d;color:#8b949e}
 .gate.ok{color:#3fb950;border-color:#238636;background:#12261e}
 .gate.run{color:#58a6ff;border-color:#1f6feb;background:#0d1d33}
 .gate.bad{color:#f85149;border-color:#da3633;background:#2d1214}
 .cols{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;align-items:start}
 .col{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px}
 .col h2{font-size:13px;margin:0 0 10px;color:#8b949e;display:flex;justify-content:space-between}
 .col h2 b{color:#e6edf3}
 .card{background:#0d1117;border:1px solid #30363d;border-left:3px solid #8b949e;border-radius:8px;padding:10px 12px;margin-bottom:10px}
 .card.s-completed{opacity:.62}
 .card.s-completed .subj::before{content:"✓ ";color:#3fb950}
 .card.s-in_progress{border-color:#1f6feb40;box-shadow:0 0 0 1px #1f6feb33}
 .row{display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px}
 .tid{color:#8b949e}.role{font-weight:600}
 .subj{font-weight:600;font-size:13.5px}
 .act{color:#58a6ff;font-size:12px;margin-top:4px}
 .sum{color:#8b949e;font-size:12px;margin-top:4px}
 .chips{margin-top:6px}.chip{font-size:11px;border:1px solid #30363d;border-radius:99px;padding:1px 8px;color:#d29922;margin-right:4px}
 .empty{color:#484f58;font-size:12px;text-align:center;padding:14px 0}
 .age{color:#6e7681;font-weight:400}
 .team{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}
 .mem{font-size:12px;border:1px solid #30363d;border-radius:99px;padding:3px 11px;display:inline-flex;align-items:center;gap:6px;color:#e6edf3}
 .mem i{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none}
 .mem.on{border-color:#23863666;background:#12261e55}
 .mem.off{color:#8b949e;opacity:.65}
 .mem em{font-style:normal;color:#58a6ff;font-weight:600}
 .mem em.hint{color:#8b949e;font-weight:400;cursor:help}
</style></head><body>
<header><h1>AGF Board</h1><span class="dim">team: $TEAM${FEATURE:+ · feature: $FEATURE}</span>
<span class="dim">$N_DONE/$N_TOTAL 完成$( [[ "$N_TOTAL" -eq 0 ]] && printf ' · ⏳ 等待派单（team 暂无 task，创建后自动上板）' ) · 更新 $TS$( [[ "$WATCH" -eq 1 ]] && printf ' · 自动刷新 %ss' "$INTERVAL" )</span></header>
<div class="gates">$GATES_HTML</div>
${MEMBERS_HTML:+<div class=\"team\">$MEMBERS_HTML</div>}
<div class="cols">
 <div class="col"><h2>⏸ Pending <b>$N_PEND</b></h2>${PEND:-<div class=\"empty\">（空）</div>}</div>
 <div class="col"><h2>🔄 In Progress <b>$N_DOING</b></h2>${DOING:-<div class=\"empty\">（空）</div>}</div>
 <div class="col"><h2>✅ Completed <b>$N_DONE</b></h2>${DONE_C:-<div class=\"empty\">（空）</div>}</div>
</div></body></html>
EOF
  mv "$TMP" "$OUT"
}

generate
echo "看板已生成: $OUT"
echo "打开:  open '$OUT'"

if [[ "$WATCH" -eq 1 ]]; then
  echo "watch 模式: 每 ${INTERVAL}s 重生成（Ctrl-C 停止）"
  # 退出时只清理仍归属自己的 pidfile（接管场景下新 watch 已改写它，不能误删）
  trap '[[ "$(cat "$PIDFILE" 2>/dev/null)" == "$$" ]] && rm -f "$PIDFILE"; echo; echo "看板 watch 已停止"; exit 0' INT TERM
  while :; do
    sleep "$INTERVAL"
    generate
  done
fi
