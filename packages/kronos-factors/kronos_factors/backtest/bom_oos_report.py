"""Audit-report helpers for supply-chain BOM OOS validation.

These helpers are deliberately pure and cheap to test. They do not run the
model; they package an already-computed OOS result into reproducible artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIXED_UNIVERSE_WARNINGS = [
    "当前固定公司池会保留选择偏差：它验证的是当前已识别BOM公司内部排序，不等同于历史时点全市场选股能力。",
    "主营占比和公司-节点映射若来自当前快照，会形成宇宙层未来信息；下一阶段需按cutoff重建候选宇宙。",
]

CUTOFF_REBUILT_CACHE_WARNINGS = [
    "公司-节点-主营占比已按cutoff从缓存主营表重建，但缓存覆盖范围仍决定候选宇宙上限；若缓存不是全市场，仍不能等同全市场选股能力。",
]


def hash_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_hashes(cache_paths: list[str | Path]) -> dict[str, dict[str, Any]]:
    out = {}
    for path in cache_paths:
        file_path = Path(path)
        out[file_path.name] = {
            "path": str(file_path),
            "sha256": hash_file(file_path),
            "size_bytes": file_path.stat().st_size,
        }
    return out


def _bias_warnings(universe_mode: str) -> list[str]:
    if universe_mode == "fixed_current_mapping":
        return FIXED_UNIVERSE_WARNINGS[:]
    if universe_mode == "cutoff_rebuilt":
        return []
    if universe_mode == "cutoff_rebuilt_cache":
        return CUTOFF_REBUILT_CACHE_WARNINGS[:]
    return [f"未知 universe_mode={universe_mode}，请人工确认是否存在样本选择偏差。"]


def build_oos_audit_report(
    *,
    model_version: str,
    universe_mode: str,
    universe_codes: list[str],
    results: dict[str, Any],
    config: dict[str, Any],
    cache_paths: list[str | Path],
    git_commit: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "model_version": model_version,
        "git_commit": git_commit,
        "universe": {
            "mode": universe_mode,
            "size": len(universe_codes),
            "codes": sorted(str(code) for code in universe_codes),
        },
        "bias_warnings": _bias_warnings(universe_mode),
        "inputs": _input_hashes(cache_paths),
        "config": config,
        "results": results,
    }


def summarize_oos_verdict(test_result: dict[str, Any]) -> dict[str, str]:
    n_cutoffs = int(test_result.get("n") or 0)
    mean_rank_ic = float(test_result.get("mean_rank_ic") or 0)
    p_value = float(test_result.get("p") or 1)
    if n_cutoffs <= 0:
        return {
            "status": "INCONCLUSIVE",
            "message": "无有效 cutoff：候选宇宙未命中足够可回测标的，本次结果只说明链路可运行，不能判断模型有效性。",
        }
    if not math.isfinite(p_value):
        return {
            "status": "INCONCLUSIVE",
            "message": "统计量不可用：IC 序列方差为 0 或样本过小，本次结果只说明链路可运行，不能判断模型有效性。",
        }
    if mean_rank_ic > 0.03 and p_value < 0.1:
        return {
            "status": "PASS",
            "message": "test 期 rankIC 显著为正 — BOM 评分有真选股能力 (OOS 成立)",
        }
    if mean_rank_ic > 0:
        return {
            "status": "WEAK_POSITIVE",
            "message": "test 期 rankIC 弱正但不显著 — 方向对, 样本/功效不足",
        }
    return {
        "status": "FAIL",
        "message": "test 期 rankIC ≤ 0 — BOM 评分 OOS 无效",
    }


def _write_cutoff_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_oos_audit_artifacts(report: dict[str, Any], out_dir: str | Path) -> dict[str, str]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    model_version = str(report.get("model_version") or "unknown_model")
    universe_mode = str((report.get("universe") or {}).get("mode") or "unknown_universe")
    report_path = target / f"bom_oos_audit_{model_version}_{universe_mode}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    paths = {"report_json": str(report_path)}
    results = report.get("results") if isinstance(report.get("results"), dict) else {}
    for key, result in results.items():
        if not isinstance(result, dict):
            continue
        rows = result.get("per_cutoff")
        if not rows:
            continue
        csv_path = target / f"bom_oos_cutoffs_{universe_mode}_{key}.csv"
        _write_cutoff_csv(csv_path, rows)
        paths[f"{key}_csv"] = str(csv_path)
    return paths
