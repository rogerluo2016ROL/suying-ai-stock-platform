#!/usr/bin/env python3
"""可转债日内出场信号计算 — 分时 VWAP + KDJ 联合判断.

用法:
    from tools.cb_intraday_exit import find_exit_signal, estimate_cb_exit_price

    bars = [{"open":10.0, "high":10.2, "low":9.9, "close":10.1, "volume":1000, "amount":10100, "time":"09:35"}, ...]
    exit_bar = find_exit_signal(bars)
    if exit_bar:
        print(f"出场信号: {exit_bar['time']} @ {exit_bar['close']}")
"""

import math


def compute_vwap(bars: list[dict]) -> list[float]:
    """计算分时累计 VWAP (成交量加权均价).

    Args:
        bars: 5min K线列表, 每条含 open/high/low/close/volume/amount/time
              按时间升序排列

    Returns:
        与 bars 等长的 VWAP 值列表
    """
    cum_amount = 0.0
    cum_volume = 0.0
    vwaps = []

    for bar in bars:
        amount = float(bar.get("amount") or 0)
        volume = float(bar.get("volume") or 0)
        cum_amount += amount
        cum_volume += volume
        if cum_volume > 0:
            vwaps.append(cum_amount / cum_volume)
        else:
            vwaps.append(0.0)

    return vwaps


def compute_kdj(bars: list[dict], n: int = 9) -> list[dict]:
    """计算分时 KDJ(9,3,3) 指标.

    Args:
        bars: 5min K线列表, 按时间升序
        n: RSV 周期, 默认 9

    Returns:
        与 bars 等长的 [{"K": float, "D": float, "J": float, "RSV": float}]
        前 n-1 根 bar 返回 None (数据不足)
    """
    result = [None] * len(bars)

    if len(bars) < n:
        return result

    k_prev = 50.0
    d_prev = 50.0

    for i in range(n - 1, len(bars)):
        # 计算最近 n 根 bar 的最高价和最低价
        window = bars[i - n + 1 : i + 1]
        hh = max(float(b["high"]) for b in window)
        ll = min(float(b["low"]) for b in window)
        close = float(bars[i]["close"])

        # RSV
        if hh - ll > 0:
            rsv = (close - ll) / (hh - ll) * 100
        else:
            rsv = 50.0  # 无波动时中性

        # KDJ 平滑
        k = 2.0 / 3.0 * k_prev + 1.0 / 3.0 * rsv
        d = 2.0 / 3.0 * d_prev + 1.0 / 3.0 * k
        j = 3.0 * k - 2.0 * d

        # 钳制到合理范围
        k = max(0.0, min(100.0, k))
        d = max(0.0, min(100.0, d))
        j = max(-20.0, min(120.0, j))

        result[i] = {"K": round(k, 2), "D": round(d, 2), "J": round(j, 2), "RSV": round(rsv, 2)}

        k_prev = k
        d_prev = d

    return result


def find_exit_signal(bars: list[dict], j_threshold: float = 95.0,
                     early_j_threshold: float = 100.0,
                     early_cutoff_bar: int = 12) -> dict or None:
    """扫描分时数据, 找到第一个出场信号: close > VWAP AND KDJ_J > threshold.

    Args:
        bars: 5min K线列表, 按时间升序
        j_threshold: J值超买阈值, 默认95
        early_j_threshold: 早盘(<10:00, bar<12) J值阈值, 默认100 (更严格)
        early_cutoff_bar: 早盘截止bar, 默认12(10:00)

    Returns:
        触发信号的 bar 数据, 或 None
    """
    if len(bars) < 10:
        return None

    vwaps = compute_vwap(bars)
    kdjs = compute_kdj(bars, n=9)

    for i in range(9, len(bars)):
        bar = bars[i]
        close = float(bar.get("close") or 0)
        vwap = vwaps[i]
        kdj = kdjs[i]

        if vwap <= 0 or kdj is None:
            continue

        # Opt 4: 早盘需要更高 J 值 (开盘噪声大)
        threshold = early_j_threshold if i < early_cutoff_bar else j_threshold

        if close > vwap and kdj["J"] > threshold:
            return {
                "open": bar.get("open"),
                "high": bar.get("high"),
                "low": bar.get("low"),
                "close": close,
                "volume": bar.get("volume"),
                "amount": bar.get("amount"),
                "time": bar.get("time", f"bar_{i}"),
                "bar_index": i,
                "vwap": round(vwap, 2),
                "kdj_k": kdj["K"],
                "kdj_d": kdj["D"],
                "kdj_j": kdj["J"],
            }

    return None


