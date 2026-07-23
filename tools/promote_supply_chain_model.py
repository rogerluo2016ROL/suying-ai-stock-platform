#!/usr/bin/env python3
"""Promote a supply-chain model version from staging to production.

晋升门槛(默认阈值,均可 CLI 配置):
- snapshot_count >= --min-snapshots(默认 20)
- win_rate >= --min-win-rate(默认 50.0,百分制,与 model_versions.win_rate 口径一致)
- mean_return > --min-mean-return(默认 0.0,百分制)
- model_registry.metrics.backtest.conclusion 不得为 no_qualifying_candidates
  (且必须存在 backtest 记录,没跑过回测视同不达标)

满足则:旧 production 降级为 archived(is_current=false),目标版本置
stage='production' + is_current=true,model_registry.stage 同步为 production。
任何时刻 production 最多 1 个。不满足则拒绝并打印每项差距,退出码 1。
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg2
import psycopg2.extras

MODEL_KEY = "supply_chain_expectation_gap_v1"

DEFAULT_THRESHOLDS = {
    "min_snapshots": 20,
    "min_win_rate": 50.0,      # 百分制
    "min_mean_return": 0.0,    # 百分制
}


def evaluate_promotion_gates(
    version_row: dict[str, Any] | None,
    backtest_metrics: dict[str, Any] | None,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """逐项评估晋升门槛,返回 {ok, checks}。纯函数,便于单测。"""
    checks: dict[str, Any] = {}
    if not version_row:
        return {"ok": False, "checks": {"version_row": {"ok": False, "reason": "目标版本不存在"}}}

    snapshot_count = version_row.get("snapshot_count")
    checks["snapshot_count"] = {
        "actual": snapshot_count,
        "required": f">= {thresholds['min_snapshots']}",
        "ok": snapshot_count is not None and int(snapshot_count) >= thresholds["min_snapshots"],
    }
    win_rate = version_row.get("win_rate")
    checks["win_rate"] = {
        "actual": win_rate,
        "required": f">= {thresholds['min_win_rate']}",
        "ok": win_rate is not None and float(win_rate) >= thresholds["min_win_rate"],
    }
    mean_return = version_row.get("mean_return")
    checks["mean_return"] = {
        "actual": mean_return,
        "required": f"> {thresholds['min_mean_return']}",
        "ok": mean_return is not None and float(mean_return) > thresholds["min_mean_return"],
    }
    conclusion = (backtest_metrics or {}).get("conclusion")
    checks["backtest_conclusion"] = {
        "actual": conclusion if backtest_metrics else None,
        "required": "存在 backtest 记录且 conclusion != no_qualifying_candidates",
        "ok": bool(backtest_metrics) and conclusion != "no_qualifying_candidates",
    }
    return {"ok": all(item["ok"] for item in checks.values()), "checks": checks}


def _load_target_version(cur, model_key: str, version_tag: str | None) -> dict[str, Any] | None:
    if version_tag:
        cur.execute(
            """
            SELECT id, model_name, version_tag, stage, is_current, snapshot_count, win_rate, mean_return
            FROM model_versions
            WHERE model_name = %s AND version_tag = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (model_key, version_tag),
        )
    else:
        # 默认目标:当前 is_current 的 staging 版本
        cur.execute(
            """
            SELECT id, model_name, version_tag, stage, is_current, snapshot_count, win_rate, mean_return
            FROM model_versions
            WHERE model_name = %s AND is_current = true AND stage = 'staging'
            ORDER BY id DESC
            LIMIT 1
            """,
            (model_key,),
        )
    row = cur.fetchone()
    return dict(row) if row else None


def _load_backtest_metrics(cur, model_key: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT metrics->'backtest' AS backtest FROM model_registry WHERE id = %s",
        (model_key,),
    )
    row = cur.fetchone()
    if not row or row["backtest"] is None:
        return None
    return dict(row["backtest"])


def promote(
    pg_url: str,
    *,
    model_key: str = MODEL_KEY,
    version_tag: str | None = None,
    thresholds: dict[str, float] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    thresholds = dict(DEFAULT_THRESHOLDS | dict(thresholds or {}))
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            target = _load_target_version(cur, model_key, version_tag)
            backtest = _load_backtest_metrics(cur, model_key)
            verdict = evaluate_promotion_gates(target, backtest, thresholds)
            result: dict[str, Any] = {
                "model_key": model_key,
                "target_version": (target or {}).get("version_tag"),
                "thresholds": thresholds,
                "verdict": verdict,
                "promoted": False,
                "dry_run": dry_run,
            }
            if not verdict["ok"] or dry_run:
                if dry_run and verdict["ok"]:
                    result["note"] = "dry-run:门槛全部满足,未实际晋升"
                return result
            if target["stage"] == "production":
                result["note"] = "目标版本已是 production,无需操作"
                return result
            # production 唯一性:旧 production 全部降级 archived
            cur.execute(
                """
                UPDATE model_versions
                SET stage = 'archived', is_current = false
                WHERE model_name = %s AND stage = 'production'
                """,
                (model_key,),
            )
            archived = cur.rowcount
            cur.execute(
                """
                UPDATE model_versions
                SET stage = 'production', is_current = true, deployed_at = now()
                WHERE id = %s
                """,
                (int(target["id"]),),
            )
            cur.execute(
                """
                UPDATE model_registry
                SET stage = 'production', updated_at = now()
                WHERE id = %s
                """,
                (model_key,),
            )
            result["promoted"] = True
            result["archived_previous_production"] = archived
        conn.commit()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote supply-chain model version to production")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--model-key", default=MODEL_KEY)
    parser.add_argument("--version-tag", default=None, help="默认取 is_current 的 staging 版本")
    parser.add_argument("--min-snapshots", type=int, default=DEFAULT_THRESHOLDS["min_snapshots"])
    parser.add_argument("--min-win-rate", type=float, default=DEFAULT_THRESHOLDS["min_win_rate"], help="百分制,默认 50")
    parser.add_argument("--min-mean-return", type=float, default=DEFAULT_THRESHOLDS["min_mean_return"], help="百分制,默认 0")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = promote(
        args.pg_url,
        model_key=args.model_key,
        version_tag=args.version_tag,
        thresholds={
            "min_snapshots": args.min_snapshots,
            "min_win_rate": args.min_win_rate,
            "min_mean_return": args.min_mean_return,
        },
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if (result["promoted"] or result["verdict"]["ok"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
