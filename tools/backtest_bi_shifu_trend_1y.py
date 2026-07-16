#!/usr/bin/env python3
"""毕师傅趋势战法最近一年资金回测。

交易规则：
  - T 日收盘产生信号。
  - T+1 开盘买入，T+2 收盘卖出。
  - T+1/T+2 触发 ATR 动态止损时卖出；T+2 跳空低开越过止损价时按开盘价成交。
  - 每日新信号批次最多使用当日开盘总资产的 50%，批次内等权。
  - 使用复权因子计算收益，买卖合计成本默认 14bp。

这个脚本不使用未来信息选股；未来 K 线仅用于模拟成交。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "kronos-factors"))
os.environ.setdefault("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

from kronos_factors.engine.bi_shifu_trend import BiShifuTrendEngine  # noqa: E402
from kronos_factors.engine.bi_shifu_trend import P  # noqa: E402
import kronos_factors.engine.bi_shifu_trend as bi_trend_module  # noqa: E402
from kronos_factors.scorer._db_stub import _get_db  # noqa: E402


VARIANT_SETTINGS = {
    # 基于各版本历史门槛的规则回放，统一使用当前已修复的数据和交易模拟口径。
    "v20": {
        "macd_below_min_days": 0,
        "min_score": 0.0,
        "near_high_max_pct": -0.99,
        "obv_leading_price": False,
    },
    "v21-score": {
        "macd_below_min_days": 3,
        "min_score": 10.0,
        "near_high_max_pct": -0.99,
        "obv_leading_price": False,
    },
    "v22": {
        "macd_below_min_days": 3,
        "min_score": 0.0,
        "near_high_max_pct": -0.04,
        "obv_leading_price": True,
    },
}


@dataclass
class Position:
    code: str
    name: str
    signal_date: str
    entry_date: str
    exit_date: str
    entry_adj: float
    stop_adj: float
    shares: float
    buy_notional: float
    score: float
    grade: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial-capital", type=float, default=1_000_000)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--variant", choices=tuple(VARIANT_SETTINGS), default="v21-score",
                        help="历史规则回放版本；统一采用当前数据修复与交易模拟口径")
    parser.add_argument("--min-pullback-days", type=int, default=None)
    parser.add_argument("--entry-gap-min", type=float, default=None)
    parser.add_argument("--entry-gap-max", type=float, default=None)
    parser.add_argument("--candidate-v23", action="store_true",
                        help="Top 5 + MACD回调至少7日 + T+1开盘偏离[-2%%,+0.5%%]")
    parser.add_argument("--cost-bps", type=float, default=14.0)
    parser.add_argument("--allocation", type=float, default=0.50)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date", help="交易结果数据截止日，默认 daily_kline 最新日")
    parser.add_argument("--output")
    return parser.parse_args()


def variant_settings(variant: str) -> dict[str, float | int | bool]:
    """返回独立副本，防止调用方意外改写全局版本配置。"""
    return dict(VARIANT_SETTINGS[variant])


def apply_variant(variant: str) -> None:
    settings = variant_settings(variant)
    P.MACD_BELOW_MIN_DAYS = int(settings["macd_below_min_days"])
    P.MIN_SCORE = float(settings["min_score"])
    P.NEAR_HIGH_MAX_PCT = float(settings["near_high_max_pct"])
    P.OBV_LEADING_PRICE = bool(settings["obv_leading_price"])


def adjusted(bar: dict, field: str) -> float:
    return float(bar[field]) * float(bar.get("adj_factor") or 1.0)


def entry_gap_allowed(gap_pct: float, minimum_pct: float | None, maximum_pct: float | None) -> bool:
    """空值表示不过滤；边界值可以成交。"""
    return (
        (minimum_pct is None or gap_pct >= minimum_pct)
        and (maximum_pct is None or gap_pct <= maximum_pct)
    )


def has_opening_budget(budget: float) -> bool:
    """零可用资金不能记作已成交的仓位或交易。"""
    return budget > 0.0


def pending_signal_dates(signal_dates: list[str], signal_cache: dict[str, list[dict]]) -> list[str]:
    """缓存中已经完成的交易日不重算，以支持中断续跑。"""
    return [trade_date for trade_date in signal_dates if trade_date not in signal_cache]


def resolve_exit(position: Position, bar: dict, sell_cost: float) -> tuple[float, str, float]:
    open_adj = adjusted(bar, "open")
    low_adj = adjusted(bar, "low")
    close_adj = adjusted(bar, "close")
    if open_adj <= position.stop_adj:
        exit_adj, reason = open_adj, "gap_stop"
    elif low_adj <= position.stop_adj:
        exit_adj, reason = position.stop_adj, "stop"
    else:
        exit_adj, reason = close_adj, "normal"
    proceeds = position.shares * exit_adj * (1.0 - sell_cost)
    gross_return = exit_adj / position.entry_adj - 1.0
    return proceeds, reason, gross_return


def open_gap_stop(position: Position, bar: dict, sell_cost: float) -> tuple[float, str, float] | None:
    """仅处理开盘已可确认的跳空止损，供新仓前释放现金使用。"""
    open_adj = adjusted(bar, "open")
    if open_adj > position.stop_adj:
        return None
    proceeds = position.shares * open_adj * (1.0 - sell_cost)
    return proceeds, "gap_stop", open_adj / position.entry_adj - 1.0


def generate_signals(model_rows: list[dict], signal_dates: set[str], top_n: int) -> dict[str, list[dict]]:
    """一次性计算全年信号，门槛与 bi_shifu_trend.screen_single 保持一致。"""
    frame = pd.DataFrame(model_rows)
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    results: dict[str, list[dict]] = defaultdict(list)

    for code, group in frame.groupby("code", sort=False):
        g = group.sort_values("trade_date").reset_index(drop=True)
        close = g["close"].astype(float)
        open_ = g["open"].astype(float)
        high = g["high"].astype(float)
        low = g["low"].astype(float)
        volume = g["volume"].astype(float)

        dif = close.ewm(span=P.EMA_FAST, adjust=False).mean() - close.ewm(span=P.EMA_SLOW, adjust=False).mean()
        dea = dif.ewm(span=P.DEA_PERIOD, adjust=False).mean()
        macd_cross = (dif > dea) & (dif.shift(1) <= dea.shift(1))
        below = (dif <= dea).to_numpy()
        below_before = np.zeros(len(g), dtype=int)
        run = 0
        for i in range(len(g)):
            below_before[i] = run
            run = run + 1 if below[i] else 0

        direction = np.sign(close.diff().fillna(0).to_numpy())
        obv = pd.Series(np.where(direction > 0, volume, np.where(direction < 0, -volume, 0))).cumsum()
        ma_obv = obv.rolling(P.OBV_MA_PERIOD).mean()
        obv_cross = (obv > ma_obv) & (obv.shift(1) <= ma_obv.shift(1))

        ma20 = close.rolling(P.MA_SHORT).mean()
        ma60 = close.rolling(P.MA_LONG).mean()
        mav5 = volume.rolling(P.VOL_MA_PERIOD).mean()
        trend_slope = ma20 / ma60 - 1.0
        vol_ratio = volume / mav5
        shadow_pct = high / close - 1.0
        high20 = high.rolling(20).max()
        near_high_pct = close / high20 - 1.0

        prev_close = close.shift(1)
        pct_source = g["change_pct"] if "change_pct" in g.columns else g.get("pct_chg")
        if pct_source is None:
            pct_source = pd.Series(np.nan, index=g.index)
        pct = pd.to_numeric(pct_source, errors="coerce")
        pct = pct.fillna((close / prev_close - 1.0) * 100).fillna(0)
        turnover = pd.to_numeric(g.get("turnover_rate"), errors="coerce").fillna(0)
        limit_threshold = (P.LIMIT_GEM if code.startswith(("688", "30")) else P.LIMIT_MAIN)

        tr = np.zeros(len(g))
        if len(g) > 1:
            tr[1:] = np.maximum.reduce([
                (high - low).to_numpy()[1:],
                np.abs((high - prev_close).to_numpy()[1:]),
                np.abs((low - prev_close).to_numpy()[1:]),
            ])
        atr = pd.Series(tr).rolling(P.ATR_PERIOD).mean()
        stop_pct = np.maximum(0.03, np.minimum(0.08, atr / close * P.STOP_ATR_MULT))

        eligible = (
            (np.arange(len(g)) + 1 >= P.MIN_DATA_DAYS)
            & macd_cross.to_numpy()
            & (below_before >= P.MACD_BELOW_MIN_DAYS)
            & obv_cross.fillna(False).to_numpy()
            & (ma20 > ma60).fillna(False).to_numpy()
            & (close > ma20).fillna(False).to_numpy()
            & (trend_slope >= P.TREND_SLOPE_MIN).fillna(False).to_numpy()
            & (volume > mav5).fillna(False).to_numpy()
            & (volume > volume.shift(1)).fillna(False).to_numpy()
            & (close > open_).to_numpy()
            & (shadow_pct <= P.SHADOW_MAX).fillna(False).to_numpy()
            & (pct < limit_threshold[0] - limit_threshold[1]).to_numpy()
            & (((turnover == 0) | ((turnover >= P.TURNOVER_MIN) & (turnover <= P.TURNOVER_MAX))).to_numpy())
            & (near_high_pct >= P.NEAR_HIGH_MAX_PCT).fillna(False).to_numpy()
        )

        for i in np.flatnonzero(eligible):
            trade_date = g.at[i, "trade_date"]
            if trade_date not in signal_dates:
                continue
            dif_val = float(dif.iat[i])
            obv_ratio = float(obv.iat[i] / ma_obv.iat[i])
            macd_score = min(5.0, max(0.0, dif_val * 5 + 2.5))
            trend_score = min(7.5, max(0.0, (float(trend_slope.iat[i]) - 0.02) / 0.02 * 1.5))
            volume_score = min(6.25, max(0.0, (float(vol_ratio.iat[i]) - 0.8) / 0.8 * 1.25))
            obv_score = min(3.75, max(0.0, (obv_ratio - 0.99) / 0.02 * 0.75))
            candle_score = max(0.0, 2.5 - float(shadow_pct.iat[i]) / 0.02)
            pullback_bonus = 1.0 if below_before[i] >= 7 else (1.5 if below_before[i] >= 14 else 0.0)
            score = round(macd_score + trend_score + volume_score + obv_score + candle_score + pullback_bonus, 2)
            if score < P.MIN_SCORE:
                continue
            grade = "S" if score >= 20 else "A" if score >= 16 else "B" if score >= 10 else "C"
            results[trade_date].append({
                "code": code,
                "name": g.at[i, "name"],
                "score": score,
                "grade": grade,
                "close": round(float(close.iat[i]), 2),
                "stop_loss_pct": round(float(stop_pct.iat[i]) * 100, 1),
                "vol_ratio": round(float(vol_ratio.iat[i]), 2),
            })

    for trade_date in signal_dates:
        results[trade_date].sort(key=lambda x: (x["score"], x["vol_ratio"]), reverse=True)
        results[trade_date] = results[trade_date][:top_n]
    return dict(results)


def main() -> int:
    args = parse_args()
    apply_variant(args.variant)
    if args.candidate_v23:
        args.top_n = 5
        args.min_pullback_days = 7
        args.entry_gap_min = -2.0
        args.entry_gap_max = 0.5
    if not 0 < args.allocation <= 1:
        raise SystemExit("--allocation 必须在 (0, 1] 内")

    buy_cost = args.cost_bps / 20000.0
    sell_cost = args.cost_bps / 20000.0

    with _get_db(readonly=True) as db:
        latest_row = db.execute("SELECT MAX(trade_date) AS d FROM daily_kline").fetchone()
        data_end = str(args.end_date or latest_row["d"])[:10]
        date_rows = db.execute(
            """SELECT DISTINCT trade_date FROM daily_kline
               WHERE trade_date <= ? ORDER BY trade_date""",
            (data_end,),
        ).fetchall()
        all_dates = [str(r["trade_date"])[:10] for r in date_rows]
        if len(all_dates) < 3:
            raise SystemExit("交易日数据不足")

        end_idx = len(all_dates) - 1
        default_start = date.fromisoformat(data_end).replace(year=date.fromisoformat(data_end).year - 1).isoformat()
        start_date = str(args.start_date or default_start)[:10]
        signal_dates = [d for d in all_dates[:-2] if d >= start_date]
        if not signal_dates:
            raise SystemExit("回测区间没有可用信号日")

        first_needed = all_dates[all_dates.index(signal_dates[0]) + 1]
        price_rows = db.execute(
            """SELECT k.code, k.trade_date, k.open, k.high, k.low, k.close,
                      a.adj_factor
               FROM daily_kline k
               LEFT JOIN adj_factor a ON a.code=k.code AND a.trade_date=k.trade_date
               WHERE k.trade_date >= ? AND k.trade_date <= ?
               ORDER BY k.trade_date, k.code""",
            (first_needed, data_end),
        ).fetchall()

    bars: dict[tuple[str, str], dict] = {}
    bars_by_code: dict[str, list[dict]] = defaultdict(list)
    for row in price_rows:
        item = dict(row)
        item["trade_date"] = str(row["trade_date"])[:10]
        bars_by_code[row["code"]].append(item)

    # adj_factor 偶发单日缺失时不能回退为 1，否则会制造数百倍的假收益。
    for code, code_bars in bars_by_code.items():
        code_bars.sort(key=lambda x: x["trade_date"])
        last_factor = None
        for item in code_bars:
            if item.get("adj_factor") is not None:
                last_factor = float(item["adj_factor"])
            elif last_factor is not None:
                item["adj_factor"] = last_factor
        next_factor = None
        for item in reversed(code_bars):
            if item.get("adj_factor") is not None:
                next_factor = float(item["adj_factor"])
            elif next_factor is not None:
                item["adj_factor"] = next_factor
            bars[(code, item["trade_date"])] = item

    date_index = {d: i for i, d in enumerate(all_dates)}
    candidate_key = args.variant
    if args.min_pullback_days is not None or args.entry_gap_min is not None or args.entry_gap_max is not None or args.top_n != 20:
        candidate_key += f"_top{args.top_n}_pb{args.min_pullback_days or P.MACD_BELOW_MIN_DAYS}_gap{args.entry_gap_min}_{args.entry_gap_max}"
    cache_path = ROOT / "outputs" / f"bi_shifu_trend_signals_exact_{candidate_key}_{signal_dates[0]}_{signal_dates[-1]}.json"
    signal_cache: dict[str, list[dict]] = {}
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if (
            cached.get("model_version") == BiShifuTrendEngine.VERSION
            and cached.get("signal_method") == "exact_engine"
            and cached.get("variant") == args.variant
            and cached.get("candidate_key") == candidate_key
        ):
            signal_cache = cached.get("signals", {})

    pending_dates = pending_signal_dates(signal_dates, signal_cache)
    if pending_dates:
        started = time.time()
        # 分钟线聚合只做一次，随后每个交易日仍调用原始引擎。
        # 这样保留原引擎的 120 日 EMA/OBV 口径和历史单位修复，同时避免重复扫描分钟表。
        with _get_db(readonly=True) as db:
            minute_bounds = db.execute(
                "SELECT MIN(trade_time::date) AS min_d, MAX(trade_time::date) AS max_d FROM stk_mins"
            ).fetchone()
            minute_start = str(minute_bounds["min_d"])[:10] if minute_bounds and minute_bounds["min_d"] else None
            minute_end = min(signal_dates[-1], str(minute_bounds["max_d"])[:10]) if minute_bounds and minute_bounds["max_d"] else None
            minute_snapshots = (
                bi_trend_module._load_minute_daily_snapshots(db, minute_start, minute_end)
                if minute_start and minute_end and minute_start <= minute_end else {}
            )
        bi_trend_module._load_minute_daily_snapshots = lambda _db, _start, _end: minute_snapshots
        if args.min_pullback_days is not None:
            P.MACD_BELOW_MIN_DAYS = args.min_pullback_days

        engine = BiShifuTrendEngine()
        for i, signal_date in enumerate(pending_dates, 1):
            signal_cache[signal_date] = engine.run(top_n=args.top_n, trade_date=signal_date)
            if i == 1 or i % 20 == 0 or i == len(pending_dates):
                print(
                    f"[{len(signal_cache)}/{len(signal_dates)}] {signal_date}: {len(signal_cache[signal_date])} signals, "
                    f"{time.time() - started:.1f}s",
                    flush=True,
                )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps({
                    "model_version": BiShifuTrendEngine.VERSION,
                    "signal_method": "exact_engine",
                    "variant": args.variant,
                    "candidate_key": candidate_key,
                    "signals": signal_cache,
                }, ensure_ascii=False, default=str))

    entries: dict[str, list[dict]] = defaultdict(list)
    for signal_date, picks in signal_cache.items():
        if signal_date not in date_index or signal_date not in signal_dates:
            continue
        entry_date = all_dates[date_index[signal_date] + 1]
        exit_date = all_dates[date_index[signal_date] + 2]
        for pick in picks:
            if (pick["code"], entry_date) in bars and (pick["code"], exit_date) in bars:
                entries[entry_date].append({**pick, "signal_date": signal_date, "exit_date": exit_date})

    capital = float(args.initial_capital)
    cash = capital
    positions: list[Position] = []
    trades: list[dict] = []
    equity_curve: list[dict] = []
    entry_gap_rejected = 0

    simulation_dates = [d for d in all_dates if first_needed <= d <= data_end]
    for trade_date in simulation_dates:
        # 开盘先执行旧仓中已可确定的跳空止损；只有这部分回笼资金可用于同日开盘新仓。
        carried_positions: list[Position] = []
        for position in positions:
            bar = bars.get((position.code, trade_date))
            gap_exit = None if bar is None or trade_date == position.entry_date else open_gap_stop(position, bar, sell_cost)
            if gap_exit is None:
                carried_positions.append(position)
                continue
            proceeds, raw_reason, gross_return = gap_exit
            cash += proceeds
            trades.append({
                "signal_date": position.signal_date,
                "code": position.code,
                "name": position.name,
                "entry_date": position.entry_date,
                "exit_date": trade_date,
                "score": position.score,
                "grade": position.grade,
                "gross_return_pct": round(gross_return * 100, 4),
                "net_return_pct": round(proceeds / (position.buy_notional * (1.0 + buy_cost)) - 1.0, 4),
                "exit_reason": "t2_" + raw_reason,
            })
        positions = carried_positions

        # 开盘按实时复权价估值旧仓，新批次最多占总资产 50%。
        open_position_value = sum(
            p.shares * adjusted(bars[(p.code, trade_date)], "open")
            for p in positions if (p.code, trade_date) in bars
        )
        equity_open = cash + open_position_value
        picks = entries.get(trade_date, [])
        eligible_picks = []
        for pick in picks:
            bar = bars[(pick["code"], trade_date)]
            gap_pct = (float(bar["open"]) / float(pick["close"]) - 1.0) * 100.0
            if entry_gap_allowed(gap_pct, args.entry_gap_min, args.entry_gap_max):
                eligible_picks.append(pick)
            else:
                entry_gap_rejected += 1
        if eligible_picks:
            budget = min(cash / (1.0 + buy_cost), equity_open * args.allocation)
            if has_opening_budget(budget):
                per_pick = budget / len(eligible_picks)
                for pick in eligible_picks:
                    bar = bars[(pick["code"], trade_date)]
                    entry_adj = adjusted(bar, "open")
                    if entry_adj <= 0:
                        continue
                    notional = per_pick
                    shares = notional / entry_adj
                    cash -= notional * (1.0 + buy_cost)
                    positions.append(Position(
                        code=pick["code"], name=pick.get("name", ""),
                        signal_date=pick["signal_date"], entry_date=trade_date,
                        exit_date=pick["exit_date"], entry_adj=entry_adj,
                        stop_adj=entry_adj * (1.0 - float(pick["stop_loss_pct"]) / 100.0),
                        shares=shares, buy_notional=notional,
                        score=float(pick.get("score") or 0), grade=pick.get("grade", ""),
                    ))

        remaining: list[Position] = []
        for position in positions:
            bar = bars.get((position.code, trade_date))
            if bar is None:
                remaining.append(position)
                continue

            is_entry_day = trade_date == position.entry_date
            low_adj = adjusted(bar, "low")
            stop_on_entry = is_entry_day and low_adj <= position.stop_adj
            should_exit = stop_on_entry or trade_date == position.exit_date
            if not should_exit:
                remaining.append(position)
                continue

            if stop_on_entry:
                exit_adj = position.stop_adj
                reason = "t1_stop"
                proceeds = position.shares * exit_adj * (1.0 - sell_cost)
                gross_return = exit_adj / position.entry_adj - 1.0
            else:
                proceeds, raw_reason, gross_return = resolve_exit(position, bar, sell_cost)
                reason = "t2_" + raw_reason
                if raw_reason == "gap_stop":
                    exit_adj = adjusted(bar, "open")
                elif raw_reason == "stop":
                    exit_adj = position.stop_adj
                else:
                    exit_adj = adjusted(bar, "close")

            cash += proceeds
            net_return = proceeds / (position.buy_notional * (1.0 + buy_cost)) - 1.0
            trades.append({
                "signal_date": position.signal_date,
                "code": position.code,
                "name": position.name,
                "entry_date": position.entry_date,
                "exit_date": trade_date,
                "score": position.score,
                "grade": position.grade,
                "gross_return_pct": round(gross_return * 100, 4),
                "net_return_pct": round(net_return * 100, 4),
                "exit_reason": reason,
            })
        positions = remaining

        close_value = sum(
            p.shares * adjusted(bars[(p.code, trade_date)], "close")
            for p in positions if (p.code, trade_date) in bars
        )
        equity_curve.append({"date": trade_date, "equity": cash + close_value})

    ending_capital = equity_curve[-1]["equity"] if equity_curve else cash
    net_returns = [t["net_return_pct"] for t in trades]
    wins = sum(r > 0 for r in net_returns)
    peak = args.initial_capital
    max_drawdown = 0.0
    for point in equity_curve:
        peak = max(peak, point["equity"])
        max_drawdown = min(max_drawdown, point["equity"] / peak - 1.0)

    summary = {
        "model": "毕师傅趋势战法候选v2.3" if args.candidate_v23 else f"毕师傅趋势战法{args.variant}规则回放",
        "model_version": BiShifuTrendEngine.VERSION,
        "replay_variant": args.variant,
        "signal_date_range": f"{signal_dates[0]} ~ {signal_dates[-1]}",
        "result_data_end": data_end,
        "signal_days": len(signal_dates),
        "days_with_signals": sum(bool(signal_cache.get(d)) for d in signal_dates),
        "total_trades": len(trades),
        "win_rate_pct": round(wins / len(trades) * 100, 2) if trades else 0.0,
        "avg_trade_return_pct": round(float(np.mean(net_returns)), 4) if trades else 0.0,
        "median_trade_return_pct": round(float(np.median(net_returns)), 4) if trades else 0.0,
        "initial_capital": round(args.initial_capital, 2),
        "ending_capital": round(ending_capital, 2),
        "total_return_pct": round((ending_capital / args.initial_capital - 1.0) * 100, 4),
        "max_drawdown_pct": round(max_drawdown * 100, 4),
        "cost_bps_round_trip": args.cost_bps,
        "cohort_allocation_pct": args.allocation * 100,
        "top_n": args.top_n,
        "min_pullback_days": args.min_pullback_days,
        "entry_gap_min_pct": args.entry_gap_min,
        "entry_gap_max_pct": args.entry_gap_max,
        "entry_gap_rejected": entry_gap_rejected,
    }

    output = Path(args.output) if args.output else ROOT / "outputs" / f"backtest_bi_shifu_trend_1y_{datetime.now():%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "trades": trades, "equity_curve": equity_curve}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"详细结果: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
