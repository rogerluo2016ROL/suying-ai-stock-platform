"""No-lookahead, adjusted-return adapter for supply-chain selection V2."""

from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean, median
from typing import Any, Iterable

from psycopg2.extras import RealDictCursor

from .base import BacktestRequest, compute_adjusted_return, evaluate_request


ELIGIBLE_POOLS = ("A", "B", "C")
BENCHMARK_CODE = "000300"
ROW_COLUMNS = (
    "trade_date",
    "stock_code",
    "factors",
    "entry_date",
    "entry_open",
    "entry_adj",
    "exit_date",
    "exit_close",
    "exit_adj",
    "chain_id",
    "benchmark_entry_open",
    "benchmark_exit_close",
)


def normalize_stock_code(value: Any) -> str:
    return str(value or "").split(".", 1)[0]


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return dict(zip(ROW_COLUMNS, row))


def _factors(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def load_supply_chain_return_rows(
    connection,
    request: BacktestRequest,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            s.trade_date,
            s.stock_code,
            s.factors,
            entry.trade_date AS entry_date,
            entry.open AS entry_open,
            entry.adj_factor AS entry_adj,
            exit.trade_date AS exit_date,
            exit.close AS exit_close,
            exit.adj_factor AS exit_adj,
            b.chain_id,
            benchmark_entry.open AS benchmark_entry_open,
            benchmark_exit.close AS benchmark_exit_close
        FROM screening_snapshots s
        LEFT JOIN business_tag_mapping b
          ON b.mapping_id = s.factors->>'primary_mapping_id'
        JOIN LATERAL (
            SELECT k.trade_date, k.open, a.adj_factor
            FROM daily_kline k
            LEFT JOIN adj_factor a
              ON a.code = k.code AND a.trade_date = k.trade_date
            WHERE k.code = split_part(s.stock_code, '.', 1)
              AND k.trade_date > s.trade_date
              AND k.open > 0
            ORDER BY k.trade_date
            LIMIT 1
        ) entry ON TRUE
        JOIN LATERAL (
            SELECT k.trade_date, k.close, a.adj_factor
            FROM daily_kline k
            LEFT JOIN adj_factor a
              ON a.code = k.code AND a.trade_date = k.trade_date
            WHERE k.code = split_part(s.stock_code, '.', 1)
              AND k.trade_date >= entry.trade_date
              AND k.close > 0
            ORDER BY k.trade_date
            OFFSET %s LIMIT 1
        ) exit ON TRUE
        LEFT JOIN index_daily benchmark_entry
          ON benchmark_entry.code = '000300'
         AND benchmark_entry.trade_date = entry.trade_date
        LEFT JOIN index_daily benchmark_exit
          ON benchmark_exit.code = '000300'
         AND benchmark_exit.trade_date = exit.trade_date
        WHERE s.model_key = %s
          AND s.factors->>'pool_code' IN ('A','B','C')
        ORDER BY s.trade_date, s.stock_code
    """
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(sql, (request.forward_days - 1, request.model_key))
        return [_row_dict(row) for row in cursor.fetchall()]


def _maximum_drawdown(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    daily: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        daily[str(row["trade_date"])].append(float(row["future_return"]))
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for trade_date in sorted(daily):
        equity *= 1.0 + mean(daily[trade_date])
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1.0)
    return drawdown


def summarize_returns(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    values = [float(row["future_return"]) for row in materialized]
    if not values:
        return {"status": "INSUFFICIENT_EVIDENCE", "observations": 0}
    positives = [value for value in values if value > 0]
    negatives = [value for value in values if value < 0]
    profit_loss_ratio = (
        mean(positives) / abs(mean(negatives))
        if positives and negatives
        else None
    )
    return {
        "status": "READY",
        "observations": len(values),
        "mean_return": mean(values),
        "median_return": median(values),
        "win_rate": len(positives) / len(values),
        "profit_loss_ratio": profit_loss_ratio,
        "max_drawdown": _maximum_drawdown(materialized),
    }


def _group_report(
    rows: list[dict[str, Any]],
    key: str,
    values: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    if values is None:
        keys = sorted(grouped)
    else:
        keys = list(values)
    return {name: summarize_returns(grouped.get(name, [])) for name in keys}


def _base_report(request: BacktestRequest) -> dict[str, Any]:
    return {
        "model_key": SupplyChainSelectionV2Adapter.model_key,
        "execution_assumption": (
            "T+1 open to future adjusted close, "
            f"{float(request.cost_bps):.1f} bps cost"
        ),
        "by_pool": {
            pool: summarize_returns([]) for pool in ELIGIBLE_POOLS
        },
        "by_chain": {},
        "by_market_regime": {},
        "benchmark": {
            "status": "INSUFFICIENT_EVIDENCE",
            "code": BENCHMARK_CODE,
            "name": "沪深300",
        },
        "excess_return": {"status": "INSUFFICIENT_EVIDENCE"},
        "coverage": {
            "snapshot_rows": 0,
            "return_rows": 0,
            "missing_adj_factor_count": 0,
            "available_score_dates": 0,
            "benchmark_return_rows": 0,
        },
        "insufficient_reason": None,
    }


class SupplyChainSelectionV2Adapter:
    model_key = "supply_chain_research_selection_v2"

    def run(self, request: BacktestRequest, readiness: dict[str, Any] | None):
        report = _base_report(request)
        if not readiness or readiness.get("status") != "ready":
            report.update(
                status="BLOCKED",
                insufficient_reason="data readiness is not ready",
                missing_requirements=["data_readiness"],
            )
            return report
        if request.connection_factory is None:
            report.update(
                status="INSUFFICIENT_EVIDENCE",
                insufficient_reason="database connection is required",
                missing_requirements=["database_connection"],
            )
            return report

        connection = request.connection_factory()
        try:
            raw_rows = load_supply_chain_return_rows(connection, request)
        finally:
            connection.close()

        eligible_rows: list[dict[str, Any]] = []
        valid_rows: list[dict[str, Any]] = []
        benchmark_rows: list[dict[str, Any]] = []
        excess_rows: list[dict[str, Any]] = []
        missing_adj_factor_count = 0
        for raw in raw_rows:
            row = dict(raw)
            factors = _factors(row.get("factors"))
            pool_code = str(factors.get("pool_code") or row.get("pool_code") or "")
            if pool_code not in ELIGIBLE_POOLS:
                continue
            row["factors"] = factors
            row["pool_code"] = pool_code
            row["chain_id"] = row.get("chain_id") or factors.get("chain_id") or "unknown"
            row["market_regime"] = factors.get("market_regime") or "unknown"
            row["stock_code"] = normalize_stock_code(row.get("stock_code"))
            eligible_rows.append(row)
            if row.get("entry_adj") is None or row.get("exit_adj") is None:
                missing_adj_factor_count += 1
                continue
            if row.get("entry_open") is None or row.get("exit_close") is None:
                continue
            row["future_return"] = compute_adjusted_return(
                row["entry_open"],
                row["entry_adj"],
                row["exit_close"],
                row["exit_adj"],
                request.cost_bps,
            )
            valid_rows.append(row)
            benchmark_entry = row.get("benchmark_entry_open")
            benchmark_exit = row.get("benchmark_exit_close")
            if (
                benchmark_entry is not None
                and benchmark_exit is not None
                and float(benchmark_entry) > 0
                and float(benchmark_exit) > 0
            ):
                benchmark_return = (
                    float(benchmark_exit) / float(benchmark_entry) - 1.0
                )
                benchmark_rows.append(
                    {**row, "future_return": benchmark_return}
                )
                excess_rows.append(
                    {
                        **row,
                        "future_return": row["future_return"] - benchmark_return,
                    }
                )

        score_dates = {str(row["trade_date"]) for row in eligible_rows}
        valid_by_date: dict[str, int] = defaultdict(int)
        for row in valid_rows:
            valid_by_date[str(row["trade_date"])] += 1
        qualified_dates = sum(
            1 for count in valid_by_date.values() if count >= request.min_per_day
        )
        report["coverage"] = {
            "snapshot_rows": len(eligible_rows),
            "return_rows": len(valid_rows),
            "missing_adj_factor_count": missing_adj_factor_count,
            "available_score_dates": len(score_dates),
            "benchmark_return_rows": len(benchmark_rows),
        }
        report["by_pool"] = _group_report(
            valid_rows,
            "pool_code",
            ELIGIBLE_POOLS,
        )
        report["by_chain"] = _group_report(valid_rows, "chain_id")
        report["by_market_regime"] = _group_report(valid_rows, "market_regime")
        report["benchmark"] = {
            "code": BENCHMARK_CODE,
            "name": "沪深300",
            **summarize_returns(benchmark_rows),
        }
        report["excess_return"] = summarize_returns(excess_rows)
        report["factor_evidence"] = evaluate_request(valid_rows, request)

        missing: list[str] = []
        if not valid_rows:
            missing.append("adjusted return rows")
        if len(valid_rows) < request.min_observations:
            missing.append(
                f"at least {request.min_observations} return observations"
            )
        if len(score_dates) < request.min_periods:
            missing.append(f"at least {request.min_periods} score dates")
        if qualified_dates < request.min_periods:
            missing.append(
                f"at least {request.min_per_day} stocks on "
                f"{request.min_periods} score dates"
            )
        if missing:
            report["status"] = "INSUFFICIENT_EVIDENCE"
            report["insufficient_reason"] = "; ".join(dict.fromkeys(missing))
            report["missing_requirements"] = list(dict.fromkeys(missing))
        else:
            report["status"] = "READY"
        return report
