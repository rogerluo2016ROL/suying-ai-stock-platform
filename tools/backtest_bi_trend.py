#!/usr/bin/env python3
"""毕师傅趋势启动战法 — 回测脚本.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/backtest_bi_trend.py --month 2026-06 --top-n 20
"""

import argparse, json, os, sys, time
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
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(pg_url)
    if adapter is None:
        raise RuntimeError(f"无法连接数据库: {pg_url}")
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def get_trading_days(db, month_prefix="2026-06"):
    """获取指定月份有 daily_kline 数据的交易日."""
    y, m = month_prefix.split("-")
    start = f"{y}-{m}-01"
    # Use next month's first day as exclusive upper bound
    nm = int(m) + 1
    ny = int(y)
    if nm > 12:
        nm = 1
        ny += 1
    end = f"{ny}-{nm:02d}-01"
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date >= ? AND trade_date < ? ORDER BY trade_date",
        (start, end)
    ).fetchall()
    return [r["trade_date"] for r in rows]


def get_adjusted_kline(db, code, trade_date):
    """T-008: 读单日 OHLC + JOIN adj_factor 做后复权, 消除除权日 close 跳变失真.

    后复权公式: adj_price = raw_price * (latest_factor / on_date_factor)
    其中 latest_factor 取该 code 历史最新 adj_factor (统一基准).

    对单笔回测 (T 买入 / T+1 卖出), 两端 latest_factor 在比值中约掉,
    故真实收益只取决于 raw_price_T * f_T 与 raw_price_T+1 * f_T+1 的比值.

    Returns: dict(open, high, low, close) 后复权价; 或 None (无数据/无 adj_factor 表).
    adj_applied: bool 表示是否做了复权 (False = adj_factor 缺失, 退回原始价).
    """
    row = db.execute(
        "SELECT k.open, k.high, k.low, k.close, a.adj_factor AS f_t, "
        "(SELECT a2.adj_factor FROM adj_factor a2 WHERE a2.code=k.code "
        " ORDER BY a2.trade_date DESC LIMIT 1) AS f_latest "
        "FROM daily_kline k LEFT JOIN adj_factor a "
        "ON k.code=a.code AND k.trade_date=a.trade_date "
        "WHERE k.code=? AND k.trade_date=?",
        (code, trade_date)
    ).fetchone()
    if not row or not row["close"]:
        return None

    out = {
        "open": float(row["open"]) if row["open"] else None,
        "high": float(row["high"]) if row["high"] else None,
        "low": float(row["low"]) if row["low"] else None,
        "close": float(row["close"]),
        "adj_applied": False,
    }
    f_t = float(row["f_t"]) if row["f_t"] else None
    f_latest = float(row["f_latest"]) if row["f_latest"] else None
    # 需 on_date factor 与 latest factor 都有且 >0 才能做后复权
    if f_t and f_latest and f_t > 0 and f_latest > 0:
        ratio = f_latest / f_t
        for col in ("open", "high", "low", "close"):
            if out[col] is not None:
                out[col] = out[col] * ratio
        out["adj_applied"] = True
    return out


# ── 阶段1 AC-1/4: 多日持有回测引擎 (simulate_position) ──
# adjust_bars / simulate_position 为纯函数 (接受 OHLC bar 序列, 不依赖 db),
# 便于离线单测 (backend/tests/ml/test_simulate_position.py). DB 查询由
# get_adjusted_bars 薄包装层提供. 详见 PRD phase1-backtest-credibility AC-1/4.

# 策略声明的 trailing 分级 (复刻 bi_trend_launch.SELL_TRAILING Tier1-5, 不重新调参):
#   (profit_from_entry_pct, drawdown_stop_pct) — 盈利达阈值后, 从高点回撤超 stop 则退出
#   来源: bi_trend_launch.py SELL_TRAILING_TIER*_PROFIT / *_STOP (V5.5)
TRAILING_TIERS = [
    (60, -12),   # T5: 盈利>60% -> 从高点回撤 -12%
    (30, -8),    # T4: 30-60%   -> -8%
    (15, -5),    # T3: 15-30%   -> -5%
    (5, -5),     # T2: 5-15%    -> -5%
]