def find_exit_info(bars: list[dict]) -> dict:
    """返回完整出场分析信息 (含每个 bar 的 VWAP/KDJ, 供调试).

    Returns:
        {
            "signal": dict or None,  # 出场信号
            "last_bar": dict,        # 尾盘 bar
            "bars_analyzed": int,    # 分析过的 bar 数
            "vwap_at_signal": float or None,
            "max_j": float,          # 日内最高 J 值
            "max_close_vs_vwap": float,  # 日内最大 close/vwap 比率
        }
    """
    vwaps = compute_vwap(bars)
    kdjs = compute_kdj(bars, n=9)

    signal = None
    max_j = -100.0
    max_close_ratio = 0.0

    for i in range(9, len(bars)):
        close = float(bars[i].get("close") or 0)
        vwap = vwaps[i]
        kdj = kdjs[i]

        if kdj:
            max_j = max(max_j, kdj["J"])
        if vwap > 0:
            max_close_ratio = max(max_close_ratio, close / vwap)

        if signal is None and vwap > 0 and kdj and close > vwap and kdj["J"] > 90:
            signal = {
                "open": bars[i].get("open"),
                "high": bars[i].get("high"),
                "low": bars[i].get("low"),
                "close": close,
                "volume": bars[i].get("volume"),
                "amount": bars[i].get("amount"),
                "time": bars[i].get("time", f"bar_{i}"),
                "bar_index": i,
                "vwap": round(vwap, 2),
                "kdj_k": kdj["K"],
                "kdj_d": kdj["D"],
                "kdj_j": kdj["J"],
            }

    last_bar = bars[-1] if bars else {}

    return {
        "signal": signal,
        "last_bar": last_bar,
        "bars_analyzed": min(len(bars), len(kdjs)),
        "vwap_at_signal": signal["vwap"] if signal else None,
        "max_j": round(max_j, 2) if max_j > -100 else None,
        "max_close_vs_vwap": round(max_close_ratio, 4) if max_close_ratio > 0 else None,
    }


def find_stop_loss(bars: list[dict], below_vwap_minutes: int = 45,
                   skip_bars: int = 6, min_pct_below: float = 0.5) -> dict or None:
    """止损: 价格持续低于VWAP超过N分钟且偏离>min_pct_below → 平仓.

    Args:
        bars: 5min K线列表
        below_vwap_minutes: 累计低于VWAP分钟数, 默认45
        skip_bars: 跳过开盘前N根bar (避免开盘噪声), 默认6(30min)
        min_pct_below: 价格需低于VWAP的最小百分比, 默认0.5%

    Returns:
        止损信号 bar, 或 None
    """
    if len(bars) < skip_bars + 5:
        return None

    vwaps = compute_vwap(bars)
    below_count = 0

    for i in range(skip_bars, len(bars)):
        close = float(bars[i].get("close") or 0)
        vwap = vwaps[i]
        if vwap <= 0:
            continue

        pct_below = (vwap - close) / vwap * 100

        if pct_below > min_pct_below:
            below_count += 1
            if below_count * 5 >= below_vwap_minutes:
                return {
                    "close": close, "vwap": round(vwap, 2),
                    "time": bars[i].get("time", f"bar_{i}"),
                    "bar_index": i, "type": "stop_loss",
                }
        else:
            below_count = 0  # 回到VWAP附近, 重置

    return None


def check_entry_quality(bars: list[dict], min_bars: int = 3) -> bool:
    """入场质量过滤: 开盘前N根bar均价须在VWAP上方.

    如果开盘15分钟价格持续在VWAP下方, 说明竞价虚高, 不入场.

    Args:
        bars: 5min K线列表
        min_bars: 检查前N根bar, 默认3(15分钟)

    Returns:
        True=通过过滤, False=开盘弱势不入场
    """
    if len(bars) < min_bars:
        return True  # 数据不足, 不拦截

    vwaps = compute_vwap(bars)
    early_closes = [float(bars[i].get("close") or 0) for i in range(min_bars) if vwaps[i] > 0]
    early_vwaps = [vwaps[i] for i in range(min_bars) if vwaps[i] > 0]

    if not early_closes or not early_vwaps:
        return True

    avg_close = sum(early_closes) / len(early_closes)
    avg_vwap = sum(early_vwaps) / len(early_vwaps)

    # 前N根bar均价低于VWAP → 弱势, 不入场
    return avg_close > avg_vwap


