#!/usr/bin/env python3
"""Backtest supply-chain expectation-gap screener with stored historical scores.

This script intentionally uses only rows already stored in
business_tag_expectation_gap_scores / business_tag_three_high_scores for each
signal date. It does not recompute old scores from today's evidence, because
that would introduce future-looking bias.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median
from typing import Any

import psycopg2
import psycopg2.extras

import register_supply_chain_expectation_gap_model as model


def _latest_kline_date(cur) -> str:
    cur.execute("SELECT max(trade_date) AS trade_date FROM daily_kline")
    row = cur.fetchone()
    if not row or not row["trade_date"]:
        raise RuntimeError("daily_kline has no trade_date")
    return str(row["trade_date"])[:10]


def _score_dates(cur, start_date: str, end_date: str) -> list[str]:
    cur.execute(
        """
        SELECT trade_date, count(*) AS row_count
        FROM business_tag_expectation_gap_scores
        WHERE trade_date BETWEEN %s AND %s
        GROUP BY trade_date
        ORDER BY trade_date
        """,
        (start_date, end_date),
    )
    return [str(row["trade_date"])[:10] for row in cur.fetchall() if int(row["row_count"] or 0) > 0]


def _return_after_days(cur, code: str, trade_date: str, hold_days: int) -> float | None:
    base_code = str(code or "").split(".", 1)[0]
    cur.execute(
        """
        SELECT close
        FROM daily_kline
        WHERE code = %s AND trade_date = %s AND close IS NOT NULL AND close > 0
        """,
        (base_code, trade_date),
    )
    entry = cur.fetchone()
    if not entry or not entry["close"]:
        return None
    entry_close = float(entry["close"])
    cur.execute(
        """
        SELECT close
        FROM daily_kline
        WHERE code = %s AND trade_date > %s AND close IS NOT NULL AND close > 0
        ORDER BY trade_date ASC
        LIMIT %s
        """,
        (base_code, trade_date, hold_days),
    )
    rows = cur.fetchall()
    if len(rows) < hold_days:
        return None
    exit_close = float(rows[-1]["close"])
    return round((exit_close / entry_close - 1.0) * 100.0, 4)


def _max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1.0)
    return round(max_dd * 100.0, 2)


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "trade_count": 0,
            "signal_days": 0,
            "win_rate": None,
            "avg_return": None,
            "median_return": None,
            "compound_return": None,
            "max_return": None,
            "min_return": None,
            "max_drawdown": None,
        }
    rets = [float(row["return_pct"]) for row in records]
    daily: dict[str, list[float]] = defaultdict(list)
    for row in records:
        daily[str(row["trade_date"])].append(float(row["return_pct"]))
    capital = 1.0
    equity = [capital]
    for trade_date in sorted(daily):
        day_return = mean(daily[trade_date]) / 100.0
        capital *= 1.0 + day_return
        equity.append(capital)
    return {
        "trade_count": len(records),
        "signal_days": len(daily),
        "win_rate": round(sum(1 for value in rets if value > 0) / len(rets) * 100.0, 2),
        "avg_return": round(mean(rets), 4),
        "median_return": round(median(rets), 4),
        "compound_return": round((capital - 1.0) * 100.0, 4),
        "max_return": round(max(rets), 4),
        "min_return": round(min(rets), 4),
        "max_drawdown": _max_drawdown(equity),
    }


def _summarize_by_signal_tier(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row.get("signal_tier") or "unknown")].append(row)
    return {tier: _summarize(rows) for tier, rows in sorted(grouped.items())}


def _update_model_metrics(cur, summary: dict[str, Any]) -> None:
    t1 = summary["by_hold_days"].get("1", {})
    if not t1 or t1.get("win_rate") is None:
        return
    metrics = {
        "backtest_start_date": summary["start_date"],
        "backtest_end_date": summary["end_date"],
        "available_score_dates": summary["available_score_dates"],
        "requested_years": summary["requested_years"],
        "is_full_requested_window_backtest": summary["is_full_requested_window_backtest"],
        "insufficient_reason": summary["insufficient_reason"],
        "by_hold_days": summary["by_hold_days"],
        "by_signal_tier_by_hold_days": summary.get("by_signal_tier_by_hold_days", {}),
    }
    cur.execute(
        """
        UPDATE model_versions
        SET win_rate = %s, mean_return = %s
        WHERE model_name = %s AND version_tag = %s AND is_current = true
        """,
        (t1["win_rate"], t1["avg_return"], model.MODEL_KEY, model.VERSION_TAG),
    )
    cur.execute(
        """
        UPDATE model_registry
        SET metrics = coalesce(metrics, '{}'::json)::jsonb || %s::jsonb,
            updated_at = now()
        WHERE id = %s
        """,
        (json.dumps({"backtest": metrics}, ensure_ascii=False), model.MODEL_KEY),
    )


def run_backtest(
    pg_url: str,
    *,
    start_date: str | None,
    end_date: str | None,
    years: int,
    top_n: int,
    min_gap: float,
    hold_days: list[int],
    update_db: bool,
) -> dict[str, Any]:
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            latest_date = end_date or _latest_kline_date(cur)
            if start_date is None:
                start_date = (date.fromisoformat(latest_date) - timedelta(days=365 * years)).isoformat()
            dates = _score_dates(cur, start_date, latest_date)
            records_by_hold: dict[int, list[dict[str, Any]]] = {days: [] for days in hold_days}
            daily_pick_counts = {}
            for score_date in dates:
                picks = model.fetch_picks(cur, score_date, top_n, min_gap)
                daily_pick_counts[score_date] = len(picks)
                for pick in picks:
                    for days in hold_days:
                        ret = _return_after_days(cur, str(pick["code"]), score_date, days)
                        if ret is not None:
                            records_by_hold[days].append(
                                {
                                    "trade_date": score_date,
                                    "code": pick["code"],
                                    "name": pick["name"],
                                    "rank": pick["rank"],
                                    "grade": pick["grade"],
                                    "signal_tier": pick.get("signal_tier"),
                                    "model_score": float(pick["model_score"]),
                                    "return_pct": ret,
                                }
                            )
            by_hold = {str(days): _summarize(rows) for days, rows in records_by_hold.items()}
            by_signal_tier_by_hold = {
                str(days): _summarize_by_signal_tier(rows)
                for days, rows in records_by_hold.items()
            }
            signal_dates_with_picks = sum(1 for count in daily_pick_counts.values() if count > 0)
            total_selected_candidates = sum(daily_pick_counts.values())
            summary = {
                "model_key": model.MODEL_KEY,
                "model_name": model.MODEL_NAME,
                "start_date": start_date,
                "end_date": latest_date,
                "requested_years": years,
                "top_n": top_n,
                "min_gap": min_gap,
                "available_score_dates": len(dates),
                "score_date_range": [dates[0], dates[-1]] if dates else [],
                "score_dates_sample": dates[:5] + (["..."] if len(dates) > 10 else []) + dates[-5:],
                "signal_dates_with_picks": signal_dates_with_picks,
                "total_selected_candidates": total_selected_candidates,
                "daily_pick_counts_nonzero": {
                    trade_date: count
                    for trade_date, count in daily_pick_counts.items()
                    if count > 0
                },
                "is_full_requested_window_backtest": len(dates) >= max(1, int(240 * years * 0.75)),
                "insufficient_reason": None,
                "by_hold_days": by_hold,
                "by_signal_tier_by_hold_days": by_signal_tier_by_hold,
            }
            if not summary["is_full_requested_window_backtest"]:
                summary["insufficient_reason"] = (
                    f"最近 {years} 年窗口内仅有已落库评分日期 "
                    f"{len(dates)} 个；严格 {years} 年回测需要历史逐日 as-of 评分，"
                    "不能用当前证据倒推过去。"
                )
            if update_db:
                _update_model_metrics(cur, summary)
        conn.commit()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest supply-chain expectation-gap screener")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--min-gap", type=float, default=8.0)
    parser.add_argument("--hold-days", default="1,3,5,10")
    parser.add_argument("--update-db", action="store_true")
    args = parser.parse_args()
    hold_days = [int(item.strip()) for item in args.hold_days.split(",") if item.strip()]
    payload = run_backtest(
        args.pg_url,
        start_date=args.start_date,
        end_date=args.end_date,
        years=args.years,
        top_n=args.top_n,
        min_gap=args.min_gap,
        hold_days=hold_days,
        update_db=args.update_db,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
