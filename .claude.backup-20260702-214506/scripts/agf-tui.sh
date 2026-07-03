#!/usr/bin/env bash
# agf-tui.sh — 纯 bash 零依赖 TUI 原语库（被 source，不是入口）
#
# 用途：给 AGF 的交互式脚本（首个消费者 = agf-team-start.sh）提供方向键驱动的
# 终端 UI 原语：多选 / 单选 / 单行输入 / 转圈 spinner。不引入任何外部依赖
# （无 gum / fzf / dialog / whiptail），仅用 ANSI 转义 + `stty` raw 模式。
# 设计权威来源：docs/superpowers/specs/2026-06-09-launcher-tui-design.md（§5/§6）。
#
# 兼容性：bash 3.2（macOS 默认）。本文件禁用 4+ 特性——无 mapfile/readarray、
# 无关联数组（declare -A）、无 ${var^^}/${var,,}、无 &>>。一律索引数组 + tr/printf。
#
# 重要：本库被 `source` 时不执行任何交互；只在被「直接执行」时跑一个自测 demo
# （见文件末尾的 BASH_SOURCE 守卫）。被 source 进开了 `set -u` 的脚本里也安全
# （所有可能未设的全局都用 ${x:-} 兜底）。
#
# ============================================================================
# 函数契约（锁定 —— 消费者照此调用，勿改名改语义）
# ============================================================================
# 全部通过全局变量/数组通信（bash 3.2 不便传数组）。调用方在调用前设入参全局，
# 函数在确认后写出参全局。
#
#   tui_capable
#       无参。可用 TUI 返回 0，否则返回 1。
#       判据：[[ -t 0 && -t 1 ]] 且 command -v stty 且 $TERM 非空非 dumb。
#
#   入参全局（调用 tui_multiselect / tui_select 前设）：
#       TUI_ITEMS=(值1 值2 ...)        必填，选项值
#       TUI_LABELS=(描述1 描述2 ...)   可选，平行于 TUI_ITEMS 的右侧描述；
#                                       空数组 / 未设则不显示描述
#   出参全局（确认后写）：
#       TUI_RESULT       单选=选中值；多选=空格分隔的选中值串（按原顺序）
#       TUI_RESULT_IDX   空格分隔的选中项下标（多选可多个；单选一个）
#
#   tui_multiselect "标题"
#       多选。键位：↑/↓ + j/k 移动，空格 勾选，a 全选，n 全不选，
#       回车 确认，q 或 Esc 取消。返回 0=确认 / 1=取消。
#   tui_select "标题"
#       单选。键位：↑/↓ + j/k 移动，回车 确认，q 或 Esc 取消。
#       返回 0=确认 / 1=取消。
#
#   tui_input "提示文案" <minlen> ["dim 辅助说明（可选）"]
#       单行输入，写 TUI_RESULT；空或长度 < minlen 则重问。返回 0。
#   tui_spinner_start "消息"
#       后台起转圈动画（braille 帧），写 TUI_SPINNER_PID。
#   tui_spinner_stop
#       kill $TUI_SPINNER_PID + 清当前行。幂等。
#   tui_step_header <cur(1-based)> "总标题" <步骤标签...>
#       清屏 + 顶部面包屑（当前步高亮 / 已过步正常 / 未到步 dim）+ 留白。
#       多步向导每步开头调一次，消灭「输出堆叠」。非 TTY 时仅打印一行纯文本。
#
# 内部 helper（下划线前缀，消费者勿直接依赖）：
#   tui_raw_begin / tui_raw_end   stty 存档/进 raw、隐/显光标（幂等）
#   _tui_cleanup                  trap EXIT/INT/TERM 时恢复终端
#   _tui_read_key                 读一次按键 → 写 _TUI_KEY（解析方向键 ESC 序列）
#   _tui_color                    依 $TUI_NO_COLOR / TTY 决定是否输出 ANSI
# ============================================================================

