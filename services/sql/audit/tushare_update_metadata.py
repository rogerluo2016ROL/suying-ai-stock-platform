#!/usr/bin/env python3
"""Audit Tushare document update metadata and write it into PostgreSQL.

The script does not guess silently. If a document does not contain a clear
update-time or update-frequency hint, the metadata is written as "unknown"
with the evidence snippet preserved for manual review.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"
DEFAULT_REPORT = ROOT / "docs/data-governance/tushare-update-metadata-current.md"
METADATA_COLUMNS = (
    "_tushare_update_time",
    "_tushare_update_frequency",
    "_tushare_doc_url",
    "_tushare_metadata_updated_at",
)


@dataclass(frozen=True)
class UpdateMetadata:
    api: str
    update_time: str
    update_frequency: str
    doc_url: str
    extraction_status: str
    evidence: str


def extract_update_metadata(api: str, text: str, doc_url: str) -> UpdateMetadata:
    normalized = _normalize_doc_text(text)
    evidence = _find_evidence(normalized)
    update_time = _extract_labeled_value(normalized, ("更新时间", "入库时间", "数据说明"))
    update_frequency = _extract_labeled_value(normalized, ("更新频率", "更新周期"))
    if update_time == "unknown":
        update_time = _extract_inline_update_sentence(normalized)

    if update_frequency == "unknown" and update_time != "unknown":
        update_frequency = _infer_frequency(update_time)
    if update_time == "unknown" and update_frequency != "unknown":
        update_time = _extract_labeled_value(normalized, ("更新时间", "入库时间"))

    status = "extracted" if update_time != "unknown" or update_frequency != "unknown" else "not_found"
    return UpdateMetadata(
        api=api,
        update_time=update_time,
        update_frequency=update_frequency,
        doc_url=doc_url,
        extraction_status=status,
        evidence=evidence,
    )


def fetch_document(url: str, timeout: int = 15) -> str:
    import requests

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def ensure_metadata_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tushare_api_update_metadata (
            api TEXT PRIMARY KEY,
            update_time TEXT NOT NULL,
            update_frequency TEXT NOT NULL,
            doc_url TEXT NOT NULL,
            extraction_status TEXT NOT NULL,
            evidence TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute("ALTER TABLE tushare_api_ingest_status ADD COLUMN IF NOT EXISTS update_time TEXT")
    cur.execute("ALTER TABLE tushare_api_ingest_status ADD COLUMN IF NOT EXISTS update_frequency TEXT")
    cur.execute("ALTER TABLE tushare_api_ingest_status ADD COLUMN IF NOT EXISTS doc_url TEXT")
    cur.execute("ALTER TABLE tushare_api_ingest_status ADD COLUMN IF NOT EXISTS update_metadata_status TEXT")
    conn.commit()


def upsert_metadata(conn, metadata: UpdateMetadata) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tushare_api_update_metadata (
            api, update_time, update_frequency, doc_url, extraction_status, evidence, updated_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (api) DO UPDATE SET
            update_time=EXCLUDED.update_time,
            update_frequency=EXCLUDED.update_frequency,
            doc_url=EXCLUDED.doc_url,
            extraction_status=EXCLUDED.extraction_status,
            evidence=EXCLUDED.evidence,
            updated_at=NOW()
        """,
        (
            metadata.api,
            metadata.update_time,
            metadata.update_frequency,
            metadata.doc_url,
            metadata.extraction_status,
            metadata.evidence[:2000],
        ),
    )
    cur.execute(
        """
        UPDATE tushare_api_ingest_status
        SET update_time=%s,
            update_frequency=%s,
            doc_url=%s,
            update_metadata_status=%s,
            updated_at=NOW()
        WHERE api=%s
        """,
        (
            metadata.update_time,
            metadata.update_frequency,
            metadata.doc_url,
            metadata.extraction_status,
            metadata.api,
        ),
    )
    conn.commit()