def adjust_bars(bars):
    """对原始 OHLC bar 序列做后复权 (Q-4 / AC-1 前置).

    后复权: 每根 bar 的 OHLC 乘以该日 adj_factor (adj_price = price * adj_factor[on_date]).
    以最早为基准, 同股跨日可比, 消除除权除息跳空. 缺 adj_factor 的 bar 按 1.0 处理 (不崩).

    对多日持有算 return = exit/entry - 1, 入场/出场各乘各自 on_date adj_factor,
    return 比例正确 (分子分母按各自日因子缩放, 跨除权日不失真).
    """
    out = []
    for b in bars:
        adj = b.get("adj")
        adj = float(adj) if adj else 1.0
        out.append({
            "date": b["date"],
            "open": float(b["open"]) * adj,
            "high": float(b["high"]) * adj,
            "low": float(b["low"]) * adj,
            "close": float(b["close"]) * adj,
        })
    return out


def _trailing_stop_pct(profit_from_entry_pct):
    """按策略 SELL_TRAILING 分级返回移动止损回撤阈值 (复刻 bi_trend_launch Tier1-5).

    Args: profit_from_entry_pct — 从入场价起算的最高涨幅 (高点相对入场, 百分比)
    Returns: 回撤阈值 (负百分比, 如 -5); 盈利<5% 未激活返回 None
    """
    for profit_threshold, stop in TRAILING_TIERS:
        if profit_from_entry_pct >= profit_threshold:
            return stop
    return None


def simulate_position(bars, signal_idx, hold_days, tp_pct=None,
                      stop_loss_pct=None, trailing_active_pct=5,
                      trailing_drawdown_pct=None):
    """多日持有回测引擎 (AC-1 多日持有 + AC-4 T+1 open 入场).

    纯函数: 接受后复权 OHLC bar 序列 + 信号日 index, 逐日模拟持有退出.
      - 入场: signal_idx 为信号日 T, T+1 (signal_idx+1) 以 open 买入 (消除同日收盘成交前视).
      - 逐日循环 (T+1 起, 共 hold_days 持有日) 检查退出, 优先级 stop > TP > trailing
        (保守, 同日同时触及避免乐观偏差):
        1. stop_loss: 当日 open<=stop (跳空按 open) 或 low<=stop (按 stop 价)
        2. TP: 当日 high>=tp_price (按 tp 价)
        3. trailing: 盈利达 trailing_active_pct 后, 按分级 trailing 从高点回撤退出
        4. 到期: 持满 hold_days 日以收盘退出

    Args:
        bars: 后复权 bar 序列 (list[dict] 含 date/open/high/low/close)
        signal_idx: 信号日 T 的 index
        hold_days: 持有天数 (策略声明 5/7/10)
        tp_pct: 止盈百分比 (20/25, None=无 TP)
        stop_loss_pct: 止损百分比 (-12, None=无止损)
        trailing_active_pct: trailing 激活盈利阈值 (默认 5)
        trailing_drawdown_pct: 显式 trailing 回撤阈值 (None=用策略分级)
    Returns: dict(entry_date/entry_price/exit_date/exit_price/exit_reason/
                  actual_hold_days/gross_return) 或 None (T+1 无 bar = pending)
    """
    entry_idx = signal_idx + 1
    if entry_idx >= len(bars):
        return None  # 无 T+1, pending
    entry_bar = bars[entry_idx]
    entry_price = float(entry_bar["open"])
    entry_date = entry_bar["date"]
    if entry_price <= 0:
        return None

    tp_price = entry_price * (1 + tp_pct / 100) if (tp_pct and tp_pct > 0) else None
    stop_price = entry_price * (1 + stop_loss_pct / 100) if (stop_loss_pct and stop_loss_pct < 0) else None

    highest_since_entry = entry_price
    for offset in range(hold_days):
        idx = entry_idx + offset
        if idx >= len(bars):
            last = bars[-1]
            return _make_exit("data_truncated", float(last["close"]),
                              last["date"], offset, entry_price, entry_date)
        bar = bars[idx]
        day_open, day_high = float(bar["open"]), float(bar["high"])
        day_low, day_close = float(bar["low"]), float(bar["close"])
        highest_since_entry = max(highest_since_entry, day_high)

        # 1. stop_loss (跳空按 open, 否则按 stop 价)
        if stop_price is not None:
            if day_open <= stop_price:
                return _make_exit("stop_loss", day_open, bar["date"], offset, entry_price, entry_date)
            if day_low <= stop_price:
                return _make_exit("stop_loss", stop_price, bar["date"], offset, entry_price, entry_date)
        # 2. TP
        if tp_price is not None and day_high >= tp_price:
            return _make_exit("take_profit", tp_price, bar["date"], offset, entry_price, entry_date)
        # 3. trailing
        profit_from_entry = (highest_since_entry / entry_price - 1) * 100
        if profit_from_entry >= trailing_active_pct:
            dd_stop = (trailing_drawdown_pct if trailing_drawdown_pct is not None
                       else _trailing_stop_pct(profit_from_entry))
            if dd_stop is not None:
                trailing_price = highest_since_entry * (1 + dd_stop / 100)
                if day_open <= trailing_price:
                    return _make_exit("trailing_stop", day_open, bar["date"], offset, entry_price, entry_date)
                if day_low <= trailing_price:
                    return _make_exit("trailing_stop", trailing_price, bar["date"], offset, entry_price, entry_date)
        # 4. 到期
        if offset == hold_days - 1:
            return _make_exit("hold_to_maturity", day_close, bar["date"], offset, entry_price, entry_date)

    last = bars[min(entry_idx + hold_days - 1, len(bars) - 1)]
    return _make_exit("hold_to_maturity", float(last["close"]), last["date"],
                      hold_days - 1, entry_price, entry_date)