# ---------- 模块级状态 ----------
# 注意：本文件可能被 `source` 进开了 `set -u` 的脚本，凡引用处一律带 ${x:-} 兜底。
_TUI_STTY_SAVE=""     # stty -g 存档（raw_begin 写，raw_end 读后清空）
_TUI_RAW_ON=0         # raw 模式是否已开（幂等守卫）
_TUI_KEY=""           # _tui_read_key 的输出：up/down/left/right/enter/space/a/n/q/esc/<char>
_TUI_SEL=()           # 多选勾选态，平行 TUI_ITEMS；menu_loop 每次重置
TUI_SPINNER_PID="${TUI_SPINNER_PID:-}"

# ---------- 能力探测 ----------
# 可用 TUI 返回 0，否则 1。任何一项不满足都判不可用 → 调用方走文本菜单降级。
tui_capable() {
  [[ -t 0 && -t 1 ]] || return 1
  command -v stty >/dev/null 2>&1 || return 1
  local term="${TERM:-}"
  [[ -n "$term" && "$term" != "dumb" ]] || return 1
  return 0
}

# ---------- 颜色（仅在 TTY 且未禁用时输出 ANSI）----------
# 用法：_tui_color <code>  → 打印对应转义；reset 用 _tui_color 0。
# 设计 token（全库统一，勿散用其他色号）：
#   1=bold 标题 · 2=dim 辅助/未到步 · 36=cyan 主色/当前步 · 7=反显选中行 · 33=yellow 告警
#
# ⚠️ 能力探测必须在 source 时做一次并缓存：_tui_color 几乎总在 $(…) 命令替换里被调，
# 彼时 stdout 是捕获管道而非终端，函数内 [[ -t 1 ]] 恒 false → 历史 bug：样式层
# （反显选中/bold 标题/dim 提示/cyan 当前步）从未真正输出过。source 发生在脚本顶层，
# stdout 仍是真终端，此时探测才准。
if [[ -t 1 && -z "${TUI_NO_COLOR:-}" ]]; then _TUI_COLOR_ON=1; else _TUI_COLOR_ON=0; fi
_tui_color() {
  [[ "${_TUI_COLOR_ON:-0}" -eq 1 && -z "${TUI_NO_COLOR:-}" ]] || return 0
  printf '\033[%sm' "$1"
}

# ---------- 多步向导面包屑（每步开头调一次：进度头 + 留白）----------
# 用法：tui_step_header <cur(1-based)> "总标题" <步骤标签...>
# 注意：**本函数不清屏**（调用方负责，以便上方可叠加 banner 等持久 header）。
# 渲染：
#   (空行)
#     <bold>总标题</bold>  <dim>[cur/total]</dim>
#     已过步(正常) ── <bold+cyan>当前步</bold+cyan> ── 未到步(dim)
#   (空行)
tui_step_header() {
  local cur="$1" title="$2"; shift 2
  local total=$# bold dim cyan rs
  if [[ ! -t 1 ]]; then
    printf '[%s/%s] %s\n' "$cur" "$total" "$title"
    return 0
  fi
  bold="$(_tui_color 1)"; dim="$(_tui_color 2)"; cyan="$(_tui_color 36)"; rs="$(_tui_color 0)"
  printf '\n'
  printf '  %s%s%s  %s[%s/%s]%s\n' "$bold" "$title" "$rs" "$dim" "$cur" "$total" "$rs"
  local i=1 sep=""
  printf '  '
  for label in "$@"; do
    [[ -n "$sep" ]] && printf '%s ── %s' "$dim" "$rs"
    if [[ "$i" -eq "$cur" ]]; then
      printf '%s%s%s%s' "$bold" "$cyan" "$label" "$rs"
    elif [[ "$i" -lt "$cur" ]]; then
      printf '%s' "$label"
    else
      printf '%s%s%s' "$dim" "$label" "$rs"
    fi
    sep="x"; i=$(( i + 1 ))
  done
  printf '\n\n'
  return 0
}

