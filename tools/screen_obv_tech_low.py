#!/usr/bin/env python3
"""
OBV科技低价选股方案快照 — OBV≥10天 + 科技板块 + 价格<50 + 回踩确认

快照参数 (2026-06-12 配置):
  - OBV 持续高于 MA10 ≥ 10 个交易日
  - 板块: 半导体/元器件/通信设备/软件服务/IT设备/互联网/
          专用机械/电器仪表/电气设备/机械基件/机床制造/航空/化工原料/矿物制品
  - 价格: 3 < price < 50
  - 回踩: 距20日高点 ≥ 3%
  - 流通市值: ≥ 30亿
  - 排除: ST, 退市

Usage:
  # 单日选股
  KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
  python tools/screen_obv_tech_low.py --date 2026-06-12

  # 回测
  python tools/screen_obv_tech_low.py --backtest 2026-06 --top-n 10
"""

import argparse, json, os, sys, time
from collections import defaultdict
import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

# ═══════════════════════════════════════════════════════════════
# 快照参数
# ═══════════════════════════════════════════════════════════════
SNAPSHOT_CONFIG = {
    "name": "OBV科技低价选股",
    "version": "1.0",
    "date": "2026-06-12",
    "params": {
        "min_obv_days_above_ma": 10,
        "max_price": 50,
        "min_price": 3,
        "min_pullback_pct": 3,        # 距20日高点至少回踩3%
        "min_float_mv_yi": 30,        # 流通市值≥30亿
        "min_trend_20d": 0,           # 20日涨幅>0% (不要求强趋势, 不跌即可)
        "min_kline_bars": 30,
        "tech_industries": [
            "半导体", "元器件", "通信设备", "软件服务", "IT设备", "互联网",
            "专用机械", "电器仪表", "电气设备", "机械基件", "机床制造",
            "航空", "化工原料", "矿物制品",
        ],
    }
}


def setup_db():
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(pg_url)
    if adapter is None:
        raise RuntimeError(f"无法连接数据库: {pg_url}")
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def calc_obv(closes, volumes):
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv[i] = obv[i-1] + volumes[i]
        elif closes[i] < closes[i-1]:
            obv[i] = obv[i-1] - volumes[i]
        else:
            obv[i] = obv[i-1]
    return obv


def screen_single_day(db, trade_date, top_n=None):
    """单日选股."""
    p = SNAPSHOT_CONFIG["params"]
    tech = p["tech_industries"]

    # 股票池
    stocks = db.execute(
        f"SELECT code, name, industry FROM stocks WHERE is_st=0 "
        f"AND name NOT LIKE '%ST%' AND name NOT LIKE '%退市%' "
        f"AND industry IN ({','.join(['?' for _ in tech])}) "
        f"AND (float_mv IS NULL OR float_mv >= ?)",
        tuple(tech) + (p["min_float_mv_yi"],)
    ).fetchall()
    print(f"  📈 科技股票池: {len(stocks)} 只")

    results = []
    for r in stocks:
        code = r['code']
        klines = db.execute(
            "SELECT close, volume FROM daily_kline "
            "WHERE code=? AND trade_date<=? ORDER BY trade_date ASC",
            (code, trade_date)
        ).fetchall()
        if len(klines) < p["min_kline_bars"]:
            continue

        closes = np.array([float(k['close']) for k in klines], dtype=np.float64)
        volumes = np.array([float(k['volume']) for k in klines], dtype=np.float64)
        price = closes[-1]

        # 价格过滤
        if price > p["max_price"] or price < p["min_price"]:
            continue

        # OBV + MA10
        obv = calc_obv(closes, volumes)
        obv_ma10 = np.convolve(obv, np.ones(10)/10, mode='valid')
        if len(obv_ma10) < 10:
            continue

        obv_days_above = 0
        for i in range(len(obv)-1, -1, -1):
            ma_idx = i - 10 + 1
            if ma_idx >= 0 and obv[i] > obv_ma10[ma_idx]:
                obv_days_above += 1
            else:
                break
        if obv_days_above < p["min_obv_days_above_ma"]:
            continue

        # 20日趋势
        ret_20d = (closes[-1]/closes[-20]-1)*100 if closes[-20] > 0 else 0
        if ret_20d < p["min_trend_20d"]:
            continue

        # 回踩: 距20日高点
        high_20d = np.max(closes[-20:])
        pct_from_high = (price / high_20d - 1) * 100
        if pct_from_high > -p["min_pullback_pct"]:
            continue

        # 附加指标
        ret_5d = (closes[-1]/closes[-5]-1)*100 if closes[-5] > 0 else 0
        obv_slope = (obv[-1]/abs(obv[-10])-1)*100 if len(obv)>=15 and abs(obv[-10])>1 else 0
        ma5 = np.mean(closes[-5:])
        ma20 = np.mean(closes[-20:])

        results.append({
            "code": code, "name": r['name'], "industry": r['industry'],
            "price": round(float(price), 2),
            "obv_days_above": obv_days_above,
            "ret_20d": round(ret_20d, 1),
            "ret_5d": round(ret_5d, 1),
            "pct_from_20d_high": round(pct_from_high, 1),
            "obv_slope_pct": round(obv_slope, 1),
            "ma_trend": "多头" if ma5 > ma20 else "震荡",
            "trade_date": trade_date,
        })

    # 综合评分
    for r in results:
        score = min(100, max(0,
            r["obv_days_above"] * 2.0 +           # OBV持续天数 (最高60)
            abs(r["pct_from_20d_high"]) * 1.5 +   # 回踩深度 (最高30)
            r["ret_20d"] * 0.5                     # 趋势强度 (最高10)
        ))
        r["score"] = round(score, 1)

    results.sort(key=lambda x: -x["score"])

    if top_n:
        results = results[:top_n]

    return results


