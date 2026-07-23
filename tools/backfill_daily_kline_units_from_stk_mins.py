#!/usr/bin/env python3
"""Backfill daily_kline volume/amount unit-scale errors from stk_mins.

Official Tushare units:
  daily_kline.volume = hands, amount = k_yuan
  stk_mins.volume = shares, amount = yuan

This task only repairs rows that look like clear unit-scale mistakes. Ordinary
source differences are reported but not updated.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

import psycopg2
import psycopg2.extras


DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"


def _connect():
    return psycopg2.connect(os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))


def _candidate_where() -> str:
    return """
        m.bars >= %(min_bars)s
        AND (
            (
                abs(d.close - m.close) <= %(max_close_diff)s
                AND (
                    CASE WHEN m.volume_hand > 0 THEN d.volume / m.volume_hand ELSE 0 END >= %(volume_ratio_max)s
                    OR CASE WHEN m.amount_k_yuan > 0 THEN d.amount / m.amount_k_yuan ELSE 0 END >= %(amount_ratio_max)s
                )
            )
            OR (
                abs(d.close - m.close) <= %(amount_only_max_close_diff)s
                AND CASE WHEN m.volume_hand > 0 THEN d.volume / m.volume_hand ELSE 0 END
                    BETWEEN %(amount_only_volume_ratio_min)s AND %(amount_only_volume_ratio_max)s
                AND CASE WHEN m.amount_k_yuan > 0 THEN d.amount / m.amount_k_yuan ELSE 0 END >= %(amount_ratio_max)s
            )
        )
    """


def _date_filter() -> str:
    return """
        (%(start_date)s IS NULL OR d.trade_date >= %(start_date)s::date)
        AND (%(end_date)s IS NULL OR d.trade_date <= %(end_date)s::date)
    """


def _base_cte() -> str:
    return f"""
    WITH minute_daily AS (
        SELECT
            code,
            trade_time::date AS trade_date,
            (array_agg(close ORDER BY trade_time DESC))[1] AS close,
            sum(volume) / 100.0 AS volume_hand,
            sum(amount) / 1000.0 AS amount_k_yuan,
            count(*) AS bars
        FROM stk_mins
        WHERE (%(start_date)s IS NULL OR trade_time::date >= %(start_date)s::date)
          AND (%(end_date)s IS NULL OR trade_time::date <= %(end_date)s::date)
        GROUP BY code, trade_time::date
    ),
    candidates AS (
        SELECT
            d.code,
            d.trade_date,
            d.close AS daily_close,
            m.close AS minute_close,
            d.volume AS old_volume,
            d.amount AS old_amount,
            m.volume_hand AS new_volume,
            m.amount_k_yuan AS new_amount,
            m.bars,
            CASE WHEN m.volume_hand > 0 THEN d.volume / m.volume_hand END AS volume_ratio,
            CASE WHEN m.amount_k_yuan > 0 THEN d.amount / m.amount_k_yuan END AS amount_ratio,
            abs(d.close - m.close) AS close_abs_diff,
            CASE
                WHEN abs(d.close - m.close) > %(max_close_diff)s
                 AND CASE WHEN m.volume_hand > 0 THEN d.volume / m.volume_hand ELSE 0 END
                     BETWEEN %(amount_only_volume_ratio_min)s AND %(amount_only_volume_ratio_max)s
                 AND CASE WHEN m.amount_k_yuan > 0 THEN d.amount / m.amount_k_yuan ELSE 0 END >= %(amount_ratio_max)s
                THEN 'amount_only'
                ELSE 'volume_amount'
            END AS repair_reason
        FROM daily_kline d
        JOIN minute_daily m
          ON m.code = d.code
         AND m.trade_date = d.trade_date
        WHERE {_date_filter()}
          AND {_candidate_where()}
    )
    """


def summarize(conn, params: dict) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            _base_cte()
            + """
            SELECT
                count(*) AS rows,
                min(trade_date) AS min_date,
                max(trade_date) AS max_date,
                avg(volume_ratio) AS avg_volume_ratio,
                avg(amount_ratio) AS avg_amount_ratio
            FROM candidates
            """,
            params,
        )
        summary = dict(cur.fetchone() or {})
        cur.execute(
            _base_cte()
            + """
            SELECT trade_date, count(*) AS rows,
                   round(avg(volume_ratio)::numeric, 2) AS avg_volume_ratio,
                   round(avg(amount_ratio)::numeric, 2) AS avg_amount_ratio
            FROM candidates
            GROUP BY trade_date
            ORDER BY rows DESC, trade_date DESC
            LIMIT 20
            """,
            params,
        )
        by_date = [dict(row) for row in cur.fetchall()]
        cur.execute(
            _base_cte()
            + """
            SELECT code, trade_date, old_volume, new_volume,
                   round(volume_ratio::numeric, 4) AS volume_ratio,
                   old_amount, new_amount,
                   round(amount_ratio::numeric, 4) AS amount_ratio,
                   bars, round(close_abs_diff::numeric, 4) AS close_abs_diff
            FROM candidates
            ORDER BY trade_date DESC, code
            LIMIT 10
            """,
            params,
        )
        samples = [dict(row) for row in cur.fetchall()]
    return {"summary": summary, "by_date": by_date, "samples": samples}


def apply_backfill(conn, params: dict, run_id: str) -> int:
    params = dict(params)
    params["run_id"] = run_id
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_kline_unit_backfill_audit (
                id bigserial PRIMARY KEY,
                run_id text NOT NULL,
                code text NOT NULL,
                trade_date date NOT NULL,
                old_volume double precision,
                old_amount double precision,
                new_volume double precision,
                new_amount double precision,
                minute_bars integer,
                volume_ratio double precision,
                amount_ratio double precision,
                close_abs_diff double precision,
                repair_reason text,
                applied_at timestamptz NOT NULL DEFAULT now(),
                UNIQUE (run_id, code, trade_date)
            )
            """
        )
        cur.execute("ALTER TABLE daily_kline_unit_backfill_audit ADD COLUMN IF NOT EXISTS repair_reason text")
        cur.execute(
            _base_cte()
            + """
            INSERT INTO daily_kline_unit_backfill_audit (
                run_id, code, trade_date, old_volume, old_amount,
                new_volume, new_amount, minute_bars, volume_ratio,
                amount_ratio, close_abs_diff, repair_reason
            )
            SELECT
                %(run_id)s, code, trade_date, old_volume, old_amount,
                new_volume, new_amount, bars, volume_ratio,
                amount_ratio, close_abs_diff, repair_reason
            FROM candidates
            ON CONFLICT (run_id, code, trade_date) DO NOTHING
            """,
            params,
        )
        cur.execute(
            _base_cte()
            + """
            UPDATE daily_kline d
            SET volume = CASE WHEN c.repair_reason = 'amount_only' THEN d.volume ELSE c.new_volume END,
                amount = c.new_amount
            FROM candidates c
            WHERE d.code = c.code
              AND d.trade_date = c.trade_date
            """,
            params,
        )
        updated = cur.rowcount
    conn.commit()
    return int(updated)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill daily_kline unit errors from stk_mins")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--min-bars", type=int, default=40)
    parser.add_argument("--volume-ratio-max", type=float, default=10.0)
    parser.add_argument("--amount-ratio-max", type=float, default=50.0)
    parser.add_argument("--max-close-diff", type=float, default=0.20)
    parser.add_argument("--amount-only-max-close-diff", type=float, default=0.30)
    parser.add_argument("--amount-only-volume-ratio-min", type=float, default=0.80)
    parser.add_argument("--amount-only-volume-ratio-max", type=float, default=1.25)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    params = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "min_bars": args.min_bars,
        "volume_ratio_max": args.volume_ratio_max,
        "amount_ratio_max": args.amount_ratio_max,
        "max_close_diff": args.max_close_diff,
        "amount_only_max_close_diff": args.amount_only_max_close_diff,
        "amount_only_volume_ratio_min": args.amount_only_volume_ratio_min,
        "amount_only_volume_ratio_max": args.amount_only_volume_ratio_max,
    }
    with _connect() as conn:
        conn.autocommit = False
        report = summarize(conn, params)
        print("candidate_summary=", report["summary"])
        print("top_dates=")
        for row in report["by_date"]:
            print(" ", row)
        print("samples=")
        for row in report["samples"]:
            print(" ", row)
        if not args.apply:
            print("dry_run=true")
            return 0
        run_id = f"daily_kline_unit_backfill_{uuid.uuid4().hex[:12]}"
        updated = apply_backfill(conn, params, run_id)
        print("dry_run=false")
        print("run_id=", run_id)
        print("updated_rows=", updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