# ---------- raw 模式（幂等）----------
# 先存档当前 stty，再进 raw（关回显、关行缓冲、单字节即返回），最后隐藏光标。
tui_raw_begin() {
  [[ "$_TUI_RAW_ON" -eq 1 ]] && return 0
  command -v stty >/dev/null 2>&1 || return 1
  _TUI_STTY_SAVE="$(stty -g 2>/dev/null || true)"
  # min 1 time 0：每次至少读到 1 字节才返回，不靠超时（方向键第 2/3 字节另用 -t 读）
  stty -echo -icanon min 1 time 0 2>/dev/null || true
  printf '\033[?25l'   # 隐藏光标
  _TUI_RAW_ON=1
  return 0
}

# 恢复：显示光标 + 还原 stty 存档。幂等（未开过 raw 直接返回）。
tui_raw_end() {
  [[ "$_TUI_RAW_ON" -eq 1 ]] || return 0
  printf '\033[?25h'   # 显示光标
  if [[ -n "$_TUI_STTY_SAVE" ]]; then
    stty "$_TUI_STTY_SAVE" 2>/dev/null || true
  else
    # 没存档也尽量把回显/行缓冲恢复到常态，别留坏终端
    stty echo icanon 2>/dev/null || true
  fi
  _TUI_STTY_SAVE=""
  _TUI_RAW_ON=0
  return 0
}

# ---------- 信号清理 ----------
# 被 source 时注册；保证 Ctrl-C / 异常退出后终端回显与光标恢复正常，不留坏终端。
# 注意：本 trap 会覆盖调用方对 EXIT/INT/TERM 已有的 trap —— 此为库已知行为，
# 由调用方知晓即可（调用方若有自己的清理需求，应在 source 本库后再叠加注册）。
_tui_cleanup() {
  tui_raw_end
  # 顺手停 spinner：若调用方起了 spinner 又被 Ctrl-C，避免后台子进程残留。
  # tui_spinner_stop 幂等、能处理未设 PID；定义在文件靠后，但 trap 触发时全文件
  # 已 source 完，运行期调用安全。
  tui_spinner_stop
}
trap '_tui_cleanup' EXIT
trap '_tui_cleanup; exit 130' INT
trap '_tui_cleanup; exit 143' TERM

# ---------- 读一次按键 → 写 _TUI_KEY ----------
# bash 3.2 注意：
#   - read -rsn1 读 1 字节；读到回车键时拿到的是「空串」（换行被吃掉），故需单独判空。
#   - 方向键是 3 字节 ESC 序列：ESC '[' 'A'。先读到 ESC（$'\e'），再用 -t 超时
#     读后续 2 字节；读不到（裸 ESC 单击）→ 当作 esc 取消。
#   - bash 3.2 不支持小数 -t（read -t 0.5 报 invalid timeout specification），
#     只能整数 1；裸 Esc 取消最长等 1s 为已知取舍（方向键 3 字节由终端一次性送达、
#     已在输入缓冲，续读不受这 1s 影响）。勿"优化"成 0.1，macOS 3.2 上会炸。
# 归一化输出（写入 _TUI_KEY）：up/down/left/right/enter/space/a/n/q/esc/<原字符>
_tui_read_key() {
  _TUI_KEY=""
  local c=""
  # 读 1 字节；read 在仅遇到换行时返回空且退出码 0
  IFS= read -rsn1 c 2>/dev/null
  if [[ -z "$c" ]]; then
    # 空 = 回车（Enter）
    _TUI_KEY="enter"
    return 0
  fi
  if [[ "$c" == $'\e' ]]; then
    # 可能是方向键 ESC 序列，或裸 ESC。用 -t 超时读后续字节。
    # -t 1 是整数：bash 3.2 不支持小数超时，勿改 0.x（见上方函数注释）。
    local c2="" c3=""
    IFS= read -rsn1 -t 1 c2 2>/dev/null
    if [[ "$c2" != "[" && "$c2" != "O" ]]; then
      # 不是 CSI/SS3 引导 → 裸 ESC（取消）
      _TUI_KEY="esc"
      return 0
    fi
    IFS= read -rsn1 -t 1 c3 2>/dev/null
    case "$c3" in
      A) _TUI_KEY="up" ;;
      B) _TUI_KEY="down" ;;
      C) _TUI_KEY="right" ;;
      D) _TUI_KEY="left" ;;
      *) _TUI_KEY="esc" ;;   # 未识别的序列，保守当取消
    esac
    return 0
  fi
  case "$c" in
    " ")    _TUI_KEY="space" ;;
    $'\n')  _TUI_KEY="enter" ;;   # 某些终端直接送 \n
    $'\r')  _TUI_KEY="enter" ;;
    j|J)    _TUI_KEY="down" ;;
    k|K)    _TUI_KEY="up" ;;
    a|A)    _TUI_KEY="a" ;;
    n|N)    _TUI_KEY="n" ;;
    q|Q)    _TUI_KEY="q" ;;
    *)      _TUI_KEY="$c" ;;
  esac
  return 0
}

