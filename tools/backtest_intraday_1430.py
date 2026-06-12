#!/usr/bin/env python3
"""V5.5 秋神龙头战法-盘中 14:30 回测脚本 — 近三月全覆盖.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/backtest_intraday_1430.py --from 2026-03-01 --top-n 15
"""
import argparse, json, os, sys, time
from collections import defaultdict
from datetime import datetime, timedelta

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import numpy as np


def setup_db():
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(pg_url)
    if adapter is None:
        raise RuntimeError(f"Cannot connect: {pg_url}")
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def get_trading_days(db, from_date="2026-03-01"):
    """Get all trading days with stk_mins 14:30 data."""
    rows = db.execute(
        "SELECT DISTINCT SUBSTR(trade_time,1,10) as trade_date "
        "FROM stk_mins WHERE trade_time LIKE '%14:30%' AND freq='5min' "
        "AND trade_time >= ? "
        "ORDER BY trade_date",
        (f"{from_date}%",)
    ).fetchall()
    return [r["trade_date"] for r in rows]


def get_next_day_return(db, code, trade_date):
    """Compute next-day return using daily_kline close."""
    row = db.execute(
        "SELECT a.close as next_close FROM daily_kline a "
        "WHERE a.code=? AND a.trade_date > ? "
        "ORDER BY a.trade_date ASC LIMIT 1",
        (code, trade_date)
    ).fetchone()
    if not row or not row["next_close"]:
        return None
    
    entry_row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    if not entry_row or not entry_row["close"]:
        return None
    
    return (float(row["next_close"]) / float(entry_row["close"]) - 1) * 100


def run_backtest_day(trade_date, top_n=15):
    """Run V5.5 screening at 14:30 for a single day."""
    from kronos_factors.engine.leader_intraday import run_intraday_screening
    import io, contextlib
    
    with contextlib.redirect_stdout(io.StringIO()):
        top, all_scores = run_intraday_screening(trade_date, time_slot="14:30", top_n=top_n)
    
    return {
        "trade_date": trade_date,
        "total_qualified": len(all_scores),
        "top_picks": top,
    }


