"""Helpers for building supply-chain BOM OOS cache files."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


CACHE_NAMES = ("fina_indicator", "forecast", "irm_qa", "research_report", "fina_mainbz")
MANIFEST_NAME = "manifest.csv"


@dataclass(frozen=True)
class CacheConfig:
    start: str = "20240101"
    end: str = "20260615"


def parse_cache_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build BOM OOS cache CSVs")
    parser.add_argument(
        "--universe",
        choices=["bom36", "all_a"],
        default="bom36",
        help="bom36 uses PG company_bom_mapping; all_a uses Tushare stock_basic listed A shares.",
    )
    parser.add_argument("--start", default=CacheConfig.start)
    parser.add_argument("--end", default=CacheConfig.end)
    parser.add_argument("--sleep-seconds", type=float, default=0.3)
    parser.add_argument("--limit", type=int, default=0, help="Optional first-N company limit for smoke runs; 0 means no limit.")
    parser.add_argument("--out-dir", default="outputs/bom_oos_cache", help="Output directory for cache CSVs.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing cache CSV files in --out-dir.")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted cache run by skipping codes in manifest.csv.")
    parser.add_argument("--codes", default="", help="Optional comma-separated code list for targeted smoke runs, e.g. 688017,300503.SZ.")
    return parser.parse_args(argv)


def prepare_cache_output_dir(
    out_dir: str | Path,
    *,
    overwrite: bool,
    resume: bool = False,
    cache_names: tuple[str, ...] = CACHE_NAMES,
) -> dict[str, Path]:
    target = Path(out_dir)
    paths = {name: target / f"{name}.csv" for name in cache_names}
    existing = [path.name for path in paths.values() if path.exists()]
    if existing and not overwrite and not resume:
        files = ", ".join(existing)
        raise FileExistsError(
            f"cache output already exists: {files}; use --out-dir for a separate smoke run or --overwrite to replace it"
        )
    target.mkdir(parents=True, exist_ok=True)
    return paths


def append_cache_frames(output_paths: dict[str, Path], frames: dict[str, pd.DataFrame]) -> None:
    for name, frame in frames.items():
        if frame is None or frame.empty:
            continue
        path = output_paths[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not path.exists()
        out = frame
        if not write_header:
            with path.open(encoding="utf-8") as f:
                header = f.readline().strip().split(",")
            out = frame.reindex(columns=header)
        out.to_csv(path, mode="a", header=write_header, index=False, encoding="utf-8")


def load_processed_codes(manifest_path: str | Path) -> set[str]:
    path = Path(manifest_path)
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        processed = set()
        for row in csv.DictReader(f):
            total_rows = sum(int(row.get(name) or 0) for name in CACHE_NAMES)
            if row.get("status") == "ok" and total_rows > 0:
                processed.add(str(row.get("code6") or "").zfill(6)[-6:])
        return processed


def mark_code_processed(
    manifest_path: str | Path,
    *,
    code6: str,
    ts_code: str,
    frame_counts: dict[str, int],
    status: str = "ok",
    errors: dict[str, str] | None = None,
) -> None:
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    fieldnames = ["code6", "ts_code", "status", *CACHE_NAMES, "error_summary"]
    row = {
        "code6": str(code6).zfill(6)[-6:],
        "ts_code": ts_code,
        "status": status,
    }
    for name in CACHE_NAMES:
        row[name] = int(frame_counts.get(name, 0))
    error_items = errors or {}
    row["error_summary"] = "; ".join(f"{name}: {message}" for name, message in sorted(error_items.items()))
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def cache_input_paths(cache_dir: str | Path, cache_names: tuple[str, ...] = CACHE_NAMES) -> dict[str, Path]:
    root = Path(cache_dir)
    return {name: root / f"{name}.csv" for name in cache_names}


def load_cache_frames(cache_dir: str | Path) -> dict[str, pd.DataFrame]:
    paths = cache_input_paths(cache_dir)
    missing = [path.name for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing BOM OOS cache files in {cache_dir}: {', '.join(missing)}")

    frames: dict[str, pd.DataFrame] = {}
    for name, path in paths.items():
        frame = pd.read_csv(path, dtype={"code6": str})
        if "code6" in frame.columns:
            frame["code6"] = frame["code6"].astype(str).str.zfill(6)
        frames[name] = frame
    return frames


def to_ts_code(code6: str) -> str:
    code = str(code6).strip().zfill(6)[-6:]
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    return f"{code}.BJ"


def parse_code_list(codes: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in str(codes or "").split(","):
        item = raw.strip()
        if not item:
            continue
        if "." in item:
            code, suffix = item.split(".", 1)
            code6 = code.strip().zfill(6)[-6:]
            out.append((code6, f"{code6}.{suffix.strip().upper()}"))
        else:
            code6 = item.zfill(6)[-6:]
            out.append((code6, to_ts_code(code6)))
    return out


def fetch_all_a_codes(pro: Any) -> list[tuple[str, str]]:
    df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,market")
    if df is None or df.empty:
        return []
    codes: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        ts_code = str(row.get("ts_code") or "")
        code6 = str(row.get("symbol") or ts_code.split(".")[0]).zfill(6)[-6:]
        if code6 and ts_code:
            codes.append((code6, ts_code))
    return codes


def _with_code6(df: pd.DataFrame | None, code6: str) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df.copy()
    out["code6"] = str(code6).zfill(6)[-6:]
    return out


def _safe_fetch(name: str, func: Any, *, code6: str, **kwargs: Any) -> tuple[str, pd.DataFrame | None, str | None]:
    try:
        return name, _with_code6(func(**kwargs), code6), None
    except Exception as exc:
        return name, None, str(exc)[:120]


def fetch_company_payload(
    pro: Any,
    code6: str,
    ts_code: str,
    config: CacheConfig,
) -> dict[str, dict[str, Any]]:
    params = {"ts_code": ts_code, "start_date": config.start, "end_date": config.end}
    qa_api = pro.irm_qa_sh if str(ts_code).endswith(".SH") else pro.irm_qa_sz
    calls = [
        ("fina_indicator", pro.fina_indicator, params),
        ("forecast", pro.forecast, params),
        ("irm_qa", qa_api, params),
        ("research_report", pro.research_report, params),
        ("fina_mainbz", pro.fina_mainbz_vip, {"ts_code": ts_code, "type": "P"}),
    ]

    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for name, func, kwargs in calls:
        key, frame, error = _safe_fetch(name, func, code6=code6, **kwargs)
        if frame is not None and len(frame):
            frames[key] = frame
        if error:
            errors[key] = error
    return {"frames": frames, "errors": errors}


def fetch_company_frames(
    pro: Any,
    code6: str,
    ts_code: str,
    config: CacheConfig,
) -> dict[str, pd.DataFrame]:
    return fetch_company_payload(pro, code6, ts_code, config)["frames"]