def find_trailing_stop(bars: list[dict], pct_from_high: float = 2.0,
                       skip_bars: int = 6) -> dict or None:
    """百分比回撤止损: 从日内最高点回撤超过 pct_from_high% → 平仓.

    Args:
        bars: 5min K线列表
        pct_from_high: 从最高点回撤百分比, 默认2%
        skip_bars: 跳过开盘前N根bar, 默认6(30min)

    Returns:
        止损信号 bar, 或 None
    """
    if len(bars) < skip_bars:
        return None

    intraday_high = 0.0
    for i in range(len(bars)):
        close = float(bars[i].get("close") or 0)
        if close > intraday_high:
            intraday_high = close

        if i >= skip_bars and intraday_high > 0:
            drawdown = (intraday_high - close) / intraday_high * 100
            if drawdown >= pct_from_high:
                return {
                    "close": close, "time": bars[i].get("time", f"bar_{i}"),
                    "bar_index": i, "type": "trailing_stop",
                    "intraday_high": round(intraday_high, 2),
                    "drawdown_pct": round(drawdown, 2),
                }

    return None


def find_take_profit(bars: list[dict], cb_open: float, stock_open: float,
                     target_pct: float = 3.0, skip_bars: int = 3) -> dict or None:
    """止盈信号: 正股日内涨幅达到 target_pct → 止盈.

    Args:
        bars: 5min K线列表
        cb_open: 转债开盘价 (未使用, 保持接口一致)
        stock_open: 正股开盘价
        target_pct: 止盈目标涨幅(%), 默认3%
        skip_bars: 跳过开盘前N根bar, 默认3(15min)

    Returns:
        止盈信号 bar, 或 None
    """
    if len(bars) < skip_bars or not stock_open or stock_open <= 0:
        return None

    for i in range(skip_bars, len(bars)):
        close = float(bars[i].get("close") or 0)
        stock_ret = (close - stock_open) / stock_open * 100
        if stock_ret >= target_pct:
            return {
                "close": close, "time": bars[i].get("time", f"bar_{i}"),
                "bar_index": i, "type": "take_profit",
                "stock_ret": round(stock_ret, 2),
            }
    return None


def adaptive_take_profit_target(atr_pct: float) -> float:
    """自适应止盈: 高波动→高目标, 低波动→低目标.

    Args:
        atr_pct: ATR(14) / 收盘价 * 100 (波动率百分比)

    Returns:
        止盈目标 (%)
    """
    if atr_pct is None or atr_pct <= 0:
        return 3.0  # 默认
    if atr_pct >= 5.0:
        return 5.0   # 高波动: 让利润奔跑
    elif atr_pct >= 3.0:
        return 4.0   # 中高波动
    elif atr_pct >= 2.0:
        return 3.0   # 正常波动
    else:
        return 2.0   # 低波动: 见好就收


def generate_trade_signals(picks: list[dict], atr_map: dict = None) -> list[dict]:
    """生成可执行的交易信号.

    Args:
        picks: 引擎选股结果, 每项含 code/name/stk_code/price/premium_rate/details
        atr_map: {stk_code: atr_pct} 正股波动率

    Returns:
        交易信号列表, 每项:
        {
            "code": "123118.SZ", "name": "惠城转债", "stk_code": "300779",
            "entry_price": 625.15,           # 竞价入场价
            "take_profit_pct": 4.0,           # 自适应止盈目标(%)
            "take_profit_price": 650.16,      # 止盈价
            "trailing_stop_pct": 2.0,         # 回撤止损(%)
            "stop_loss_price": 612.65,        # 初始止损价(-2%)
            "kdj_exit_threshold": 95,         # KDJ出场J值
            "max_hold_minutes": 240,          # 最大持仓(尾盘前)
            "grade": "A",                     # 等级
            "suggested_weight": 0.15,         # 建议仓位(15% of capital)
        }
    """
    atr_map = atr_map or {}
    signals = []
    for p in picks:
        stk = p.get("stk_code", "")
        atr_pct = atr_map.get(stk) if atr_map else None
        tp_pct = adaptive_take_profit_target(atr_pct)
        entry = p.get("price") or 0

        grade = p.get("grade", "B")
        weight = {"S": 0.20, "A": 0.15, "B": 0.10, "C": 0.05}.get(grade, 0.08)

        signals.append({
            "code": p.get("code"),
            "name": p.get("name"),
            "stk_code": stk,
            "entry_price": entry,
            "take_profit_pct": tp_pct,
            "take_profit_price": round(entry * (1 + tp_pct / 100 * 0.85), 2) if entry else None,
            "trailing_stop_pct": 2.0,
            "stop_loss_price": round(entry * 0.98, 2) if entry else None,
            "kdj_exit_threshold": 95,
            "max_hold_minutes": 240,
            "grade": grade,
            "suggested_weight": weight,
            "premium_rate": p.get("premium_rate"),
            "atr_pct": round(atr_pct, 2) if atr_pct else None,
            "sector": p.get("sector"),
            "total_score": p.get("total_score"),
        })
    return signals