def _make_exit(reason, price, date, hold_offset, entry_price, entry_date):
    """构造 simulate_position 退出结果 dict."""
    return {
        "entry_date": entry_date,
        "entry_price": float(entry_price),
        "exit_date": date,
        "exit_price": float(price),
        "exit_reason": reason,
        "actual_hold_days": hold_offset + 1,  # 入场日为第 1 持有日
        "gross_return": (price / entry_price - 1) * 100,
    }


def get_adjusted_bars(db, code, signal_date, max_hold_days=10):
    """从 PG 读 signal_date 当日 + 之后 max_hold_days+1 交易日的原始 OHLC + adj_factor,
    返回后复权 bar 序列 (供 simulate_position 消费). DB 薄包装层. AC-1 Q-4 复权."""
    # 复权因子 forward-fill: adj_factor 缺失某交易日时 (如 2026-06-17 全表缺口),
    # 用该 code 此前最近一个非空 adj_factor 填充, 而非塌成 1.0. 复权因子单调缓慢变化,
    # 缺一天填前值才连续; 若 fallback 1.0 会让后复权序列出现 -85% 假跳变,
    # 误触发 stop_loss (data-defect-2026-06-17: 中际旭创/兆易创新畸形 -85% 亏损根因).
    # 全无历史 adj_factor 时才退回 1.0 (新股/无复权数据, 与旧行为一致).
    rows = db.execute(
        "SELECT d.trade_date AS date, d.open, d.high, d.low, d.close, "
        "COALESCE(a.adj_factor, "
        "  (SELECT a2.adj_factor FROM adj_factor a2 "
        "   WHERE a2.code = d.code AND a2.trade_date <= d.trade_date "
        "   ORDER BY a2.trade_date DESC LIMIT 1), "
        "  1.0) AS adj "
        "FROM daily_kline d LEFT JOIN adj_factor a "
        "ON a.code = d.code AND a.trade_date = d.trade_date "
        "WHERE d.code = ? AND d.trade_date >= ? "
        "ORDER BY d.trade_date ASC LIMIT ?",
        (code, signal_date, max_hold_days + 2)
    ).fetchall()
    if not rows:
        return []
    bars = [{"date": str(r["date"]), "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"], "adj": r["adj"]} for r in rows]
    return adjust_bars(bars)


def simulate_pick(db, code, signal_date, hold_days=None, tp_pct=None,
                  stop_loss_pct=None, cost_bps=0):
    """对一只 pick 跑多日持有回测 (AC-1/4/6 + Q-4). 参数从 pick 自带字段传入
    (hold_days/tp/sl 来自策略声明, 不引入新参数). 成本 cost_bps 往返一次性扣.

    Returns: simulate_position 结果 + code/signal_date/net_return, 或 None (pending).
    """
    hd = hold_days or 5
    bars = get_adjusted_bars(db, code, signal_date, max_hold_days=hd)
    if len(bars) < 2:
        return None
    result = simulate_position(bars, signal_idx=0, hold_days=hd,
                               tp_pct=tp_pct, stop_loss_pct=stop_loss_pct)
    if result is None:
        return None
    result["code"] = code
    result["signal_date"] = signal_date
    result["hold_days_target"] = hold_days
    result["tp_pct"] = tp_pct
    result["stop_loss_pct"] = stop_loss_pct
    result["net_return"] = result["gross_return"] - cost_bps / 100
    return result


