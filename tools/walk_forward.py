#!/usr/bin/env python3
"""阶段1 AC-3 — walk-forward 样本外验证 (3+1 rolling).

设计 (PRD Q-2 确认):
  - 3 月调参窗口 (T-3..T-1) + 1 月样本外验证 (T), rolling 步长 1 月.
  - 本阶段冻结 bi_trend 策略参数 (铁律), 调参窗口仅做口径一致性校验 (不真调参).
  - 覆盖 2024-01 ~ 2025-12 共 24 个样本外月.
  - 输出: 样本外逐月 net (加权, AC-6) + 聚合 Sharpe-like = monthly_net mean/std * sqrt(12).

口径:
  - 多日持有 (AC-1): hold_days 5/7/10 + TP 20/25 + trailing 分级 + stop, T+1 open 入场.
  - 后复权读价 (Q-4).
  - 扣往返成本 (AC-11, --cost-bps, 默认 14).
  - 加权 (AC-6): S级 weight=0.6.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/walk_forward.py --start 2024-01 --end 2025-12 --cost-bps 14 \
        --export outputs/walk_forward_2024-2025.json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)
_TOOLS = os.path.join(_PROJ, "tools")
if os.path.isdir(_TOOLS) and _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from backtest_bi_trend import (  # noqa: E402
    setup_db, get_trading_days, run_backtest_day, simulate_pick,
)


def _git_strategy_commit(strategy_path: str) -> dict:
    """M01: record which commit of bi_trend_launch.py is being used.

    The walk-forward "sample-out" is only valid if the strategy module's
    parameters predate the OOS window. Without an explicit commit record,
    the loop silently uses HEAD — which, when HEAD carries in-sample tuning,
    leaks future parameters into the past (audit-model-2026-06-22 M01).

    Returns dict with commit / subject / dirty flag for the strategy file.
    """
    info = {"path": strategy_path, "commit": "unknown", "subject": "",
            "date": "", "dirty": False, "error": None}
    try:
        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=_PROJ, timeout=5).stdout.strip()
        if not repo_root:
            info["error"] = "not a git repo"
            return info
        rel = os.path.relpath(strategy_path, repo_root)
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", rel],
            capture_output=True, text=True, cwd=repo_root, timeout=5).stdout.strip()
        info["commit"] = commit or "untracked"
        if commit and commit != "untracked":
            info["subject"] = subprocess.run(
                ["git", "log", "-1", "--format=%s", commit],
                capture_output=True, text=True, cwd=repo_root, timeout=5).stdout.strip()
            info["date"] = subprocess.run(
                ["git", "show", "-s", "--format=%cI", commit],
                capture_output=True, text=True, cwd=repo_root, timeout=5).stdout.strip()[:10]
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", rel],
            capture_output=True, text=True, cwd=repo_root, timeout=5).stdout.strip()
        info["dirty"] = bool(status)
    except Exception as e:
        info["error"] = str(e)
    return info


def _timeline_guard_decision(strategy_info: dict, start_month: str, strict: bool) -> dict:
    """M01-A/C 流程护栏: 决定是否阻断 walk-forward 跑批 (纯函数, 可单测).

    返回 ``{"exit": False}`` 放行, 或 ``{"exit": True, "code": 2, "message": "..."}``
    阻断. main() 拿到 exit=True 后打印 message 并 sys.exit(code).

    两条护栏 (tech-lead 评估 docs/reviews/m01-techlead-assessment-2026-06-22.md §3):
      - M01-C (始终强制, 不受 strict 控制): 工作区 dirty → exit(2). 本地有未提交
        策略修改跑样本外任何情况都不可信, 没有"兼容"必要.
      - M01-A (受 --strict-timeline 控制): strict 启用且 commit 日期晚于 start_month
        → exit(2). commit 日期 > 样本外起始月 = 参数从未来泄漏到过去, 拒绝跑;
        若确需用此 commit 回测, 去掉 --strict-timeline 但结果不可作样本外结论.

    注: 这是跨策略护栏, 价值延续到 bi_trend 重设之后 — 任何新策略走 walk-forward
    都应传 --strict-timeline (memory phase1-sample-out-conclusion How-to-apply #4).
    M01 不能自动用对时点参数 (那是方案 B, 重设后视情况), 只逼操作者显式声明 commit.
    """
    # M01-C: dirty 始终强制阻断.
    if strategy_info.get("dirty"):
        return {
            "exit": True, "code": 2,
            "message": (
                f"❌ M01-C: 策略模块 {strategy_info.get('path')} 有未提交的本地修改 "
                f"(dirty=True). dirty 工作区跑样本外任何情况都不可信, 先 commit 或 stash "
                f"再回测. (此护栏始终强制, 不受 --strict-timeline 控制)"),
        }
    # M01-A: 仅 strict 模式下阻断时序泄露.
    if strict:
        commit_date = strategy_info.get("date", "")
        if commit_date and commit_date > start_month:
            return {
                "exit": True, "code": 2,
                "message": (
                    f"❌ M01-A: 策略 commit 日期 {commit_date} 晚于样本外起始 {start_month} "
                    f"— 参数时序泄露 (用未来参数测过去), 拒绝跑. 若确需用此 commit 回测, "
                    f"去掉 --strict-timeline, 但结果不可作样本外结论. 正确做法: "
                    f"git checkout <commit-at-oos> 后再跑."),
            }
    return {"exit": False}


def month_iter(start, end):
    """生成 start..end (含) 的 YYYY-MM 列表."""
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def shift_month(ym, delta):
    """ym 位移 delta 月 (delta 可负), 返回 YYYY-MM."""
    y, m = map(int, ym.split("-"))
    idx = (y * 12 + (m - 1)) + delta
    ny, nm = divmod(idx, 12)
    return f"{ny:04d}-{nm + 1:02d}"


def run_month(db, month, top_n, cost_bps, progress_cb=None, frozen_defaults=None):
    """跑单月回测 (多日持有 AC-1), 返回该月所有 pick 的 net_return / weighted_return 列表.

    frozen_defaults: AC-5 冻结参数模式 — 当 pick 缺 hold_days/tp/sl/weight 时
    (调参前版本如 V5.9 无个性化持有建议), 用此默认 dict 补全.
    """
    trading_days = get_trading_days(db, month)
    if not trading_days:
        return [], 0
    picks = []
    for i, td in enumerate(trading_days):
        try:
            r = run_backtest_day(db, td, top_n=top_n)
        except Exception as e:
            if progress_cb:
                progress_cb(f"  {td} 选股失败: {e}")
            continue
        for s in r["top_picks"]:
            hd = s.get("hold_days")
            tp = s.get("take_profit")
            sl = s.get("stop_loss")
            weight = s.get("weight", 1.0)
            if frozen_defaults:  # AC-5: 冻结参数补全 (pick 缺字段时用 V5.9 默认)
                hd = hd if hd is not None else frozen_defaults["hold_days"]
                tp = tp if tp is not None else frozen_defaults["take_profit"]
                sl = sl if sl is not None else frozen_defaults["stop_loss"]
                weight = weight if s.get("weight") is not None else frozen_defaults.get("weight", 1.0)
            sim = simulate_pick(db, s["code"], td,
                                hold_days=hd, tp_pct=tp, stop_loss_pct=sl,
                                cost_bps=cost_bps)
            if sim is None:
                continue
            picks.append({
                "trade_date": td, "code": s["code"], "grade": s.get("grade"),
                "net_return": sim["net_return"],
                "weighted_return": sim["net_return"] * weight,
                "exit_reason": sim["exit_reason"],
                "actual_hold_days": sim["actual_hold_days"],
            })
        if progress_cb:
            progress_cb(f"  [{i+1}/{len(trading_days)}] {td}: {len(r['top_picks'])} picks")
    return picks, len(trading_days)


def summarize_month(picks):
    """聚合单月: 加权 net mean/sum, 净胜率, 退出原因."""
    if not picks:
        return None
    net = np.array([p["net_return"] for p in picks])
    weighted = np.array([p["weighted_return"] for p in picks])
    reasons = defaultdict(int)
    for p in picks:
        reasons[p["exit_reason"]] += 1
    return {
        "n_trades": len(picks),
        "weighted_net_mean": float(weighted.mean()),
        "weighted_net_sum": float(weighted.sum()),
        "net_mean": float(net.mean()),
        "net_median": float(np.median(net)),
        "win_rate_net": float((net > 0).sum() / len(net) * 100),
        "exit_reasons": dict(reasons),
    }


def sharpe_like(monthly_weighted_means):
    """Sharpe-like = monthly mean / std * sqrt(12) (年化, 无风险利率=0)."""
    if len(monthly_weighted_means) < 2:
        return None
    arr = np.array(monthly_weighted_means)
    std = arr.std(ddof=1)
    if std == 0:
        return None
    return float(arr.mean() / std * np.sqrt(12))


def main():
    parser = argparse.ArgumentParser(description="阶段1 AC-3 walk-forward 样本外验证")
    parser.add_argument("--start", type=str, default="2024-01", help="样本外起始月 YYYY-MM")
    parser.add_argument("--end", type=str, default="2025-12", help="样本外结束月 YYYY-MM")
    parser.add_argument("--top-n", type=int, default=20, help="每日选股数")
    parser.add_argument("--cost-bps", type=int, default=14, help="往返成本 bp (AC-11)")
    parser.add_argument("--train-months", type=int, default=3, help="调参窗口月数 (本阶段冻结, 仅校验)")
    parser.add_argument("--frozen", action="store_true",
                        help="AC-5 冻结参数模式: pick 缺 hold_days/tp/sl 时用 V5.9 调参前默认 "
                             "(hold=5, tp=15, stop=-10, weight=1.0). 需配合 git checkout 调参前 bi_trend_launch.py.")
    parser.add_argument("--export", type=str, default=None, help="导出JSON路径")
    parser.add_argument("--strict-timeline", action="store_true",
                        help="M01-A 流程护栏: 启用后若策略 commit 日期晚于 --start 样本外起始月, "
                             "sys.exit(2) 硬阻断 (参数时序泄露, 拒绝跑). "
                             "CI 跑 walk_forward 必须传此 flag 结果才算有效样本外. "
                             "默认 False 保持兼容 (诊断性跑批). "
                             "注: 工作区 dirty 始终强制 exit(2), 不受此 flag 控制 (M01-C).")
    args = parser.parse_args()

    # AC-5 冻结参数默认 (V5.9 调参前, git 972a10f): 统一持有, 无个性化建议
    frozen_defaults = None
    if args.frozen:
        frozen_defaults = {"hold_days": 5, "take_profit": 15, "stop_loss": -10, "weight": 1.0}

    adapter = setup_db()
    from kronos_factors.scorer._db_stub import _get_db

    # M01: 显式记录本次样本外跑用的是哪个 commit 的策略模块, 避免"用未来参数测过去".
    # walk_forward 的 run_month 调 HEAD 版本的 bi_trend_launch.py — 若 HEAD 带样本内调参,
    # 就把未来参数泄漏到过去. 这里记录 commit + 日期, 若 commit 日期晚于样本外起始月则警告.
    strategy_path = os.path.join(
        _PROJ, "packages", "kronos-factors", "kronos_factors", "engine",
        "bi_trend_launch.py")
    strategy_info = _git_strategy_commit(strategy_path)
    print(f"📌 策略模块: {strategy_info['path']}")
    print(f"   commit: {strategy_info['commit'][:12]} ({strategy_info['date']}) — {strategy_info['subject']}")
    print(f"   dirty(本地未提交修改): {strategy_info['dirty']}")

    # M01-A/C 流程护栏 (tech-lead 评估 §3): dirty 始终 exit(2) (M01-C);
    # --strict-timeline 启用时 commit 日期 > 样本外起始 exit(2) (M01-A).
    # 决策抽成纯函数 _timeline_guard_decision, 便于行为级单测 (不需起进程).
    guard = _timeline_guard_decision(strategy_info, args.start, args.strict_timeline)
    if guard["exit"]:
        print(guard["message"])
        sys.exit(guard["code"])
    # 未启用 --strict-timeline 且 commit 日期晚于起始: 软警告 (D 模式过渡兜底,
    # 诊断性跑批放行但结果不可作样本外结论).
    if (not args.strict_timeline) and strategy_info["date"] and strategy_info["date"] > args.start:
        print(f"   ⚠️  警告: 策略 commit 日期 {strategy_info['date']} 晚于样本外起始 {args.start} — "
              f"参数可能从未来泄漏到过去 (M01). 加 --strict-timeline 可硬阻断; "
              f"结果不可作样本外结论, 应 checkout 样本外时点的策略版本再回测.")
    print()

    sample_months = month_iter(args.start, args.end)
    print(f"📅 walk-forward 样本外: {args.start} ~ {args.end} ({len(sample_months)} 月)")
    print(f"   调参窗口: {args.train_months} 月 (冻结参数, 仅口径校验, 不真调参)")
    print(f"   成本: {args.cost_bps}bp | 多日持有 AC-1 | 后复权 Q-4 | 加权 AC-6")
    print()

    monthly_table = []
    all_picks_sample = []  # 样本外所有 pick (用于聚合)

    for mi, oos_month in enumerate(sample_months):
        train_start = shift_month(oos_month, -args.train_months)
        train_end = shift_month(oos_month, -1)
        t0 = time.time()
        print(f"[{mi+1}/{len(sample_months)}] OOS={oos_month} (train {train_start}..{train_end})")

        with _get_db() as db:
            picks, n_days = run_month(db, oos_month, args.top_n, args.cost_bps,
                                      progress_cb=lambda m: None,
                                      frozen_defaults=frozen_defaults)
        stat = summarize_month(picks)
        elapsed = time.time() - t0
        if stat:
            stat["oos_month"] = oos_month
            stat["train_window"] = f"{train_start}..{train_end}"
            stat["n_trading_days"] = n_days
            monthly_table.append(stat)
            all_picks_sample.extend(picks)
            print(f"   → {stat['n_trades']}笔 | 加权net均值 {stat['weighted_net_mean']:+.4f}% "
                  f"| 净胜率 {stat['win_rate_net']:.1f}% | {elapsed:.0f}s")
        else:
            print(f"   → 无数据 | {elapsed:.0f}s")

    # ── 聚合 Sharpe-like ──
    monthly_weighted_means = [m["weighted_net_mean"] for m in monthly_table]
    sharpe = sharpe_like(monthly_weighted_means)

    # 调参窗口口径校验 (本阶段冻结, 仅报告 — 不真调参)
    print(f"\n{'=' * 70}")
    print(f"  walk-forward 样本外聚合 ({len(monthly_table)} 月)")
    print(f"{'=' * 70}")
    if monthly_weighted_means:
        arr = np.array(monthly_weighted_means)
        pos = (arr > 0).sum()
        print(f"  逐月加权net均值: mean {arr.mean():+.4f}%  median {np.median(arr):+.4f}%  std {arr.std(ddof=1):.4f}%")
        print(f"  正月数: {pos}/{len(arr)} = {pos/len(arr)*100:.1f}%")
        print(f"  Sharpe-like (年化, mean/std*√12): {sharpe:+.3f}" if sharpe else "  Sharpe-like: N/A (std=0)")
    if all_picks_sample:
        all_net = np.array([p["net_return"] for p in all_picks_sample])
        all_w = np.array([p["weighted_return"] for p in all_picks_sample])
        print(f"\n  全样本外聚合 (笔级):")
        print(f"    总笔数: {len(all_picks_sample)}")
        print(f"    净均值: {all_net.mean():+.4f}%  净中位: {np.median(all_net):+.4f}%  净胜率: {(all_net>0).sum()/len(all_net)*100:.1f}%")
        print(f"    加权净均值: {all_w.mean():+.4f}%  加权净累计: {all_w.sum():+.2f}%")

    print(f"\n  逐月表 (样本外):")
    print(f"  {'月份':<10} {'笔数':<6} {'加权net均值':<12} {'净胜率':<8} {'train窗口'}")
    print(f"  {'-' * 60}")
    for m in monthly_table:
        print(f"  {m['oos_month']:<10} {m['n_trades']:<6} {m['weighted_net_mean']:>+10.4f}% "
              f"{m['win_rate_net']:>6.1f}%  {m['train_window']}")

    # ── 导出 ──
    export_path = args.export or f"outputs/walk_forward_{args.start}_{args.end}.json"
    os.makedirs(os.path.dirname(export_path) or "outputs", exist_ok=True)
    conclusion = {
        "sample_out_range": f"{args.start}~{args.end}",
        "n_sample_months": len(monthly_table),
        "monthly_weighted_net_mean_avg": float(np.mean(monthly_weighted_means)) if monthly_weighted_means else None,
        "monthly_pos_count": int((np.array(monthly_weighted_means) > 0).sum()) if monthly_weighted_means else 0,
        "sharpe_like_annualized": sharpe,
        "weighted_net_sign_aggregate": ("正" if all_picks_sample and np.mean([p["weighted_return"] for p in all_picks_sample]) > 0 else "负") if all_picks_sample else "N/A",
    }
    out = {
        "design": {"train_months": args.train_months, "step_months": 1,
                   "frozen_params": True, "cost_bps": args.cost_bps,
                   "frozen_v59_defaults": frozen_defaults,
                   "mode": "multi_day AC-1 + 后复权 Q-4 + 加权 AC-6"},
        # M01: 记录本次样本外用的策略 commit, 审计时可核对 commit 日期是否早于样本外窗口.
        "strategy_commit": strategy_info,
        "monthly_table": monthly_table,
        "sharpe_like_annualized": sharpe,
        "conclusion": conclusion,
    }
    with open(export_path, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 导出: {export_path}")
    print(f"   样本外净符号 (加权聚合): {conclusion['weighted_net_sign_aggregate']}")

    if hasattr(adapter, 'close'):
        adapter.close()


if __name__ == "__main__":
    main()