def estimate_cb_exit_price(cb_open: float, stock_open: float,
                           stock_exit_close: float, premium_rate: float = None) -> float:
    """根据正股日内涨幅估算转债出场价 (动态 delta).

    Args:
        cb_open: 转债开盘价
        stock_open: 正股开盘价
        stock_exit_close: 正股出场时的 bar close
        premium_rate: 转股溢价率(%), 用于动态调整 delta

    Returns:
        估算的转债出场价
    """
    if not stock_open or stock_open <= 0:
        return cb_open

    stock_return = (stock_exit_close - stock_open) / stock_open

    # Opt 2: 动态 delta — 折价转债跟涨更紧
    if premium_rate is not None:
        if premium_rate <= 0:
            delta = 0.95   # 折价: 几乎完全跟涨
        elif premium_rate <= 15:
            delta = 0.85   # 低溢价: 紧跟
        elif premium_rate <= 30:
            delta = 0.70   # 中溢价: 部分跟涨
        else:
            delta = 0.55   # 高溢价: 弱跟涨
    else:
        delta = 0.80  # 无溢价数据时保守估计

    cb_exit = cb_open * (1 + stock_return * delta)
    return round(cb_exit, 2)


# ── 命令行调试入口 ──
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    # 演示: 加载一天的 stk_mins 数据计算 VWAP + KDJ
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    import psycopg2
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor()

    # 取一只股票的分时数据
    code = sys.argv[1] if len(sys.argv) > 1 else "000001"
    date = sys.argv[2] if len(sys.argv) > 2 else None

    if not date:
        cur.execute("SELECT MAX(DATE(trade_time)) FROM stk_mins WHERE freq='5min' AND code=%s", (code,))
        date = str(cur.fetchone()[0])

    cur.execute("""
        SELECT trade_time, open, high, low, close, volume, amount
        FROM stk_mins
        WHERE code = %s AND DATE(trade_time) = %s AND freq = '5min'
        ORDER BY trade_time
    """, (code, date))
    rows = cur.fetchall()

    if not rows:
        print(f"No data for {code} on {date}")
        conn.close()
        sys.exit(1)

    bars = []
    for r in rows:
        bars.append({
            "time": str(r[0])[-8:],
            "open": float(r[1] or 0),
            "high": float(r[2] or 0),
            "low": float(r[3] or 0),
            "close": float(r[4] or 0),
            "volume": float(r[5] or 0),
            "amount": float(r[6] or 0),
        })

    conn.close()

    exit_info = find_exit_info(bars)
    sig = exit_info["signal"]

    print(f"Stock: {code}  Date: {date}")
    print(f"Bars: {len(bars)} (analyzed: {exit_info['bars_analyzed']})")
    print(f"Open: {bars[0]['open']:.2f}  Close: {bars[-1]['close']:.2f}")
    print(f"Max J: {exit_info['max_j']}  Max close/VWAP: {exit_info['max_close_vs_vwap']}")

    if sig:
        print(f"\n[SIGNAL] Time: {sig['time']}  Bar: {sig['bar_index']}")
        print(f"  Close: {sig['close']:.2f}  VWAP: {sig['vwap']:.2f}")
        print(f"  K={sig['kdj_k']}  D={sig['kdj_d']}  J={sig['kdj_j']}")
        open_px = bars[0]["open"]
        ret = (sig["close"] - open_px) / open_px * 100 if open_px > 0 else 0
        print(f"  Return @ signal: {ret:+.2f}%")
        # 持有到收盘
        close_ret = (bars[-1]["close"] - open_px) / open_px * 100 if open_px > 0 else 0
        print(f"  Return @ close: {close_ret:+.2f}%")
    else:
        print(f"\n[NO SIGNAL] No exit trigger found today")
        open_px = bars[0]["open"]
        close_ret = (bars[-1]["close"] - open_px) / open_px * 100 if open_px > 0 else 0
        print(f"  Return @ close: {close_ret:+.2f}%")