def get_next_day_return(db, code, trade_date, stop_loss_pct=None, adjusted=True):
    """获取次日收益率: T日收盘买入, T+1日收盘卖出 (可选止损).

    V13 P1: 支持盘中止损模拟.
    止损逻辑: 如果 T+1日最低价触及止损价, 以止损价退出; 否则以收盘价退出.
    跳空低开: 如果开盘价已低于止损价, 以开盘价退出 (模拟竞价止损).

    T-008: adjusted=True 时 entry/exit 价走后复权 (get_adjusted_kline),
    消除除权日 close 跳变失真 (单笔收益由 f_T/f_T+1 校正, latest_factor 在比值中约掉).
    adjusted=False 退回原始价 (旧行为, 仅用于复现/对比).
    """
    if adjusted:
        entry = get_adjusted_kline(db, code, trade_date)
        if not entry or entry["close"] is None:
            return None, None
        # T+1 日: 取 trade_date 之后首个有数据的交易日
        next_td_row = db.execute(
            "SELECT trade_date FROM daily_kline WHERE code=? AND trade_date > ? "
            "ORDER BY trade_date ASC LIMIT 1",
            (code, trade_date)
        ).fetchone()
        if not next_td_row:
            return None, None
        nxt = get_adjusted_kline(db, code, next_td_row["trade_date"])
        if not nxt or nxt["close"] is None:
            return None, None
        entry_price = entry["close"]
        next_row = nxt  # dict with open/high/low/close (后复权)
    else:
        entry_row = db.execute(
            "SELECT close FROM daily_kline WHERE code=? AND trade_date=?",
            (code, trade_date)
        ).fetchone()
        if not entry_row or not entry_row["close"]:
            return None, None
        entry_price = float(entry_row["close"])
        next_row = db.execute(
            "SELECT open, high, low, close FROM daily_kline WHERE code=? AND trade_date > ? "
            "ORDER BY trade_date ASC LIMIT 1",
            (code, trade_date)
        ).fetchone()
        if not next_row or not next_row["close"]:
            return None, None
        next_row = {"open": float(next_row["open"]) if next_row["open"] else None,
                    "high": float(next_row["high"]) if next_row["high"] else None,
                    "low": float(next_row["low"]) if next_row["low"] else None,
                    "close": float(next_row["close"])}

    exit_price = next_row["close"]
    stopped = False

    if stop_loss_pct is not None and stop_loss_pct < 0:
        stop_price = entry_price * (1 + stop_loss_pct / 100)
        next_open = next_row["open"] if next_row["open"] is not None else exit_price
        next_low = next_row["low"] if next_row["low"] is not None else exit_price

        # 跳空低开: 开盘即跌破止损
        if next_open <= stop_price:
            exit_price = next_open
            stopped = True
        # 盘中触及止损
        elif next_low <= stop_price:
            exit_price = stop_price
            stopped = True

    ret = (exit_price / entry_price - 1) * 100
    return ret, stopped


def get_st_codes_on(db, trade_date):
    """AC-2: T 日已戴帽/退市股集合 (st_history 区间过滤).

    幸存者偏差修复 — 选股池后置过滤, 剔除 trade_date 当日处于 ST/*ST 区间的股,
    防止"今日已退市/戴帽"被误纳入历史回测. 数据源 st_history (Tushare namechange
    历史区间, source='tushare_namechange'; 积分不足 fallback 'stocks_is_st_snapshot').

    返回: set[str] T 日戴帽的 code (含 sh./sz./bj. 前缀, 与 daily_kline.code 一致).
    """
    rows = db.execute(
        "SELECT DISTINCT code FROM st_history "
        "WHERE start_date <= ? AND (end_date IS NULL OR end_date > ?)",
        (trade_date, trade_date)
    ).fetchall()
    return {r["code"] for r in rows}


