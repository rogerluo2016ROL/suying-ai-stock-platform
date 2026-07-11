#!/usr/bin/env python3
"""CLI for scoped supply-chain evidence orchestration."""

from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
WORKTREE_IMPORT_PATHS = (
    str(_ROOT / "tools"),
    str(_ROOT / "packages" / "kronos-factors"),
    str(_ROOT / "services" / "screener-service"),
)
for _path in reversed(WORKTREE_IMPORT_PATHS):
    while _path in sys.path:
        sys.path.remove(_path)
    sys.path.insert(0, _path)


# Business imports intentionally follow worktree path pinning above.
import argparse
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from functools import partial
import json
import os
from typing import Any

import psycopg2

from app.domains.supply_chain.evidence_orchestration_repository import (
    EvidenceOrchestrationRepository,
)
from score_supply_chain_selection_v2 import run_batch_score
from supply_chain_data_collection_center import (
    fetch_cninfo_documents,
    fetch_cninfo_keyword_documents,
    fetch_official_ir_documents,
)
from supply_chain_evidence_adapters import (
    LocalEvidenceAdapter,
    OfficialDiscoveryAdapter,
    OfficialGapAdapter,
    ScopedOfficialDiscoveryFetcher,
    ScopedOfficialFetcher,
)
from supply_chain_evidence_orchestrator import (
    EvidenceRunRequest,
    EvidenceRunResult,
    run_evidence_orchestration,
)
from supply_chain_evidence_report import render_evidence_report


DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"


def pg_connection_factory(pg_url: str):
    def factory():
        return psycopg2.connect(pg_url, connect_timeout=5)

    return factory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and score scoped supply-chain evidence"
    )
    parser.add_argument("--chain-id", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument(
        "--mode", required=True, choices=("dry-run", "collect", "score", "full")
    )
    parser.add_argument(
        "--source-policy",
        required=True,
        choices=("local-first", "official-gap"),
    )
    parser.add_argument("--source-limit", action="append", default=[])
    parser.add_argument("--mapping-id", action="append", default=[])
    parser.add_argument("--company-code", action="append", default=[])
    parser.add_argument("--allow-score", action="store_true")
    parser.add_argument(
        "--pg-url",
        default=os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL),
    )
    parser.add_argument("--output-dir")
    return parser


def parse_source_limits(values: Sequence[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError("source limit must use key=value")
        key, value = raw.split("=", 1)
        key = key.strip()
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"source limit {key or '<empty>'} must be an integer") from exc
        if not key or parsed <= 0:
            raise ValueError("source limit key=value requires a positive integer")
        result[key] = parsed
    return result


def request_from_args(args: argparse.Namespace) -> EvidenceRunRequest:
    try:
        as_of_date = date.fromisoformat(args.as_of_date)
    except ValueError as exc:
        raise ValueError("as-of-date must use YYYY-MM-DD") from exc
    return EvidenceRunRequest(
        chain_id=args.chain_id,
        as_of_date=as_of_date,
        mode=args.mode,
        source_policy=args.source_policy,
        source_limits=parse_source_limits(args.source_limit),
        mapping_ids=tuple(args.mapping_id),
        company_codes=tuple(args.company_code),
        allow_score=bool(args.allow_score),
    )


def build_runtime_dependencies(args: argparse.Namespace) -> dict[str, Any]:
    repository = EvidenceOrchestrationRepository(
        connection_factory=pg_connection_factory(args.pg_url)
    )
    local_adapter = LocalEvidenceAdapter(repository)
    official_fetcher = ScopedOfficialFetcher(
        cninfo_fetch=partial(fetch_cninfo_documents, args.pg_url),
        ir_fetch=partial(fetch_official_ir_documents, args.pg_url),
    )
    official_adapter = OfficialGapAdapter(official_fetcher)
    official_discovery_adapter = OfficialDiscoveryAdapter(
        ScopedOfficialDiscoveryFetcher(
            global_cninfo_fetch=fetch_cninfo_keyword_documents,
            ir_fetch=partial(fetch_official_ir_documents, args.pg_url),
        )
    )
    return {
        "repository": repository,
        "local_adapter": local_adapter,
        "official_discovery_adapter": official_discovery_adapter,
        "official_adapter": official_adapter,
        "score_runner": partial(
            run_batch_score,
            pg_url=args.pg_url,
            model_version="v2.0",
        ),
    }


def _jsonable(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    return value


def result_payload(result: EvidenceRunResult) -> dict[str, object]:
    payload = _jsonable(result)
    if not isinstance(payload, dict):
        raise TypeError("evidence result must serialize to an object")
    return payload


def write_outputs(
    output_dir: str | Path,
    result: EvidenceRunResult,
    markdown: str,
) -> None:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "result.json").write_text(
        json.dumps(result_payload(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (path / "report.md").write_text(markdown, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        request = request_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    dependencies = build_runtime_dependencies(args)
    result = run_evidence_orchestration(
        request,
        **dependencies,
    )
    markdown = render_evidence_report(result)
    if args.output_dir:
        write_outputs(args.output_dir, result, markdown)
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