# ---------- 内部：渲染一帧菜单（clack 式脊柱时间线）----------
# 入参（caller 局部）：
#   $1 模式 multi|single ; $2 标题 ; $3 当前光标行 cur ; $4 键位提示（dim 渲染）
# 读全局：TUI_ITEMS / TUI_LABELS / _TUI_SEL[]（多选勾选态，平行 TUI_ITEMS）
# 布局（标题 1 + 空 1 + n 项 + 空 1 + 提示 1 = 共 n + 4 行，改动需同步 _tui_menu_loop 的 total_rows）：
#   ◆ 标题(bold) / │空 / │n 个选项行(选中内容反显) / │空 / │提示(dim)
#   ◇/◆/■/│ 均为 E2 系窄字符（与既有 │─ 同族，无 CJK 宽度风险）。
# 约定：调用前光标已在帧顶部；本函数逐行打印，每行末尾 \033[K 清到行尾。
_tui_render() {
  local mode="$1" title="$2" cur="$3" hint="$4"
  local n="${#TUI_ITEMS[@]}"
  local hi rs bold dim cyan gut
  hi="$(_tui_color '7;36')" # 反显 + cyan（选中条带品牌色，而非黑白硬反显）
  rs="$(_tui_color 0)"      # reset
  bold="$(_tui_color 1)"
  dim="$(_tui_color 2)"
  cyan="$(_tui_color 36)"
  gut="$(printf '%s│%s' "$dim" "$rs")"   # 脊柱
  # 值列宽度动态：最长值 + 3（原固定 25 在短值集上留出大片空洞，扫读断裂）
  local i vw=8 l
  for (( i = 0; i < n; i++ )); do
    l="${#TUI_ITEMS[$i]}"
    (( l + 3 > vw )) && vw=$(( l + 3 ))
  done
  printf '  %s◆%s %s%s%s\033[K\r\n' "$cyan" "$rs" "$bold" "$title" "$rs"
  printf '  %s\033[K\r\n' "$gut"
  local mark prefix line label
  for (( i = 0; i < n; i++ )); do
    # 光标前缀
    if [[ "$i" -eq "$cur" ]]; then prefix="›"; else prefix=" "; fi
    # 勾选标记（仅多选；ASCII 标记是刻意的——Unicode 圆点/对勾在 CJK 终端宽度不定会错位）
    if [[ "$mode" == "multi" ]]; then
      if [[ "${_TUI_SEL[$i]:-0}" -eq 1 ]]; then mark="[x]"; else mark="[ ]"; fi
    else
      mark=" "
    fi
    # 描述（可选）
    label="${TUI_LABELS[$i]:-}"
    # 组装一行：前缀 + 标记 + 值（左对齐动态宽，值为 ASCII 时对齐才可靠）+ 描述
    if [[ -n "$label" ]]; then
      line="$(printf ' %s %s %-*s %s' "$prefix" "$mark" "$vw" "${TUI_ITEMS[$i]}" "$label")"
    else
      line="$(printf ' %s %s %s' "$prefix" "$mark" "${TUI_ITEMS[$i]}")"
    fi
    if [[ "$i" -eq "$cur" ]]; then
      # 当前行内容反显（cyan 条；脊柱保持常态不卷入）
      printf '  %s%s%s%s\033[K\r\n' "$gut" "$hi" "$line" "$rs"
    else
      printf '  %s%s\033[K\r\n' "$gut" "$line"
    fi
  done
  printf '  %s\033[K\r\n' "$gut"
  printf '  %s %s%s%s\033[K\r\n' "$gut" "$dim" "$hint" "$rs"
}