def run_backtest_day(db, trade_date, top_n=20, st_filter=True):
    """单日回测 V2.0 — 使用优化引擎+市场熔断 + ST 后置过滤 (AC-2).

    st_filter=True (默认): 选股结果按 trade_date JOIN st_history 剔除当时戴帽股
    (幸存者偏差修复). 不修改 strategy engine (铁律), 仅 backtest 口径过滤.
    """
    from kronos_factors.engine.bi_trend_launch import run_bi_screening

    top, all_scores, market_info = run_bi_screening(db, trade_date, top_n=top_n)
    n_pre = len(top)
    n_st_removed = 0
    if st_filter:
        st_codes = get_st_codes_on(db, trade_date)
        if st_codes:
            top = [s for s in top if s["code"] not in st_codes]
            n_st_removed = n_pre - len(top)
    return {
        "trade_date": trade_date,
        "total_qualified": len(all_scores),
        "top_picks": top,
        "market_info": market_info,
        "n_st_removed": n_st_removed,  # AC-2: T 日 ST 过滤剔除数
    }


def analyze_results(results, db, adjusted=True, multi_day=False, cost_bps=0):
    """分析回测结果.

    - 默认 (multi_day=False): 单日口径 (T收盘买 T+1收盘卖), 阶段0 AC-11, T-008 后复权.
    - multi_day=True (阶段1 AC-1/4/6): 多日持有走 simulate_pick, 实现 hold_days 5/7/10 +
      TP 20/25% + trailing 分级 + stop_loss 逐日检查, T+1 open 入场. pick 产物含
      entry_price/exit_price/exit_reason/actual_hold_days/gross_return/net_return/weighted_return.
    - cost_bps: 往返成本 (bp), 两种模式都从收益扣 (AC-11 口径).
    """
    all_picks = []
    for r in results:
        td = r["trade_date"]
        for s in r["top_picks"]:
            sl = s.get("stop_loss")  # 负数 (如 -12) 或 None
            weight = s.get("weight", 1.0)
            hd = s.get("hold_days")
            tp = s.get("take_profit")

            if multi_day:
                # 阶段1 AC-1/4: 多日持有 simulate_pick (T+1 open 入场 + TP/trailing/stop 逐日)
                sim = simulate_pick(db, s["code"], td, hold_days=hd, tp_pct=tp,
                                    stop_loss_pct=sl, cost_bps=cost_bps)
                if sim is None:
                    pick = {"trade_date": td, "code": s["code"], "name": s["name"],
                            "grade": s["grade"], "signal": s["signal"], "weight": weight,
                            "hold_days": hd, "stop_loss": sl, "take_profit": tp,
                            "gross_return": None, "net_return": None,
                            "exit_reason": "pending", "weighted_return": None}
                else:
                    gross = sim["gross_return"]
                    net = sim["net_return"]
                    pick = {
                        "trade_date": td, "code": s["code"], "name": s["name"],
                        "industry": s.get("industry"), "grade": s["grade"],
                        "total_score": s.get("total_score"), "signal": s["signal"],
                        "obv_days_above": s.get("obv_days_above"),
                        "obv_level": s.get("obv_level"), "wr_level": s.get("wr_level"),
                        "vol_level": s.get("vol_level"),
                        "weight": weight,
                        "hold_days": hd, "stop_loss": sl, "take_profit": tp,
                        "checklist_score": s.get("checklist_score"),
                        "entry_date": sim["entry_date"], "entry_price": sim["entry_price"],
                        "exit_date": sim["exit_date"], "exit_price": sim["exit_price"],
                        "exit_reason": sim["exit_reason"],
                        "actual_hold_days": sim["actual_hold_days"],
                        "gross_return": gross, "net_return": net,
                        # AC-6: weighted_return = net_return * weight (S级 0.6x 降权)
                        "weighted_return": net * weight,
                    }
                all_picks.append(pick)
                continue

            # 单日口径 (向后兼容)
            ret, stopped = get_next_day_return(db, s["code"], td, stop_loss_pct=sl, adjusted=adjusted)
            net = (ret - cost_bps / 100) if ret is not None else None
            all_picks.append({
                "trade_date": td, "code": s["code"], "name": s["name"],
                "industry": s.get("industry"), "grade": s["grade"],
                "total_score": s.get("total_score"), "signal": s["signal"],
                "obv_days_above": s.get("obv_days_above"),
                "obv_level": s.get("obv_level"), "wr_level": s.get("wr_level"),
                "vol_level": s.get("vol_level"),
                "next_day_return": ret, "net_return": net, "stopped": stopped,
                "weight": weight,
                "hold_days": hd, "stop_loss": sl, "take_profit": tp,
                "trailing_stop": s.get("trailing_stop"),
                "checklist_score": s.get("checklist_score"),
                "weighted_return": (net * weight) if net is not None else None,
            })

    ret_key = "gross_return" if multi_day else "next_day_return"
    valid = [p for p in all_picks if p[ret_key] is not None]
    pending = len(all_picks) - len(valid)

    if not valid:
        print("⚠️ 无有效收益数据")
        return all_picks

    returns = np.array([p[ret_key] for p in valid])
    net_returns = np.array([p["net_return"] for p in valid if p["net_return"] is not None])
    weighted = np.array([p["weighted_return"] for p in valid if p["weighted_return"] is not None])
    win_mask = returns > 0
    win_count = win_mask.sum()
    total = len(valid)

    mode_label = "多日持有 (AC-1)" if multi_day else "单日 T+1"
    print(f"\n{'=' * 80}")
    print(f"  毕师傅趋势启动战法 — 回测汇总 [{mode_label}]")
    print(f"  {len(results)} 交易日 | {total} 笔交易 | pending={pending} | 成本 {cost_bps}bp")
    if not multi_day:
        # M08: 单日口径 (T收盘买 T+1收盘卖) 含成交假设前视 — T日 close 物理上不可成交,
        # 系统性高估收益, 仅作向后兼容对比, 禁止对外披露/据此投资决策.
        print(f"  ⚠️ 单日口径含成交假设前视 (T收盘买入不可成交), 仅对比用, 禁止对外披露")
    print(f"{'=' * 80}")
    print(f"  📊 总体统计 (毛 {ret_key}):")
    print(f"    胜率:      {win_count}/{total} = {win_count/total*100:.1f}%")
    print(f"    均值收益:  {returns.mean():+.2f}%")
    print(f"    中位数:    {np.median(returns):+.2f}%")
    print(f"    累计收益:  {returns.sum():+.2f}%")
    print(f"    标准差:    {returns.std():.2f}%")
    if len(net_returns):
        print(f"  📊 净收益 (扣 {cost_bps}bp 成本):")
        print(f"    净均值:    {net_returns.mean():+.4f}%  净中位数: {np.median(net_returns):+.4f}%")
        print(f"    净累计:    {net_returns.sum():+.2f}%  净胜率: {(net_returns>0).sum()}/{len(net_returns)} = {(net_returns>0).sum()/len(net_returns)*100:.1f}%")
    if len(weighted):
        print(f"  📊 加权 (AC-6, S级0.6x):")
        print(f"    加权均值:  {weighted.mean():+.4f}%  加权累计: {weighted.sum():+.2f}%")
    if multi_day:
        reasons = {}
        holds = []
        for p in valid:
            reasons[p["exit_reason"]] = reasons.get(p["exit_reason"], 0) + 1
            holds.append(p["actual_hold_days"])
        holds = np.array(holds)
        print(f"  📊 退出原因: {reasons}")
        print(f"     实际持有天数: 均值 {holds.mean():.1f} 中位 {np.median(holds):.0f} 范围 {holds.min()}-{holds.max()}")

    # ── 按评级分组 ──
    print(f"\n  📊 按评级分组:")
    print(f"  {'评级':<6} {'笔数':<6} {'胜率':<8} {'均值':<8} {'中位数':<8} {'盈亏比':<12} {'最大盈':<8} {'最大亏':<8}")
    print(f"  {'-' * 78}")
    for grade in ["S", "A", "B", "C"]:
        g = [p for p in valid if p["grade"] == grade]
        if not g:
            continue
        gr = np.array([p[ret_key] for p in g])
        gw = (gr > 0).sum()
        pw = gr[gr > 0].mean() if (gr > 0).any() else 0
        nw = gr[gr <= 0].mean() if (gr <= 0).any() else 0
        print(f"  {grade:<6} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}% "
              f"{np.median(gr):>+7.2f}% {pw:>+6.2f}/{nw:>+6.2f} {gr.max():>+7.2f}% {gr.min():>+7.2f}%")

    # ── 按信号分组 ──
    print(f"\n  📊 按信号分组:")
    print(f"  {'信号':<14} {'笔数':<6} {'胜率':<8} {'均值':<8} {'中位数':<8} {'盈亏比':<12}")
    print(f"  {'-' * 60}")
    for sig in ["strong_buy", "buy", "watch", "no_signal"]:
        g = [p for p in valid if p["signal"] == sig]
        if not g:
            continue
        gr = np.array([p[ret_key] for p in g])
        gw = (gr > 0).sum()
        pw = gr[gr > 0].mean() if (gr > 0).any() else 0
        nw = gr[gr <= 0].mean() if (gr <= 0).any() else 0
        print(f"  {sig:<14} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}% "
              f"{np.median(gr):>+7.2f}% {pw:>+6.2f}/{nw:>+6.2f}")

    # ── V13 P1: 加权止损统计 (单日模式 stopped; 多日模式 exit_reason=stop_loss) ──
    if multi_day:
        stopped_picks = [p for p in valid if p["exit_reason"] == "stop_loss"]
        if stopped_picks:
            print(f"\n  🛑 止损触发: {len(stopped_picks)}/{total} 笔 ({len(stopped_picks)/total*100:.0f}%)")
            for p in stopped_picks[:5]:
                print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']}级 → {p['gross_return']:+.2f}% (持{p['actual_hold_days']}日)")
    else:
        stopped_count = sum(1 for p in valid if p.get("stopped"))
        if stopped_count > 0:
            print(f"\n  🛑 止损触发: {stopped_count}/{total} 笔 ({stopped_count/total*100:.0f}%)")
            for p in [p for p in valid if p.get("stopped")][:5]:
                print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']}级 止损{p['stop_loss']}% → {p[ret_key]:+.2f}%")

    # ── 每日汇总 (加权收益) ──
    print(f"\n  📊 每日汇总 (加权):")
    print(f"  {'日期':<12} {'笔数':<5} {'胜率':<8} {'加权均值':<10} {'S级权重':<8} {'止损':<5}")
    print(f"  {'-' * 55}")
    for r in results:
        td = r["trade_date"]
        day_picks = [p for p in valid if p["trade_date"] == td]
        if not day_picks:
            continue
        dr = np.array([p[ret_key] for p in day_picks])
        dw = (dr > 0).sum()
        # 加权均值: S级 0.6x, A/B级 1.0x
        weights = np.array([p.get("weight", 1.0) for p in day_picks])
        weighted_avg = np.average(dr, weights=weights) if weights.sum() > 0 else dr.mean()
        s_count = sum(1 for p in day_picks if p["grade"] == "S")
        if multi_day:
            st = sum(1 for p in day_picks if p["exit_reason"] == "stop_loss")
        else:
            st = sum(1 for p in day_picks if p.get("stopped"))
        print(f"  {td:<12} {len(day_picks):<5} {dw/len(day_picks)*100:>6.1f}% "
              f"{weighted_avg:>+8.2f}%  {s_count}x0.6{'':<4} {st:<5}")

    # ── Top winners & losers ──
    print(f"\n  🏆 最佳10笔:")
    top_win = sorted(valid, key=lambda x: -(x[ret_key] if x[ret_key] is not None else -999))[:10]
    for p in top_win:
        hold_tag = f" 持{p['actual_hold_days']}日" if multi_day else ""
        print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']} "
              f"{p['signal']:<12} → {p[ret_key]:>+6.2f}%{hold_tag}")

    print(f"\n  💀 最差10笔:")
    top_loss = sorted(valid, key=lambda x: (x[ret_key] if x[ret_key] is not None else 999))[:10]
    for p in top_loss:
        hold_tag = f" 持{p['actual_hold_days']}日" if multi_day else ""
        print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']} "
              f"{p['signal']:<12} → {p[ret_key]:>+6.2f}%{hold_tag}")

    return all_picks


