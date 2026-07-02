#!/usr/bin/env python3
"""Build a read-only Tushare data governance catalog.

The script connects four things that used to be reviewed separately:
Tushare reference API -> ETL sync function -> PG table/columns -> UI data status.
It does not call Tushare and does not write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REFERENCE = ROOT / "skills/tushare-data/references/数据接口.md"
DEFAULT_ROUTES = ROOT / "services/signal-service/app/routes.py"
DEFAULT_SCHEDULER = ROOT / "services/data-service/app/scheduler.py"
DEFAULT_ETL = ROOT / "packages/kronos-data/kronos_data/etl.py"
DEFAULT_OUTPUT = ROOT / "docs/data-governance/data-catalog-current.md"


@dataclass(frozen=True)
class TushareApiRef:
    name: str
    title: str
    category: str
    url: str
    description: str


@dataclass(frozen=True)
class EtlTarget:
    function: str
    api: str
    table: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class PgTableStats:
    table: str
    columns: tuple[str, ...]
    rows: int
    min_date: date | datetime | str | None
    max_date: date | datetime | str | None


@dataclass(frozen=True)
class CatalogRow:
    table_key: str
    name: str
    category: str
    tushare_api: str
    pg_table: str
    sync_mode: str
    monitored: bool
    date_col: str
    pg_columns: tuple[str, ...]
    etl_columns: tuple[str, ...]
    rows: int
    min_date: date | datetime | str | None
    max_date: date | datetime | str | None
    coverage_status: str
    history_status: str
    issues: tuple[str, ...]


@dataclass(frozen=True)
class ApiDirectoryRow:
    api: str
    title: str
    api_category: str
    project_status: str
    governance_status: str
    table_key: str
    pg_table: str
    sync_mode: str
    monitored: bool
    date_col: str
    rows: int
    min_date: date | datetime | str | None
    max_date: date | datetime | str | None
    history_status: str
    issues: tuple[str, ...]
    url: str


@dataclass(frozen=True)
class RawApiIngestStatus:
    api: str
    table_name: str
    status: str
    rows_fetched: int
    rows_inserted: int
    columns: tuple[str, ...]
    error: str


def parse_tushare_reference_apis(text: str) -> dict[str, TushareApiRef]:
    """Parse the bundled Tushare markdown API index."""
    apis: dict[str, TushareApiRef] = {}
    row_pattern = re.compile(
        r"^\|\s*\[([A-Za-z_][A-Za-z0-9_]*)\]\(([^)]+)\)\s*"
        r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|$"
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = row_pattern.match(line)
        if not match:
            continue
        name, url, title, category, description = match.groups()
        apis[name] = TushareApiRef(
            name=name,
            title=_clean_cell(title),
            category=_clean_cell(category),
            url=url.strip(),
            description=_clean_cell(description),
        )
    return apis


def parse_signal_route_catalog(path: Path = DEFAULT_ROUTES) -> tuple[list[dict[str, Any]], dict[str, tuple], dict[str, tuple[str, ...]]]:
    """Read _DATA_SOURCES, _SYNC_MAP and DATA_STATUS_DATE_COLUMNS from routes.py."""
    tree = ast.parse(path.read_text("utf-8"))
    data_sources: list[dict[str, Any]] = []
    sync_map: dict[str, tuple] = {}
    date_columns: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        names, value = _assignment_names_and_value(node)
        if "_DATA_SOURCES" in names:
            data_sources = ast.literal_eval(value)
        elif "_SYNC_MAP" in names:
            sync_map = ast.literal_eval(value)
        elif "DATA_STATUS_DATE_COLUMNS" in names:
            date_columns = ast.literal_eval(value)
    return data_sources, sync_map, date_columns


def parse_scheduler_monitored_tables(path: Path = DEFAULT_SCHEDULER) -> dict[str, dict[str, Any]]:
    """Read MONITORED_TABLES without importing the service."""
    tree = ast.parse(path.read_text("utf-8"))
    for node in tree.body:
        names, value = _assignment_names_and_value(node)
        if "MONITORED_TABLES" in names:
            return ast.literal_eval(value)
    return {}


def parse_etl_targets(path: Path = DEFAULT_ETL) -> dict[str, EtlTarget]:
    """Extract _insert_rows table/columns and pro.<api>() calls from etl.py."""
    tree = ast.parse(path.read_text("utf-8"))
    targets: dict[str, EtlTarget] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("sync_"):
            continue
        cols_by_name: dict[str, tuple[str, ...]] = {}
        apis: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                value = _literal_str_tuple(child.value)
                if value:
                    for target in child.targets:
                        if isinstance(target, ast.Name):
                            cols_by_name[target.id] = value
            elif isinstance(child, ast.Call):
                api = _pro_api_name(child)
                if api and api not in apis:
                    apis.append(api)
                insert_target = _insert_rows_target(child, cols_by_name)
                if insert_target:
                    table, columns = insert_target
                    targets[table] = EtlTarget(
                        function=node.name,
                        api=apis[0] if apis else "",
                        table=table,
                        columns=columns,
                    )
    return targets


def known_cross_module_etl_targets() -> dict[str, EtlTarget]:
    """ETL targets that are wired outside direct etl.py _insert_rows calls."""
    return {
        "stocks": EtlTarget(
            function="services.data-service.sync.stocks.sync_stock_list",
            api="stock_basic",
            table="stocks",
            columns=("code", "name", "board", "industry", "listed_date", "is_st"),
        ),
        "stk_factor_pro": EtlTarget(
            function="services.data-service.scheduler.sync_stk_factor_pro_backfill",
            api="stk_factor_pro",
            table="stk_factor_pro",
            columns=(
                "ts_code", "macd_dif", "macd_dea", "macd", "kdj_k", "kdj_d", "kdj_j",
                "rsi_6", "rsi_12", "rsi_24", "boll_upper", "boll_mid", "boll_lower",
                "turnover_rate", "vol_ratio",
            ),
        ),
        "financial_income": EtlTarget(
            function="kronos_data.etl.sync_income",
            api="income",
            table="financial_income",
            columns=(
                "code", "end_date", "report_type", "basic_eps", "total_revenue", "revenue",
                "oper_cost", "sell_expense", "admin_expense", "fin_expense", "n_income",
                "n_income_attr_p", "operate_profit", "total_profit",
            ),
        ),
        "financial_balance": EtlTarget(
            function="kronos_data.etl.sync_balancesheet",
            api="balancesheet",
            table="financial_balance",
            columns=(
                "code", "end_date", "report_type", "total_assets", "total_cur_assets",
                "total_liab", "total_cur_liab", "total_hldr_eqy_exc_min_int",
                "total_share", "cap_rese", "undistr_porfit",
            ),
        ),
        "financial_cashflow": EtlTarget(
            function="kronos_data.etl.sync_cashflow",
            api="cashflow",
            table="financial_cashflow",
            columns=(
                "code", "end_date", "report_type", "n_cashflow_act", "n_cashflow_inv_act",
                "n_cashflow_fin_act", "c_fr_sale_sg", "net_profit",
            ),
        ),
        "financial_indicator": EtlTarget(
            function="kronos_data.etl.sync_financial_indicator",
            api="fina_indicator",
            table="financial_indicator",
            columns=(
                "code", "end_date", "roe", "roa", "gross_margin", "net_margin",
                "debt_ratio", "eps", "current_ratio", "revenue_growth", "profit_growth",
            ),
        ),
    }


def introspect_pg_tables(
    tables: set[str],
    date_columns: dict[str, tuple[str, ...]],
    pg_url: str | None = None,
) -> dict[str, PgTableStats]:
    """Return exact PG columns/count/date range for requested tables."""
    pg_url = pg_url or os.environ.get("KRONOS_PG_URL")
    if not pg_url or not tables:
        return {}
    import psycopg2
    from psycopg2.sql import SQL, Identifier

    conn = psycopg2.connect(pg_url, connect_timeout=5)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema='public'
        ORDER BY table_name, ordinal_position
        """
    )
    cols_by_table: dict[str, list[str]] = {}
    for table_name, column_name in cur.fetchall():
        cols_by_table.setdefault(table_name, []).append(column_name)

    stats: dict[str, PgTableStats] = {}
    for table in sorted(tables):
        columns = tuple(cols_by_table.get(table, []))
        if not columns:
            continue
        rows = 0
        min_date = max_date = None
        try:
            cur.execute(SQL("SELECT COUNT(*) FROM {}").format(Identifier(table)))
            rows = int(cur.fetchone()[0])
        except Exception:
            conn.rollback()
        for col in date_columns.get(table, ()):
            if col not in columns:
                continue
            try:
                cur.execute(
                    SQL("SELECT MIN({}), MAX({}) FROM {} WHERE {} IS NOT NULL").format(
                        Identifier(col), Identifier(col), Identifier(table), Identifier(col)
                    )
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    min_date, max_date = row
                    break
            except Exception:
                conn.rollback()
        stats[table] = PgTableStats(table, columns, rows, min_date, max_date)
    conn.close()
    return stats


def introspect_raw_ingest_status(pg_url: str | None = None) -> dict[str, RawApiIngestStatus]:
    pg_url = pg_url or os.environ.get("KRONOS_PG_URL")
    if not pg_url:
        return {}
    import psycopg2

    try:
        conn = psycopg2.connect(pg_url, connect_timeout=5)
    except Exception:
        return {}
    cur = conn.cursor()
    try:
        cur.execute("SELECT to_regclass('public.tushare_api_ingest_status')")
        if not cur.fetchone()[0]:
            conn.close()
            return {}
        cur.execute(
            """
            SELECT api, table_name, status, rows_fetched, rows_inserted, columns, COALESCE(error, '')
            FROM tushare_api_ingest_status
            """
        )
        statuses: dict[str, RawApiIngestStatus] = {}
        for api, table_name, status, rows_fetched, rows_inserted, columns, error in cur.fetchall():
            statuses[api] = RawApiIngestStatus(
                api=api,
                table_name=table_name,
                status=status,
                rows_fetched=int(rows_fetched or 0),
                rows_inserted=int(rows_inserted or 0),
                columns=tuple(columns or ()),
                error=error or "",
            )
        conn.close()
        return statuses
    except Exception:
        conn.rollback()
        conn.close()
        return {}


def build_catalog_rows(
    data_sources: list[dict[str, Any]],
    sync_map: dict[str, tuple],
    monitored_tables: dict[str, dict[str, Any]],
    etl_targets: dict[str, EtlTarget],
    pg_tables: dict[str, PgTableStats],
    reference_apis: dict[str, TushareApiRef],
) -> list[CatalogRow]:
    rows: list[CatalogRow] = []
    for source in data_sources:
        table_key = str(source["key"])
        pg_table = table_key
        api = _api_from_source(source.get("source", "")) or _api_from_sync_map(table_key, sync_map)
        etl = etl_targets.get(pg_table) or _find_etl_target(api, etl_targets)
        pg = pg_tables.get(pg_table)
        monitored_cfg = monitored_tables.get(pg_table, {})
        date_col = str(monitored_cfg.get("date_col") or "")
        issues = _row_issues(api, reference_apis, etl, pg)
        rows.append(
            CatalogRow(
                table_key=table_key,
                name=str(source.get("name", "")),
                category=str(source.get("category", "")),
                tushare_api=api,
                pg_table=pg_table,
                sync_mode=str(sync_map.get(table_key, ("",))[0]),
                monitored=table_key in monitored_tables,
                date_col=date_col,
                pg_columns=pg.columns if pg else (),
                etl_columns=etl.columns if etl else (),
                rows=pg.rows if pg else 0,
                min_date=pg.min_date if pg else None,
                max_date=pg.max_date if pg else None,
                coverage_status=_coverage_status(pg, etl),
                history_status=_history_status(pg),
                issues=tuple(issues),
            )
        )
    return rows


def uncovered_reference_apis(
    reference_apis: dict[str, TushareApiRef],
    catalog_rows: list[CatalogRow],
) -> list[TushareApiRef]:
    covered = {row.tushare_api for row in catalog_rows if row.tushare_api}
    return [api for name, api in sorted(reference_apis.items()) if name not in covered]


def build_full_api_directory_rows(
    reference_apis: dict[str, TushareApiRef],
    catalog_rows: list[CatalogRow],
    raw_status: dict[str, RawApiIngestStatus] | None = None,
) -> list[ApiDirectoryRow]:
    """Return one directory row for every Tushare reference API."""
    raw_status = raw_status or {}
    by_api: dict[str, CatalogRow] = {}
    for row in catalog_rows:
        if row.tushare_api and row.tushare_api not in by_api:
            by_api[row.tushare_api] = row

    directory: list[ApiDirectoryRow] = []
    for api_name, api in sorted(reference_apis.items()):
        row = by_api.get(api_name)
        if row:
            directory.append(
                ApiDirectoryRow(
                    api=api.name,
                    title=api.title,
                    api_category=api.category,
                    project_status=row.coverage_status,
                    governance_status=_implemented_governance_status(row),
                    table_key=row.table_key,
                    pg_table=row.pg_table,
                    sync_mode=row.sync_mode,
                    monitored=row.monitored,
                    date_col=row.date_col,
                    rows=row.rows,
                    min_date=row.min_date,
                    max_date=row.max_date,
                    history_status=row.history_status,
                    issues=row.issues,
                    url=api.url,
                )
            )
        elif api.name in raw_status:
            raw = raw_status[api.name]
            directory.append(
                ApiDirectoryRow(
                    api=api.name,
                    title=api.title,
                    api_category=api.category,
                    project_status="raw_landed" if raw.status == "collected" else "raw_table_created",
                    governance_status=raw.status,
                    table_key="",
                    pg_table=raw.table_name,
                    sync_mode="raw_bulk_ingest",
                    monitored=False,
                    date_col="",
                    rows=raw.rows_inserted,
                    min_date=None,
                    max_date=None,
                    history_status="raw_unverified",
                    issues=() if raw.status == "collected" else (raw.status,),
                    url=api.url,
                )
            )
        else:
            directory.append(
                ApiDirectoryRow(
                    api=api.name,
                    title=api.title,
                    api_category=api.category,
                    project_status="not_in_project_catalog",
                    governance_status="unclassified",
                    table_key="",
                    pg_table="",
                    sync_mode="",
                    monitored=False,
                    date_col="",
                    rows=0,
                    min_date=None,
                    max_date=None,
                    history_status="not_applicable",
                    issues=("not_classified",),
                    url=api.url,
                )
            )
    return directory


def render_markdown(
    rows: list[CatalogRow],
    reference_apis: dict[str, TushareApiRef],
    uncovered: list[TushareApiRef],
    raw_status: dict[str, RawApiIngestStatus] | None = None,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now()
    raw_status = raw_status or {}
    directory_rows = build_full_api_directory_rows(reference_apis, rows, raw_status)
    covered = sum(1 for row in rows if row.coverage_status == "covered")
    ten_year = sum(1 for row in rows if row.history_status == "10y_ok")
    issue_rows = sum(1 for row in rows if row.issues)
    unclassified = sum(1 for row in directory_rows if row.governance_status == "unclassified")
    raw_landed = sum(1 for row in directory_rows if row.project_status == "raw_landed")
    raw_table_created = sum(1 for row in directory_rows if row.project_status == "raw_table_created")
    lines = [
        "# Tushare 数据资产目录",
        "",
        f"> 生成时间: {generated_at.isoformat(timespec='seconds')}",
        "",
        "## 汇总",
        "",
        f"- Tushare 本地接口文档 API 数: {len(reference_apis)}",
        f"- 前端/后端已登记数据源: {len(rows)}",
        f"- PG+ETL 双覆盖: {covered}",
        f"- 10 年跨度达标: {ten_year}",
        f"- 存在字段/覆盖问题的数据源: {issue_rows}",
        f"- 全量 API 目录行数: {len(directory_rows)}",
        f"- 原始层已采集 API: {raw_landed}",
        f"- 原始层已建表但需补参数/权限/API 支持的 API: {raw_table_created}",
        f"- 尚未分类治理结论的 API: {unclassified}",
        f"- 尚未实现 PG/ETL 的 API: {len(uncovered)}",
        "",
        "## 已登记数据源",
        "",
        "| 表 | Tushare API | 分类 | 同步 mode | 监控 | 日期列 | 行数 | 起始 | 最新 | 覆盖 | 历史 | 问题 |",
        "|---|---|---|---|---|---|---:|---|---|---|---|---|",
    ]
    for row in rows:
        issues = "<br>".join(row.issues) if row.issues else ""
        lines.append(
            "| {table} | {api} | {category} | {mode} | {monitored} | {date_col} | {rows} | {min_date} | {max_date} | {coverage} | {history} | {issues} |".format(
                table=row.pg_table,
                api=row.tushare_api,
                category=row.category,
                mode=row.sync_mode,
                monitored="是" if row.monitored else "否",
                date_col=row.date_col,
                rows=row.rows,
                min_date=_fmt_date(row.min_date),
                max_date=_fmt_date(row.max_date),
                coverage=row.coverage_status,
                history=row.history_status,
                issues=issues,
            )
        )
    lines.extend(
        [
            "",
            "## 全量 Tushare API 覆盖矩阵",
            "",
            "> 每个 Tushare API 都在本表中。未实现不等于遗漏，而是必须继续补治理结论。",
            "",
            "| API | 标题 | 分类 | 项目状态 | 治理状态 | PG表 | 同步mode | 监控 | 日期列 | 行数 | 起始 | 最新 | 历史 | 问题 | 文档 |",
            "|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|",
        ]
    )
    for row in directory_rows:
        issues = "<br>".join(row.issues) if row.issues else ""
        lines.append(
            "| {api} | {title} | {category} | {project_status} | {governance_status} | {pg_table} | {sync_mode} | {monitored} | {date_col} | {rows} | {min_date} | {max_date} | {history} | {issues} | {url} |".format(
                api=row.api,
                title=row.title,
                category=row.api_category,
                project_status=row.project_status,
                governance_status=row.governance_status,
                pg_table=row.pg_table,
                sync_mode=row.sync_mode,
                monitored="是" if row.monitored else "否",
                date_col=row.date_col,
                rows=row.rows,
                min_date=_fmt_date(row.min_date),
                max_date=_fmt_date(row.max_date),
                history=row.history_status,
                issues=issues,
                url=row.url,
            )
        )
    lines.append("")
    return "\n".join(lines)


def build_catalog(pg_url: str | None = None) -> tuple[list[CatalogRow], dict[str, TushareApiRef], list[TushareApiRef]]:
    reference_apis = parse_tushare_reference_apis(DEFAULT_REFERENCE.read_text("utf-8"))
    data_sources, sync_map, date_columns = parse_signal_route_catalog(DEFAULT_ROUTES)
    monitored = parse_scheduler_monitored_tables(DEFAULT_SCHEDULER)
    etl_targets = parse_etl_targets(DEFAULT_ETL)
    etl_targets.update({k: v for k, v in known_cross_module_etl_targets().items() if k not in etl_targets})
    combined_date_columns = _combined_date_columns(data_sources, monitored, date_columns)
    requested_tables = {source["key"] for source in data_sources} | set(monitored)
    pg_tables = introspect_pg_tables(requested_tables, combined_date_columns, pg_url=pg_url)
    rows = build_catalog_rows(data_sources, sync_map, monitored, etl_targets, pg_tables, reference_apis)
    uncovered = uncovered_reference_apis(reference_apis, rows)
    return rows, reference_apis, uncovered


def main() -> int:
    parser = argparse.ArgumentParser(description="Build read-only Tushare data governance catalog")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows, reference_apis, uncovered = build_catalog(pg_url=args.pg_url)
    raw_status = introspect_raw_ingest_status(args.pg_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(rows, reference_apis, uncovered, raw_status), "utf-8")
    print(f"OK {args.output} | sources={len(rows)} reference_apis={len(reference_apis)} uncovered={len(uncovered)}")
    return 0


def _clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("<br>", " ")).strip()


def _assignment_names_and_value(node: ast.AST) -> tuple[list[str], ast.AST]:
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)], node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
        return [node.target.id], node.value
    return [], ast.Constant(None)


