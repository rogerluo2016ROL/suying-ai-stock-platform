#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

from kronos_factors.backtest.portfolio_v2 import (  # noqa: E402
    EntryOrder,
    build_portfolio_result,
    process_exits,
)
from kronos_factors.engine.bi_hardtech_v2 import (  # noqa: E402
    V2Config,
    market_allows_entry,
    select_daily_entries,
)
from kronos_factors.engine.bi_trend_launch import run_bi_screening  # noqa: E402
from backtest_bi_trend import get_adjusted_bars, simulate_position  # noqa: E402


MODEL_ID = "bi_hardtech_v2_comparison_backtest"
BASELINE_VERSION = "bi_trend_launch_v13_v5.9"
ARMS = ("baseline", "v2_a", "v2_b")
HISTORICAL_GLOBAL_REGIME = {"regime": "neutral", "bonus": 0.0}
HOLD_DAYS = 5
TAKE_PROFIT_PCT = 15
STOP_LOSS_PCT = -10
LIMITATIONS = [
    "历史滚动模拟，非完全未见样本。",
    "metadata 缺失或 unknown 仅作为数据告警，不自动推断发布时间。",
    "adj_factor 仅允许向过去 as-of 填充，禁止未来填充。",
]


def setup_db():
    pg_url = os.environ.get(
        "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"
    )
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter

    adapter = create_pg_adapter(pg_url)
    if adapter is None:
        raise RuntimeError(f"无法连接数据库: {pg_url}")
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="毕师傅硬核科技 V2 三臂历史回测")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--cost-bps", type=float, default=14.0)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(argv)


def _date_text(value):
    if value is None:
        return None
    return str(value)[:10]


def _normalize_meta_value(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _metadata_warning_codes(metadata_rows):
    warnings = []
    expected = {"daily", "adj_factor", "index_daily"}
    by_api = {row["api"]: row for row in metadata_rows if row.get("api")}
    for api in sorted(expected - set(by_api)):
        warnings.append(f"metadata_missing:{api}")
    for api in sorted(expected & set(by_api)):
        row = by_api[api]
        critical_fields = (
            row.get("update_time"),
            row.get("update_frequency"),
            row.get("doc_url"),
            row.get("extraction_status"),
        )
        if any(_normalize_meta_value(v) in {"", "unknown"} for v in critical_fields):
            warnings.append(f"metadata_unknown:{api}")
    return warnings


def _signal_end_date(db, result_data_end, hold_days=HOLD_DAYS):
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date <= ? ORDER BY trade_date",
        (result_data_end,),
    ).fetchall()
    trade_dates = [_date_text(row["trade_date"]) for row in rows]
    if len(trade_dates) <= hold_days:
        return None
    return trade_dates[-(hold_days + 1)]


def audit_sources(db, start_date, end_date):
    daily = db.execute(
        "SELECT MIN(trade_date) AS min_date, MAX(trade_date) AS max_date, "
        "COUNT(DISTINCT trade_date) AS trade_days, COUNT(*) AS row_count "
        "FROM daily_kline"
    ).fetchone()
    adj = db.execute(
        "SELECT MIN(trade_date) AS min_date, MAX(trade_date) AS max_date, "
        "COUNT(DISTINCT trade_date) AS trade_days, COUNT(*) AS row_count "
        "FROM adj_factor"
    ).fetchone()
    sector = db.execute(
        "SELECT MIN(trade_date) AS min_date, MAX(trade_date) AS max_date, "
        "COUNT(DISTINCT trade_date) AS trade_days, COUNT(*) AS row_count "
        "FROM index_daily"
    ).fetchone()
    st_history = db.execute("SELECT COUNT(*) AS row_count FROM st_history").fetchone()
    metadata_rows = db.execute(
        "SELECT api, update_time, update_frequency, doc_url, "
        "extraction_status, evidence, updated_at "
        "FROM tushare_api_update_metadata "
        "WHERE api IN ('daily', 'adj_factor', 'index_daily') "
        "ORDER BY api"
    ).fetchall()
    signal_end = _signal_end_date(db, end_date)
    return {
        "signal_start": start_date,
        "signal_end": signal_end,
        "result_data_end": end_date,
        "daily_kline_latest": _date_text(daily["max_date"]) if daily else None,
        "adj_factor_latest": _date_text(adj["max_date"]) if adj else None,
        "sector_latest": _date_text(sector["max_date"]) if sector else None,
        "daily_kline": {
            "min_date": _date_text(daily["min_date"]) if daily else None,
            "max_date": _date_text(daily["max_date"]) if daily else None,
            "trade_days": int(daily["trade_days"] or 0) if daily else 0,
            "row_count": int(daily["row_count"] or 0) if daily else 0,
        },
        "adj_factor": {
            "min_date": _date_text(adj["min_date"]) if adj else None,
            "max_date": _date_text(adj["max_date"]) if adj else None,
            "trade_days": int(adj["trade_days"] or 0) if adj else 0,
            "row_count": int(adj["row_count"] or 0) if adj else 0,
        },
        "index_daily": {
            "min_date": _date_text(sector["min_date"]) if sector else None,
            "max_date": _date_text(sector["max_date"]) if sector else None,
            "trade_days": int(sector["trade_days"] or 0) if sector else 0,
            "row_count": int(sector["row_count"] or 0) if sector else 0,
        },
        "st_history_rows": int(st_history["row_count"] or 0) if st_history else 0,
        "metadata": [dict(row) for row in metadata_rows],
        "source_warnings": _metadata_warning_codes(metadata_rows),
        "adj_factor_missing_trade_rows": 0,
        "adj_factor_missing_rows": [],
    }