def main():
    parser = argparse.ArgumentParser(description="毕师傅趋势启动战法回测")
    parser.add_argument("--month", type=str, default="2026-06", help="回测月份 YYYY-MM")
    parser.add_argument("--top-n", type=int, default=20, help="每日选股数")
    parser.add_argument("--export", type=str, default=None, help="导出JSON路径")
    parser.add_argument("--no-adj", action="store_true",
                        help="关闭后复权 (退回原始价, 旧行为). 默认开启后复权消除除权日跳变. T-008.")
    parser.add_argument("--multi-day", action="store_true",
                        help="阶段1 AC-1: 多日持有回测 (hold_days 5/7/10 + TP 20/25%% + trailing + stop, "
                             "T+1 open 入场). 默认关闭 (单日 T+1, 阶段0 口径).")
    parser.add_argument("--cost-bps", type=int, default=0,
                        help="往返交易成本 (bp), 如 14 = 0.14%%. 默认 0 (不扣). AC-11.")
    args = parser.parse_args()
    adjusted = not args.no_adj

    adapter = setup_db()

    from kronos_factors.scorer._db_stub import _get_db
    with _get_db() as db:
        trading_days = get_trading_days(db, args.month)
        print(f"📅 {args.month} 交易日: {len(trading_days)} 天")
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
            with _get_db() as db:
                r = run_backtest_day(db, td, args.top_n)
            elapsed = time.time() - t0
            top_n = len(r["top_picks"])
            grades = f"S={sum(1 for s in r['top_picks'] if s['grade']=='S')} " \
                     f"A={sum(1 for s in r['top_picks'] if s['grade']=='A')}"
            sb = sum(1 for s in r['top_picks'] if s['signal']=='strong_buy')
            print(f"✅ {top_n}只/{r['total_qualified']}入选 {grades} 🔥{sb} {elapsed:.1f}s")
            results.append(r)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"❌ {elapsed:.1f}s - {e}")

    # ── 分析 ──
    with _get_db() as db:
        all_picks = analyze_results(results, db, adjusted=adjusted,
                                    multi_day=args.multi_day, cost_bps=args.cost_bps)

    # ── 导出 ──
    suffix = "_multiday" if args.multi_day else ""
    if args.cost_bps:
        suffix += f"_cost{args.cost_bps}"
    export_path = args.export or f"outputs/backtest_bi_trend_{args.month}{suffix}.json"
    os.makedirs(os.path.dirname(export_path) or "outputs", exist_ok=True)
    serializable = []
    for p in all_picks:
        serializable.append({k: (float(v) if isinstance(v, (np.floating,)) else v)
                             for k, v in p.items()})

    # AC-6: summary 含 weighted net (S级 0.6x 降权), 多日模式用 gross/net/weighted
    valid_picks = [p for p in all_picks if (p.get("gross_return") if args.multi_day
                                            else p.get("next_day_return")) is not None]
    net_vals = [p["net_return"] for p in valid_picks if p.get("net_return") is not None]
    weighted_vals = [p["weighted_return"] for p in valid_picks if p.get("weighted_return") is not None]
    summary = {
        "valid": len(valid_picks),
        "pending": len(all_picks) - len(valid_picks),
        "mode": "multi_day (AC-1)" if args.multi_day else "single_day_T+1",
        "cost_bps": args.cost_bps,
    }
    if not args.multi_day:
        # M08: 单日口径含成交假设前视, 显式标注禁止对外披露.
        summary["lookahead_warning"] = (
            "单日口径 (T收盘买 T+1收盘卖) 含成交假设前视 — T日 close 物理上不可成交, "
            "系统性高估收益, 仅向后兼容对比用, 禁止对外披露或据此投资决策 (M08)."
        )
    if net_vals:
        summary["net"] = {
            "mean_per_trade": float(np.mean(net_vals)),
            "median_per_trade": float(np.median(net_vals)),
            "sum": float(np.sum(net_vals)),
            "win_rate": float((np.array(net_vals) > 0).sum() / len(net_vals) * 100),
        }
    if weighted_vals:
        summary["weighted"] = {  # AC-6
            "mean_per_trade": float(np.mean(weighted_vals)),
            "sum": float(np.sum(weighted_vals)),
            "weight_rule": "S级 weight=0.6, 其余 1.0 (bi_trend_launch L1010)",
        }
    if args.multi_day:
        reasons = {}
        for p in valid_picks:
            reasons[p["exit_reason"]] = reasons.get(p["exit_reason"], 0) + 1
        summary["exit_reasons"] = reasons

    with open(export_path, 'w') as f:
        json.dump({
            "month": args.month,
            "price_adjustment": "post-adjusted (后复权)" if adjusted else "raw (原始价)",
            "multi_day": args.multi_day,
            "cost_bps": args.cost_bps,
            "total_picks": len(all_picks),
            "summary": summary,
            "picks": serializable,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 结果导出: {export_path}")
    print(f"   读价口径: {'后复权 (adj_factor JOIN)' if adjusted else '原始价 (--no-adj)'}")
    print(f"   模式: {'多日持有 AC-1' if args.multi_day else '单日 T+1'} | 成本 {args.cost_bps}bp")

    if hasattr(adapter, 'close'):
        adapter.close()


if __name__ == "__main__":
    main()
