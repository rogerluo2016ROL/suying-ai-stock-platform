#!/usr/bin/env python3
"""V5.1 秋神龙头战法-盘中 回测脚本 — 6月全量验证 P0+P1 优化效果.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/backtest_intraday_v51.py --month 2026-06 --top-n 15
"""
import argparse, json, os, sys, time
from collections import defaultdict
from datetime import datetime, timedelta

# Ensure packages are importable
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import numpy as np


def setup_db():
    """Inject PG adapter."""
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(pg_url)
    if adapter is None:
        raise RuntimeError(f"无法连接数据库: {pg_url}")
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def get_trading_days(db, month_prefix="2026-06"):
    """获取指定月份的所有交易日 (有 stk_mins 14:00 数据的)."""
    rows = db.execute(
        "SELECT DISTINCT SUBSTR(trade_time,1,10) as trade_date "
        "FROM stk_mins WHERE trade_time LIKE ? AND freq='5min' "
        "AND trade_time LIKE '%14:%' "
        "ORDER BY trade_date",
        (f"{month_prefix}%",)
    ).fetchall()
    return [r["trade_date"] for r in rows]


def get_next_day_return(db, code, trade_date, entry_price=None,
                        stop_loss=None, take_profit=None, morning_stop=None,
                        exit_strategy="close"):
    """V8.0: 基于次日 OHLC 的真实退出模拟.

    exit_strategy:
      - "close": T日收盘→T+1日收盘 (baseline)
      - "fixed": 固定止损-4% + 固定止盈+5%
      - "atr": ATR动态止损 + 分级止盈 + 开盘动量检测

    退出优先级:
      1. 开盘价 < morning_stop → 开盘止损
      2. 最高价 >= take_profit → 止盈成交
      3. 最低价 <= stop_loss → 止损成交
      4. 默认 → 收盘卖出

    Returns: (return_pct, exit_reason) or None if insufficient data
    """
    # Get next day OHLC
    row = db.execute(
        "SELECT open, high, low, close, trade_date "
        "FROM daily_kline WHERE code=? AND trade_date > ? "
        "ORDER BY trade_date ASC LIMIT 1",
        (code, trade_date)
    ).fetchone()
    if not row or not row["close"]:
        return None

    next_open = float(row["open"] or row["close"])
    next_high = float(row["high"] or row["close"])
    next_low = float(row["low"] or row["close"])
    next_close = float(row["close"])

    # Entry price: use provided close_14, fall back to daily close
    if entry_price is None or entry_price <= 0:
        entry_row = db.execute(
            "SELECT close FROM daily_kline WHERE code=? AND trade_date=?",
            (code, trade_date)
        ).fetchone()
        if not entry_row or not entry_row["close"]:
            return None
        entry_price = float(entry_row["close"])

    # ── Baseline: close-to-close ──
    if exit_strategy == "close":
        ret = (next_close / entry_price - 1) * 100
        return (ret, "close")

    # ── Fixed strategy: -4% stop, +5% take-profit ──
    if exit_strategy == "fixed":
        sl = entry_price * 0.96
        tp = entry_price * 1.05
    elif exit_strategy == "atr":
        sl = stop_loss if stop_loss else entry_price * 0.96
        tp = take_profit if take_profit else entry_price * 1.05
        ms = morning_stop if morning_stop else entry_price * 0.98
    else:
        ret = (next_close / entry_price - 1) * 100
        return (ret, "close")

    # ── Realistic exit simulation (OHLC) ──
    # Priority 1: Morning gap-down stop (only for ATR strategy)
    if exit_strategy == "atr" and next_open < ms:
        ret = (next_open / entry_price - 1) * 100
        return (ret, f"open_gap({ret:+.1f}%)")

    # Priority 2: Take-profit hit
    if next_high >= tp:
        ret = (tp / entry_price - 1) * 100
        return (ret, f"tp({ret:+.1f}%)")

    # Priority 3: Stop-loss hit
    if next_low <= sl:
        ret = (sl / entry_price - 1) * 100
        return (ret, f"sl({ret:+.1f}%)")

    # Priority 4: Close exit
    ret = (next_close / entry_price - 1) * 100
    return (ret, "close")


