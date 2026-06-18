#!/usr/bin/env python3
"""今日秋神午后选股 — 快速版 (使用PG数据 + 历史均价近似).

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/run_today_afternoon.py --date 2026-06-17 --time 14:00 --top-n 20
"""
import argparse, os, sys, time
from collections import defaultdict
from datetime import datetime
import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


def setup_db():
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter, _get_db
    adapter = create_pg_adapter(pg_url)
    if adapter is None:
        raise RuntimeError(f"无法连接数据库: {pg_url}")
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def get_stock_name_map(db):
    """获取 code -> name 映射."""
    rows = db.execute("SELECT code, name, industry FROM stocks WHERE is_st=0").fetchall()
    return {r["code"]: {"name": r["name"], "industry": r.get("industry", "其他")} for r in rows}


def get_latest_min_snapshot(db, trade_date):
    """获取今天最新的分钟快照 (兼容PG code列名)."""
    rows = db.execute(
        "SELECT code, MAX(trade_time) as max_time FROM stk_mins "
        "WHERE trade_time LIKE ? AND freq='5min' GROUP BY code",
        (f"{trade_date}%",)
    ).fetchall()
    if not rows:
        return {}

    # Get the latest time slot
    max_time = max(r["max_time"] for r in rows)
    print(f"  📊 最新分钟时段: {max_time}")

    # Get snapshot at latest time
    snapshot = {}
    for r in db.execute(
        "SELECT code, open, high, low, close, volume, amount FROM stk_mins "
        "WHERE trade_time = ? AND freq='5min'",
        (max_time,)
    ).fetchall():
        code = r["code"]
        snapshot[code] = {
            "open": float(r["open"] or 0),
            "high": float(r["high"] or 0),
            "low": float(r["low"] or 0),
            "close": float(r["close"] or 0),
            "volume": float(r["volume"] or 0),
            "amount": float(r["amount"] or 0),
        }
    return snapshot


def get_pre_close_map(db, trade_date):
    """获取前收盘价."""
    rows = db.execute(
        "SELECT code, pre_close FROM stk_limit WHERE trade_date=?", (trade_date,)
    ).fetchall()
    return {r["code"]: float(r["pre_close"] or 0) for r in rows if r["pre_close"] and float(r["pre_close"]) > 0}


def get_avg_daily_amount(db, code, trade_date, lookback=10):
    """历史日均成交额 (千元 -> 亿元)."""
    rows = db.execute(
        "SELECT AVG(amount) as avg_amount FROM ("
        "SELECT amount FROM daily_kline "
        "WHERE code=? AND trade_date < ? ORDER BY trade_date DESC LIMIT ?"
        ") sub",
        (code, trade_date, lookback)
    ).fetchone()
    if rows and rows["avg_amount"]:
        # daily_kline amount is in 元, convert to 亿
        return float(rows["avg_amount"]) / 1e8
    return 0


def get_kline_history(db, code, trade_date, lookback=60):
    """历史日K线."""
    rows = db.execute(
        "SELECT open, high, low, close, volume, amount, trade_date "
        "FROM daily_kline WHERE code=? AND trade_date<=? "
        "ORDER BY trade_date ASC",
        (code, trade_date)
    ).fetchall()
    return rows


def compute_ma(closes, period):
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


