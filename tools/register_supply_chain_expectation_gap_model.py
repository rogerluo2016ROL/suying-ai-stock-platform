#!/usr/bin/env python3
"""Register and snapshot the supply-chain expectation-gap screener.

This script is intentionally SQL-backed: it registers the model in the project
model tables and records the latest pick snapshot from already-landed
business-tag scores. It does not invent evidence or call an LLM.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import psycopg2
import psycopg2.extras


MODEL_KEY = "supply_chain_expectation_gap_v1"
MODEL_NAME = "产业链预期差选股模型"
DISPLAY_NAME = "产业链预期差选股模型 V1.0"
VERSION_TAG = "v1.0"

FACTOR_KEYS = [
    "model_score",
    "expectation_gap_score",
    "reliability_adjusted_gap_score",
    "evidence_quality_score",
    "label_fit_score",
    "gap_momentum_score",
    "actual_progress_score",
    "market_expectation_score",
    "evidence_delta_score",
    "risk_penalty_score",
    "three_high_total",
    "growth_score",
    "profit_score",
    "moat_score",
    "stage_score",
    "evidence_score",
    "prosperity_score",
    "price_change_20d",
    "approved_evidence_count",
]

REASSESSMENT_ALLOWED_STATUSES = {"strong_confirmed", "watch_review"}

REASSESSMENT_KNOWN_STATUSES = (
    "strong_confirmed",
    "watch_review",
    "manual_review",
    "downgrade_or_remove",
)


def parse_min_reassessment(value: str | None) -> list[str]:
    """解析 --min-reassessment(逗号分隔状态列表);空值回退默认门槛。"""
    if not value:
        return sorted(REASSESSMENT_ALLOWED_STATUSES)
    statuses = [item.strip() for item in str(value).split(",") if item.strip()]
    unknown = [item for item in statuses if item not in REASSESSMENT_KNOWN_STATUSES]
    if unknown:
        raise ValueError(f"unknown reassessment status: {unknown}; known: {list(REASSESSMENT_KNOWN_STATUSES)}")
    return statuses

SIGNAL_TIER_THRESHOLDS = {
    "strong": 15.0,
    "watch": 8.0,
    "early": 3.0,
}


def grade_from_score(score: float) -> str:
    if score >= 65:
        return "S"
    if score >= 55:
        return "A"
    if score >= 45:
        return "B"
    return "C"


def signal_tier_from_gap(gap_score: float) -> str:
    score = float(gap_score or 0.0)
    if score >= SIGNAL_TIER_THRESHOLDS["strong"]:
        return "strong"
    if score >= SIGNAL_TIER_THRESHOLDS["watch"]:
        return "watch"
    if score >= SIGNAL_TIER_THRESHOLDS["early"]:
        return "early"
    return "none"


def latest_trade_date(cur) -> str:
    cur.execute("SELECT max(trade_date) AS trade_date FROM business_tag_expectation_gap_scores")
    row = cur.fetchone()
    if not row or not row["trade_date"]:
        raise RuntimeError("business_tag_expectation_gap_scores has no trade_date")
    return str(row["trade_date"])[:10]


def _num(row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key)
    if value is None:
        return default
    return float(value)


def is_reassessment_eligible(row: dict) -> bool:
    return str(row.get("reassessment_status") or "") in REASSESSMENT_ALLOWED_STATUSES


def model_score_from_row(row: dict) -> float:
    """Score one already re-assessed mapping.

    The important change is that the leading gap factor uses the conservative
    reliability-adjusted score, not the raw expectation-gap score.
    """

    score = (
        _num(row, "reliability_adjusted_gap_score") * 0.40
        + _num(row, "gap_momentum_score", 50) * 0.12
        + _num(row, "three_high_total") * 0.20
        + _num(row, "evidence_delta_score") * 0.10
        + _num(row, "moat_score") * 0.08
        + _num(row, "prosperity_score", 50) * 0.08
        + _num(row, "evidence_quality_score") * 0.12
        + _num(row, "label_fit_score") * 0.08
        - max(_num(row, "price_change_20d"), 0) * 0.08
    )
    return round(score, 2)


def fetch_picks(
    cur,
    trade_date: str,
    top_n: int,
    min_gap: float,
    min_reassessment: list[str] | None = None,
    allow_lookahead: bool = False,
) -> list[dict]:
    statuses = list(min_reassessment) if min_reassessment else sorted(REASSESSMENT_ALLOWED_STATUSES)
    if allow_lookahead:
        # 旧行为(仅对比用):把全库最新 assessment_date 的评估 join 到所有历史 score_date,
        # 对历史日期而言是未来函数。
        reassessment_join = """
            JOIN business_tag_evidence_reassessment r
              ON r.mapping_id = g.mapping_id
             AND r.assessment_date = (
                 SELECT max(assessment_date) FROM business_tag_evidence_reassessment
             )
        """
        params: tuple = (trade_date, statuses, min_gap, top_n)
    else:
        # as-of join:每个 score_date 只用 assessment_date <= 当日的最近一次评估。
        reassessment_join = """
            JOIN (
                SELECT DISTINCT ON (mapping_id)
                    mapping_id, assessment_date, reliability_adjusted_gap_score,
                    evidence_quality_score, label_fit_score, review_status
                FROM business_tag_evidence_reassessment
                WHERE assessment_date <= %s
                ORDER BY mapping_id, assessment_date DESC
            ) r ON r.mapping_id = g.mapping_id
        """
        params = (trade_date, trade_date, statuses, min_gap, top_n)
    cur.execute(
        """
        WITH scored AS (
            SELECT
                b.mapping_id,
                b.code,
                coalesce(s.name, split_part(b.code, '.', 1)) AS name,
                b.chain_id,
                b.tag_name,
                g.expectation_gap_score,
                g.gap_type,
                r.reliability_adjusted_gap_score,
                r.evidence_quality_score,
                r.label_fit_score,
                r.review_status AS reassessment_status,
                g.actual_progress_score,
                g.market_expectation_score,
                g.evidence_delta_score,
                g.risk_penalty_score,
                t.total_score AS three_high_total,
                t.growth_score,
                t.profit_score,
                t.moat_score,
                t.stage_score,
                t.evidence_score,
                coalesce((g.score_detail->>'prosperity_score')::numeric, 50) AS prosperity_score,
                coalesce((g.score_detail->>'gap_momentum_score')::numeric, 50) AS gap_momentum_score,
                (g.score_detail->>'price_change_20d')::numeric AS price_change_20d,
                coalesce((g.score_detail->>'approved_evidence_count')::int, 0) AS approved_evidence_count,
                dk.close,
                dk.change_pct,
                round((
                    r.reliability_adjusted_gap_score * 0.40
                    + coalesce((g.score_detail->>'gap_momentum_score')::numeric, 50) * 0.12
                    + coalesce(t.total_score, 0) * 0.20
                    + g.evidence_delta_score * 0.10
                    + coalesce(t.moat_score, 0) * 0.08
                    + coalesce((g.score_detail->>'prosperity_score')::numeric, 50) * 0.08
                    + r.evidence_quality_score * 0.12
                    + r.label_fit_score * 0.08
                    - greatest(coalesce((g.score_detail->>'price_change_20d')::numeric, 0), 0) * 0.08
                )::numeric, 2) AS model_score
            FROM business_tag_expectation_gap_scores g
            JOIN business_tag_mapping b ON b.mapping_id = g.mapping_id
            """ + reassessment_join + """
            LEFT JOIN business_tag_three_high_scores t
              ON t.mapping_id = g.mapping_id AND t.trade_date = g.trade_date
            LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
            LEFT JOIN daily_kline dk
              ON dk.code = split_part(b.code, '.', 1) AND dk.trade_date = g.trade_date
            WHERE g.trade_date = %s
              AND g.gap_type IN ('positive', 'positive_evidence_delta', 'neutral')
              AND r.review_status = ANY(%s)
              AND r.reliability_adjusted_gap_score >= %s
              AND coalesce(s.is_st, 0) = 0
        ),
        ranked AS (
            SELECT *,
                row_number() OVER (
                    PARTITION BY split_part(code, '.', 1)
                    ORDER BY model_score DESC, reliability_adjusted_gap_score DESC
                ) AS rn
            FROM scored
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
        ORDER BY model_score DESC, reliability_adjusted_gap_score DESC, expectation_gap_score DESC
        LIMIT %s
        """,
        params,
    )
    rows = [dict(row) for row in cur.fetchall()]
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
        row["grade"] = grade_from_score(float(row.get("model_score") or 0))
        row["signal_tier"] = signal_tier_from_gap(float(row.get("reliability_adjusted_gap_score") or 0))
    return rows


def reassessment_candidate_counts(cur, trade_date: str, min_gap: float) -> dict[str, int]:
    """按 reassessment 档位统计当日(as-of)候选数,用于日志观察候选池厚度。"""
    cur.execute(
        """
        SELECT r.review_status, count(*) AS count
        FROM business_tag_expectation_gap_scores g
        JOIN (
            SELECT DISTINCT ON (mapping_id)
                mapping_id, reliability_adjusted_gap_score, review_status
            FROM business_tag_evidence_reassessment
            WHERE assessment_date <= %s
            ORDER BY mapping_id, assessment_date DESC
        ) r ON r.mapping_id = g.mapping_id
        WHERE g.trade_date = %s
          AND g.gap_type IN ('positive', 'positive_evidence_delta', 'neutral')
          AND r.reliability_adjusted_gap_score >= %s
        GROUP BY r.review_status
        ORDER BY count(*) DESC
        """,
        (trade_date, trade_date, min_gap),
    )
    return {str(row["review_status"]): int(row["count"]) for row in cur.fetchall()}


def factor_payload(row: dict) -> dict:
    payload = {}
    for key in FACTOR_KEYS:
        value = row.get(key)
        if value is not None:
            payload[key] = float(value)
    payload.update({
        "chain_id": row.get("chain_id"),
        "tag_name": row.get("tag_name"),
        "gap_type": row.get("gap_type"),
        "reassessment_status": row.get("reassessment_status"),
        "signal_tier": row.get("signal_tier") or signal_tier_from_gap(float(row.get("reliability_adjusted_gap_score") or row.get("expectation_gap_score") or 0)),
    })
    return payload


def next_version_tag(existing_count: int) -> str:
    """版本历史保留:首个版本用基础 tag,之后追加 -rN 序号后缀,不再覆盖旧行。"""
    if existing_count <= 0:
        return VERSION_TAG
    return f"{VERSION_TAG}-r{existing_count + 1}"


def count_existing_versions(cur, model_key: str = MODEL_KEY) -> int:
    cur.execute(
        """
        SELECT count(*) AS count
        FROM model_versions
        WHERE model_name = %s AND (version_tag = %s OR version_tag LIKE %s)
        """,
        (model_key, VERSION_TAG, f"{VERSION_TAG}-r%"),
    )
    return int(cur.fetchone()["count"] or 0)


def resolve_active_version(cur, model_key: str = MODEL_KEY) -> tuple[dict | None, bool]:
    """解析当前生效版本:production 优先;无 production 退回 is_current 行。

    返回 (version_row, fell_back_to_staging);无版本行时返回 (None, True)。
    """
    cur.execute(
        """
        SELECT id, model_name, version_tag, stage, is_current
        FROM model_versions
        WHERE model_name = %s AND stage = 'production'
        ORDER BY id DESC
        LIMIT 1
        """,
        (model_key,),
    )
    row = cur.fetchone()
    if row:
        return dict(row), False
    cur.execute(
        """
        SELECT id, model_name, version_tag, stage, is_current
        FROM model_versions
        WHERE model_name = %s AND is_current = true
        ORDER BY id DESC
        LIMIT 1
        """,
        (model_key,),
    )
    row = cur.fetchone()
    return (dict(row) if row else None), True


def register_model(cur, *, trade_date: str, top_n: int, pick_count: int, positive_count: int) -> dict:
    active_version, fell_back = resolve_active_version(cur, MODEL_KEY)
    production_active = bool(active_version) and not fell_back
    if production_active:
        # 已有 production 版本:快照挂到 production 下,不再铸造新 staging 行。
        version_tag = str(active_version["version_tag"])
    else:
        version_tag = next_version_tag(count_existing_versions(cur, MODEL_KEY))
    params = {
        "model_key": MODEL_KEY,
        "display_name": DISPLAY_NAME,
        "version_tag": version_tag,
        "selection_universe": "business_tag_mapping candidates across 18 supply chains",
        "dedupe": "one strongest mapping per stock code",
        "hard_filters": [
            "latest expectation-gap score date",
            "as-of evidence reassessment (latest assessment_date <= trade_date)",
            "gap_type in positive-compatible or neutral labels",
            "reassessment_status in configurable whitelist (default strong_confirmed/watch_review)",
            "reliability_adjusted_gap_score >= 8 by default",
            "exclude ST stocks",
        ],
        "ranking_formula": (
            "reliability_adjusted_gap*0.40 + gap_momentum*0.12 + three_high*0.20 "
            "+ evidence_delta*0.10 + moat*0.08 + prosperity*0.08 "
            "+ evidence_quality*0.12 + label_fit*0.08 - positive_20d_return*0.08"
        ),
        "guardrails": [
            "not an automatic buy list",
            "weak signals cannot approve evidence or upgrade stages",
            "downgrade_or_remove and manual_review mappings are excluded from recommendations",
            "staging until forward returns are backfilled",
        ],
    }
    metrics = {
        "trade_date": trade_date,
        "top_n": top_n,
        "snapshot_count": pick_count,
        "positive_candidate_count": positive_count,
        "active_version_tag": version_tag,
    }
    cur.execute(
        """
        INSERT INTO screening_models (model_key, display_name, category, factor_keys, is_active)
        VALUES (%s, %s, %s, %s, true)
        ON CONFLICT (model_key) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            category = EXCLUDED.category,
            factor_keys = EXCLUDED.factor_keys,
            is_active = true
        """,
        (MODEL_KEY, DISPLAY_NAME, "产业链", FACTOR_KEYS),
    )
    # stage 由 promote 流程治理(production/archived),register 不在冲突时覆盖。
    cur.execute(
        """
        INSERT INTO model_registry (
            id, name, version, model_type, stage, run_id, params, metrics,
            artifact_uri, created_by, updated_at, notes
        )
        VALUES (%s, %s, 1, 'screener', 'staging', %s, %s::json, %s::json,
                %s, 'codex', now(), %s)
        ON CONFLICT (name, version) DO UPDATE SET
            id = EXCLUDED.id,
            model_type = EXCLUDED.model_type,
            run_id = EXCLUDED.run_id,
            params = EXCLUDED.params,
            metrics = EXCLUDED.metrics,
            artifact_uri = EXCLUDED.artifact_uri,
            updated_at = now(),
            notes = EXCLUDED.notes
        """,
        (
            MODEL_KEY,
            MODEL_NAME,
            f"{MODEL_KEY}-{trade_date}",
            json.dumps(params, ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False),
            "tools/register_supply_chain_expectation_gap_model.py",
            "三层证据驱动的产业链预期差选股模型；当前为 staging，需回填收益后再转 production。",
        ),
    )
    if production_active:
        # 快照计数记到 production 版本上,is_current 不动。
        cur.execute(
            """
            UPDATE model_versions
            SET snapshot_count = %s, deployed_at = now()
            WHERE id = %s
            """,
            (pick_count, int(active_version["id"])),
        )
    else:
        cur.execute(
            """
            UPDATE model_versions
            SET is_current = false
            WHERE model_name = %s
            """,
            (MODEL_KEY,),
        )
        # 历史版本保留:不再 DELETE,新行用序号后缀 tag、stage=staging。
        cur.execute(
            """
            INSERT INTO model_versions (
                model_name, version_tag, snapshot_count, win_rate,
                mean_return, is_current, deployed_at, stage
            )
            VALUES (%s, %s, %s, NULL, NULL, true, now(), 'staging')
            """,
            (MODEL_KEY, version_tag, pick_count),
        )
    return {
        "version_tag": version_tag,
        "production_active": production_active,
        "fell_back_to_staging": fell_back,
    }


def write_snapshot(cur, picks: list[dict], trade_date: str, time_slot: str) -> int:
    cur.execute(
        """
        DELETE FROM screening_snapshots
        WHERE model_key = %s AND trade_date = %s AND time_slot = %s
        """,
        (MODEL_KEY, trade_date, time_slot),
    )
    rows = []
    for row in picks:
        rows.append(
            (
                MODEL_KEY,
                trade_date,
                str(row["code"]),
                time_slot,
                json.dumps(factor_payload(row), ensure_ascii=False),
                float(row.get("model_score") or 0),
                row["grade"],
                int(row["rank"]),
            )
        )
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO screening_snapshots (
            model_key, trade_date, stock_code, time_slot,
            factors, total_score, grade, rank_in_day
        )
        VALUES %s
        """,
        rows,
        page_size=100,
    )
    return len(rows)


