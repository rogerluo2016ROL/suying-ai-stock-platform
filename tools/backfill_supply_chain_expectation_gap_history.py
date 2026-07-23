#!/usr/bin/env python3
"""Backfill historical as-of scores for the supply-chain expectation-gap model.

Strict 模式(默认,--as-of-strict)只使用评分日 D 当日可见的数据:
- approved evidence events:reviewed_at(Asia/Shanghai 折算)<= D;存量 approved 行
  reviewed_at 为 NULL 时用 created_at 兜底(分布会打印在输出里)
- stage tracking rows:review_status='approved' 且可见日 <= D;该表无 reviewed_at 列,
  按规则用 created_at 兜底
- expectation monitor claims:claim_date 落在 [D-60d, D] 滚动窗内(不再单调累积)
- kline price reaction up to score date
- industry proxy rows with trade_date <= score date

--allow-lookahead 保留旧行为(按 event_date/trade_date 回放、monitor 累积计数),
仅用于对比验证未来函数的影响,不得用于正式评分。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict, deque
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

# 注入共享 packages(照 bom 工具惯例)
_KRONOS_FACTORS = Path(__file__).resolve().parents[1] / "packages" / "kronos-factors"
if _KRONOS_FACTORS.is_dir() and str(_KRONOS_FACTORS) not in sys.path:
    sys.path.insert(0, str(_KRONOS_FACTORS))

# 双评分公式唯一实现;不再从 supply_chain_data_collection_center 反向 import。
from kronos_factors.engine.supply_chain_scoring import (
    calculate_evidence_score,
    calculate_gap_momentum_score,
    calculate_market_expectation_score,
    calculate_prosperity_score,
    calculate_stage_progress_score,
    classify_business_tag_events,
    compute_expectation_gap_score,
    compute_three_high_score,
    split_claim_counts,
)


def _row_id(prefix: str, mapping_id: str, trade_date: str) -> str:
    payload = f"{prefix}:{mapping_id}:{trade_date}"
    return f"{prefix}-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _base_code(code: str) -> str:
    return str(code or "").split(".", 1)[0]


def _load_trade_dates(cur, start_date: str, end_date: str) -> list[date]:
    cur.execute(
        """
        SELECT DISTINCT trade_date
        FROM daily_kline
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY trade_date
        """,
        (start_date, end_date),
    )
    return [_to_date(row["trade_date"]) for row in cur.fetchall() if _to_date(row["trade_date"])]


def _load_mappings(cur, require_evidence: bool = False) -> list[dict[str, Any]]:
    # require_evidence: 只保留 status='verified' 或存在 approved 证据事件的映射,
    # 用于把诚实回放限定在有研究覆盖的宇宙内。
    scope = ""
    if require_evidence:
        scope = """
          AND (
              b.status = 'verified'
              OR EXISTS (
                  SELECT 1 FROM business_tag_evidence_events e
                  WHERE e.mapping_id = b.mapping_id AND e.review_status = 'approved'
              )
          )
        """
    cur.execute(
        """
        SELECT b.mapping_id, b.code, split_part(b.code, '.', 1) AS base_code,
               b.chain_id, b.tag_name, b.revenue_ratio, b.gross_profit_ratio,
               b.confidence, s.listed_date, coalesce(s.is_st, 0) AS is_st
        FROM business_tag_mapping b
        LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
        WHERE coalesce(b.status, 'active') <> 'disabled'
        """ + scope + """
        ORDER BY b.mapping_id
        """
    )
    return [dict(row) for row in cur.fetchall()]


def _load_kline_features(cur, codes: list[str], start_date: str, end_date: str) -> tuple[set[tuple[str, date]], dict[tuple[str, date], float | None]]:
    if not codes:
        return set(), {}
    warmup_start = (date.fromisoformat(start_date) - timedelta(days=80)).isoformat()
    cur.execute(
        """
        SELECT code, trade_date, close
        FROM daily_kline
        WHERE code = ANY(%s)
          AND trade_date BETWEEN %s AND %s
          AND close IS NOT NULL
          AND close > 0
        ORDER BY code, trade_date
        """,
        (codes, warmup_start, end_date),
    )
    by_code: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in cur.fetchall():
        day = _to_date(row["trade_date"])
        if day:
            by_code[str(row["code"])].append((day, float(row["close"])))

    start = date.fromisoformat(start_date)
    tradable: set[tuple[str, date]] = set()
    price_change: dict[tuple[str, date], float | None] = {}
    for code, rows in by_code.items():
        window: deque[float] = deque(maxlen=21)
        for day, close in rows:
            window.append(close)
            if day < start:
                continue
            tradable.add((code, day))
            if len(window) >= 21 and window[0] > 0:
                price_change[(code, day)] = round((close / window[0] - 1.0) * 100.0, 2)
            else:
                price_change[(code, day)] = None
    return tradable, price_change


def _load_events(cur) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    # as-of 可见性规则:评分日 D 可见 = review_status='approved' 且审批时间不晚于 D。
    # reviewed_at 为 timestamptz,统一按 Asia/Shanghai 折算成日期再与 D 比较。
    # 存量 approved 行若 reviewed_at 为 NULL(如早期批量导入),用 created_at 兜底,
    # 即"进入数据库的时间"视为可见时间;两类行数分布写入 stats 供调用方打印。
    cur.execute(
        """
        SELECT mapping_id, event_id, code, title, evidence_type, impact_dimensions,
               confidence, event_date,
               (reviewed_at AT TIME ZONE 'Asia/Shanghai')::date AS reviewed_date,
               created_at::date AS created_date
        FROM business_tag_evidence_events
        WHERE review_status = 'approved'
          AND event_date IS NOT NULL
        ORDER BY mapping_id, event_date, created_at
        """
    )
    events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats = {"approved_total": 0, "with_reviewed_at": 0, "created_at_fallback": 0}
    for row in cur.fetchall():
        item = dict(row)
        item["event_date"] = _to_date(item.get("event_date"))
        reviewed_date = _to_date(item.get("reviewed_date"))
        created_date = _to_date(item.get("created_date"))
        stats["approved_total"] += 1
        if reviewed_date is not None:
            stats["with_reviewed_at"] += 1
        else:
            stats["created_at_fallback"] += 1
        item["approved_date"] = reviewed_date or created_date or item["event_date"]
        events[str(item["mapping_id"])].append(item)
    return events, stats


def _load_monitors(cur) -> dict[str, list[dict[str, Any]]]:
    cur.execute(
        """
        SELECT mapping_id, claim_source_type, claim_date
        FROM business_tag_expectation_monitor
        WHERE claim_date IS NOT NULL
          AND review_status IN ('candidate', 'pending_review', 'approved')
        ORDER BY mapping_id, claim_date, created_at
        """
    )
    monitors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cur.fetchall():
        item = dict(row)
        item["claim_date"] = _to_date(item.get("claim_date"))
        monitors[str(item["mapping_id"])].append(item)
    return monitors


def _load_stages(cur) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    # as-of 可见性规则:评分日 D 可见 = review_status='approved' 且审批时间不晚于 D。
    # 注意:business_tag_stage_tracking 当前没有 reviewed_at 列(migration 020/033
    # 均未添加),按既定兜底规则用 created_at(审批后落库时间)作为可见时间。
    cur.execute(
        """
        SELECT mapping_id, trade_date, research_stage, commercialization_stage,
               created_at::date AS created_date
        FROM business_tag_stage_tracking
        WHERE trade_date IS NOT NULL
          AND review_status = 'approved'
        ORDER BY mapping_id, trade_date, created_at
        """
    )
    stages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats = {"approved_total": 0, "with_reviewed_at": 0, "created_at_fallback": 0}
    for row in cur.fetchall():
        item = dict(row)
        item["trade_date"] = _to_date(item.get("trade_date"))
        item["approved_date"] = _to_date(item.get("created_date")) or item["trade_date"]
        stats["approved_total"] += 1
        stats["created_at_fallback"] += 1
        stages[str(item["mapping_id"])].append(item)
    return stages, stats


def _load_prosperity(cur, trade_dates: list[date]) -> dict[tuple[str, date], dict[str, Any]]:
    cur.execute(
        """
        SELECT chain_id, trade_date, avg(metric_value) AS avg_pct
        FROM industry_price_series
        WHERE metric_name = 'dc_index_pct_change'
          AND trade_date IS NOT NULL
        GROUP BY chain_id, trade_date
        ORDER BY chain_id, trade_date
        """
    )
    series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in cur.fetchall():
        day = _to_date(row["trade_date"])
        if day and row["avg_pct"] is not None:
            series[str(row["chain_id"])].append((day, float(row["avg_pct"])))

    result: dict[tuple[str, date], dict[str, Any]] = {}
    for chain_id, rows in series.items():
        idx = 0
        window: deque[float] = deque(maxlen=5)
        for score_date in trade_dates:
            while idx < len(rows) and rows[idx][0] <= score_date:
                window.append(rows[idx][1])
                idx += 1
            if window:
                values = list(window)
                result[(chain_id, score_date)] = {
                    "latest_pct_change": values[-1],
                    "avg_pct_change": round(sum(values) / len(values), 4),
                    "sample_days": len(values),
                }
    return result


MONITOR_WINDOW_DAYS = 60  # strict 模式下市场预期只计 [D-60d, D] 滚动窗内的 claims


def _build_scores_for_mapping(
    mapping: dict[str, Any],
    trade_dates: list[date],
    tradable: set[tuple[str, date]],
    price_change: dict[tuple[str, date], float | None],
    events: list[dict[str, Any]],
    monitors: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    prosperity_by_chain_date: dict[tuple[str, date], dict[str, Any]],
    as_of_strict: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mapping_id = str(mapping["mapping_id"])
    base_code = str(mapping.get("base_code") or _base_code(mapping.get("code") or ""))
    listed_date = _to_date(mapping.get("listed_date"))
    is_st = int(mapping.get("is_st") or 0)
    revenue_ratio = mapping.get("revenue_ratio")
    gross_profit_ratio = mapping.get("gross_profit_ratio")

    # strict 模式按"审批可见日"(approved_date)回放,lookahead 对比模式沿用旧的
    # 按 event_date/trade_date 回放(审批动作发生在未来,属于未来函数)。
    if as_of_strict:
        events = sorted(events, key=lambda row: (row.get("approved_date") or row["event_date"], row["event_date"]))
        stages = sorted(stages, key=lambda row: (row.get("approved_date") or row["trade_date"], row["trade_date"]))

    event_idx = monitor_idx = stage_idx = 0
    active_events: list[dict[str, Any]] = []
    monitor_counts: dict[str, int] = defaultdict(int)
    monitor_window: deque[tuple[date, str]] = deque()
    current_stage: dict[str, Any] = {}
    three_high_rows: list[dict[str, Any]] = []
    gap_rows: list[dict[str, Any]] = []
    gap_history: deque[float] = deque(maxlen=20)

    for score_date in trade_dates:
        if is_st:
            continue
        if listed_date and listed_date > score_date:
            continue
        if (base_code, score_date) not in tradable:
            continue

        if as_of_strict:
            while event_idx < len(events) and (events[event_idx].get("approved_date") or events[event_idx]["event_date"]) <= score_date:
                active_events.append(events[event_idx])
                event_idx += 1
        else:
            while event_idx < len(events) and events[event_idx]["event_date"] <= score_date:
                active_events.append(events[event_idx])
                event_idx += 1
        while monitor_idx < len(monitors) and monitors[monitor_idx]["claim_date"] <= score_date:
            source_type = str(monitors[monitor_idx].get("claim_source_type") or "unknown")
            monitor_counts[source_type] += 1
            monitor_window.append((monitors[monitor_idx]["claim_date"], source_type))
            monitor_idx += 1
        if as_of_strict:
            # 滚动 [D-60d, D] 窗口:过期 claim 移出计数,避免 market_expectation 被动抬升。
            window_start = score_date - timedelta(days=MONITOR_WINDOW_DAYS)
            while monitor_window and monitor_window[0][0] < window_start:
                _, source_type = monitor_window.popleft()
                monitor_counts[source_type] -= 1
                if monitor_counts[source_type] <= 0:
                    del monitor_counts[source_type]
        if as_of_strict:
            while stage_idx < len(stages) and (stages[stage_idx].get("approved_date") or stages[stage_idx]["trade_date"]) <= score_date:
                current_stage = stages[stage_idx]
                stage_idx += 1
        else:
            while stage_idx < len(stages) and stages[stage_idx]["trade_date"] <= score_date:
                current_stage = stages[stage_idx]
                stage_idx += 1

        event_counts = classify_business_tag_events(active_events)
        growth_events = event_counts["growth"]
        profit_events = event_counts["profit"]
        moat_events = event_counts["moat"]
        evidence_score = calculate_evidence_score(active_events, event_counts)
        stage_score = calculate_stage_progress_score(
            current_stage.get("research_stage"),
            current_stage.get("commercialization_stage"),
        )
        analyst_claims, news_claims, total_claims = split_claim_counts(monitor_counts)
        price_change_20d = price_change.get((base_code, score_date))
        market_expectation_score = calculate_market_expectation_score(
            analyst_claims=analyst_claims,
            news_claims=news_claims,
            total_claims=total_claims,
            price_change_20d=price_change_20d,
        )
        prosperity = prosperity_by_chain_date.get(
            (str(mapping.get("chain_id") or ""), score_date),
            {"latest_pct_change": None, "avg_pct_change": None, "sample_days": 0},
        )
        prosperity_score = calculate_prosperity_score(
            prosperity["latest_pct_change"],
            prosperity["avg_pct_change"],
        )
        revenue_value = float(revenue_ratio) if revenue_ratio is not None else None
        gross_profit_value = float(gross_profit_ratio) if gross_profit_ratio is not None else None
        three_high = compute_three_high_score(
            revenue_ratio=revenue_value,
            gross_profit_ratio=gross_profit_value,
            events=active_events,
            stage_score=stage_score,
            prosperity_score=prosperity_score,
        )
        growth_score = three_high["growth_score"]
        profit_score = three_high["profit_score"]
        moat_score = three_high["moat_score"]
        score_cap = three_high["score_cap"]
        total_score = three_high["total_score"]
        gap = compute_expectation_gap_score(
            stage_score=stage_score,
            evidence_score=evidence_score,
            prosperity_score=prosperity_score,
            market_expectation_score=market_expectation_score,
            risk_events=event_counts["risk"],
            price_change_20d=price_change_20d,
        )
        risk_penalty_score = gap["risk_penalty_score"]
        actual_progress_score = gap["actual_progress_score"]
        raw_gap = gap["raw_gap"]
        expectation_gap_score = gap["expectation_gap_score"]
        gap_type = gap["gap_type"]
        previous_gap = gap_history[-1] if gap_history else None
        gap_20d_ago = gap_history[0] if len(gap_history) >= 20 else None
        gap_momentum_score = calculate_gap_momentum_score(
            current_gap=expectation_gap_score,
            previous_gap=previous_gap,
            gap_20d_ago=gap_20d_ago,
        )
        gap_history.append(expectation_gap_score)

        score_date_text = score_date.isoformat()
        evidence_ids = [str(row["event_id"]) for row in active_events if row.get("event_id")][-50:]
        shared_detail = {
            "version": "supply-chain-history-asof-v2-strict" if as_of_strict else "supply-chain-history-asof-v1-lookahead",
            "trade_date_source": "historical_asof_backfill",
            "as_of_strict": as_of_strict,
            "approved_evidence_count": len(active_events),
            "monitor_counts": dict(monitor_counts),
            "monitor_window_days": MONITOR_WINDOW_DAYS if as_of_strict else None,
            "price_change_20d": price_change_20d,
            "previous_gap_score": previous_gap,
            "gap_20d_ago": gap_20d_ago,
            "gap_momentum_score": gap_momentum_score,
            "prosperity_score": prosperity_score,
            "prosperity_proxy": prosperity,
            "score_note": (
                "as-of 严格模式:证据/阶段按审批可见日(reviewed_at,缺失时 created_at 兜底)回放,"
                "monitor 计数为 [D-60d, D] 滚动窗;不使用未来审批结果。"
                if as_of_strict
                else "lookahead 对比模式:按 event_date/trade_date 回放且 monitor 单调累积,含未来函数,仅用于对比。"
            ),
        }
        three_high_rows.append({
            "score_id": _row_id("THREE-HIGH", mapping_id, score_date_text),
            "mapping_id": mapping_id,
            "trade_date": score_date_text,
            "growth_score": growth_score,
            "profit_score": profit_score,
            "moat_score": moat_score,
            "stage_score": stage_score,
            "evidence_score": evidence_score,
            "total_score": total_score,
            "score_detail": json.dumps({
                **shared_detail,
                "revenue_supported": revenue_value is not None,
                "profit_supported": profit_score is not None,
                "score_cap": score_cap,
                "growth_events": growth_events,
                "profit_events": profit_events,
                "moat_events": moat_events,
            }, ensure_ascii=False),
            "evidence_ids": json.dumps(evidence_ids, ensure_ascii=False),
        })
        gap_rows.append({
            "gap_id": _row_id("GAP", mapping_id, score_date_text),
            "mapping_id": mapping_id,
            "trade_date": score_date_text,
            "actual_progress_score": actual_progress_score,
            "market_expectation_score": market_expectation_score,
            "evidence_delta_score": evidence_score,
            "risk_penalty_score": risk_penalty_score,
            "expectation_gap_score": expectation_gap_score,
            "gap_type": gap_type,
            "score_detail": json.dumps({
                **shared_detail,
                "market_expectation_source": "asof_monitor_and_price_reaction",
                "actual_progress_formula": "stage*0.50 + evidence*0.32 + prosperity*0.18",
                "raw_gap": round(raw_gap, 2),
                "formula": "actual_progress - market_expectation + evidence*0.22 + prosperity_delta*0.20 - risk*0.40",
            }, ensure_ascii=False),
            "evidence_ids": json.dumps(evidence_ids, ensure_ascii=False),
        })
    return three_high_rows, gap_rows


def _insert_three_high(cur, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO business_tag_three_high_scores (
            score_id, mapping_id, trade_date, growth_score, profit_score,
            moat_score, stage_score, evidence_score, total_score,
            score_detail, evidence_ids
        )
        VALUES %s
        ON CONFLICT (mapping_id, trade_date) DO UPDATE SET
            growth_score = EXCLUDED.growth_score,
            profit_score = EXCLUDED.profit_score,
            moat_score = EXCLUDED.moat_score,
            stage_score = EXCLUDED.stage_score,
            evidence_score = EXCLUDED.evidence_score,
            total_score = EXCLUDED.total_score,
            score_detail = EXCLUDED.score_detail,
            evidence_ids = EXCLUDED.evidence_ids
        """,
        [
            (
                row["score_id"], row["mapping_id"], row["trade_date"],
                row["growth_score"], row["profit_score"], row["moat_score"],
                row["stage_score"], row["evidence_score"], row["total_score"],
                row["score_detail"], row["evidence_ids"],
            )
            for row in rows
        ],
        page_size=5000,
    )


