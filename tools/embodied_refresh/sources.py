"""Independent, cursor-based adapters for locally landed evidence sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import psycopg2
import psycopg2.extras


@dataclass(frozen=True)
class SourceSpec:
    table: str
    cursor_column: str
    code_column: str = "code"


SOURCE_SPECS = {
    "announcement": SourceSpec("announcements", "ann_date"),
    "interact_qa": SourceSpec("interact_qa", "pub_date"),
    "research": SourceSpec("research_reports_tushare", "pub_date"),
    "profile": SourceSpec("stock_profiles", "updated_at"),
    "main_business": SourceSpec("fina_mainbz", "update_time"),
}


@dataclass(frozen=True)
class SourceQuery:
    source_name: str
    table: str
    cursor_column: str
    since: str | None


@dataclass
class SourceRefreshResult:
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    queries: dict[str, SourceQuery] = field(default_factory=dict)
    next_cursors: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def successful_sources(self) -> set[str]:
        return set(self.rows) - set(self.errors)


def fetch_incremental_sources(
    pg_url: str | Any, cursors: Mapping[str, str | None]
) -> SourceRefreshResult:
    """Fetch every source independently; a failure cannot advance its cursor."""
    result = SourceRefreshResult()
    for source_name, spec in SOURCE_SPECS.items():
        since = cursors.get(source_name)
        result.queries[source_name] = SourceQuery(
            source_name, spec.table, spec.cursor_column, since
        )
        connection = None
        owns_connection = isinstance(pg_url, str)
        try:
            connection = psycopg2.connect(pg_url) if owns_connection else pg_url
            rows = _fetch_one_source(connection, spec, since)
            result.rows[source_name] = rows
            observed = [
                str(row["source_cursor"])
                for row in rows
                if row.get("source_cursor") is not None
            ]
            # An empty successful poll retains its known cursor. A source with no
            # prior cursor remains absent until it yields a real high-water mark.
            if observed:
                result.next_cursors[source_name] = max(observed)
            elif since is not None:
                result.next_cursors[source_name] = since
        except Exception as exc:
            result.errors[source_name] = f"{type(exc).__name__}: {exc}"
            if connection is not None:
                connection.rollback()
        finally:
            if owns_connection and connection is not None:
                connection.close()
    return result


def _fetch_one_source(
    connection: Any, spec: SourceSpec, since: str | None
) -> list[dict[str, Any]]:
    clause = f"WHERE {spec.cursor_column} > %s" if since is not None else ""
    sql = f"""
        SELECT *, {spec.cursor_column} AS source_cursor
          FROM {spec.table}
          {clause}
         ORDER BY {spec.cursor_column} ASC
    """
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql, (since,) if since is not None else ())
        return [dict(row) for row in cursor.fetchall()]
