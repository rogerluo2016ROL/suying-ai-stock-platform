#!/usr/bin/env python3
"""Run strict snapshot and full-candidate ablations for supply-chain V2."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Callable

import psycopg2
from psycopg2.extras import RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKTEST_ROOT = PROJECT_ROOT / "services" / "backtest-service"
PACKAGE_ROOT = PROJECT_ROOT / "packages" / "kronos-factors"
for path in (BACKTEST_ROOT, PACKAGE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.adapters.base import BacktestRequest, compute_adjusted_return  # noqa: E402
from app.adapters.supply_chain_selection_v2 import (  # noqa: E402
    ELIGIBLE_POOLS,
    SupplyChainSelectionV2Adapter,
    normalize_stock_code,
    summarize_returns,
)
from kronos_factors.scorer.supply_chain_selection_v2 import (  # noqa: E402
    aggregate_stock_mappings,
)


MODEL_ID = "supply_chain_research_selection_v2"
MODEL_VERSION = "v2.0"
ABLATIONS = (
    "v1",
    "v2_full",
    "v2_without_dimensions",
    "v2_without_market_expectation",
    "v2_without_risk_penalty",
    "v2_three_high_only",
    "v2_evidence_stage_only",
)
DEFAULT_DSN = os.environ.get(
    "KRONOS_PG_URL",
    "postgresql://kronos:kronos@localhost:6432/kronos",
)
EVIDENCE_RANK = {f"E{level}": level for level in range(7)}


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _opportunity_score(
    row: dict[str, Any],
    *,
    benefit_score: float | None = None,
    include_expectation: bool = True,
    include_risk: bool = True,
) -> float | None:
    benefit = benefit_score if benefit_score is not None else _number(row, "benefit_score")
    catalyst = _number(row, "catalyst_score")
    risk = _number(row, "risk_score")
    expectation = _number(row, "expectation_gap_score")
    if benefit is None or catalyst is None:
        return None
    if include_expectation and expectation is None:
        return None
    if include_risk and risk is None:
        return None
    if include_expectation:
        positive = benefit * 0.55 + float(expectation) * 0.30 + catalyst * 0.15
    else:
        positive = (benefit * 0.55 + catalyst * 0.15) / 0.70
    penalty = float(risk) * 0.30 if include_risk else 0.0
    return _clamp(positive - penalty)


def _benefit_without_node_dimensions(row: dict[str, Any]) -> float | None:
    detail = _json_dict(row.get("benefit_detail"))
    components = (
        ("operating_quality_score", 0.20),
        ("revenue_exposure_score", 0.20),
        ("order_certainty_score", 0.15),
        ("profit_elasticity_score", 0.15),
        ("delivery_capability_score", 0.10),
    )
    known: list[tuple[float, float]] = []
    for key, weight in components:
        value = detail.get(key)
        if value is None:
            return None
        known.append((float(value), weight))
    authenticity = _number(row, "authenticity_score")
    if authenticity is None:
        return None
    raw = sum(value * weight for value, weight in known) / sum(
        weight for _, weight in known
    )
    return _clamp(raw * authenticity / 100.0)


def _stage_rank(value: Any) -> int | None:
    text = str(value or "")
    if len(text) < 2 or text[0] != "C":
        return None
    try:
        rank = int(text[1:])
    except ValueError:
        return None
    return rank if 0 <= rank <= 6 else None


def ablation_score(row: dict[str, Any], variant: str) -> float | None:
    if variant not in ABLATIONS:
        raise ValueError(f"unknown ablation variant: {variant}")
    if variant == "v1":
        return _number(row, "v1_score")
    if variant == "v2_full":
        return _number(row, "opportunity_score")
    if variant == "v2_without_dimensions":
        benefit = _benefit_without_node_dimensions(row)
        if benefit is None:
            return None
        return _opportunity_score(row, benefit_score=benefit)
    if variant == "v2_without_market_expectation":
        return _opportunity_score(row, include_expectation=False)
    if variant == "v2_without_risk_penalty":
        return _opportunity_score(row, include_risk=False)
    if variant == "v2_three_high_only":
        return _number(row, "operating_quality_score")
    evidence_rank = EVIDENCE_RANK.get(str(row.get("evidence_level") or ""))
    stage_rank = _stage_rank(row.get("commercial_stage"))
    if evidence_rank is None or stage_rank is None:
        return None
    return _clamp(evidence_rank / 6 * 60.0 + stage_rank / 6 * 40.0)


def rank_full_candidate_set(
    rows: list[dict[str, Any]],
    *,
    variant: str,
    top_n: int,
) -> list[dict[str, Any]]:
    if variant not in ABLATIONS:
        raise ValueError(f"unknown ablation variant: {variant}")
    if top_n < 1:
        raise ValueError("top_n must be positive")
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("pool_code") not in ELIGIBLE_POOLS:
            continue
        if row.get("eligibility_status") != "eligible":
            continue
        if row.get("veto_reasons"):
            continue
        by_date[str(row.get("trade_date"))].append(dict(row))

    selected: list[dict[str, Any]] = []
    for trade_date in sorted(by_date):
        stocks = aggregate_stock_mappings(by_date[trade_date])
        scored: list[dict[str, Any]] = []
        for stock in stocks:
            score = ablation_score(stock, variant)
            if score is None:
                continue
            scored.append(
                {
                    **stock,
                    "variant": variant,
                    "variant_score": score,
                    "source_scope": "full_historical_candidate_set",
                }
            )
        scored.sort(
            key=lambda row: (
                -float(row["variant_score"]),
                normalize_stock_code(row.get("code")),
            )
        )
        for rank, row in enumerate(scored[:top_n], start=1):
            row["rank_in_date"] = rank
            selected.append(row)
    return selected


def evaluate_ablation_rows(
    rows: list[dict[str, Any]],
    *,
    cost_bps: float,
    min_dates: int,
    min_observations: int,
) -> dict[str, Any]:
    valid: list[dict[str, Any]] = []
    missing_adj_factor_count = 0
    for source in rows:
        row = dict(source)
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
            cost_bps,
        )
        valid.append(row)
    dates = {str(row.get("trade_date")) for row in valid}
    by_pool = {
        pool: summarize_returns(
            [row for row in valid if row.get("pool_code") == pool]
        )
        for pool in ELIGIBLE_POOLS
    }
    coverage = {
        "candidate_rows": len(rows),
        "return_rows": len(valid),
        "score_dates": len(dates),
        "missing_adj_factor_count": missing_adj_factor_count,
    }
    missing: list[str] = []
    if len(dates) < min_dates:
        missing.append(f"at least {min_dates} score dates")
    if len(valid) < min_observations:
        missing.append(f"at least {min_observations} return observations")
    if not valid:
        missing.append("adjusted return rows")
    return {
        "status": "INSUFFICIENT_EVIDENCE" if missing else "READY",
        "summary": summarize_returns(valid),
        "by_pool": by_pool,
        "coverage": coverage,
        "insufficient_reason": "; ".join(dict.fromkeys(missing)) or None,
    }


def load_full_candidate_rows(
    connection,
    *,
    model_version: str,
    forward_days: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    filters = [
        "s.model_version = %s",
        "s.pool_code IN ('A','B','C')",
        "s.eligibility_status = 'eligible'",
        "b.status <> 'rejected'",
    ]
    params: list[Any] = [forward_days - 1, model_version]
    if start_date:
        filters.append("s.trade_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("s.trade_date <= %s")
        params.append(end_date)
    where_clause = " AND ".join(filters)
    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT
                s.trade_date,
                b.code,
                b.mapping_id,
                b.business_segment_id,
                b.chain_id,
                (b.business_segment_id IS NOT NULL AND
                 (b.revenue_ratio IS NOT NULL OR b.gross_profit_ratio IS NOT NULL))
                    AS independent_revenue,
                s.benefit_score,
                s.expectation_gap_score,
                s.catalyst_score,
                s.risk_score,
                s.confidence_score,
                s.opportunity_score,
                s.pool_code,
                s.eligibility_status,
                s.veto_reasons,
                a.evidence_level,
                a.authenticity_score,
                o.total_score AS operating_quality_score,
                ben.score_detail AS benefit_detail,
                stage.commercialization_stage AS commercial_stage,
                NULL::double precision AS v1_score,
                entry.trade_date AS entry_date,
                entry.open AS entry_open,
                entry.adj_factor AS entry_adj,
                exit.close AS exit_close,
                exit.adj_factor AS exit_adj
            FROM business_tag_selection_scores s
            JOIN business_tag_mapping b ON b.mapping_id = s.mapping_id
            JOIN business_tag_authenticity_scores a
              ON a.mapping_id = s.mapping_id
             AND a.trade_date = s.trade_date
             AND a.model_version = s.model_version
            JOIN business_tag_operating_quality_scores o
              ON o.mapping_id = s.mapping_id
             AND o.trade_date = s.trade_date
             AND o.model_version = s.model_version
            JOIN business_tag_benefit_scores ben
              ON ben.mapping_id = s.mapping_id
             AND ben.trade_date = s.trade_date
             AND ben.model_version = s.model_version
            LEFT JOIN LATERAL (
                SELECT st.commercialization_stage
                FROM business_tag_stage_tracking st
                WHERE st.mapping_id = b.mapping_id
                  AND st.trade_date <= s.trade_date
                ORDER BY st.trade_date DESC, st.created_at DESC
                LIMIT 1
            ) stage ON TRUE
            JOIN LATERAL (
                SELECT k.trade_date, k.open, a.adj_factor
                FROM daily_kline k
                LEFT JOIN adj_factor a
                  ON a.code = k.code AND a.trade_date = k.trade_date
                WHERE k.code = split_part(b.code, '.', 1)
                  AND k.trade_date > s.trade_date
                  AND k.open > 0
                ORDER BY k.trade_date
                LIMIT 1
            ) entry ON TRUE
            JOIN LATERAL (
                SELECT k.close, a.adj_factor
                FROM daily_kline k
                LEFT JOIN adj_factor a
                  ON a.code = k.code AND a.trade_date = k.trade_date
                WHERE k.code = split_part(b.code, '.', 1)
                  AND k.trade_date >= entry.trade_date
                  AND k.close > 0
                ORDER BY k.trade_date
                OFFSET %s LIMIT 1
            ) exit ON TRUE
            WHERE {where_clause}
            ORDER BY s.trade_date, b.code, b.mapping_id
            """,
            tuple(params),
        )
        return [dict(row) for row in cur.fetchall()]


