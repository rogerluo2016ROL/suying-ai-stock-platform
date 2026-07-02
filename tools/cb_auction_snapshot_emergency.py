#!/usr/bin/env python3
"""Emergency CB T+0 picks from stk_auction_o when limit_list_d is unavailable.

This is a temporary intraday fallback. It does not replace the official
cb_auction_t0 models, which use limit_list_d trigger stocks.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "kronos-factors"))

from kronos_factors.engine.cb_auction_t0 import CbAuctionT0V21Engine
from tools.cb_auction_t0_picks import print_summary, write_outputs


class CbAuctionSnapshotEmergencyEngine(CbAuctionT0V21Engine):
    """Use auction snapshot leaders as temporary trigger stocks."""

    model_id = "cb_auction_snapshot_emergency"

    def __init__(
        self,
        pg_url: str | None = None,
        min_gap_pct: float = 8.0,
        min_amount_wan: float = 1000.0,
        max_triggers: int = 30,
    ):
        super().__init__(pg_url=pg_url)
        self.min_gap_pct = min_gap_pct
        self.min_amount = min_amount_wan * 10_000
        self.max_triggers = max_triggers

    def _fetch_trigger_stocks(self, cur, trade_date, prev_trade_date):
        trade_key, trade_key_compact = self._date_keys(trade_date)
        prev_key, prev_key_compact = self._date_keys(prev_trade_date) if prev_trade_date else ("", "")
        cur.execute(
            """
            SELECT
                a.code,
                COALESCE(s.name, a.code) AS name,
                a.amount,
                ROUND(((a.open / NULLIF(a.close, 0) - 1) * 100)::numeric, 4) AS gap_pct,
                EXISTS (
                    SELECT 1
                    FROM limit_list_d p
                    WHERE (p.trade_date::text = %s OR REPLACE(p.trade_date::text, '-', '') = %s)
                      AND p.limit_type = 'U'
                      AND SPLIT_PART(p.ts_code, '.', 1) = a.code
                ) AS prev_was_limit_up
            FROM stk_auction_o a
            LEFT JOIN stocks s ON s.code = a.code
            WHERE (a.trade_date::text = %s OR REPLACE(a.trade_date::text, '-', '') = %s)
              AND a.open > 0
              AND a.close > 0
              AND a.amount >= %s
              AND ((a.open / NULLIF(a.close, 0) - 1) * 100) >= %s
              AND COALESCE(s.name, '') NOT LIKE '%%ST%%'
            ORDER BY ((a.open / NULLIF(a.close, 0) - 1) * 100) DESC, a.amount DESC
            LIMIT %s
            """,
            (
                prev_key,
                prev_key_compact,
                trade_key,
                trade_key_compact,
                self.min_amount,
                self.min_gap_pct,
                self.max_triggers,
            ),
        )
        triggers = []
        rejections = []
        for code, name, amount, gap_pct, prev_was_limit_up in cur.fetchall():
            if prev_was_limit_up:
                rejections.append({"code": code, "name": name, "reason": "昨日已涨停"})
                continue
            amount_value = float(amount or 0)
            gap_value = float(gap_pct or 0)
            triggers.append(
                {
                    "trigger_stock_code": str(code),
                    "trigger_stock_name": name,
                    "fd_amount": amount_value,
                    "fd_amount_yi": round(amount_value / 100_000_000, 2),
                    "first_time": "09:25:00",
                    "prev_was_limit_up": False,
                    "emergency_source": "stk_auction_o",
                    "auction_gap_pct": round(gap_value, 2),
                    "auction_amount_wan": round(amount_value / 10_000, 1),
                }
            )
        return triggers, rejections


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="临时竞价快照选债")
    parser.add_argument("trade_date", nargs="?", help="交易日 YYYY-MM-DD")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--max-triggers", type=int, default=30)
    parser.add_argument("--min-gap-pct", type=float, default=8.0)
    parser.add_argument("--min-amount-wan", type=float, default=1000.0)
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "cb_auction_snapshot_emergency"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    engine = CbAuctionSnapshotEmergencyEngine(
        pg_url=os.environ.get("KRONOS_PG_URL"),
        min_gap_pct=args.min_gap_pct,
        min_amount_wan=args.min_amount_wan,
        max_triggers=args.max_triggers,
    )
    try:
        result = engine.run(trade_date=args.trade_date, top_n=args.top_n)
    finally:
        engine.close()
    result["note"] = "临时口径: limit_list_d 未更新时，使用 stk_auction_o 竞价涨幅和成交额触发。"
    json_path, csv_path = write_outputs(result, args.output_dir)
    print_summary(result)
    print("\n触发股")
    print("-" * 120)
    for idx, row in enumerate(result.get("trigger_stocks", []), 1):
        print(
            f"{idx:<3} {row.get('trigger_stock_name',''):<10} "
            f"{row.get('trigger_stock_code',''):<8} "
            f"竞价涨幅{row.get('auction_gap_pct', 0):>6.2f}% "
            f"竞价成交{row.get('auction_amount_wan', 0):>8.1f}万"
        )
    print(f"\nJSON: {json_path}")
    print(f"CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