def validate_source_audit(audit):
    errors = []
    warnings = []
    if (
        audit.get("daily_kline_latest") is None
        or audit["daily_kline_latest"] < audit["result_data_end"]
    ):
        errors.append("daily_kline_stale")
    if audit.get("signal_end") is None:
        errors.append("signal_window_unavailable")
    if audit.get("sector_latest") is None or audit["sector_latest"] < audit["signal_end"]:
        errors.append("sector_stale")
    if audit.get("adj_factor_missing_trade_rows", 0) > 0:
        errors.append("adj_factor_trade_coverage_missing")
    elif (
        audit.get("adj_factor_latest") is None
        or audit["adj_factor_latest"] < audit["result_data_end"]
    ):
        warnings.append("adj_factor_lags_result_end")
    return {"errors": errors, "warnings": warnings}


def evaluate_acceptance(summary):
    gates = {
        "annual_trade_count": 200 <= summary["total_trades"] <= 400,
        "positive_net_return": summary["total_return_pct"] > 0,
        "max_drawdown": summary["max_drawdown_pct"] >= -15,
        "worst_month": summary["worst_month_pct"] >= -8,
        "no_runtime_errors": summary["runtime_errors"] == 0,
    }
    return {"passed": all(gates.values()), "gates": gates}


def get_signal_dates(db, start_date, signal_end):
    if signal_end is None:
        return []
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date >= ? AND trade_date <= ? ORDER BY trade_date",
        (start_date, signal_end),
    ).fetchall()
    return [_date_text(row["trade_date"]) for row in rows]


def next_trade_date(db, signal_date):
    row = db.execute(
        "SELECT MIN(trade_date) AS d FROM daily_kline WHERE trade_date > ?",
        (signal_date,),
    ).fetchone()
    return _date_text(row["d"]) if row and row["d"] else None


def load_prices(db, trade_date, field, codes):
    if field not in {"open", "close"}:
        raise ValueError(f"unsupported price field: {field}")
    if not codes:
        return {}
    placeholders = ",".join("?" for _ in codes)
    rows = db.execute(
        f"SELECT code, {field} AS price FROM daily_kline "
        f"WHERE trade_date=? AND code IN ({placeholders})",
        [trade_date, *codes],
    ).fetchall()
    return {
        row["code"]: float(row["price"])
        for row in rows
        if row["price"] is not None and float(row["price"]) > 0
    }


def make_orders(picks, signal_date, entry_date, market_info):
    return [
        EntryOrder(
            signal_date=signal_date,
            entry_date=entry_date,
            code=pick["code"],
            name=pick.get("name", ""),
            regime=market_info.get("regime", ""),
            weight=float(pick.get("weight", 1.0)),
        )
        for pick in picks
    ]


def reject_day(picks, signal_date, reason):
    return [{"signal_date": signal_date, "code": pick["code"], "reason": reason} for pick in picks]


