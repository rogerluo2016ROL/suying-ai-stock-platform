"""Unit tests for push_telemetry — pure logic only (no network/lark-cli).

Covers compute_status_health (status bands + score anchoring) and _merge
(delta accumulation + latest-field + failure_reasons merge). These are the
correctness core that every push task depends on.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub the config so importing the module never depends on a real Base token.
os.environ.setdefault("PUSH_METRICS_BASE_TOKEN", "")
os.environ.setdefault("PUSH_METRICS_TABLE_ID", "")

from push_telemetry import compute_status_health, _merge  # noqa: E402


# ---------------- compute_status_health ----------------
def test_down_when_no_pushes():
    assert compute_status_health({"push_count": 0}) == ("down", 0)


def test_perfect_run_is_healthy_high_score():
    status, score = compute_status_health(
        {"push_count": 10, "success": 10, "delivery_confirmed": 10, "delivery_unconfirmed": 0, "retries": 0, "latency_ms_p95": 800}
    )
    assert status == "healthy"
    assert score >= 90


def test_one_failure_out_of_six_is_degraded():
    # alert 08-12 seed scenario: 6 pushes, 5 success
    status, score = compute_status_health(
        {"push_count": 6, "success": 5, "retries": 1, "latency_ms_p95": 800}
    )
    assert status == "degraded"  # 83% < 90%
    assert score < 70


def test_warning_band_at_ninety_percent():
    status, _ = compute_status_health(
        {"push_count": 10, "success": 9, "retries": 0, "latency_ms_p95": 500}
    )
    assert status == "warning"  # exactly 90%


def test_uninstrumented_delivery_still_healthy_when_success_perfect():
    # screener: no delivery confirmation (delivery_* absent) but 100% success
    status, score = compute_status_health(
        {"push_count": 20, "success": 20, "retries": 0, "latency_ms_p95": 500}
    )
    assert status == "healthy"
    assert score >= 90  # only the small -5 uninstrumented penalty applies


def test_retries_and_latency_drain_score():
    base = compute_status_health(
        {"push_count": 100, "success": 100, "delivery_confirmed": 100, "retries": 0, "latency_ms_p95": 1000}
    )[1]
    heavy = compute_status_health(
        {"push_count": 100, "success": 100, "delivery_confirmed": 100, "retries": 6, "latency_ms_p95": 3000}
    )[1]
    assert heavy < base


def test_score_clamped_0_100():
    s_lo, _ = compute_status_health({"push_count": 100, "success": 0, "retries": 50, "latency_ms_p95": 5000})
    assert s_lo == "degraded"
    _, hi = compute_status_health({"push_count": 1, "success": 1, "delivery_confirmed": 1, "retries": 0, "latency_ms_p95": 100})
    assert hi <= 100


# ---------------- _merge ----------------
def test_additive_fields_sum():
    merged = _merge({"push_count": 12, "success": 12, "retries": 2},
                    {"push_count": 3, "success": 2, "failure": 1, "retries": 1})
    assert merged["push_count"] == 15
    assert merged["success"] == 14
    assert merged["failure"] == 1
    assert merged["retries"] == 3


def test_latest_fields_take_delta_over_existing():
    merged = _merge({"latency_ms_p95": 2100, "target_chats": 3},
                    {"latency_ms_p95": 1800, "target_chats": 3})
    assert merged["latency_ms_p95"] == 1800  # delta wins
    assert merged["target_chats"] == 3


def test_latest_fields_keep_existing_when_delta_null():
    merged = _merge({"latency_ms_p95": 2100}, {"latency_ms_p95": None})
    assert merged["latency_ms_p95"] == 2100


def test_failure_reasons_merge_unique_capped():
    existing = {"failure_reasons": "timeout; rate_limit"}
    delta = {"failure_reasons": ["timeout", "chat_not_found", "a", "b", "c", "d"]}
    merged = _merge(existing, delta)
    items = [x for x in merged["failure_reasons"].split("; ") if x]
    assert "timeout" in items and items.count("timeout") == 1  # dedup
    assert "chat_not_found" in items
    assert len(items) <= 5  # cap


def test_merge_handles_non_numeric_existing_gracefully():
    merged = _merge({"push_count": None, "success": "bad"}, {"push_count": 1, "success": 1})
    assert merged["push_count"] == 1
    assert merged["success"] == 1