# ---------- 内部：折叠已完成的菜单帧（clack 式：交互块收成 2 行留痕）----------
# 调用前提：光标在帧底部（_tui_render 刚画完一帧，占 total_rows 行）。
# 动作：上移 total_rows → 打印 2 行折叠态（◇ 标题 / │ dim 答案）→ 把余下行清空 →
#       光标回到折叠块之后，使后续输出紧接时间线。
# $1=total_rows  $2=标题  $3=答案文本  $4=节点字形（◇ 完成 / ■ 取消）+颜色 code
_tui_collapse() {
  local total="$1" title="$2" answer="$3" glyph="${4:-◇}" gcolor="${5:-32}"
  local rs dim gc
  rs="$(_tui_color 0)"; dim="$(_tui_color 2)"; gc="$(_tui_color "$gcolor")"
  printf '\033[%dA' "$total"
  printf '  %s%s%s %s\033[K\r\n' "$gc" "$glyph" "$rs" "$title"
  printf '  %s│%s  %s%s%s\033[K\r\n' "$dim" "$rs" "$dim" "$answer" "$rs"
  local i wipe=$(( total - 2 ))
  for (( i = 0; i < wipe; i++ )); do printf '\033[K\r\n'; done
  [[ "$wipe" -gt 0 ]] && printf '\033[%dA' "$wipe"
  return 0
}

# ---------- 内部：选择菜单主循环（multiselect / select 共用）----------
# 入参：$1 mode(multi|single) ; $2 title
# 读全局：TUI_ITEMS（必填）/ TUI_LABELS（可选）
# 写全局：TUI_RESULT / TUI_RESULT_IDX（确认时）
# 返回：0=确认 / 1=取消
_tui_menu_loop() {
  local mode="$1" title="$2"
  local n="${#TUI_ITEMS[@]}"
  if [[ "$n" -eq 0 ]]; then
    # 没有任何选项：直接当取消返回（调用方应在调用前保证非空）
    return 1
  fi

  # 多选勾选态数组（平行 TUI_ITEMS）；单选不用但仍初始化以简化渲染分支
  _TUI_SEL=()
  local i
  for (( i = 0; i < n; i++ )); do _TUI_SEL+=("0"); done

  local cur=0
  # 提示行（hint）；总渲染行数 = 标题 1 + │空 1 + n 项 + │空 1 + │提示 1（见 _tui_render 布局注释）
  local hint
  if [[ "$mode" == "multi" ]]; then
    hint="↑/↓ 移动 · 空格 勾选 · a 全选 · n 全不选 · 回车 确认 · q 取消"
  else
    hint="↑/↓ 移动 · 回车 确认 · q 取消"
  fi
  local total_rows=$(( n + 4 ))

  tui_raw_begin || return 1

  # 首帧
  _tui_render "$mode" "$title" "$cur" "$hint"

  local rc=1   # 默认取消
  while true; do
    _tui_read_key
    case "$_TUI_KEY" in
      up)    (( cur > 0 )) && cur=$(( cur - 1 )) || cur=$(( n - 1 )) ;;
      down)  (( cur < n - 1 )) && cur=$(( cur + 1 )) || cur=0 ;;
      space)
        if [[ "$mode" == "multi" ]]; then
          if [[ "${_TUI_SEL[$cur]:-0}" -eq 1 ]]; then _TUI_SEL[$cur]=0; else _TUI_SEL[$cur]=1; fi
        fi
        ;;
      a)
        if [[ "$mode" == "multi" ]]; then
          for (( i = 0; i < n; i++ )); do _TUI_SEL[$i]=1; done
        fi
        ;;
      n)
        if [[ "$mode" == "multi" ]]; then
          for (( i = 0; i < n; i++ )); do _TUI_SEL[$i]=0; done
        fi
        ;;
      enter)
        if [[ "$mode" == "single" ]]; then
          TUI_RESULT="${TUI_ITEMS[$cur]}"
          TUI_RESULT_IDX="$cur"
          rc=0
          break
        else
          # 多选：收集勾选项（按原顺序）
          local vals="" idxs=""
          for (( i = 0; i < n; i++ )); do
            if [[ "${_TUI_SEL[$i]:-0}" -eq 1 ]]; then
              if [[ -z "$vals" ]]; then vals="${TUI_ITEMS[$i]}"; idxs="$i"; else
                vals="$vals ${TUI_ITEMS[$i]}"; idxs="$idxs $i"; fi
            fi
          done
          TUI_RESULT="$vals"
          TUI_RESULT_IDX="$idxs"
          rc=0
          break
        fi
        ;;
      q|esc)
        rc=1
        break
        ;;
      *) : ;;   # 其它键忽略
    esac
    # 原地重绘：光标移回帧顶部（上移 total_rows 行）再重画
    printf '\033[%dA' "$total_rows"
    _tui_render "$mode" "$title" "$cur" "$hint"
  done

  # clack 式折叠留痕：交互块收成「◇ 标题 / │ 答案」2 行（取消则 ■ 红 + 已取消）
  local answer
  if [[ "$rc" -eq 0 ]]; then
    if [[ "$mode" == "single" ]]; then
      answer="${TUI_ITEMS[$cur]}"
      [[ -n "${TUI_LABELS[$cur]:-}" ]] && answer="$answer · ${TUI_LABELS[$cur]}"
    else
      answer="${TUI_RESULT:-（未选）}"
      [[ -z "$answer" ]] && answer="（未选）"
    fi
    _tui_collapse "$total_rows" "$title" "$answer" "◇" 32
  else
    _tui_collapse "$total_rows" "$title" "已取消" "■" 31
  fi

  tui_raw_end
  return "$rc"
}

