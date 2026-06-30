from datetime import date

from services.sql.audit import tushare_data_catalog as catalog


def test_parse_tushare_reference_apis_from_markdown_table():
    text = """
| 接口 | 标题 | 分类 | 描述 |
| [daily](https://tushare.pro/wctapi/documents/27.md) | 日线行情 | 股票数据 | A股日线 |
| [moneyflow](https://tushare.pro/wctapi/documents/170.md) | 个股资金流向 | 股票数据 | 资金流 |
"""

    apis = catalog.parse_tushare_reference_apis(text)

    assert apis["daily"].title == "日线行情"
    assert apis["daily"].category == "股票数据"
    assert apis["moneyflow"].url.endswith("/170.md")


def test_build_catalog_flags_pg_coverage_history_and_field_drift():
    rows = catalog.build_catalog_rows(
        data_sources=[
            {
                "key": "daily_kline",
                "name": "日线行情",
                "category": "行情",
                "source": "Tushare daily",
                "update": "每日盘后",
                "note": "",
            }
        ],
        sync_map={"daily_kline": ("daily_kline", 30, "日K线")},
        monitored_tables={"daily_kline": {"date_col": "trade_date", "freq": "L2-daily"}},
        etl_targets={
            "daily_kline": catalog.EtlTarget(
                function="sync_daily_kline",
                api="daily",
                table="daily_kline",
                columns=("code", "trade_date", "open", "high", "low", "close", "change_pct"),
            )
        },
        pg_tables={
            "daily_kline": catalog.PgTableStats(
                table="daily_kline",
                columns=("code", "trade_date", "open", "high", "low", "close"),
                rows=100,
                min_date=date(2016, 1, 1),
                max_date=date(2026, 6, 30),
            )
        },
        reference_apis={"daily": catalog.TushareApiRef("daily", "日线行情", "股票数据", "url", "A股日线")},
    )

    row = rows[0]

    assert row.coverage_status == "covered"
    assert row.history_status == "10y_ok"
    assert "etl_cols_not_in_pg: change_pct" in row.issues


def test_uncovered_reference_apis_excludes_mapped_sources():
    uncovered = catalog.uncovered_reference_apis(
        reference_apis={
            "daily": catalog.TushareApiRef("daily", "日线行情", "股票数据", "url", ""),
            "fund_daily": catalog.TushareApiRef("fund_daily", "ETF日线", "ETF专题", "url", ""),
        },
        catalog_rows=[
            catalog.CatalogRow(
                table_key="daily_kline",
                name="日线行情",
                category="行情",
                tushare_api="daily",
                pg_table="daily_kline",
                sync_mode="daily_kline",
                monitored=True,
                date_col="trade_date",
                pg_columns=(),
                etl_columns=(),
                rows=0,
                min_date=None,
                max_date=None,
                coverage_status="covered",
                history_status="no_data",
                issues=(),
            )
        ],
    )

    assert [api.name for api in uncovered] == ["fund_daily"]
