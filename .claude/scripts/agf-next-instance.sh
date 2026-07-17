#!/usr/bin/env bash
# agf-next-instance.sh — Multi-instance Worker Pool 的「N 分配算法」可执行版
#
# 把 workflow.md §命名与寻址 的算法落成脚本：查同 type 已存在的最大 N，stdout
# 只输出 NEXT_N = MAX_N + 1（整数）。3 路扫描（pool 产物文件名 pattern 各异）：
#   - progress/<type>-<N>.md                   N 在文件名末尾
#   - docs/reviews/<feat>-r<N>-<date>.md       N 在 'r' 后（mid-string）
#   - docs/qa/<feat>-{e2e,uat}-q<N>-<date>.md  N 在 'q' 后（mid-string）
#
# 用法:
#   bash .claude/scripts/agf-next-instance.sh <type> [<feature-slug>]
#   <type>          实例类型（如 backend-dev / code-reviewer / qa-engineer）
#   <feature-slug>  省略时跳过 review / qa 两路扫描（只扫 progress）
#
# 在仓库根目录执行（与 agf-matrix.sh 同约定，路径全相对）。
# 参考: ADR-001 + .claude/standards/workflow.md §Multi-instance Worker Pool

set -uo pipefail

TYPE=""
FEATURE=""

# === 参数解析 ===
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    -*) echo "Unknown arg: $1" >&2; exit 1 ;;
    *)
      if [[ -z "$TYPE" ]]; then TYPE="$1"
      elif [[ -z "$FEATURE" ]]; then FEATURE="$1"
      else echo "多余参数: $1" >&2; exit 1
      fi
      shift ;;
  esac
done

if [[ -z "$TYPE" ]]; then
  echo "Usage: $0 <type> [<feature-slug>]   (see --help)" >&2
  exit 1
fi

# === 3 路扫描（与 workflow.md 代码块一致；无匹配时 ls 报错被吞，变量留空）===
# 1) progress/<type>-<N>.md：N 在末尾
N_PROGRESS=$(ls progress/"${TYPE}"-*.md 2>/dev/null | grep -oE '\-[0-9]+\.md$' | grep -oE '[0-9]+' | sort -n | tail -1)

N_REVIEW=""
N_QA=""
if [[ -n "$FEATURE" ]]; then
  # 2) docs/reviews/<feat>-r<N>-<date>.md：N 在 'r' 后跟 mid-string
  N_REVIEW=$(ls docs/reviews/"${FEATURE}"-r*-*.md 2>/dev/null | grep -oE '\-r[0-9]+-' | grep -oE '[0-9]+' | sort -n | tail -1)
  # 3) docs/qa/<feat>-{e2e,uat}-q<N>-<date>.md：N 在 'q' 后跟 mid-string
  N_QA=$(ls docs/qa/"${FEATURE}"-{e2e,uat}-q*-*.md 2>/dev/null | grep -oE '\-q[0-9]+-' | grep -oE '[0-9]+' | sort -n | tail -1)
fi

MAX_N=$(printf '%s\n' "${N_PROGRESS:-0}" "${N_REVIEW:-0}" "${N_QA:-0}" | sort -n | tail -1)
NEXT_N=$(( ${MAX_N:-0} + 1 ))

# A-F2: pool 上限校验（读 roles.yaml pool.limit；防 PL 误 fan-out 单实例锁定角色）
# 单实例角色（deploy-engineer / apple-release-engineer pool=1 唯一 UAT/签名身份等）
# 原 PURE 靠自觉——本块用 roles.yaml pool.limit 机械守，NEXT_N 超限 exit 2。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROLES_YAML="$SCRIPT_DIR/../agents/roles.yaml"
if [[ -f "$ROLES_YAML" ]] && command -v python3 >/dev/null 2>&1; then
  POOL_LIMIT=$(TYPE="$TYPE" ROLES_YAML="$ROLES_YAML" python3 -c '
import os, yaml
try:
    data = yaml.safe_load(open(os.environ["ROLES_YAML"]))
    for a in data.get("agents") or []:
        if a.get("name") == os.environ["TYPE"]:
            print((a.get("pool") or {}).get("limit") or "")
            break
except Exception:
    pass
' 2>/dev/null)
  if [[ -n "$POOL_LIMIT" ]] && (( NEXT_N > POOL_LIMIT )); then
    echo "❌ [agf-next-instance] role '$TYPE' pool 上限 ${POOL_LIMIT}，NEXT_N=${NEXT_N} 超限——禁 fan-out（roles.yaml pool.limit + ADR-001）。单实例锁定角色（deploy / apple-release 唯一 UAT / 签名身份等）不得并发。" >&2
    exit 2
  fi
fi

echo "$NEXT_N"