def run_backtest(trade_date, top_n=15):
    """Run V8.0 screening on a single day and generate trading plans."""
    from kronos_factors.engine.leader_intraday import (
        run_intraday_screening, generate_intraday_plan, _sector_climax_cache
    )

    # Suppress print output during batch run
    import io
    import contextlib

    with contextlib.redirect_stdout(io.StringIO()):
        top, all_scores = run_intraday_screening(trade_date, top_n=top_n)

    plans = generate_intraday_plan(top) if top else []

    return {
        "trade_date": trade_date,
        "total_qualified": len(all_scores),
        "top_picks": top,
        "plans": plans,          # V8.0: with entry/stop/tp/morning_stop
        "all_scores": all_scores,
    }


def analyze_results(results, db, compare_exits=False):
    """V8.0: 分析回测结果, 支持多策略对比."""
    plans_lookup = {}  # (trade_date, code) -> plan dict
    all_picks = []
    for r in results:
        td = r["trade_date"]
        for plan in r.get("plans", []):
            plans_lookup[(td, plan["code"])] = plan
        for s in r["top_picks"]:
            plan = plans_lookup.get((td, s["code"]), {})
            entry = plan.get("entry_price", s.get("close_14", 0))

            if compare_exits:
                # Baseline: close_14 → next close (no slippage, no stops)
                ret_close = get_next_day_return(db, s["code"], td,
                    entry_price=s.get("close_14", entry), exit_strategy="close")
                # Fixed: plan entry_price with slippage + fixed stop/tp
                ret_fixed = get_next_day_return(db, s["code"], td,
                    entry_price=entry, exit_strategy="fixed")
                # ATR: plan entry_price with dynamic stop/tp + morning gap
                ret_atr = get_next_day_return(db, s["code"], td,
                    entry_price=entry,
                    stop_loss=plan.get("stop_loss"),
                    take_profit=plan.get("take_profit"),
                    morning_stop=plan.get("morning_stop"),
                    exit_strategy="atr")

                all_picks.append({
                    "trade_date": td,
                    "code": s["code"], "name": s["name"],
                    "industry": s["industry"], "grade": s["grade"],
                    "total_score": s["total_score"], "gain_14": s["gain_14"],
                    "peer_count": s.get("peer_count", 0),
                    "climax_penalty": s.get("climax_penalty", 0),
                    "independent_penalty": s.get("independent_penalty", 0),
                    "next_day_return": ret_close[0] if ret_close else None,
                    "exit_reason": ret_close[1] if ret_close else None,
                    "ret_close": ret_close[0] if ret_close else None,
                    "close_reason": ret_close[1] if ret_close else None,
                    "ret_fixed": ret_fixed[0] if ret_fixed else None,
                    "fixed_reason": ret_fixed[1] if ret_fixed else None,
                    "ret_atr": ret_atr[0] if ret_atr else None,
                    "atr_reason": ret_atr[1] if ret_atr else None,
                })
            else:
                # Baseline only (backward compatible)
                ret = get_next_day_return(db, s["code"], td,
                    entry_price=entry, exit_strategy="close")
                all_picks.append({
                    "trade_date": td,
                    "code": s["code"], "name": s["name"],
                    "industry": s["industry"], "grade": s["grade"],
                    "total_score": s["total_score"], "gain_14": s["gain_14"],
                    "peer_count": s.get("peer_count", 0),
                    "climax_penalty": s.get("climax_penalty", 0),
                    "independent_penalty": s.get("independent_penalty", 0),
                    "sector_change": s.get("sector_change", 0),
                    "next_day_return": ret[0] if ret else None,
                    "exit_reason": ret[1] if ret else None,
                })

    # ── 总体统计 ──
    valid = [p for p in all_picks if p["next_day_return"] is not None]
    pending = len(all_picks) - len(valid)

    if not valid:
        print("⚠️ 无有效次日收益数据 (可能需要等待次日收盘)")
        return all_picks

    returns = np.array([p["next_day_return"] for p in valid])
    win_mask = returns > 0
    win_count = win_mask.sum()
    total = len(valid)

    print(f"\n{'=' * 80}")
    print(f"  V5.1 回测汇总 — {len(results)} 个交易日, {total} 笔交易 (pending={pending})")
    print(f"{'=' * 80}")
    print(f"  胜率: {win_count}/{total} = {win_count/total*100:.1f}%")
    print(f"  均值收益: {returns.mean():+.2f}%")
    print(f"  中位数收益: {np.median(returns):+.2f}%")
    print(f"  最大单笔盈利: {returns.max():+.2f}%")
    print(f"  最大单笔亏损: {returns.min():+.2f}%")
    print(f"  累计收益: {returns.sum():+.2f}%")
    print(f"  收益标准差: {returns.std():.2f}%")
    print(f"  盈亏比: {returns[win_mask].mean():+.2f}% / {returns[~win_mask].mean():+.2f}%")

    # ── 按评级分组 ──
    print(f"\n{'─' * 60}")
    print(f"  按评级分组:")
    print(f"  {'评级':<6} {'笔数':<6} {'胜率':<8} {'均值':<8} {'中位数':<8} {'最大':<8} {'最小':<8}")
    print(f"  {'-' * 56}")
    for grade in ["S", "A", "B", "C"]:
        g = [p for p in valid if p["grade"] == grade]
        if not g:
            continue
        gr = np.array([p["next_day_return"] for p in g])
        gw = (gr > 0).sum()
        print(f"  {grade:<6} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}% {np.median(gr):>+7.2f}% {gr.max():>+7.2f}% {gr.min():>+7.2f}%")

    # ── P0 高潮惩罚效果 ──
    climax_picks = [p for p in valid if p["climax_penalty"] >= 12]
    if climax_picks:
        cr = np.array([p["next_day_return"] for p in climax_picks])
        cw = (cr > 0).sum()
        print(f"\n  🔴 板块高潮次日标的 (penalty≥12): {len(climax_picks)}笔")
        print(f"     胜率: {cw/len(climax_picks)*100:.1f}%  均值: {cr.mean():+.2f}%  "
              f"最差: {cr.min():+.2f}%")
        for p in climax_picks:
            tag = "✅" if p["next_day_return"] > 0 else "❌"
            print(f"     {tag} {p['trade_date']} {p['code']} {p['name']:<8} "
                  f"高潮罚-{p['climax_penalty']} 次日{p['next_day_return']:+.1f}% | {p['industry']}")

    # ── P1 独立标的惩罚效果 ──
    indep_picks = [p for p in valid if p["independent_penalty"] >= 4]
    if indep_picks:
        ir = np.array([p["next_day_return"] for p in indep_picks])
        iw = (ir > 0).sum()
        print(f"\n  🟡 独立/独苗标的 (penalty≥4): {len(indep_picks)}笔")
        print(f"     胜率: {iw/len(indep_picks)*100:.1f}%  均值: {ir.mean():+.2f}%  "
              f"最差: {ir.min():+.2f}%")
        for p in indep_picks:
            tag = "✅" if p["next_day_return"] > 0 else "❌"
            p_type = "零板块" if p["independent_penalty"] >= 12 else "独苗"
            print(f"     {tag} {p['trade_date']} {p['code']} {p['name']:<8} "
                  f"{p_type} 次日{p['next_day_return']:+.1f}% | {p['industry']}")

    # ── 板块集群标的 (有板块支撑) ──
    cluster_picks = [p for p in valid if p["peer_count"] >= 3 and p["climax_penalty"] == 0]
    if cluster_picks:
        cr2 = np.array([p["next_day_return"] for p in cluster_picks])
        cw2 = (cr2 > 0).sum()
        print(f"\n  🟢 板块集群标的 (peer≥3, 无高潮惩罚): {len(cluster_picks)}笔")
        print(f"     胜率: {cw2/len(cluster_picks)*100:.1f}%  均值: {cr2.mean():+.2f}%  "
              f"最差: {cr2.min():+.2f}%")

    # ── V8.0: 三种退出策略对比 ──
    if compare_exits:
        print(f"\n{'=' * 80}")
        print(f"  V8.0 退出策略对比")
        print(f"{'=' * 80}")
        strategies = [
            ("close", "收盘→收盘 (Baseline)"),
            ("fixed", "固定止损-4% + 止盈+5%"),
            ("atr",  "ATR动态 + 分级止盈 + 开盘检测"),
        ]
        print(f"  {'策略':<35} {'胜率':<8} {'均值':<8} {'中位数':<8} {'盈亏比':<15} {'最大盈':<8} {'最大亏':<8}")
        print(f"  {'-' * 100}")
        for key, label in strategies:
            rets = [p[f"ret_{key}"] for p in valid if p.get(f"ret_{key}") is not None]
            if not rets:
                continue
            rets = np.array(rets)
            wins = rets[rets > 0]
            losses = rets[rets <= 0]
            w_rate = len(wins) / len(rets) * 100
            pf = abs(wins.mean() / losses.mean()) if len(losses) > 0 and losses.mean() != 0 else float('inf')
            reasons = [p.get(f"{key}_reason", "") for p in valid if p.get(f"ret_{key}") is not None]
            from collections import Counter
            reason_dist = Counter(reasons)
            reason_str = " | ".join(f"{k}:{v}" for k, v in reason_dist.most_common(4))

            print(f"  {label:<35} {w_rate:>6.1f}% {rets.mean():>+7.2f}% {np.median(rets):>+7.2f}% "
                  f"{wins.mean():>+6.2f}%/{losses.mean():>+6.2f}% {rets.max():>+7.2f}% {rets.min():>+7.2f}%")
            print(f"    {' ':>35} 退出分布: {reason_str}")

    # ── 每日汇总 ──
    print(f"\n{'─' * 80}")
    print(f"  每日汇总:")
    print(f"  {'日期':<12} {'笔数':<5} {'胜率':<8} {'均值':<8} {'S级':<4} {'高潮罚':<6} {'独立罚':<6}")
    print(f"  {'-' * 58}")
    for r in results:
        td = r["trade_date"]
        day_picks = [p for p in valid if p["trade_date"] == td]
        if not day_picks:
            continue
        dr = np.array([p["next_day_return"] for p in day_picks])
        dw = (dr > 0).sum()
        s_cnt = sum(1 for p in day_picks if p["grade"] == "S")
        c_cnt = sum(1 for p in day_picks if p["climax_penalty"] >= 12)
        i_cnt = sum(1 for p in day_picks if p["independent_penalty"] >= 4)
        print(f"  {td:<12} {len(day_picks):<5} {dw/len(day_picks)*100:>6.1f}% {dr.mean():>+7.2f}% "
              f"{s_cnt:<4} {c_cnt:<6} {i_cnt:<6}")

    return all_picks