# ---------- 公共：多选 ----------
tui_multiselect() {
  _tui_menu_loop "multi" "${1:-请选择（可多选）}"
}

# ---------- 公共：单选 ----------
tui_select() {
  _tui_menu_loop "single" "${1:-请选择}"
}

# ---------- 公共：单行输入 ----------
# 用富 prompt + read -e（非 raw；行编辑交给终端 readline，支持左右键 / Ctrl-A 等）。
# 空或长度 < minlen 则提示重问。写 TUI_RESULT，返回 0。
# $3 可选：dim 辅助说明行（约束 / 示例 / 退出方式），显示在提示与输入符之间。
# -e 在 bash 3.2 安全（agf-team-start.sh 一贯在用），与 spec §5 "readline 行编辑" 一致。
# 布局（clack 式脊柱）：◆ 提示(bold) / [│ 辅助说明(dim)] / │ › 输入符；
# 成功后折叠为「◇ 提示 / │ 答案」2 行（行数随重试可变，用 rows 计数追踪供折叠上移）。
tui_input() {
  local prompt="${1:-请输入}" minlen="${2:-1}" note="${3:-}"
  local bold dim cyan rs yellow gut
  bold="$(_tui_color 1)"; dim="$(_tui_color 2)"; cyan="$(_tui_color 36)"
  rs="$(_tui_color 0)"; yellow="$(_tui_color 33)"
  gut="$(printf '%s│%s' "$dim" "$rs")"
  local val="" rows=1
  printf '  %s◆%s %s%s%s\n' "$cyan" "$rs" "$bold" "$prompt" "$rs"
  if [[ -n "$note" ]]; then
    printf '  %s %s%s%s\n' "$gut" "$dim" "$note" "$rs"
    rows=$(( rows + 1 ))
  fi
  while true; do
    printf '  %s %s›%s ' "$gut" "$cyan" "$rs"
    # 注意：勿加 2>/dev/null —— read -e 的 readline 字符回显走 stderr，
    # 重定向掉会导致"输入看不见"（输入其实读到了，只是不回显）。原启动器
    # 的 read -er 也从不重定向 stderr，正是此因。
    IFS= read -er val || val=""
    rows=$(( rows + 1 ))   # 本次输入行（read 回车后光标已到下一行）
    # 去首尾空白
    val="$(printf '%s' "$val" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [[ -z "$val" ]]; then
      printf '  %s %s输入不能为空，请重试。%s\n' "$gut" "$yellow" "$rs"
      rows=$(( rows + 1 ))
      continue
    fi
    if [[ "${#val}" -lt "$minlen" ]]; then
      printf '  %s %s至少需要 %s 个字符（当前 %s），请重试。%s\n' "$gut" "$yellow" "$minlen" "${#val}" "$rs"
      rows=$(( rows + 1 ))
      continue
    fi
    break
  done
  _tui_collapse "$rows" "$prompt" "$val" "◇" 32
  TUI_RESULT="$val"
  return 0
}