def print_results(results, trade_date):
    """打印选股结果."""
    print(f"\n{'=' * 90}")
    print(f"  OBV科技低价选股 — {trade_date} | 共 {len(results)} 只")
    print(f"{'=' * 90}")
    print(f"  {'代码':<8} {'名称':<10} {'板块':<10} {'价格':<6} {'评分':<5} "
          f"{'OBV天':<5} {'20日':<7} {'距高点':<7} {'近5日':<7} {'均线'}")
    print(f"  {'-' * 80}")
    for r in results:
        print(f"  {r['code']:<8} {r['name']:<10} {r['industry']:<10} "
              f"¥{r['price']:<5.2f} {r['score']:<5.0f} "
              f"{r['obv_days_above']:<5} {r['ret_20d']:>+5.1f}%  {r['pct_from_20d_high']:>+5.1f}%  "
              f"{r['ret_5d']:>+5.1f}%  {r['ma_trend']}")


def run_backtest(db, month, top_n=10):
    """回测模式."""
    y, m = month.split("-")
    start = f"{y}-{m}-01"
    nm = int(m) + 1; ny = int(y)
    if nm > 12: nm = 1; ny += 1
    end = f"{ny}-{nm:02d}-01"

    days = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date >= ? AND trade_date < ? ORDER BY trade_date",
        (start, end)
    ).fetchall()
    trading_days = [d["trade_date"] for d in days]
    print(f"📅 {month}: {len(trading_days)} 个交易日\n")

    all_picks = []
    for td in trading_days:
        t0 = time.time()
        results = screen_single_day(db, td, top_n=top_n)
        elapsed = time.time() - t0

        # 计算次日收益
        for r in results:
            exit_row = db.execute(
                "SELECT close FROM daily_kline WHERE code=? AND trade_date > ? "
                "ORDER BY trade_date ASC LIMIT 1",
                (r["code"], td)
            ).fetchone()
            if exit_row and exit_row["close"]:
                r["next_day_return"] = round((float(exit_row["close"]) / r["price"] - 1) * 100, 2)

        all_picks.extend(results)
        if results:
            valid = [r for r in results if "next_day_return" in r]
            win = sum(1 for r in valid if r["next_day_return"] > 0)
            avg_ret = sum(r["next_day_return"] for r in valid) / len(valid) if valid else 0
            print(f"  {td}: {len(results)}只 | 胜{win}/{len(valid)} | 均{avg_ret:+.1f}% | {elapsed:.0f}s")
        else:
            print(f"  {td}: 0只 | {elapsed:.0f}s")

    # 汇总
    valid = [p for p in all_picks if "next_day_return" in p]
    if valid:
        returns = np.array([p["next_day_return"] for p in valid])
        win = (returns > 0).sum()
        print(f"\n{'=' * 60}")
        print(f"  回测汇总: {len(trading_days)}天, {len(valid)}笔")
        print(f"  胜率: {win}/{len(valid)} = {win/len(valid)*100:.1f}%")
        print(f"  均值: {returns.mean():+.2f}%  累计: {returns.sum():+.1f}%")
        print(f"  盈亏比: {returns[returns>0].mean():+.2f}% / {returns[returns<=0].mean():+.2f}%")

    return all_picks


def main():
    parser = argparse.ArgumentParser(description="OBV科技低价选股方案")
    parser.add_argument("--date", type=str, help="单日选股 YYYY-MM-DD")
    parser.add_argument("--backtest", type=str, help="回测月份 YYYY-MM")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--export", type=str, help="导出JSON")
    parser.add_argument("--show-config", action="store_true", help="显示快照配置")
    args = parser.parse_args()

    if args.show_config:
        print(json.dumps(SNAPSHOT_CONFIG, ensure_ascii=False, indent=2))
        return

    adapter = setup_db()
    from kronos_factors.scorer._db_stub import _get_db

    if args.backtest:
        with _get_db() as db:
            picks = run_backtest(db, args.backtest, args.top_n)
        if args.export:
            os.makedirs(os.path.dirname(args.export) or "outputs", exist_ok=True)
            with open(args.export, 'w') as f:
                json.dump({"config": SNAPSHOT_CONFIG, "picks": picks}, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n📁 {args.export}")
    elif args.date:
        with _get_db(readonly=True) as db:
            results = screen_single_day(db, args.date, args.top_n)
        print_results(results, args.date)
    else:
        # 默认: 最新交易日
        with _get_db(readonly=True) as db:
            row = db.execute("SELECT MAX(trade_date) as d FROM daily_kline").fetchone()
            latest = row["d"] if row else None
        if latest:
            print(f"📅 最新交易日: {latest}")
            with _get_db(readonly=True) as db:
                results = screen_single_day(db, latest, args.top_n)
            print_results(results, latest)

    if hasattr(adapter, 'close'):
        adapter.close()


if __name__ == "__main__":
    main()
