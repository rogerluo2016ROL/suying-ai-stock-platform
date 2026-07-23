#!/usr/bin/env python3
"""按链成分股等权日涨幅构建 industry_price_series 序列。

成分股来源:business_tag_mapping 的链公司(status != 'rejected' 的去重 code);
涨幅来源:daily_kline.change_pct,按 trade_date 等权平均。
写入 metric_name='chain_equal_weight_pct_change',source_id='chain_equal_weight_local',
供 _chain_prosperity / screener-service 景气读取方优先于 dc_index_pct_change 使用
(原有 17 条链的 dc_index 快照只有几天数据,活跃链如 storage_chips /
near_memory_computing 无数据导致 prosperity 恒 50)。

函数形式可被 data-service 调度复用:
    refresh_chain_equal_weight_series(pg_url, trade_days=3, apply=True)

CLI 默认 dry-run,--apply 写库;--days 60 回填近 60 个交易日。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get(
    "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"
)

SOURCE_ID = "chain_equal_weight_local"
METRIC_NAME = "chain_equal_weight_pct_change"
REGION = "A股等权"
UNIT = "%"


def series_id_for(chain_id: str, trade_date: str) -> str:
    payload = f"{SOURCE_ID}:{chain_id}:{METRIC_NAME}:{trade_date}:{REGION}"
    return "IPS-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def load_chain_components(cur, chain_ids: list[str] | None = None) -> dict[str, list[str]]:
    """business_tag_mapping 的链公司(去重 code,剔除 rejected)。"""
    sql = """
        SELECT chain_id, code
        FROM business_tag_mapping
        WHERE chain_id IS NOT NULL AND code IS NOT NULL
          AND status != 'rejected'
        GROUP BY chain_id, code
        ORDER BY chain_id, max(confidence) DESC, code
    """
    cur.execute(sql)
    components: dict[str, list[str]] = {}
    for row in cur.fetchall():
        chain_id = row["chain_id"] if isinstance(row, dict) else row[0]
        code = row["code"] if isinstance(row, dict) else row[1]
        components.setdefault(str(chain_id), []).append(str(code))
    if chain_ids:
        components = {k: v for k, v in components.items() if k in set(chain_ids)}
    return components


def compute_chain_daily_returns(
    cur, codes: list[str], min_trade_date: str
) -> list[dict[str, Any]]:
    """daily_kline 等权日涨幅:按 trade_date 对成分股 change_pct 取均值。"""
    if not codes:
        return []
    cur.execute(
        """
        SELECT trade_date, avg(change_pct) AS avg_pct, count(*) AS components
        FROM daily_kline
        WHERE code = ANY(%s) AND change_pct IS NOT NULL AND trade_date >= %s
        GROUP BY trade_date
        ORDER BY trade_date
        """,
        (codes, min_trade_date),
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row) if not isinstance(row, dict) else row
        rows.append({
            "trade_date": item["trade_date"],
            "avg_pct": round(float(item["avg_pct"]), 4),
            "components": int(item["components"]),
        })
    return rows


def _min_trade_date(cur, trade_days: int) -> str | None:
    cur.execute(
        """
        SELECT min(trade_date) AS d FROM (
            SELECT DISTINCT trade_date FROM daily_kline
            ORDER BY trade_date DESC LIMIT %s
        ) t
        """,
        (trade_days,),
    )
    row = cur.fetchone()
    value = row["d"] if isinstance(row, dict) else row[0]
    return str(value) if value else None


def _ensure_source(cur) -> None:
    cur.execute(
        """
        INSERT INTO evidence_source_catalog (
            source_id, source_name, source_type, source_level,
            source_reliability_score, confidence_cap,
            is_official, is_third_party_estimate, is_market_sentiment,
            requires_cross_validation, license_status, update_frequency,
            crawl_method, enabled, metadata
        )
        VALUES (
            %(source_id)s, %(source_name)s, 'chain_price', 'mid',
            0.7, 0.7, false, true, false, true,
            'available', 'daily', 'existing_table', true, %(metadata)s::jsonb
        )
        ON CONFLICT (source_id) DO NOTHING
        """,
        {
            "source_id": SOURCE_ID,
            "source_name": "链成分股等权日涨幅(本地 daily_kline)",
            "metadata": json.dumps(
                {"generator": "build_industry_price_series.py",
                 "components": "business_tag_mapping",
                 "price": "daily_kline.change_pct"},
                ensure_ascii=False,
            ),
        },
    )


def refresh_chain_equal_weight_series(
    pg_url: str,
    trade_days: int = 60,
    chain_ids: list[str] | None = None,
    apply: bool = True,
) -> dict[str, Any]:
    """计算并(apply 时)upsert 链等权日涨幅,返回统计。供 CLI 与调度复用。"""
    import psycopg2
    import psycopg2.extras

    stats: dict[str, Any] = {
        "apply": apply, "trade_days": trade_days, "chains": {}, "rows_written": 0,
    }
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            min_date = _min_trade_date(cur, trade_days)
            if not min_date:
                stats["error"] = "daily_kline 无数据"
                return stats
            stats["min_trade_date"] = min_date
            components = load_chain_components(cur, chain_ids)
            if apply:
                _ensure_source(cur)
            upsert_rows: list[dict[str, Any]] = []
            for chain_id, codes in sorted(components.items()):
                daily = compute_chain_daily_returns(cur, codes, min_date)
                stats["chains"][chain_id] = {
                    "components": len(codes), "days": len(daily),
                    "latest": daily[-1] if daily else None,
                }
                for item in daily:
                    upsert_rows.append({
                        "series_id": series_id_for(chain_id, str(item["trade_date"])),
                        "source_id": SOURCE_ID,
                        "chain_id": chain_id,
                        "metric_name": METRIC_NAME,
                        "metric_value": item["avg_pct"],
                        "unit": UNIT,
                        "trade_date": item["trade_date"],
                        "region": REGION,
                        "metadata": json.dumps(
                            {"components": item["components"],
                             "method": "equal_weight_avg_change_pct"},
                            ensure_ascii=False,
                        ),
                    })
            stats["rows_planned"] = len(upsert_rows)
            if apply and upsert_rows:
                cur.executemany(
                    """
                    INSERT INTO industry_price_series (
                        series_id, source_id, chain_id, node_id, metric_name,
                        metric_value, unit, trade_date, region, source_url, metadata
                    )
                    VALUES (
                        %(series_id)s, %(source_id)s, %(chain_id)s, NULL,
                        %(metric_name)s, %(metric_value)s, %(unit)s,
                        %(trade_date)s, %(region)s, NULL, %(metadata)s::jsonb
                    )
                    ON CONFLICT (series_id) DO UPDATE SET
                        metric_value = EXCLUDED.metric_value,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    upsert_rows,
                )
                stats["rows_written"] = len(upsert_rows)
                conn.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--apply", action="store_true", help="实际写库(默认 dry-run)")
    parser.add_argument("--days", type=int, default=60, help="回填最近 N 个交易日")
    parser.add_argument("--chains", nargs="*", default=None, help="只处理指定 chain_id")
    args = parser.parse_args()
    stats = refresh_chain_equal_weight_series(
        args.pg_url, trade_days=args.days, chain_ids=args.chains, apply=args.apply
    )
    print(json.dumps(stats, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