# ---------- 公共：spinner ----------
# 后台进程循环打印转圈字符 + 消息，主进程拿 PID。stop 时 kill + 清当前行。
# 设计：spinner 子进程自身做光标隐藏/恢复，避免与主进程 raw 状态纠缠。
tui_spinner_start() {
  local msg="${1:-处理中…}"
  # 已有一个在转 → 先停掉，避免叠加
  tui_spinner_stop
  # 非 TTY 直接打印一行静态消息，不起后台动画（管道/CI 安全）
  if [[ ! -t 1 ]]; then
    printf '%s\n' "$msg"
    TUI_SPINNER_PID=""
    return 0
  fi
  (
    # 子进程：忽略 INT，让父进程负责 kill；隐藏光标，退出恢复
    trap 'printf "\033[?25h" 2>/dev/null; exit 0' TERM INT
    printf '\033[?25l' 2>/dev/null
    # braille 帧（数组而非字符串切片：bash 3.2 的 ${var:n:1} 对多字节不可靠）
    local frames=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
    local cyan rs i=0 ch
    cyan="$(_tui_color 36)"; rs="$(_tui_color 0)"
    while true; do
      ch="${frames[$(( i % 10 ))]}"
      printf '\r  %s%s%s %s ' "$cyan" "$ch" "$rs" "$msg"
      i=$(( i + 1 ))
      sleep 0.1
    done
  ) &
  TUI_SPINNER_PID="$!"
  return 0
}

tui_spinner_stop() {
  local pid="${TUI_SPINNER_PID:-}"
  [[ -z "$pid" ]] && return 0
  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" 2>/dev/null || true
  TUI_SPINNER_PID=""
  # 清当前行 + 回行首 + 恢复光标（防子进程被 kill 在隐藏态）
  printf '\r\033[K\033[?25h'
  return 0
}

# ============================================================================
# 自测 demo —— 仅在「直接执行」本文件时运行；被 source 时不触发。
# 用法：bash .claude/scripts/agf-tui.sh
# ============================================================================
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  if ! tui_capable; then
    printf 'tui_capable: 当前环境不支持 TUI（非 TTY / 无 stty / TERM=dumb）。\n'
    printf '这是库文件，请在真实终端直接执行以体验交互 demo。\n'
    exit 0
  fi
  printf '=== agf-tui.sh 自测 demo ===\n\n'

  TUI_ITEMS=(frontend-dev backend-dev code-reviewer qa-engineer)
  TUI_LABELS=("前端实现" "后端实现" "代码评审（只读）" "E2E / UAT 测试")
  if tui_multiselect "多选 teammate（demo）"; then
    printf '多选结果: TUI_RESULT=[%s]  idx=[%s]\n\n' "$TUI_RESULT" "$TUI_RESULT_IDX"
  else
    printf '多选已取消。\n\n'
  fi

  TUI_ITEMS=(claude deepseek minimax qwen)
  TUI_LABELS=("官方" "DeepSeek" "MiniMax" "Qwen")
  if tui_select "单选 provider（demo）"; then
    printf '单选结果: TUI_RESULT=[%s]  idx=[%s]\n\n' "$TUI_RESULT" "$TUI_RESULT_IDX"
  else
    printf '单选已取消。\n\n'
  fi

  tui_input "输入 feature 描述（≥4 字符）" 4
  printf '输入结果: TUI_RESULT=[%s]\n\n' "$TUI_RESULT"

  tui_spinner_start "模拟启动中…"
  sleep 1.5
  tui_spinner_stop
  printf 'demo 结束。\n'
fi
