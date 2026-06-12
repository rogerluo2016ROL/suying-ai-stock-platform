#!/usr/bin/env python3
"""V5.2 秋神龙头战法-盘后 回测脚本 — 对比 sector_index 修复 + 过热惩罚优化效果."""
import argparse, json, os, sys, time, io, contextlib
from collections import defaultdict
import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


def setup_db():
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(pg_url)
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def get_trading_days(db, month_prefix="2026-06"):
    # Use >= AND < to avoid PG adapter % escaping issue with LIKE
    next_month = f"{int(month_prefix[:4])}-{int(month_prefix[5:])+1:02d}"
    if next_month == "2026-13": next_month = "2027-01"
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date >= ? AND trade_date < ? ORDER BY trade_date",
        (f"{month_prefix}-01", f"{next_month}-01")
    ).fetchall()
    return [r["trade_date"] for r in rows]


def get_next_day_return(db, code, trade_date):
    row = db.execute(
        "SELECT a.close as next_close FROM daily_kline a "
        "WHERE a.code=? AND a.trade_date > ? ORDER BY a.trade_date ASC LIMIT 1",
        (code, trade_date)
    ).fetchone()
    if not row or not row["next_close"]: return None
    entry_row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? AND trade_date=?", (code, trade_date)
    ).fetchone()
    if not entry_row or not entry_row["close"]: return None
    return (float(row["next_close"]) / float(entry_row["close"]) - 1) * 100


def main():
    parser = argparse.ArgumentParser(description="秋神龙头战法-盘后 回测")
    parser.add_argument("--month", type=str, default="2026-06")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--export", type=str, default=None)
    args = parser.parse_args()

    adapter = setup_db()
    from kronos_factors.scorer._db_stub import _get_db

    with _get_db() as db:
        trading_days = get_trading_days(db, args.month)
        print(f"📅 {args.month} 交易日: {len(trading_days)} 天")

    from kronos_factors.engine.leader_scalp import run_leader_screening

    results = []
    for i, td in enumerate(trading_days):
        t0 = time.time()
        print(f"[{i+1}/{len(trading_days)}] {td} ...", end=" ", flush=True)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                top, all_scores = run_leader_screening(td, top_n=args.top_n, env_check=False)
            elapsed = time.time() - t0
            s_cnt = sum(1 for s in top if s.get("grade") == "S")
            oh_cnt = sum(1 for s in top if s.get("_sector_overheat"))
            print(f"✅ {len(top)}只/{len(all_scores)}入选 S={s_cnt} 过热={oh_cnt} {elapsed:.1f}s")
            results.append({"trade_date": td, "top_picks": top, "all_scores": all_scores,
                           "total_qualified": len(all_scores)})
        except Exception as e:
            print(f"❌ {time.time()-t0:.1f}s - {e}")

    # Analysis
    with _get_db() as db:
        all_picks = []
        for r in results:
            for s in r["top_picks"]:
                ret = get_next_day_return(db, s["code"], r["trade_date"])
                all_picks.append({
                    "trade_date": r["trade_date"], "code": s["code"], "name": s["name"],
                    "industry": s["industry"], "grade": s["grade"],
                    "total_score": s["total_score"], "gain_pct": s.get("gain_pct", 0),
                    "sector_strong_count": s.get("sector_strong_count", 0),
                    "sector_overheat": s.get("_sector_overheat", False),
                    "next_day_return": ret,
                })

        valid = [p for p in all_picks if p["next_day_return"] is not None]
        if not valid:
            print("⚠️ 无有效次日数据")
            return

        returns = np.array([p["next_day_return"] for p in valid])
        win = (returns > 0).sum()
        total = len(valid)

        print(f"\n{'=' * 80}")
        print(f"  盘后模型 V5.2 回测 — {len(results)} 天, {total} 笔")
        print(f"{'=' * 80}")
        print(f"  胜率: {win}/{total} = {win/total*100:.1f}%")
        print(f"  均值收益: {returns.mean():+.2f}%  中位数: {np.median(returns):+.2f}%")
        print(f"  最大盈利: {returns.max():+.2f}%  最大亏损: {returns.min():+.2f}%")
        print(f"  累计收益: {returns.sum():+.2f}%")

        for grade in ["S", "A", "B", "C"]:
            g = [p for p in valid if p["grade"] == grade]
            if not g: continue
            gr = np.array([p["next_day_return"] for p in g])
            print(f"  {grade}级: {len(g)}笔 胜率{(gr>0).sum()/len(g)*100:.1f}% 均值{gr.mean():+.2f}%")

        # Overheat analysis
        oh = [p for p in valid if p.get("sector_overheat")]
        if oh:
            ohr = np.array([p["next_day_return"] for p in oh])
            print(f"\n  🔥 板块过热标的: {len(oh)}笔")
            print(f"     胜率: {(ohr>0).sum()/len(oh)*100:.1f}%  均值: {ohr.mean():+.2f}%  最差: {ohr.min():+.2f}%")

        normal = [p for p in valid if not p.get("sector_overheat")]
        if normal:
            nr = np.array([p["next_day_return"] for p in normal])
            print(f"  🟢 正常标的: {len(normal)}笔")
            print(f"     胜率: {(nr>0).sum()/len(normal)*100:.1f}%  均值: {nr.mean():+.2f}%")

        # Daily
        print(f"\n  每日汇总:")
        for r in results:
            td = r["trade_date"]
            dp = [p for p in valid if p["trade_date"] == td]
            if not dp: continue
            dr = np.array([p["next_day_return"] for p in dp])
            print(f"  {td}: {len(dp)}笔 胜率{(dr>0).sum()/len(dp)*100:.0f}% 均值{dr.mean():+.2f}%")


if __name__ == "__main__":
    main()