def calc_atr(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1:
        return 0
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr_arr = np.zeros(n)
    atr_arr[period] = np.mean(tr[1:period+1])
    for i in range(period+1, n):
        atr_arr[i] = (atr_arr[i-1] * (period - 1) + tr[i]) / period
    return float(atr_arr[-1]) if atr_arr[-1] > 0 else 0


def get_shanghai_pct(db, trade_date):
    """上证指数涨跌幅."""
    row = db.execute(
        "SELECT change_pct FROM index_daily WHERE code='000001' AND trade_date=?",
        (trade_date,)
    ).fetchone()
    if row:
        # PG adapter translates change_pct -> pct_chg
        val = row.get("pct_chg") or row.get("change_pct")
        if val is not None:
            return float(val)
    return 0.0


def compute_market_breadth(db, trade_date, snapshot, pre_closes):
    """计算涨跌比."""
    up = sum(1 for c, s in snapshot.items()
             if c in pre_closes and pre_closes[c] > 0 and s["close"] > pre_closes[c])
    down = sum(1 for c, s in snapshot.items()
               if c in pre_closes and pre_closes[c] > 0 and s["close"] < pre_closes[c])
    total = up + down
    return up / max(1, total) * 100


def compute_sector_stats(db, snapshot, pre_closes):
    """板块统计."""
    name_map = get_stock_name_map(db)
    industry_gains = defaultdict(list)
    for code, snap in snapshot.items():
        if code in pre_closes and pre_closes[code] > 0:
            gain = (snap["close"] / pre_closes[code] - 1) * 100
            info = name_map.get(code, {})
            ind = info.get("industry", "其他")
            industry_gains[ind].append(gain)

    stats = {}
    for ind, gains in industry_gains.items():
        strong = [g for g in gains if g >= 5]
        avg_gain = np.mean(gains) if gains else 0
        stats[ind] = {
            "peer_count": len(strong),
            "max_gain": round(max(strong), 2) if strong else 0,
            "pct_change": round(avg_gain, 2),
        }
    return stats


def detect_limits(db, trade_date, snapshot, pre_closes):
    """涨停检测."""
    limit_rows = db.execute(
        "SELECT code, up_limit FROM stk_limit WHERE trade_date=?", (trade_date,)
    ).fetchall()
    limit_prices = {}
    for r in limit_rows:
        code = r["code"]
        up = r["up_limit"]
        if up and float(up) > 0:
            limit_prices[code] = float(up)

    result = {}
    for code, snap in snapshot.items():
        close_14 = snap["close"]
        up_lim = limit_prices.get(code, 99999)
        pc = pre_closes.get(code, 0)
        if pc <= 0 or close_14 <= 0:
            result[code] = {"is_at_limit": False, "dist_to_limit_pct": 99}
            continue
        is_at_limit = close_14 >= up_lim * 0.995 if up_lim < 99999 else False
        dist_pct = (up_lim / close_14 - 1) * 100 if close_14 > 0 else 99
        result[code] = {"is_at_limit": is_at_limit, "dist_to_limit_pct": round(dist_pct, 1)}
    return result


def score_stock(code, name, industry, snap, pre_close, db, trade_date,
                limit_info, sector_stats, avg_amounts):
    """秋神午后选股评分 (简版 — 用历史均价替代累计成交额)."""
    close_14 = snap["close"]
    amount_14 = snap["amount"]
    volume_14 = snap["volume"]

    if close_14 <= 0 or pre_close <= 0:
        return None

    # 北交所排除
    if code.startswith(('92', '83', '87', '4')):
        return None

    if 'ST' in name.upper():
        return None

    gain_pct = (close_14 / pre_close - 1) * 100

    board_type = 'star' if code.startswith('688') else ('gem' if code.startswith(('300', '301')) else 'main')

    # 涨幅窗口
    if gain_pct < 7.0:
        return None
    if gain_pct > 25.0:
        return None

    # 已封板淘汰
    is_at_limit = limit_info.get(code, {}).get("is_at_limit", False)
    if is_at_limit:
        return None

    dist_to_limit = limit_info.get(code, {}).get("dist_to_limit_pct", 99)

    # ── F1: 涨幅评分 ──
    if board_type == 'main':
        if gain_pct >= 9.0: gain_score = 18
        elif gain_pct >= 8.5: gain_score = 16
        elif gain_pct >= 8.0: gain_score = 14
        elif gain_pct >= 7.0: gain_score = 12
        else: gain_score = 10
    else:
        if gain_pct >= 18.0: gain_score = 18
        elif gain_pct >= 14.0: gain_score = 16
        elif gain_pct >= 11.0: gain_score = 14
        elif gain_pct >= 8.5: gain_score = 12
        else: gain_score = 10

    day_range = snap["high"] - snap["low"]
    if day_range > 0 and (close_14 - snap["low"]) / day_range > 0.9:
        gain_score += 2
    gain_score = min(18, gain_score)

    # ── F2: 封板潜力 ──
    if dist_to_limit <= 2.0:
        seal_score = 8
        seal_weakness = "即将封板"
    elif dist_to_limit <= 4.0:
        seal_score = 6
        seal_weakness = "接近涨停"
    elif dist_to_limit <= 7.0:
        seal_score = 4
        seal_weakness = "拉升中"
    else:
        seal_score = 2
        seal_weakness = "距涨停较远"

    # ── F3: 均线趋势 ──
    hist_klines = get_kline_history(db, code, trade_date, lookback=60)
    hist_closes = np.array([float(r["close"]) for r in hist_klines])
    hist_highs = np.array([float(r["high"]) for r in hist_klines])
    hist_lows = np.array([float(r["low"]) for r in hist_klines])

    if len(hist_closes) < 20:
        return None

    ma5 = compute_ma(hist_closes, 5)
    ma10 = compute_ma(hist_closes, 10)
    ma20 = compute_ma(hist_closes, 20)

    if ma5 is None or ma10 is None:
        return None

    if ma20 and ma5 > ma10 > ma20 and close_14 > ma20:
        ma_score = 10
    elif ma5 > ma10 and close_14 > ma20:
        ma_score = 8
    elif ma5 > ma10:
        ma_score = 6
    elif close_14 > ma20:
        ma_score = 3
    else:
        ma_score = 1

    # MA多头收紧
    if ma20 and ma20 > 0 and not (ma5 > ma10 > ma20):
        if ma5 > ma10:
            ma_score = min(ma_score, 3)
        else:
            ma_score = min(ma_score, 1)

    # 月跌幅 > 30% 淘汰
    if len(hist_closes) >= 20:
        month_ret = (hist_closes[-1] / hist_closes[-20] - 1) * 100
        if month_ret < -30:
            return None

    # ── F4: 成交额 (用历史日均估值 + 当日实时修正) ──
    avg_amount_yi = avg_amounts.get(code, 0)
    if avg_amount_yi < 0.3:  # 历史太冷门
        return None

    # 当日实时修正: 如果当天有成交, 取 max(历史日均, 当日实时)
    amount_yi = max(avg_amount_yi, amount_14 / 1e8) if amount_14 > 0 else avg_amount_yi

    if amount_yi >= 5.0:
        turnover_score = 10
    elif amount_yi >= 3.0:
        turnover_score = 8
    elif amount_yi >= 1.5:
        turnover_score = 7
    elif amount_yi >= 1.0:
        turnover_score = 6
    elif amount_yi >= 0.5:
        turnover_score = 4
    else:
        return None

    # ── F5: 量比 ──
    hist_vols = np.array([float(r["volume"]) for r in hist_klines[-10:]])
    vol_ma5 = np.mean(hist_vols[-6:-1]) if len(hist_vols) >= 6 else np.mean(hist_vols[:-1])
    vol_ratio = volume_14 / (vol_ma5 / 48) if vol_ma5 > 0 else 1.0  # 单bar vs 日均bar
    if vol_ratio >= 3.0: volume_score = 10
    elif vol_ratio >= 2.5: volume_score = 8
    elif vol_ratio >= 2.0: volume_score = 7
    elif vol_ratio >= 1.5: volume_score = 5
    else: volume_score = 3

    # ── F6: 板块共振 ──
    sector_change = sector_stats.get(industry, {}).get("pct_change", 0)
    peer_count = sector_stats.get(industry, {}).get("peer_count", 0)
    sh_pct = get_shanghai_pct(db, trade_date)

    if peer_count <= 1 and sector_change <= 0:
        return None  # 孤立行情

    if sh_pct == 0: sh_pct = 0.01
    if sector_change == 0: sector_change = 0.01

    if sector_change > 0 and sh_pct < 0:
        resonance_score = 15
    elif sector_change > 0 and sh_pct > 0 and (sector_change - sh_pct) > 3:
        resonance_score = 15
    elif sector_change > 0 and sh_pct > 0 and (sector_change - sh_pct) > 1:
        resonance_score = 12
    elif sector_change > 0 and sh_pct > 0:
        resonance_score = 10
    elif sector_change < 0 and sh_pct < 0 and sector_change > sh_pct:
        resonance_score = 8
    elif sector_change < 0 and sh_pct > 0:
        resonance_score = 3
    else:
        resonance_score = 5

    # ── F7: 板块动量 ──
    if sector_change > 3: sector_momentum_score = 10
    elif sector_change > 1: sector_momentum_score = 7
    elif sector_change > 0: sector_momentum_score = 5
    elif sector_change > -1: sector_momentum_score = 3
    else: sector_momentum_score = 0

    # ── F8: 板块龙头 ──
    if peer_count >= 5: sl_score = 12
    elif peer_count >= 3: sl_score = 9
    elif peer_count >= 2: sl_score = 6
    elif peer_count == 1: sl_score = 3
    else: sl_score = 0

    # ── F9: 分歧不死 ──
    resilience_score = 0
    tod_open = snap["open"]
    tod_low = snap["low"]
    tod_high = snap["high"]
    if tod_open > 0:
        intraday_drop = (tod_low / tod_open - 1) * 100
        high_ratio = close_14 / tod_high if tod_high > 0 else 0
        if tod_low >= tod_open: resilience_score += 3
        elif intraday_drop > -2: resilience_score += 2
        elif intraday_drop > -4: resilience_score += 1
        if high_ratio >= 0.99: resilience_score += 1
    resilience_score = min(4, resilience_score)

    # ── 综合评分 ──
    total = (gain_score + sl_score + min(6, ma_score) + turnover_score +
             resonance_score + 0 + min(15, sector_momentum_score * 1.5) +
             seal_score + resilience_score * 2)

    if total >= 85: grade = "S"
    elif total >= 72: grade = "A"
    elif total >= 60: grade = "B"
    else: grade = "C"

    atr_val = calc_atr(hist_highs, hist_lows, hist_closes, 14)
    atr_pct = (atr_val / close_14 * 100) if close_14 > 0 and atr_val > 0 else 0

    return {
        "code": code, "name": name, "industry": industry,
        "gain_pct": round(gain_pct, 2), "close_14": close_14, "pre_close": pre_close,
        "amount_yi_est": round(amount_yi, 1),
        "total_score": total, "grade": grade,
        "is_at_limit": is_at_limit,
        "gain_score": gain_score, "seal_score": seal_score,
        "ma_score": ma_score, "turnover_score": turnover_score,
        "volume_score": volume_score,
        "resonance_score": resonance_score, "sector_momentum_score": sector_momentum_score,
        "sector_leader_score": sl_score, "resilience_score": resilience_score,
        "sector_change": round(sector_change, 2),
        "peer_count": peer_count, "dist_to_limit": dist_to_limit,
        "seal_weakness": seal_weakness,
        "atr_pct": round(atr_pct, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="今日秋神午后选股")
    parser.add_argument("--date", type=str, default="2026-06-17")
    parser.add_argument("--time", type=str, default="14:00")
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()

    trade_date = args.date
    time_slot = args.time
    top_n = args.top_n

    print("=" * 80)
    print(f"  秋神龙头战法-午后选股 — {trade_date} {time_slot}")
    print("=" * 80)

    t0 = time.time()
    adapter = setup_db()
    from kronos_factors.scorer._db_stub import _get_db

    with _get_db(readonly=True) as db:
        # 1. Snapshot
        snapshot = get_latest_min_snapshot(db, trade_date)
        print(f"  📊 快照: {len(snapshot)} 只")

        # 2. Pre-close
        pre_closes = get_pre_close_map(db, trade_date)
        print(f"  📊 pre_close: {len(pre_closes)} 只")

        # 3. Market breadth
        breadth = compute_market_breadth(db, trade_date, snapshot, pre_closes) if pre_closes else 50
        print(f"  📊 涨跌比: {breadth:.1f}%")

        # 4. 上证
        sh_pct = get_shanghai_pct(db, trade_date)
        print(f"  📊 上证涨幅: {sh_pct:+.2f}%")

        # 5. 涨停检测
        limit_info = detect_limits(db, trade_date, snapshot, pre_closes)
        at_limit = sum(1 for v in limit_info.values() if v["is_at_limit"])
        print(f"  🔒 涨停检测: {at_limit} 只封板")

        # 6. 板块统计
        sector_stats = compute_sector_stats(db, snapshot, pre_closes)
        print(f"  📊 板块统计: {len(sector_stats)} 个行业")

        # 7. 历史均价 (批量预计算, 提速)
        name_map = get_stock_name_map(db)
        avg_amounts = {}
        for code in snapshot:
            if code in pre_closes and pre_closes[code] > 0:
                avg_amounts[code] = get_avg_daily_amount(db, code, trade_date)
        print(f"  📊 历史均价: {len(avg_amounts)} 只计算完成 ({time.time()-t0:.1f}s)")

        # 8. 逐股评分
        scores = []
        for code, snap in snapshot.items():
            if code not in pre_closes or pre_closes[code] <= 0:
                continue
            info = name_map.get(code, {})
            name = info.get("name", code)
            industry = info.get("industry", "其他")
            try:
                res = score_stock(
                    code, name, industry, snap, pre_closes[code], db, trade_date,
                    limit_info, sector_stats, avg_amounts
                )
                if res:
                    scores.append(res)
            except Exception as e:
                continue

        print(f"  ✅ 评分完成: {len(scores)} 只通过筛选 ({time.time()-t0:.1f}s)")

        # 9. 排序 + Top-N
        scores.sort(key=lambda x: -x["total_score"])

        # 板块集中度控制
        if sh_pct > 0.5:
            max_per_sector = 3
            min_grade = "B"
            market_env = "🟢 做多"
        elif sh_pct > -0.5:
            max_per_sector = 2
            min_grade = "A"
            market_env = "🟡 中性"
        else:
            max_per_sector = 1
            min_grade = "S"
            market_env = "🔴 谨慎"

        grade_order = {"S": 0, "A": 1, "B": 2, "C": 3}
        top = []
        sector_counts = {}
        for s in scores:
            ind = s.get("industry", "其他")
            cnt = sector_counts.get(ind, 0)
            if grade_order.get(s.get("grade", "C"), 3) > grade_order.get(min_grade, 2):
                continue
            if cnt < max_per_sector:
                top.append(s)
                sector_counts[ind] = cnt + 1
            if len(top) >= top_n:
                break

        if breadth < 25:
            effective_n = max(3, int(top_n * 0.3))
            top = top[:effective_n]
            market_env += " | 极弱市收紧"

    # ═══════════════════════════════════════════
    # 输出: 选股清单
    # ═══════════════════════════════════════════
    print(f"\n{'=' * 110}")
    print(f"  秋神午后选股清单 — {trade_date} {time_slot}  Top {len(top)} | 市场: {market_env}")
    print(f"  因子: 涨幅+龙头+均线+成交+共振+板块动量+封板潜力+分歧不死")
    print(f"  (成交额使用历史日均估值,盘中数据不完整)")
    print(f"{'=' * 110}")
    print(f"  {'#':<3} {'代码':<8} {'名称':<8} {'总分':<5} {'级':<3} {'涨':<7} {'成交(估)':<9} {'封板潜力':<10} {'分歧':<5} {'龙头':<5} {'板块'}")
    print(f"  {'-' * 100}")
    for i, s in enumerate(top, 1):
        seal_str = f"距{s['dist_to_limit']:.1f}%"
        print(f"  {i:<3} {s['code']:<8} {s['name']:<8} {s['total_score']:<5.0f} {s['grade']:<3} "
              f"{s['gain_pct']:>+5.1f}% {s['amount_yi_est']:<7.1f}亿 {seal_str:<10} "
              f"{s['resilience_score']:<5} {s['sector_leader_score']:<5} {s['industry']}")

    sc = sum(1 for s in top if s['grade'] == 'S')
    ac = sum(1 for s in top if s['grade'] == 'A')
    bc = sum(1 for s in top if s['grade'] == 'B')
    print(f"\n  📊 S级={sc}  A级={ac}  B级={bc} | 市场={market_env}")

    # ── 详细清单 ──
    print(f"\n{'=' * 110}")
    print(f"  📋 详细选股清单")
    print(f"{'=' * 110}")
    for i, s in enumerate(top, 1):
        print(f"  {i:>2}. {s['code']} {s['name']:<8} │ {s['grade']}级 │ "
              f"总分:{s['total_score']:.0f} │ "
              f"涨幅:{s['gain_pct']:>+5.1f}% │ "
              f"成交(估):{s['amount_yi_est']:.1f}亿 │ "
              f"距涨停:{s['dist_to_limit']:.1f}% │ "
              f"共振:{s['resonance_score']} │ "
              f"分歧:{s['resilience_score']} │ "
              f"龙头:{s['sector_leader_score']}/{s['peer_count']} │ "
              f"板块:{s['industry']} │ "
              f"封板:{s['seal_weakness']}")

    # ── 板块分析 ──
    print(f"\n{'=' * 100}")
    print(f"  📊 板块共振分析 (Top 20)")
    print(f"{'=' * 100}")
    sec_groups = defaultdict(list)
    for s in scores[:200]:
        sec_groups[s['industry']].append(s)
    sorted_sec = sorted(sec_groups.items(), key=lambda x: len(x[1]), reverse=True)
    print(f"  {'板块':<16} {'股数':<5} {'均分':<6} {'均涨幅':<7} {'信号'}")
    print(f"  {'-' * 60}")
    for sector, stks in sorted_sec[:20]:
        avg_score = sum(s['total_score'] for s in stks) / len(stks)
        avg_gain = sum(s['gain_pct'] for s in stks) / len(stks)
        if avg_gain > 3: tag = '🟢 强势板块'
        elif avg_gain > 1: tag = '🟡 温和走强'
        elif avg_gain > 0: tag = '⚪ 平盘'
        else: tag = '🔴 弱势'
        top_names = ', '.join(f"{s['code']}({s['total_score']:.0f})" for s in sorted(stks, key=lambda x: -x['total_score'])[:3])
        print(f"  {sector:<16} {len(stks):<5} {avg_score:<6.0f} {avg_gain:>+5.1f}%  {tag:<12} {top_names}")

    print(f"\n  ⏱️ 总耗时: {time.time()-t0:.1f}s")
    print(f"\n  ⚠️ 注意: 盘中成交额为历史估算值, 收盘后可重新运行获取精确结果")

    if hasattr(adapter, 'close'):
        try: adapter.close()
        except: pass


if __name__ == "__main__":
    main()
