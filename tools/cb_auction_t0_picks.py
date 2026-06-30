#!/usr/bin/env python3
"""Run 竞价选债 T+0 model and export results."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "kronos-factors"))

from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="竞价选债 T+0 模型")
    parser.add_argument("trade_date", nargs="?", help="交易日，格式 YYYY-MM-DD")
    parser.add_argument("--top-n", type=int, default=50, help="最多输出转债数量")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "cb_auction_t0"),
    )
    parser.add_argument("--json-only", action="store_true", help="只输出 JSON 路径")
    return parser


def write_outputs(result: dict, output_dir: str) -> tuple[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trade_date = result.get("trade_date") or "unknown"
    json_path = out_dir / f"{trade_date}_cb_auction_t0.json"
    csv_path = out_dir / f"{trade_date}_cb_auction_t0.csv"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    fields = [
        "cb_code",
        "cb_name",
        "stk_code",
        "stk_name",
        "theme_score",
        "matched_concepts",
        "trigger_sources",
        "relation_reason",
        "premium_rate",
        "cb_amount",
        "remain_size_yi",
        "call_status",
        "risk_notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for bond in result.get("bonds", []):
            row = {key: bond.get(key) for key in fields}
            row["matched_concepts"] = "、".join(bond.get("matched_concepts") or [])
            row["trigger_sources"] = "、".join(bond.get("trigger_sources") or [])
            row["risk_notes"] = "；".join(bond.get("risk_notes") or [])
            writer.writerow(row)

    return str(json_path), str(csv_path)


def print_summary(result: dict) -> None:
    print(f"竞价选债 T+0 | {result.get('trade_date')}")
    print(
        "触发股票: "
        f"{len(result.get('trigger_stocks', []))} | 概念: {len(result.get('concepts', []))} | 转债: "
        f"{len(result.get('bonds', []))}"
    )
    print("-" * 120)
    print(
        f"{'#':<3} {'转债':<12} {'正股':<10} {'题材分':>7} {'概念':<24} {'风险提示'}"
    )
    for idx, bond in enumerate(result.get("bonds", [])[:50], 1):
        concepts = "、".join(bond.get("matched_concepts") or [])[:24]
        risks = "；".join(bond.get("risk_notes") or [])
        print(
            f"{idx:<3} "
            f"{bond.get('cb_name', ''):<12} "
            f"{bond.get('stk_name', ''):<10} "
            f"{bond.get('theme_score', 0):>7.1f} "
            f"{concepts:<24} "
            f"{risks}"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = CbAuctionT0Engine(pg_url=os.environ.get("KRONOS_PG_URL"))
    try:
        result = engine.run(trade_date=args.trade_date, top_n=args.top_n)
    finally:
        engine.close()

    json_path, csv_path = write_outputs(result, args.output_dir)
    if args.json_only:
        print(json_path)
    else:
        print_summary(result)
        print(f"\nJSON: {json_path}")
        print(f"CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
