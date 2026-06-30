from datetime import date
import importlib.util
import sys
from pathlib import Path


_MODULE_PATH = Path(__file__).with_name("tushare_data_catalog.py")
_SPEC = importlib.util.spec_from_file_location("tushare_data_catalog", _MODULE_PATH)
catalog = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = catalog
_SPEC.loader.exec_module(catalog)


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


def test_parse_scheduler_monitored_tables_accepts_annotated_assignment(tmp_path):
    scheduler = tmp_path / "scheduler.py"
    scheduler.write_text(
        'MONITORED_TABLES: dict[str, dict] = {"daily_kline": {"date_col": "trade_date", "freq": "L2-daily"}}',
        encoding="utf-8",
    )

    monitored = catalog.parse_scheduler_monitored_tables(scheduler)

    assert monitored["daily_kline"]["date_col"] == "trade_date"


def test_known_cross_module_etl_targets_cover_service_side_syncs():
    targets = catalog.known_cross_module_etl_targets()

    assert targets["stocks"].api == "stock_basic"
    assert targets["stocks"].function == "services.data-service.sync.stocks.sync_stock_list"
    assert targets["stk_factor_pro"].api == "stk_factor_pro"
    assert targets["financial_balance"].api == "balancesheet"


def test_build_full_api_directory_rows_includes_every_reference_api():
    reference_apis = {
        "daily": catalog.TushareApiRef("daily", "日线行情", "股票数据", "url-daily", ""),
        "fund_daily": catalog.TushareApiRef("fund_daily", "ETF日线", "ETF专题", "url-fund", ""),
    }
    catalog_rows = [
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
            rows=10,
            min_date=None,
            max_date=None,
            coverage_status="covered",
            history_status="no_data",
            issues=(),
        )
    ]

    directory_rows = catalog.build_full_api_directory_rows(reference_apis, catalog_rows)

    assert [row.api for row in directory_rows] == ["daily", "fund_daily"]
    assert directory_rows[0].project_status == "covered"
    assert directory_rows[0].pg_table == "daily_kline"
    assert directory_rows[1].project_status == "not_in_project_catalog"
    assert directory_rows[1].governance_status == "unclassified"


def test_render_markdown_does_not_omit_uncovered_reference_apis():
    reference_apis = {
        f"api_{i}": catalog.TushareApiRef(f"api_{i}", f"接口{i}", "测试", f"url-{i}", "")
        for i in range(3)
    }

    markdown = catalog.render_markdown([], reference_apis, list(reference_apis.values()))

    assert "## 全量 Tushare API 覆盖矩阵" in markdown
    assert "| api_0 | 接口0 | 测试 | not_in_project_catalog | unclassified |" in markdown
    assert "| api_2 | 接口2 | 测试 | not_in_project_catalog | unclassified |" in markdown
    assert "其余" not in markdown


def test_init_postgres_moneyflow_hsgt_matches_live_pg_contract():
    ddl = (Path(__file__).parents[3] / "services/sql/init_postgres.sql").read_text(encoding="utf-8")
    block = ddl.split("CREATE TABLE IF NOT EXISTS moneyflow_hsgt", 1)[1].split(");", 1)[0]

    for column in (
        "trade_date",
        "north_net_inflow",
        "south_net_inflow",
        "ggt_ss",
        "ggt_sz",
        "hgt",
        "sgt",
        "north_money",
        "south_money",
    ):
        assert column in block
