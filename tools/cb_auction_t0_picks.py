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

from kronos_factors.engine.cb_auction_t0 import (
    CbAuctionT0Engine,
    CbAuctionT0V21Engine,
    CbAuctionT0V2Engine,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="竞价选债 T+0 模型")
    parser.add_argument("trade_date", nargs="?", help="交易日，格式 YYYY-MM-DD")
    parser.add_argument("--model", choices=["v1", "v2", "v2.1"], default="v1", help="模型版本")
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
    model = result.get("model") or "cb_auction_t0"
    json_path = out_dir / f"{trade_date}_{model}.json"
    csv_path = out_dir / f"{trade_date}_{model}.csv"

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    fields = [
        "list_type",
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
        "quality_tier",
        "quality_tier_reason",
        "observation_reason",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        output_bonds = list(result.get("bonds", [])) + list(result.get("observation_bonds", []))
        for bond in output_bonds:
            row = {key: bond.get(key) for key in fields}
            row["matched_concepts"] = "、".join(bond.get("matched_concepts") or [])
            row["trigger_sources"] = "、".join(bond.get("trigger_sources") or [])
            row["risk_notes"] = "；".join(bond.get("risk_notes") or [])
            writer.writerow(row)

    pending = result.get("pending_confirmation_stocks") or []
    if pending:
        pending_path = out_dir / f"{trade_date}_{model}_pending_confirmation.csv"
        pending_fields = [
            "trigger_stock_code",
            "trigger_stock_name",
            "auction_price",
            "up_limit",
            "auction_amount",
            "auction_amount_yi",
            "confirmation_status",
            "data_source",
        ]
        with pending_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=pending_fields)
            writer.writeheader()
            for row in pending:
                writer.writerow({key: row.get(key) for key in pending_fields})

    return str(json_path), str(csv_path)


def print_summary(result: dict) -> None:
    model_names = {
        "cb_auction_t0": "竞价选债 T+0",
        "cb_auction_t0_v2": "竞价选债 T+0 优化版 V2",
        "cb_auction_t0_v2_1": "竞价选债 T+0 优化版 V2.1 稳健版",
    }
    model_name = model_names.get(result.get("model"), "竞价选债 T+0")
    print(f"{model_name} | {result.get('trade_date')}")
    print(
        "触发股票: "
        f"{len(result.get('trigger_stocks', []))} | 概念: {len(result.get('concepts', []))} | 转债: "
        f"{len(result.get('bonds', []))}"
        f" | 观察: {len(result.get('observation_bonds', []))}"
        f" | 待确认: {len(result.get('pending_confirmation_stocks', []))}"
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
    observation_bonds = result.get("observation_bonds", [])
    if observation_bonds:
        print("\n观察清单")
        print("-" * 120)
        for idx, bond in enumerate(observation_bonds[:50], 1):
            concepts = "、".join(bond.get("matched_concepts") or [])[:24]
            risks = "；".join(bond.get("risk_notes") or [])
            print(
                f"{idx:<3} "
                f"{bond.get('cb_name', ''):<12} "
                f"{bond.get('stk_name', ''):<10} "
                f"{bond.get('quality_tier', ''):<4} "
                f"{concepts:<24} "
                f"{bond.get('observation_reason', '')} {risks}"
            )
    pending = result.get("pending_confirmation_stocks", [])
    if pending:
        print("\n待确认池（不进主买/观察，等待真实封单金额）")
        print("-" * 120)
        for idx, stock in enumerate(pending[:50], 1):
            amount_yi = stock.get("auction_amount_yi")
            amount_text = f"{amount_yi:.2f}亿" if isinstance(amount_yi, (int, float)) else ""
            print(
                f"{idx:<3} "
                f"{stock.get('trigger_stock_name', ''):<10} "
                f"{stock.get('trigger_stock_code', ''):<8} "
                f"竞价价={stock.get('auction_price', '')} "
                f"涨停价={stock.get('up_limit', '')} "
                f"竞价额={amount_text} "
                f"{stock.get('confirmation_status', '')}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.top_n < 0:
        parser.error("--top-n must be >= 0")
    engine_map = {
        "v1": CbAuctionT0Engine,
        "v2": CbAuctionT0V2Engine,
        "v2.1": CbAuctionT0V21Engine,
    }
    engine_cls = engine_map[args.model]
    engine = engine_cls(pg_url=os.environ.get("KRONOS_PG_URL"))
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
