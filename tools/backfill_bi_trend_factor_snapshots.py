#!/usr/bin/env python3
"""Persist real bi_trend_launch scored universes for historical factor evidence.

This never fabricates rows: each date is evaluated by the production engine and
only returned scored rows are written to ``screening_snapshots``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for rel in ("services/screener-service", "packages/kronos-factors", "packages/kronos-data"):
    sys.path.insert(0, os.path.join(ROOT, rel))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-date", required=True)
    # screening_snapshots.time_slot is a legacy varchar(5); keep the evidence
    # run distinguishable without violating the existing schema contract.
    parser.add_argument("--time-slot", default="14:40")
    args = parser.parse_args()

    from app.domains.screening.service import _run_bi_trend_mode
    from kronos_factors.recorder import record_picks

    with contextlib.redirect_stdout(io.StringIO()):
        result = _run_bi_trend_mode("bi_trend_launch", 30, args.trade_date)
    observations = result.get("factor_observations") or []
    if not observations:
        print(f"{args.trade_date}: no real scored observations; nothing written")
        return 0
    written = record_picks("bi_trend_launch", args.trade_date, args.time_slot, observations)
    print(f"{args.trade_date}: observations={len(observations)} written={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