def ensure_table_metadata_columns(conn, table_names: list[str]) -> None:
    for table in table_names:
        if not _table_exists(conn, table):
            continue
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE {pg_ident(table)} ADD COLUMN IF NOT EXISTS {pg_ident(METADATA_COLUMNS[0])} TEXT")
        cur.execute(f"ALTER TABLE {pg_ident(table)} ADD COLUMN IF NOT EXISTS {pg_ident(METADATA_COLUMNS[1])} TEXT")
        cur.execute(f"ALTER TABLE {pg_ident(table)} ADD COLUMN IF NOT EXISTS {pg_ident(METADATA_COLUMNS[2])} TEXT")
        cur.execute(
            f"ALTER TABLE {pg_ident(table)} "
            f"ADD COLUMN IF NOT EXISTS {pg_ident(METADATA_COLUMNS[3])} TIMESTAMPTZ"
        )
    conn.commit()


def stamp_table_metadata(conn, table_name: str, metadata: UpdateMetadata) -> None:
    if not _table_exists(conn, table_name):
        return
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {pg_ident(table_name)}
        SET {pg_ident(METADATA_COLUMNS[0])}=%s,
            {pg_ident(METADATA_COLUMNS[1])}=%s,
            {pg_ident(METADATA_COLUMNS[2])}=%s,
            {pg_ident(METADATA_COLUMNS[3])}=NOW()
        WHERE {pg_ident(METADATA_COLUMNS[0])} IS DISTINCT FROM %s
           OR {pg_ident(METADATA_COLUMNS[1])} IS DISTINCT FROM %s
           OR {pg_ident(METADATA_COLUMNS[2])} IS DISTINCT FROM %s
           OR {pg_ident(METADATA_COLUMNS[3])} IS NULL
        """,
        (
            metadata.update_time,
            metadata.update_frequency,
            metadata.doc_url,
            metadata.update_time,
            metadata.update_frequency,
            metadata.doc_url,
        ),
    )
    conn.commit()


def load_api_table_map(pg_url: str) -> dict[str, set[str]]:
    catalog = _load_module("tushare_data_catalog", Path(__file__).with_name("tushare_data_catalog.py"))
    rows, reference_apis, uncovered = catalog.build_catalog(pg_url=pg_url)
    api_tables: dict[str, set[str]] = {api: set() for api in reference_apis}
    for row in rows:
        if row.tushare_api:
            api_tables.setdefault(row.tushare_api, set()).add(row.pg_table)
    for api in reference_apis:
        raw_table = f"ts_raw_{_safe_name(api)}"
        api_tables.setdefault(api, set()).add(raw_table)
    return api_tables


def load_reference_apis(pg_url: str) -> dict[str, Any]:
    catalog = _load_module("tushare_data_catalog", Path(__file__).with_name("tushare_data_catalog.py"))
    _rows, reference_apis, _uncovered = catalog.build_catalog(pg_url=pg_url)
    return reference_apis


def render_report(results: list[UpdateMetadata], output: Path = DEFAULT_REPORT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    extracted = sum(1 for result in results if result.extraction_status == "extracted")
    lines = [
        "# Tushare 更新时间/频率审计",
        "",
        f"> 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 汇总",
        "",
        f"- 接口数: {len(results)}",
        f"- 已抽取更新时间或频率: {extracted}",
        f"- 未在文档中找到明确描述: {len(results) - extracted}",
        "",
        "## 明细",
        "",
        "| API | 更新时间点 | 更新频率 | 状态 | 证据 | 文档 |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        evidence = result.evidence.replace("|", "｜")[:180]
        lines.append(
            f"| {result.api} | {result.update_time} | {result.update_frequency} | "
            f"{result.extraction_status} | {evidence} | {result.doc_url} |"
        )
    output.write_text("\n".join(lines) + "\n", "utf-8")


def pg_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Tushare doc update metadata and write to PG")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))
    parser.add_argument("--max-apis", type=int, default=None)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--stamp-table-rows",
        action="store_true",
        help="Also update every existing row with metadata constants. Off by default to avoid large-table bloat.",
    )
    args = parser.parse_args()

    import psycopg2

    reference_apis = load_reference_apis(args.pg_url)
    selected = list(reference_apis.values())
    if args.only:
        wanted = set(args.only)
        selected = [api for api in selected if api.name in wanted]
    if args.max_apis is not None:
        selected = selected[: args.max_apis]

    conn = psycopg2.connect(args.pg_url, connect_timeout=10)
    ensure_metadata_table(conn)
    api_tables = load_api_table_map(args.pg_url)
    results: list[UpdateMetadata] = []
    for index, api_ref in enumerate(selected, 1):
        print(f"[{index}/{len(selected)}] doc {api_ref.name}", flush=True)
        try:
            text = fetch_document(api_ref.url)
            metadata = extract_update_metadata(api_ref.name, text, api_ref.url)
        except Exception as exc:  # noqa: BLE001 - audit result must preserve failure
            metadata = UpdateMetadata(
                api=api_ref.name,
                update_time="unknown",
                update_frequency="unknown",
                doc_url=api_ref.url,
                extraction_status="doc_unavailable",
                evidence=str(exc)[:1000],
            )
        upsert_metadata(conn, metadata)
        tables = sorted(api_tables.get(api_ref.name, ()))
        ensure_table_metadata_columns(conn, tables)
        if args.stamp_table_rows:
            for table in tables:
                stamp_table_metadata(conn, table, metadata)
        results.append(metadata)
    conn.close()
    render_report(results, args.report)
    print(f"OK {args.report} | apis={len(results)}")
    return 0


def _normalize_doc_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        pattern = re.compile(rf"{re.escape(label)}[：:]\s*([^\n。；;]+)")
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            if label == "数据说明":
                value = _extract_update_phrase(value)
            return value[:120] if value else "unknown"
    return "unknown"


def _extract_update_phrase(value: str) -> str:
    parts = re.split(r"[。；;]", value)
    for part in parts:
        if any(token in part for token in ("入库", "更新", "交易日", "每日", "每周", "每月", "实时")):
            return part.strip()
    return value.strip()


def _infer_frequency(update_time: str) -> str:
    if "上一交易日" in update_time or "次日" in update_time:
        return "每日"
    if "交易日每天" in update_time:
        return "交易日每天"
    if "每日" in update_time or "每天" in update_time:
        return "每日"
    if "每周" in update_time or "周" in update_time:
        return "每周"
    if "每月" in update_time or "月" in update_time:
        return "每月"
    if "实时" in update_time:
        return "实时"
    return "unknown"


def _extract_inline_update_sentence(text: str) -> str:
    sentences = re.split(r"[。\n；;]", text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if "更新" in sentence and any(
            token in sentence
            for token in ("实时", "次日", "每日", "每天", "交易日", "盘后", "收盘后", "日频", "月", "周")
        ):
            return _trim_update_sentence(sentence)[:120]
        if "入库" in sentence and any(token in sentence for token in ("每日", "每天", "交易日", "次日", "盘后")):
            return sentence[:120]
    return "unknown"


def _trim_update_sentence(sentence: str) -> str:
    if "，" in sentence and "更新" in sentence:
        parts = [part.strip() for part in sentence.split("，") if part.strip()]
        for part in parts:
            if "更新" in part:
                return part
    return sentence


def _find_evidence(text: str) -> str:
    for token in ("更新频率", "更新时间", "入库", "数据说明"):
        idx = text.find(token)
        if idx >= 0:
            return text[idx : idx + 240].replace("\n", " ")
    return ""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _table_exists(conn, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
    return cur.fetchone()[0] is not None


def _safe_name(api_name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", api_name.strip()).strip("_").lower()
    if safe and safe[0].isdigit():
        return f"api_{safe}"
    return safe or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
