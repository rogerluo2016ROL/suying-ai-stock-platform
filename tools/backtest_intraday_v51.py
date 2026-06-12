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


def get_next_day_return(db, code, trade_date):
    """获取次日收益率: (次日close / 当日close - 1) * 100.

    如果次日无数据(今天是最后交易日), 返回 None.
    """
    # Get today's close at 14:00 (not daily close — use stk_mins snapshot)
    # For backtest, we use the 14:00 close as entry, next day close as exit
    row = db.execute(
        "SELECT a.close as next_close "
        "FROM daily_kline a "
        "WHERE a.code=? AND a.trade_date > ? "
        "ORDER BY a.trade_date ASC LIMIT 1",
        (code, trade_date)
    ).fetchone()
    if not row or not row["next_close"]:
        return None

    # Get entry price (today's daily close as proxy for 14:00)
    entry_row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    if not entry_row or not entry_row["close"]:
        return None

    next_close = float(row["next_close"])
    entry_close = float(entry_row["close"])
    return (next_close / entry_close - 1) * 100


def run_backtest(trade_date, top_n=15):
    """Run V5.1 screening on a single day and compute next-day returns."""
    from kronos_factors.engine.leader_intraday import (
        run_intraday_screening, _sector_climax_cache
    )

    # Suppress print output during batch run
    import io
    import contextlib

    with contextlib.redirect_stdout(io.StringIO()):
        top, all_scores = run_intraday_screening(trade_date, top_n=top_n)

    return {
        "trade_date": trade_date,
        "total_qualified": len(all_scores),
        "top_picks": top,
        "all_scores": all_scores,
    }


def analyze_results(results, db):
    """分析回测结果: 计算胜率、均值收益、按评级分组等."""
    all_picks = []
    for r in results:
        td = r["trade_date"]
        for s in r["top_picks"]:
            ret = get_next_day_return(db, s["code"], td)
            all_picks.append({
                "trade_date": td,
                "code": s["code"],
                "name": s["name"],
                "industry": s["industry"],
                "grade": s["grade"],
                "total_score": s["total_score"],
                "gain_14": s["gain_14"],
                "peer_count": s.get("peer_count", 0),
                "climax_penalty": s.get("climax_penalty", 0),
                "independent_penalty": s.get("independent_penalty", 0),
                "sector_change": s.get("sector_change", 0),
                "next_day_return": ret,
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
        all_picks = analyze_results(results, db)

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