def _literal_str_tuple(node: ast.AST) -> tuple[str, ...]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return ()
    values: list[str] = []
    for item in node.elts:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            values.append(item.value)
        else:
            return ()
    return tuple(values)


def _pro_api_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        if call.func.value.id == "pro":
            return call.func.attr
    return ""


def _insert_rows_target(call: ast.Call, cols_by_name: dict[str, tuple[str, ...]]) -> tuple[str, tuple[str, ...]] | None:
    if not isinstance(call.func, ast.Name) or call.func.id != "_insert_rows":
        return None
    if len(call.args) < 4:
        return None
    table_arg = call.args[1]
    cols_arg = call.args[2]
    if not isinstance(table_arg, ast.Constant) or not isinstance(table_arg.value, str):
        return None
    columns: tuple[str, ...] = ()
    if isinstance(cols_arg, ast.Name):
        columns = cols_by_name.get(cols_arg.id, ())
    else:
        columns = _literal_str_tuple(cols_arg)
    return table_arg.value, columns


def _api_from_source(source: str) -> str:
    match = re.search(r"\bTushare\s+([A-Za-z_][A-Za-z0-9_]*)", source)
    return match.group(1) if match else ""


def _api_from_sync_map(table_key: str, sync_map: dict[str, tuple]) -> str:
    mode = str(sync_map.get(table_key, ("",))[0])
    aliases = {
        "weekly": "weekly",
        "monthly": "monthly",
        "limit_list": "limit_list_d",
        "income": "income",
        "balancesheet": "balancesheet",
        "cashflow": "cashflow",
        "fina_indicator": "fina_indicator",
        "stock_news": "news",
        "research_report": "research_report",
    }
    return aliases.get(mode, mode)