def _insert_gap(cur, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO business_tag_expectation_gap_scores (
            gap_id, mapping_id, trade_date, actual_progress_score,
            market_expectation_score, evidence_delta_score, risk_penalty_score,
            expectation_gap_score, gap_type, score_detail, evidence_ids
        )
        VALUES %s
        ON CONFLICT (mapping_id, trade_date) DO UPDATE SET
            actual_progress_score = EXCLUDED.actual_progress_score,
            market_expectation_score = EXCLUDED.market_expectation_score,
            evidence_delta_score = EXCLUDED.evidence_delta_score,
            risk_penalty_score = EXCLUDED.risk_penalty_score,
            expectation_gap_score = EXCLUDED.expectation_gap_score,
            gap_type = EXCLUDED.gap_type,
            score_detail = EXCLUDED.score_detail,
            evidence_ids = EXCLUDED.evidence_ids
        """,
        [
            (
                row["gap_id"], row["mapping_id"], row["trade_date"],
                row["actual_progress_score"], row["market_expectation_score"],
                row["evidence_delta_score"], row["risk_penalty_score"],
                row["expectation_gap_score"], row["gap_type"],
                row["score_detail"], row["evidence_ids"],
            )
            for row in rows
        ],
        page_size=5000,
    )


def backfill_history(
    pg_url: str,
    *,
    start_date: str | None,
    end_date: str | None,
    years: int,
    commit_every: int,
    replace: bool,
    as_of_strict: bool = True,
    require_evidence: bool = False,
) -> dict[str, Any]:
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if end_date is None:
                cur.execute("SELECT max(trade_date) AS trade_date FROM daily_kline")
                end_date = str(cur.fetchone()["trade_date"])[:10]
            if start_date is None:
                start_date = (date.fromisoformat(end_date) - timedelta(days=365 * years)).isoformat()
            trade_dates = _load_trade_dates(cur, start_date, end_date)
            mappings = _load_mappings(cur, require_evidence=require_evidence)
            codes = sorted({_base_code(row["code"]) for row in mappings if row.get("code")})
            tradable, price_change = _load_kline_features(cur, codes, start_date, end_date)
            events_by_mapping, event_visibility = _load_events(cur)
            monitors_by_mapping = _load_monitors(cur)
            stages_by_mapping, stage_visibility = _load_stages(cur)
            prosperity_by_chain_date = _load_prosperity(cur, trade_dates)

            deleted_three_high = deleted_gap = 0
            if replace:
                cur.execute(
                    "DELETE FROM business_tag_three_high_scores WHERE trade_date BETWEEN %s AND %s",
                    (start_date, end_date),
                )
                deleted_three_high = cur.rowcount
                cur.execute(
                    "DELETE FROM business_tag_expectation_gap_scores WHERE trade_date BETWEEN %s AND %s",
                    (start_date, end_date),
                )
                deleted_gap = cur.rowcount
                conn.commit()

            written_three_high = written_gap = 0
            buffer_three_high: list[dict[str, Any]] = []
            buffer_gap: list[dict[str, Any]] = []
            for index, mapping in enumerate(mappings, start=1):
                mapping_id = str(mapping["mapping_id"])
                three_rows, gap_rows = _build_scores_for_mapping(
                    mapping,
                    trade_dates,
                    tradable,
                    price_change,
                    events_by_mapping.get(mapping_id, []),
                    monitors_by_mapping.get(mapping_id, []),
                    stages_by_mapping.get(mapping_id, []),
                    prosperity_by_chain_date,
                    as_of_strict=as_of_strict,
                )
                buffer_three_high.extend(three_rows)
                buffer_gap.extend(gap_rows)
                if index % commit_every == 0:
                    _insert_three_high(cur, buffer_three_high)
                    _insert_gap(cur, buffer_gap)
                    written_three_high += len(buffer_three_high)
                    written_gap += len(buffer_gap)
                    buffer_three_high.clear()
                    buffer_gap.clear()
                    conn.commit()
            _insert_three_high(cur, buffer_three_high)
            _insert_gap(cur, buffer_gap)
            written_three_high += len(buffer_three_high)
            written_gap += len(buffer_gap)
            conn.commit()

            cur.execute(
                """
                SELECT gap_type, count(*) AS count
                FROM business_tag_expectation_gap_scores
                WHERE trade_date BETWEEN %s AND %s
                GROUP BY gap_type
                ORDER BY gap_type
                """,
                (start_date, end_date),
            )
            distribution = {str(row["gap_type"]): int(row["count"]) for row in cur.fetchall()}
    return {
        "start_date": start_date,
        "end_date": end_date,
        "trade_dates": len(trade_dates),
        "mappings": len(mappings),
        "replace": replace,
        "as_of_strict": as_of_strict,
        "require_evidence": require_evidence,
        "event_visibility_stats": event_visibility,
        "stage_visibility_stats": stage_visibility,
        "deleted_three_high_scores": deleted_three_high,
        "deleted_expectation_gap_scores": deleted_gap,
        "written_three_high_scores": written_three_high,
        "written_expectation_gap_scores": written_gap,
        "gap_distribution": distribution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill historical supply-chain expectation-gap scores")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--commit-every", type=int, default=50)
    parser.add_argument("--replace", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--as-of-strict", dest="as_of_strict", action="store_true", default=True,
                      help="默认开启:按审批可见日(reviewed_at/created_at)回放,monitor 用 [D-60d, D] 滚动窗")
    mode.add_argument("--allow-lookahead", dest="as_of_strict", action="store_false",
                      help="对比模式:沿用旧的 event_date/trade_date 回放 + 累积 monitor 计数(含未来函数)")
    parser.add_argument("--require-evidence", action="store_true",
                        help="只回放 status='verified' 或存在 approved 证据的映射")
    args = parser.parse_args()
    payload = backfill_history(
        args.pg_url,
        start_date=args.start_date,
        end_date=args.end_date,
        years=args.years,
        commit_every=args.commit_every,
        replace=args.replace,
        as_of_strict=args.as_of_strict,
        require_evidence=args.require_evidence,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
