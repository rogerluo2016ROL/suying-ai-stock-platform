import importlib.util
import sys
from pathlib import Path


_MODULE_PATH = Path(__file__).with_name("tushare_bulk_ingest.py")
_SPEC = importlib.util.spec_from_file_location("tushare_bulk_ingest", _MODULE_PATH)
ingest = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = ingest
_SPEC.loader.exec_module(ingest)


def test_raw_table_name_is_safe_and_prefixed():
    assert ingest.raw_table_name("daily") == "ts_raw_daily"
    assert ingest.raw_table_name("Bad-Name") == "ts_raw_bad_name"
    assert ingest.raw_table_name("123abc") == "ts_raw_api_123abc"


def test_build_date_windows_covers_requested_years():
    windows = ingest.build_date_windows(end_date="20260701", years=3)

    assert windows[0] == ("20230702", "20231231")
    assert windows[-1] == ("20260101", "20260701")
    assert len(windows) == 4


def test_row_hash_is_stable_across_column_order():
    row_a = {"ts_code": "000001.SZ", "trade_date": "20260101", "close": "10.2"}
    row_b = {"close": "10.2", "trade_date": "20260101", "ts_code": "000001.SZ"}

    assert ingest.row_hash(row_a) == ingest.row_hash(row_b)


def test_pg_identifier_quotes_internal_quotes():
    assert ingest.pg_ident('a"b') == '"a""b"'


def test_normalize_records_preserves_returned_fields_and_adds_hash():
    records = ingest.normalize_records(
        "daily",
        [{"ts_code": "000001.SZ", "trade_date": 20260101, "close": 10.2}],
    )

    assert records[0]["ts_code"] == "000001.SZ"
    assert records[0]["trade_date"] == "20260101"
    assert records[0]["close"] == "10.2"
    assert records[0]["_source_api"] == "daily"
    assert len(records[0]["_row_hash"]) == 64


def test_choose_next_request_tries_date_window_then_no_param_fallback():
    attempts = ingest.request_attempts_for_window("fund_basic", "20250101", "20251231")

    assert attempts[0] == {"start_date": "20250101", "end_date": "20251231"}
    assert attempts[-1] == {}


def test_raw_metadata_columns_are_fixed_contract():
    assert ingest.RAW_METADATA_COLUMNS == (
        "_tushare_update_time",
        "_tushare_update_frequency",
        "_tushare_doc_url",
        "_tushare_metadata_updated_at",
    )