def analyze_results(results, db):
    """Comprehensive backtest analysis."""
    all_picks = []
    for r in results:
        td = r["trade_date"]
        for s in r["top_picks"]:
            ret = get_next_day_return(db, s["code"], td)
            all_picks.append({
                "trade_date": td,
                "code": s["code"], "name": s.get("name", ""),
                "industry": s.get("industry", ""),
                "grade": s.get("grade", ""), "total_score": s.get("total_score", 0),
                "gain_14": s.get("gain_14", 0),
                "sector_leader_score": s.get("sector_leader_score", 0),
                "leadership_bonus": s.get("leadership_bonus", 0) if "leadership_bonus" in s else 0,
                "resonance_score": s.get("resonance_score", 0),
                "afternoon_score": s.get("afternoon_score", 0),
                "next_day_return": ret,
            })
    
    valid = [p for p in all_picks if p["next_day_return"] is not None]
    pending = len(all_picks) - len(valid)
    
    if not valid:
        print("⚠️ No valid next-day returns")
        return all_picks
    
    returns = np.array([p["next_day_return"] for p in valid])
    wins = (returns > 0).sum()
    total = len(valid)
    
    print(f"\n{'='*85}")
    print(f"  V5.5 14:30 回测总览 — {len(results)}交易日, {total}笔 (pending={pending})")
    print(f"{'='*85}")
    print(f"  胜率:       {wins}/{total} = {wins/total*100:.1f}%")
    print(f"  均值收益:   {returns.mean():+.2f}%")
    print(f"  中位数:     {np.median(returns):+.2f}%")
    print(f"  标准差:     {returns.std():.2f}%")
    print(f"  最大盈利:   {returns.max():+.2f}%")
    print(f"  最大亏损:   {returns.min():+.2f}%")
    print(f"  累计收益:   {returns.sum():+.2f}%")
    
    gains = returns[returns > 0]
    losses = returns[returns < 0]
    avg_win = gains.mean() if len(gains) else 0
    avg_loss = losses.mean() if len(losses) else 0
    print(f"  盈亏比:     +{avg_win:.2f}% / {avg_loss:.2f}%")
    print(f"  盈亏比:     {abs(avg_win/avg_loss):.1f}:1" if avg_loss != 0 else "  N/A")
    
    # By grade
    print(f"\n  {'─'*75}")
    print(f"  按评级: {'评级':>4} {'笔数':>5} {'胜率':>7} {'均值':>8} {'中位':>8}")
    print(f"  {'─'*75}")
    for g in ["S", "A", "B"]:
        gr = [p for p in valid if p["grade"] == g]
        if gr:
            grr = np.array([p["next_day_return"] for p in gr])
            print(f"  {g:>4} {len(gr):>5} {((grr>0).sum()/len(gr)*100):>6.1f}% {grr.mean():>+7.2f}% {np.median(grr):>+7.2f}%")
    
    # By month
    print(f"\n  {'─'*75}")
    print(f"  按月: {'月份':>8} {'交易日':>6} {'笔数':>5} {'胜率':>7} {'均值':>8} {'累计':>8}")
    print(f"  {'─'*75}")
    months = sorted(set(p["trade_date"][:7] for p in valid))
    for m in months:
        mp = [p for p in valid if p["trade_date"].startswith(m)]
        mr = np.array([p["next_day_return"] for p in mp])
        td_count = len(set(p["trade_date"] for p in mp))
        print(f"  {m:>8} {td_count:>6} {len(mp):>5} {((mr>0).sum()/len(mr)*100):>6.1f}% {mr.mean():>+7.2f}% {mr.sum():>+7.2f}%")
    
    # By sector leader score
    print(f"\n  {'─'*75}")
    print(f"  板块龙头效应: {'龙头分':>6} {'笔数':>5} {'胜率':>7} {'均值':>8}")
    print(f"  {'─'*75}")
    for lo, hi, label in [(0, 10, "弱龙头"), (10, 18, "中等"), (18, 24, "强龙头"), (24, 99, "满分龙头")]:
        gp = [p for p in valid if lo <= p["sector_leader_score"] < hi]
        if gp:
            gr = np.array([p["next_day_return"] for p in gp])
            print(f"  {label:>6} {len(gp):>5} {((gr>0).sum()/len(gr)*100):>6.1f}% {gr.mean():>+7.2f}%")
    
    # By resonance score
    print(f"\n  板块共振效应:")
    for lo, hi, label in [(0, 3, "弱共振"), (3, 7, "中等"), (7, 10, "强共振"), (10, 99, "满分共振")]:
        gp = [p for p in valid if lo <= p["resonance_score"] < hi]
        if gp:
            gr = np.array([p["next_day_return"] for p in gp])
            print(f"    {label:>6} {len(gp):>5} {((gr>0).sum()/len(gr)*100):>6.1f}% {gr.mean():>+7.2f}%")
    
    # Market environment analysis
    print(f"\n  市场环境效应:")
    # Classify by number of qualified stocks as proxy for market strength
    for lo, hi, label in [(0, 20, "极弱(<20)"), (20, 60, "弱(20-60)"), (60, 120, "中(60-120)"), (120, 999, "强(>120)")]:
        days_in_range = [r for r in results if lo <= r["total_qualified"] < hi]
        if days_in_range:
            gp = [p for p in valid if any(p["trade_date"] == d["trade_date"] for d in days_in_range)]
            if gp:
                gr = np.array([p["next_day_return"] for p in gp])
                td_count = len(days_in_range)
                picks_per_day = len(gp) / td_count if td_count else 0
                print(f"    {label:>12} {td_count:>3}天 {int(picks_per_day):>3}只/天 {((gr>0).sum()/len(gr)*100):>5.1f}% {gr.mean():>+7.2f}%")
    
    # Daily detail
    print(f"\n  {'─'*85}")
    print(f"  每日明细:")
    print(f"  {'日期':<12} {'笔数':>4} {'胜率':>7} {'均值':>8} {'S':>3} {'A':>3} {'合格数':>6} {'最佳':>10}")
    print(f"  {'─'*85}")
    for r in results:
        td = r["trade_date"]
        dp = [p for p in valid if p["trade_date"] == td]
        if dp:
            dr = np.array([p["next_day_return"] for p in dp])
            sg = sum(1 for p in dp if p["grade"] == "S")
            ag = sum(1 for p in dp if p["grade"] == "A")
            best = max(dp, key=lambda x: x["next_day_return"])
            print(f"  {td:<12} {len(dp):>4} {((dr>0).sum()/len(dr)*100):>6.1f}% {dr.mean():>+7.2f}% {sg:>3} {ag:>3} {r['total_qualified']:>6} {best['code']} {best['next_day_return']:>+6.2f}%")
    
    return all_picks


def main():
    parser = argparse.ArgumentParser(description="V5.5 秋神龙头战法-盘中 14:30 回测")
    parser.add_argument("--from", dest="from_date", type=str, default="2026-03-01")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--export", type=str, default="")
    args = parser.parse_args()
    
    adapter = setup_db()
    from kronos_factors.scorer._db_stub import _get_db
    
    t0 = time.time()
    
    with _get_db() as db:
        days = get_trading_days(db, vars(args)["from_date"])
    
    print(f"交易天数: {len(days)} (14:30数据)")
    if len(days) > 5:
        print(f"  范围: {days[0]} → {days[-1]}")
    
    results = []
    for i, td in enumerate(days):
        try:
            r = run_backtest_day(td, args.top_n)
            results.append(r)
            n = len(r["top_picks"])
            sg = sum(1 for s in r["top_picks"] if s.get("grade") == "S")
            if (i+1) % 10 == 0 or i == len(days)-1 or i == 0:
                print(f"  [{i+1}/{len(days)}] {td}: {n} picks (S={sg})")
        except Exception as e:
            print(f"  [{i+1}/{len(days)}] {td}: ERROR - {e}")
    
    with _get_db() as db:
        all_picks = analyze_results(results, db)
    
    elapsed = time.time() - t0
    print(f"\n总耗时: {elapsed:.0f}s ({elapsed/len(days):.1f}s/天)")
    
    # Export
    if args.export:
        export_path = args.export
    else:
        export_path = f"outputs/backtest_intraday_1430_v55_{args.from_date}.json"
    
    os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)
    with open(export_path, "w") as f:
        json.dump({"args": vars(args), "results": results, "picks": all_picks}, f,
                  ensure_ascii=False, indent=2, default=str)
    print(f"导出: {export_path}")


if __name__ == "__main__":
    main()