def export_json(all_picks, path):
    """导出回测结果."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    serializable = []
    for p in all_picks:
        serializable.append({k: (float(v) if isinstance(v, (np.floating,)) else v)
                             for k, v in p.items()})
    with open(path, 'w') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 结果导出: {path}")


def main():
    parser = argparse.ArgumentParser(description="V5.1 秋神龙头战法-盘中 回测")
    parser.add_argument("--month", type=str, default="2026-06", help="回测月份 (YYYY-MM)")
    parser.add_argument("--top-n", type=int, default=15, help="每日选股数")
    parser.add_argument("--compare-exits", action="store_true", help="对比三种退出策略")
    parser.add_argument("--export", type=str, default=None, help="导出JSON路径")
    args = parser.parse_args()

    adapter = setup_db()

    from kronos_factors.scorer._db_stub import _get_db
    with _get_db() as db:
        trading_days = get_trading_days(db, args.month)
        print(f"📅 {args.month} 有 14:00 数据的交易日: {len(trading_days)} 天")
        for td in trading_days:
            print(f"   {td}")
        print()

    if not trading_days:
        print("❌ 无可用交易日")
        return

    results = []
    for i, td in enumerate(trading_days):
        t0 = time.time()
        print(f"[{i+1}/{len(trading_days)}] {td} ...", end=" ", flush=True)
        try:
            r = run_backtest(td, args.top_n)
            elapsed = time.time() - t0
            top_n = len(r["top_picks"])
            qualified = r["total_qualified"]
            grades = f"S={sum(1 for s in r['top_picks'] if s['grade']=='S')} " \
                     f"A={sum(1 for s in r['top_picks'] if s['grade']=='A')}"
            climax = sum(1 for s in r["top_picks"] if s.get("climax_penalty", 0) >= 12)
            indep = sum(1 for s in r["top_picks"] if s.get("independent_penalty", 0) >= 4)
            risks = ""
            if climax: risks += f" 🔴高潮{climax}"
            if indep: risks += f" 🟡独立{indep}"
            print(f"✅ {top_n}只/{qualified}入选 {grades} {elapsed:.1f}s{risks}")
            results.append(r)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"❌ {elapsed:.1f}s - {e}")

    # ── 分析 ──
    with _get_db() as db:
        all_picks = analyze_results(results, db, compare_exits=args.compare_exits)

    if args.export:
        export_json(all_picks, args.export)
    else:
        default_path = f"outputs/backtest_intraday_v51_{args.month}.json"
        export_json(all_picks, default_path)

    # Cleanup
    if hasattr(adapter, 'close'):
        adapter.close()


if __name__ == "__main__":
    main()