def confirm_for_next_open(db, signal_date, picks, config):
    entry_date = next_trade_date(db, signal_date)
    if entry_date is None:
        return [], reject_day(picks, signal_date, "entry_date_missing")
    selected, rejected = select_daily_entries(
        picks,
        open_by_code=load_prices(db, entry_date, "open", [p["code"] for p in picks]),
        close_by_code=load_prices(db, signal_date, "close", [p["code"] for p in picks]),
        config=config,
    )
    return selected, [
        {
            "signal_date": signal_date,
            "code": row["code"],
            "reason": row["confirmation_reason"],
        }
        for row in rejected
    ]


def build_arms(db, signal_dates, top_n, config):
    arms = {name: [] for name in ARMS}
    rejected = []
    for signal_date in signal_dates:
        entry_date = next_trade_date(db, signal_date)
        if entry_date is None:
            rejected.append(
                {"signal_date": signal_date, "code": None, "reason": "entry_date_missing"}
            )
            continue
        top, _scores, market_info = run_bi_screening(
            db,
            signal_date,
            top_n=top_n,
            global_market_regime=HISTORICAL_GLOBAL_REGIME,
        )
        arms["baseline"].extend(make_orders(top, signal_date, entry_date, market_info))
        if not market_allows_entry(market_info.get("regime", "")):
            rejected.extend(reject_day(top, signal_date, "market_gate"))
            continue
        arms["v2_a"].extend(make_orders(top, signal_date, entry_date, market_info))
        selected, day_rejected = confirm_for_next_open(db, signal_date, top, config)
        arms["v2_b"].extend(make_orders(selected, signal_date, entry_date, market_info))
        rejected.extend(day_rejected)
    return arms, rejected


def count_missing_trade_factor_rows(trade_rows, factor_rows):
    unique_rows = sorted(
        {(row["code"], _date_text(row["trade_date"])) for row in trade_rows if row.get("code") and row.get("trade_date")}
    )
    history = defaultdict(list)
    for row in sorted(
        factor_rows,
        key=lambda item: (item["code"], _date_text(item["trade_date"])),
    ):
        factor = row.get("adj_factor")
        if factor is None or float(factor) <= 0:
            continue
        history[row["code"]].append((_date_text(row["trade_date"]), float(factor)))

    missing_rows = []
    for code, trade_date in unique_rows:
        candidates = history.get(code, [])
        matched = False
        for factor_date, _factor in reversed(candidates):
            if factor_date <= trade_date:
                matched = True
                break
        if not matched:
            missing_rows.append({"code": code, "trade_date": trade_date})
    return {"missing_count": len(missing_rows), "missing_rows": missing_rows}


def _fetch_factor_rows(db, codes, max_date):
    if not codes:
        return []
    placeholders = ",".join("?" for _ in codes)
    rows = db.execute(
        f"SELECT code, trade_date, adj_factor FROM adj_factor "
        f"WHERE code IN ({placeholders}) AND trade_date <= ? "
        f"ORDER BY code, trade_date",
        [*sorted(codes), max_date],
    ).fetchall()
    return [dict(row) for row in rows]


def _prepare_order_cache(db, arms, result_data_end):
    cache = {}
    runtime_errors = []
    bars = {}
    trade_rows = []
    for order in sorted(
        {
            (order.signal_date, order.code): order
            for orders in arms.values()
            for order in orders
        }.values(),
        key=lambda item: (item.signal_date, item.code),
    ):
        try:
            adjusted_bars = get_adjusted_bars(db, order.code, order.signal_date, max_hold_days=HOLD_DAYS)
            if len(adjusted_bars) < 2:
                cache[(order.signal_date, order.code)] = None
                continue
            for bar in adjusted_bars[1:]:
                trade_date = _date_text(bar["date"])
                if trade_date is None or trade_date > result_data_end:
                    continue
                bars[(trade_date, order.code)] = {
                    "open": float(bar["open"]),
                    "high": float(bar["high"]),
                    "low": float(bar["low"]),
                    "close": float(bar["close"]),
                    "adj_factor": 1.0,
                }
                trade_rows.append({"code": order.code, "trade_date": trade_date})
            outcome = simulate_position(
                adjusted_bars,
                signal_idx=0,
                hold_days=HOLD_DAYS,
                tp_pct=TAKE_PROFIT_PCT,
                stop_loss_pct=STOP_LOSS_PCT,
            )
            if outcome is not None and outcome.get("exit_reason") == "data_truncated":
                outcome = {
                    **outcome,
                    "exit_date": None,
                    "exit_price": None,
                }
            cache[(order.signal_date, order.code)] = outcome
        except Exception as exc:
            runtime_errors.append(
                {
                    "signal_date": order.signal_date,
                    "code": order.code,
                    "error": str(exc),
                }
            )
            cache[(order.signal_date, order.code)] = None
    return cache, bars, trade_rows, runtime_errors


