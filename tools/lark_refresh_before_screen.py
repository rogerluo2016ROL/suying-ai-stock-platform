#!/usr/bin/env python3
"""Refresh minimum market data before Lark-triggered screening."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_SERVICE = ROOT / "services" / "data-service"
KRONOS_DATA = ROOT / "packages" / "kronos-data"
SCREENER_SERVICE = ROOT / "services" / "screener-service"
sys.path = [p for p in sys.path if Path(p or ".").resolve() != SCREENER_SERVICE]
for path in (str(DATA_SERVICE), str(KRONOS_DATA)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh data before Lark screener run")
    parser.add_argument("--mode", default="")
    parser.add_argument("--trade-date", default="")
    args = parser.parse_args()

    trade_date = args.trade_date or _today()
    results: dict[str, object] = {
        "mode": args.mode,
        "trade_date": trade_date,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    if not os.environ.get("KRONOS_PG_URL"):
        os.environ["KRONOS_PG_URL"] = "postgresql://kronos:kronos@localhost:6432/kronos"

    try:
        from app.sync.rt_min import collect_rt_min

        results["stk_mins"] = collect_rt_min()
    except Exception as exc:  # noqa: BLE001 - keep refresh best-effort
        results["stk_mins"] = {"status": "error", "message": str(exc)[:300]}

    try:
        from app.sync.tushare import sync_post_market_core

        results["post_market_core"] = sync_post_market_core(trade_date)
    except Exception as exc:  # noqa: BLE001 - some APIs are unavailable intraday
        results["post_market_core"] = {"status": "error", "message": str(exc)[:300]}

    results["finished_at"] = datetime.now().isoformat(timespec="seconds")
    print(json.dumps(results, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