def persist_factor_evaluation(
    connection,
    *,
    variant: str,
    request: dict[str, Any],
    report: dict[str, Any],
) -> str:
    evaluation_id = f"FE-SCV2-{uuid.uuid4()}"
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO factor_evaluations (
                evaluation_id, model_key, status, request, report
            ) VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                evaluation_id,
                f"{MODEL_ID}:{variant}",
                report.get("status", "UNKNOWN"),
                json.dumps(request, ensure_ascii=False, default=str),
                json.dumps(report, ensure_ascii=False, default=str),
            ),
        )
    return evaluation_id


def run_backtest(
    *,
    pg_url: str,
    forward_days: int,
    cost_bps: float,
    top_n: int,
    model_version: str,
    min_dates: int,
    min_observations: int,
    run_ablation: bool,
    dry_run: bool,
    start_date: str | None = None,
    end_date: str | None = None,
    connection_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    if forward_days < 1:
        raise ValueError("forward_days must be positive")
    factory = connection_factory or (
        lambda: psycopg2.connect(pg_url, connect_timeout=5)
    )
    snapshot_report = SupplyChainSelectionV2Adapter().run(
        BacktestRequest(
            model_key=MODEL_ID,
            forward_days=forward_days,
            cost_bps=cost_bps,
            min_periods=min_dates,
            min_per_day=1,
            min_observations=min_observations,
            connection_factory=factory,
        ),
        readiness={"status": "ready"},
    )
    ablations: dict[str, dict[str, Any]] = {}
    if run_ablation:
        connection = factory()
        try:
            full_rows = load_full_candidate_rows(
                connection,
                model_version=model_version,
                forward_days=forward_days,
                start_date=start_date,
                end_date=end_date,
            )
            for variant in ABLATIONS:
                selected = rank_full_candidate_set(
                    full_rows,
                    variant=variant,
                    top_n=top_n,
                )
                report = evaluate_ablation_rows(
                    selected,
                    cost_bps=cost_bps,
                    min_dates=min_dates,
                    min_observations=min_observations,
                )
                report.update(
                    variant=variant,
                    forward_days=forward_days,
                    source_scope="full_historical_candidate_set",
                )
                request_payload = {
                    "variant": variant,
                    "forward_days": forward_days,
                    "cost_bps": cost_bps,
                    "top_n": top_n,
                    "model_version": model_version,
                    "min_dates": min_dates,
                    "min_observations": min_observations,
                    "start_date": start_date,
                    "end_date": end_date,
                    "source_scope": "full_historical_candidate_set",
                }
                report["evaluation_id"] = (
                    None
                    if dry_run
                    else persist_factor_evaluation(
                        connection,
                        variant=variant,
                        request=request_payload,
                        report=report,
                    )
                )
                ablations[variant] = report
            if dry_run:
                connection.rollback()
            else:
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    return {
        "model_key": MODEL_ID,
        "model_version": model_version,
        "forward_days": forward_days,
        "cost_bps": cost_bps,
        "snapshot_report": snapshot_report,
        "ablations": ablations,
        "dry_run": dry_run,
        "limitations": [
            "v1 requires frozen full historical legacy candidate scores; absent rows remain insufficient",
            "no production promotion is performed by this tool",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest supply-chain research selection V2"
    )
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--forward-days", type=int, default=5)
    parser.add_argument("--cost-bps", type=float, default=14.0)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--model-version", default=MODEL_VERSION)
    parser.add_argument("--min-dates", type=int, default=20)
    parser.add_argument("--min-observations", type=int, default=100)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--run-ablation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_backtest(
        pg_url=args.pg_url,
        forward_days=args.forward_days,
        cost_bps=args.cost_bps,
        top_n=args.top_n,
        model_version=args.model_version,
        min_dates=args.min_dates,
        min_observations=args.min_observations,
        run_ablation=args.run_ablation,
        dry_run=args.dry_run,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