def _attach_exit(order, outcome):
    if outcome is None:
        return order
    exit_date = _date_text(outcome.get("exit_date"))
    exit_price = outcome.get("exit_price")
    if exit_date is None or exit_price is None:
        return EntryOrder(
            signal_date=order.signal_date,
            entry_date=order.entry_date,
            code=order.code,
            regime=order.regime,
            weight=order.weight,
            name=order.name,
            exit_date=None,
            exit_price=None,
            exit_reason=outcome.get("exit_reason"),
        )
    return EntryOrder(
        signal_date=order.signal_date,
        entry_date=order.entry_date,
        code=order.code,
        regime=order.regime,
        weight=order.weight,
        name=order.name,
        exit_date=exit_date,
        exit_price=float(exit_price),
        exit_reason=outcome.get("exit_reason"),
    )


def _require_bar(bars, trade_date, code):
    try:
        return bars[(trade_date, code)]
    except KeyError as exc:
        raise KeyError(f"missing_bar:{trade_date}:{code}") from exc


def _arm_constraints(arm_name):
    if arm_name == "baseline":
        return {
            "regime_caps": defaultdict(lambda: 1.0),
            "single_position_cap": None,
            "daily_entry_limit": None,
            "equal_split": True,
        }
    return {
        "regime_caps": {"bull": 0.50, "neutral": 0.30},
        "single_position_cap": 0.15,
        "daily_entry_limit": 2 if arm_name == "v2_b" else None,
        "equal_split": False,
    }


def simulate_arm_portfolio(arm_name, orders, bars, initial_capital=1_000_000.0, cost_bps=14.0):
    constraints = _arm_constraints(arm_name)
    buy_cost_rate = float(cost_bps) / 20_000.0
    sell_cost_rate = float(cost_bps) / 20_000.0
    cash = float(initial_capital)
    positions = []
    trades = []
    equity_curve = []
    orders_by_entry_date = defaultdict(list)
    for order in orders:
        orders_by_entry_date[order.entry_date].append(order)

    dates = sorted(
        {trade_date for trade_date, _code in bars}
        | {order.entry_date for order in orders}
        | {order.exit_date for order in orders if order.exit_date}
    )
    for trade_date in dates:
        opening_exposure = 0.0
        for position in positions:
            bar = _require_bar(bars, trade_date, position["code"])
            opening_exposure += position["shares"] * float(bar["open"])

        equity_open = cash + opening_exposure
        gross_exposure = opening_exposure
        day_orders = list(orders_by_entry_date.get(trade_date, []))
        daily_limit = constraints["daily_entry_limit"]
        if daily_limit is not None:
            day_orders = day_orders[:daily_limit]

        remaining_orders = len(day_orders)
        for order in day_orders:
            regime_caps = constraints["regime_caps"]
            regime_cap = (
                regime_caps[order.regime]
                if isinstance(regime_caps, defaultdict)
                else regime_caps.get(order.regime, 0.0)
            )
            if regime_cap <= 0:
                remaining_orders -= 1
                continue

            available_capacity = max(0.0, equity_open * regime_cap - gross_exposure)
            cash_budget = cash / (1.0 + buy_cost_rate)
            if constraints["equal_split"]:
                slots = max(1, remaining_orders)
                buy_notional = min(available_capacity / slots, cash_budget / slots)
            else:
                single_cap = constraints["single_position_cap"]
                single_budget = equity_open * single_cap if single_cap is not None else available_capacity
                buy_notional = min(available_capacity, single_budget, cash_budget)
            remaining_orders -= 1
            if buy_notional <= 0:
                continue

            bar = _require_bar(bars, trade_date, order.code)
            entry_price = float(bar["open"])
            if entry_price <= 0:
                continue
            shares = buy_notional / entry_price
            buy_cost = buy_notional * buy_cost_rate
            buy_cash = buy_notional + buy_cost
            cash -= buy_cash
            gross_exposure += buy_notional
            positions.append(
                {
                    "order": order,
                    "code": order.code,
                    "shares": shares,
                    "buy_notional": buy_notional,
                    "buy_cost": buy_cost,
                    "buy_cash": buy_cash,
                    "entry_price": entry_price,
                }
            )

        positions, cash, completed = process_exits(
            trade_date=trade_date,
            positions=positions,
            cash=cash,
            sell_cost_rate=sell_cost_rate,
        )
        trades.extend(completed)

        position_value = 0.0
        position_cost = 0.0
        for position in positions:
            bar = _require_bar(bars, trade_date, position["code"])
            position_value += position["shares"] * float(bar["close"])
            position_cost += position["buy_cash"]

        equity_curve.append(
            {
                "date": trade_date,
                "cash": cash,
                "position_value": position_value,
                "position_cost": position_cost,
                "equity_open": equity_open,
                "equity_close": cash + position_value,
                "gross_exposure": gross_exposure,
            }
        )

    return build_portfolio_result(
        initial_capital=float(initial_capital),
        trades=trades,
        equity_curve=equity_curve,
    )