def register_and_snapshot(
    pg_url: str,
    trade_date: str | None,
    top_n: int,
    min_gap: float,
    time_slot: str,
    min_reassessment: list[str] | None = None,
    allow_lookahead: bool = False,
) -> dict:
    statuses = list(min_reassessment) if min_reassessment else sorted(REASSESSMENT_ALLOWED_STATUSES)
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            score_date = trade_date or latest_trade_date(cur)
            picks = fetch_picks(
                cur, score_date, top_n, min_gap,
                min_reassessment=statuses, allow_lookahead=allow_lookahead,
            )
            candidate_counts = reassessment_candidate_counts(cur, score_date, min_gap)
            positive_count = sum(candidate_counts.get(status, 0) for status in statuses)
            version_info = register_model(
                cur,
                trade_date=score_date,
                top_n=top_n,
                pick_count=len(picks),
                positive_count=positive_count,
            )
            snapshot_count = write_snapshot(cur, picks, score_date, time_slot)
        conn.commit()
    if version_info["fell_back_to_staging"] and not version_info["production_active"]:
        print(
            f"[register] 无 production 版本,快照挂到新 staging 版本 {version_info['version_tag']};"
            "晋升请使用 tools/promote_supply_chain_model.py"
        )
    elif version_info["production_active"]:
        print(f"[register] 快照挂到 production 版本 {version_info['version_tag']}")
    return {
        "model_key": MODEL_KEY,
        "display_name": DISPLAY_NAME,
        "version_tag": version_info["version_tag"],
        "stage": "production" if version_info["production_active"] else "staging",
        "trade_date": score_date,
        "top_n": top_n,
        "min_gap": min_gap,
        "min_reassessment": statuses,
        "allow_lookahead": allow_lookahead,
        "reassessment_candidate_counts": candidate_counts,
        "positive_candidate_count": positive_count,
        "snapshot_count": snapshot_count,
        "top_picks": [
            {
                "rank": row["rank"],
                "code": row["code"],
                "name": row["name"],
                "chain_id": row["chain_id"],
                "tag_name": row["tag_name"],
                "model_score": float(row["model_score"]),
                "expectation_gap_score": float(row["expectation_gap_score"]),
                "reliability_adjusted_gap_score": float(row.get("reliability_adjusted_gap_score") or 0),
                "evidence_quality_score": float(row.get("evidence_quality_score") or 0),
                "label_fit_score": float(row.get("label_fit_score") or 0),
                "reassessment_status": row.get("reassessment_status"),
                "gap_momentum_score": float(row.get("gap_momentum_score") or 0),
                "three_high_total": float(row["three_high_total"] or 0),
                "grade": row["grade"],
                "signal_tier": row["signal_tier"],
            }
            for row in picks[:10]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Register supply-chain expectation-gap screener")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--min-gap", type=float, default=8.0)
    parser.add_argument("--time-slot", default="close")
    parser.add_argument("--min-reassessment", default=None,
                        help="逗号分隔的 reassessment 状态白名单,默认 strong_confirmed,watch_review")
    parser.add_argument("--allow-lookahead", action="store_true",
                        help="对比模式:join 全库最新 reassessment(未来函数),仅用于对比")
    args = parser.parse_args()
    payload = register_and_snapshot(
        args.pg_url,
        args.trade_date,
        args.top_n,
        args.min_gap,
        args.time_slot,
        min_reassessment=parse_min_reassessment(args.min_reassessment),
        allow_lookahead=args.allow_lookahead,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
