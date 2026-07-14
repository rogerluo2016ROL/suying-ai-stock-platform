"""盘中全市场涨跌宽度计算。

该模块只基于明确的行情快照做统计，不使用入选股票数量代替全市场强弱。
"""

from __future__ import annotations

from statistics import median
from typing import Any, Callable, Iterable, Mapping


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def compute_market_strength(
    trade_date: str,
    cutoff_time: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    minimum_coverage: int = 100,
) -> dict[str, Any]:
    """计算指定时点的全市场涨跌家数与涨跌幅中位数。"""

    valid_rows: list[tuple[str, float]] = []
    for row in rows:
        close = _number(row.get("close"))
        pre_close = _number(row.get("pre_close"))
        if close is None or pre_close is None:
            continue
        snapshot_time = str(row.get("snapshot_time") or "")
        pct = (close / pre_close - 1) * 100
        valid_rows.append((snapshot_time, pct))

    snapshot_time = max(
        (item[0] for item in valid_rows if item[0]),
        default=f"{trade_date} {cutoff_time}:00",
    )
    coverage = len(valid_rows)
    if coverage < minimum_coverage:
        return {
            "status": "insufficient",
            "scope": "intraday_market_breadth",
            "trade_date": trade_date,
            "cutoff_time": cutoff_time,
            "snapshot_time": snapshot_time,
            "coverage": coverage,
            "reason": f"有效股票数 {coverage} 低于最低要求 {minimum_coverage}",
        }

    percentages = [item[1] for item in valid_rows]
    return {
        "status": "ok",
        "scope": "intraday_market_breadth",
        "trade_date": trade_date,
        "cutoff_time": cutoff_time,
        "snapshot_time": snapshot_time,
        "coverage": coverage,
        "advancers": sum(value > 0 for value in percentages),
        "decliners": sum(value < 0 for value in percentages),
        "flat": sum(value == 0 for value in percentages),
        "median_pct": round(median(percentages), 2),
        "above_5pct": sum(value >= 5 for value in percentages),
        "below_minus_5pct": sum(value <= -5 for value in percentages),
    }


def load_market_strength(
    trade_date: str,
    cutoff_time: str,
    pg_url: str,
    *,
    minimum_coverage: int = 100,
    connect: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """从 PostgreSQL 读取截止时点前每只股票的最新行情并计算市场宽度。"""

    if connect is None:
        import psycopg2

        connect = psycopg2.connect

    cutoff_timestamp = f"{trade_date} {cutoff_time}:59"
    start_timestamp = f"{trade_date} 00:00:00"
    sql = """
        WITH latest_minute AS (
            SELECT DISTINCT ON (m.code)
                m.code,
                m.trade_time AS snapshot_time,
                m.close
            FROM stk_mins AS m
            WHERE m.trade_time >= %s AND m.trade_time <= %s
            ORDER BY m.code, m.trade_time DESC
        )
        SELECT
            lm.code,
            lm.snapshot_time,
            lm.close,
            COALESCE(auction.close, previous.close) AS pre_close
        FROM latest_minute AS lm
        LEFT JOIN LATERAL (
            SELECT a.close
            FROM stk_auction_o AS a
            WHERE a.code = lm.code AND a.trade_date = %s::date
            ORDER BY a.trade_date DESC
            LIMIT 1
        ) AS auction ON TRUE
        LEFT JOIN LATERAL (
            SELECT d.close
            FROM daily_kline AS d
            WHERE d.code = lm.code AND d.trade_date < %s::date
            ORDER BY d.trade_date DESC
            LIMIT 1
        ) AS previous ON TRUE
        WHERE lm.close > 0 AND COALESCE(auction.close, previous.close) > 0
    """

    try:
        with connect(pg_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (start_timestamp, cutoff_timestamp, trade_date, trade_date),
                )
                columns = [column[0] for column in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as exc:
        return {
            "status": "insufficient",
            "scope": "intraday_market_breadth",
            "trade_date": trade_date,
            "cutoff_time": cutoff_time,
            "snapshot_time": cutoff_timestamp,
            "coverage": 0,
            "reason": f"市场行情读取失败: {type(exc).__name__}",
        }

    return compute_market_strength(
        trade_date,
        cutoff_time,
        rows,
        minimum_coverage=minimum_coverage,
    )