def _rejection_counts(rows):
    counter = Counter()
    for row in rows:
        counter[row["reason"]] += 1
    return dict(sorted(counter.items()))


def _monthly_summary(summary):
    return [
        {"month": month, "return_pct": value}
        for month, value in sorted(summary.get("monthly_returns", {}).items())
    ]


def _comparison_rows(arm_results):
    rows = []
    for arm in ARMS:
        summary = arm_results[arm]["summary"]
        rows.append(
            {
                "arm": arm,
                "total_trades": summary["total_trades"],
                "total_return_pct": summary["total_return_pct"],
                "max_drawdown_pct": summary["max_drawdown_pct"],
                "worst_month_pct": summary["worst_month_pct"],
                "runtime_errors": summary["runtime_errors"],
            }
        )
    return rows


def _git_commit():
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=_PROJ, text=True)
            .strip()
        )
    except Exception:
        return "unknown"


def _write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _render_report(result):
    comparison = result["comparison"]
    status = result["promotion_status"]
    lines = [
        "# 毕师傅硬核科技 V2 历史滚动模拟",
        "",
        f"结论：`{status}`",
        "",
        "| 臂 | 成交笔数 | 累计收益% | 最大回撤% | 最差单月% | 运行错误 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison:
        lines.append(
            f"| {row['arm']} | {row['total_trades']} | "
            f"{row['total_return_pct']:.2f} | {row['max_drawdown_pct']:.2f} | "
            f"{row['worst_month_pct']:.2f} | {row['runtime_errors']} |"
        )
    lines.extend(
        [
            "",
            "## 数据审计",
            f"- signal range: {result['signal_range']['start_date']} -> {result['signal_range']['end_date']}",
            f"- result_data_end: {result['result_data_end']}",
            f"- source errors: {', '.join(result['source_decision']['errors']) or 'none'}",
            f"- source warnings: {', '.join(result['source_decision']['warnings'] + result['source_audit']['source_warnings']) or 'none'}",
            "",
            "## 拒绝原因",
        ]
    )
    for reason, count in result["rejection_reasons"].items():
        lines.append(f"- {reason}: {count}")
    lines.extend(["", "## 限制"])
    for limitation in result["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def run_backtest(db, start_date, end_date, initial_capital, cost_bps, top_n):
    audit = audit_sources(db, start_date, end_date)
    signal_dates = get_signal_dates(db, start_date, audit["signal_end"])
    arms, rejected = build_arms(db, signal_dates, top_n, V2Config())
    cache, bars, trade_rows, runtime_errors = _prepare_order_cache(db, arms, end_date)

    codes = {row["code"] for row in trade_rows}
    factor_rows = _fetch_factor_rows(db, codes, end_date)
    factor_audit = count_missing_trade_factor_rows(trade_rows, factor_rows)
    audit["adj_factor_missing_trade_rows"] = factor_audit["missing_count"]
    audit["adj_factor_missing_rows"] = factor_audit["missing_rows"]
    source_decision = validate_source_audit(audit)

    arm_results = {}
    acceptance = {}
    trades_csv = []
    equity_csv = []
    for arm in ARMS:
        realized_orders = [_attach_exit(order, cache.get((order.signal_date, order.code))) for order in arms[arm]]
        result = simulate_arm_portfolio(
            arm,
            realized_orders,
            bars,
            initial_capital=initial_capital,
            cost_bps=cost_bps,
        )
        result.summary["runtime_errors"] = len(runtime_errors)
        arm_results[arm] = {
            "summary": result.summary,
            "monthly": _monthly_summary(result.summary),
        }
        acceptance[arm] = evaluate_acceptance(result.summary)
        for trade in result.trades:
            trades_csv.append({"arm": arm, **trade})
        for point in result.equity_curve:
            equity_csv.append({"arm": arm, **point})

    promotion_status = (
        "PROMOTE_TO_PAPER"
        if acceptance["v2_b"]["passed"] and not source_decision["errors"]
        else "KEEP_EXPERIMENTAL"
    )
    return {
        "model_key": MODEL_ID,
        "baseline_version": BASELINE_VERSION,
        "git_commit": _git_commit(),
        "parameters": {
            "start_date": start_date,
            "end_date": end_date,
            "signal_end": audit["signal_end"],
            "initial_capital": initial_capital,
            "cost_bps": cost_bps,
            "top_n": top_n,
            "hold_days": HOLD_DAYS,
            "take_profit_pct": TAKE_PROFIT_PCT,
            "stop_loss_pct": STOP_LOSS_PCT,
            "global_market_regime": HISTORICAL_GLOBAL_REGIME,
        },
        "signal_range": {
            "start_date": start_date,
            "end_date": audit["signal_end"],
        },
        "result_data_end": end_date,
        "source_audit": audit,
        "source_decision": source_decision,
        "comparison": _comparison_rows(arm_results),
        "arm_summaries": {arm: arm_results[arm]["summary"] for arm in ARMS},
        "monthly_summaries": {arm: arm_results[arm]["monthly"] for arm in ARMS},
        "rejection_reasons": _rejection_counts(rejected),
        "rejections": sorted(rejected, key=lambda row: (row["signal_date"], row["code"] or "", row["reason"])),
        "runtime_errors": runtime_errors,
        "acceptance": acceptance,
        "promotion_status": promotion_status,
        "limitations": LIMITATIONS,
        "trades_csv": sorted(trades_csv, key=lambda row: (row["arm"], row["entry_date"], row["code"])),
        "equity_csv": sorted(equity_csv, key=lambda row: (row["arm"], row["date"])),
    }


def write_artifacts(output_dir, result):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    result_path = output_path / "result.json"
    report_path = output_path / "report.md"
    trades_path = output_path / "trades.csv"
    equity_path = output_path / "equity.csv"

    stored_result = {
        key: value
        for key, value in result.items()
        if key not in {"trades_csv", "equity_csv"}
    }
    result_path.write_text(
        json.dumps(stored_result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_render_report(result), encoding="utf-8")

    trade_fields = [
        "arm",
        "signal_date",
        "entry_date",
        "exit_date",
        "code",
        "name",
        "regime",
        "buy_notional",
        "buy_cost",
        "buy_cash",
        "entry_price",
        "exit_price",
        "sell_proceeds",
        "sell_cost",
        "exit_reason",
        "net_return_pct",
    ]
    _write_csv(trades_path, result["trades_csv"], trade_fields)

    equity_fields = [
        "arm",
        "date",
        "cash",
        "position_value",
        "position_cost",
        "equity_open",
        "equity_close",
        "gross_exposure",
    ]
    _write_csv(equity_path, result["equity_csv"], equity_fields)
    return result_path, report_path, trades_path, equity_path


def main(argv=None):
    args = parse_args(argv)
    db = setup_db()
    result = run_backtest(
        db=db,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        cost_bps=args.cost_bps,
        top_n=args.top_n,
    )
    result_path, report_path, trades_path, equity_path = write_artifacts(args.output_dir, result)
    print(
        json.dumps(
            {
                "result_json": str(result_path),
                "report_md": str(report_path),
                "trades_csv": str(trades_path),
                "equity_csv": str(equity_path),
                "promotion_status": result["promotion_status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