def _find_etl_target(api: str, etl_targets: dict[str, EtlTarget]) -> EtlTarget | None:
    if not api:
        return None
    for target in etl_targets.values():
        if target.api == api:
            return target
    return None


def _coverage_status(pg: PgTableStats | None, etl: EtlTarget | None) -> str:
    if pg and etl:
        return "covered"
    if pg:
        return "pg_only"
    if etl:
        return "etl_no_pg"
    return "not_implemented"


def _history_status(pg: PgTableStats | None) -> str:
    if not pg or pg.rows <= 0 or not pg.min_date or not pg.max_date:
        return "no_data"
    start = _to_date(pg.min_date)
    end = _to_date(pg.max_date)
    if not start or not end:
        return "unknown"
    if (end - start).days >= 3650:
        return "10y_ok"
    return "short_history"


def _row_issues(
    api: str,
    reference_apis: dict[str, TushareApiRef],
    etl: EtlTarget | None,
    pg: PgTableStats | None,
) -> list[str]:
    issues: list[str] = []
    if api and api not in reference_apis:
        issues.append("api_not_in_reference")
    if pg is None:
        issues.append("missing_pg_table")
    if etl is None:
        issues.append("missing_etl_target")
    if etl and pg:
        missing_cols = [col for col in etl.columns if col not in pg.columns]
        if missing_cols:
            issues.append("etl_cols_not_in_pg: " + ",".join(missing_cols))
    return issues


def _implemented_governance_status(row: CatalogRow) -> str:
    if row.coverage_status != "covered":
        return "needs_mapping"
    if row.issues:
        return "needs_field_decision"
    if row.history_status in {"short_history", "unknown", "no_data"}:
        return "needs_history_decision"
    return "active"


def _combined_date_columns(
    data_sources: list[dict[str, Any]],
    monitored: dict[str, dict[str, Any]],
    route_date_columns: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    combined = {key: tuple(value) for key, value in route_date_columns.items()}
    for table, cfg in monitored.items():
        col = cfg.get("date_col")
        if col and table not in combined:
            combined[table] = (str(col),)
    for source in data_sources:
        key = str(source["key"])
        combined.setdefault(key, ("trade_date", "end_date", "ann_date", "pub_date", "pub_time", "updated_at"))
    return combined


def _to_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _fmt_date(value: date | datetime | str | None) -> str:
    if value is None:
        return ""
    return str(value)[:19]


if __name__ == "__main__":
    raise SystemExit(main())
