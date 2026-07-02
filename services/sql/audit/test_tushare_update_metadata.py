import importlib.util
import sys
from pathlib import Path


_MODULE_PATH = Path(__file__).with_name("tushare_update_metadata.py")
_SPEC = importlib.util.spec_from_file_location("tushare_update_metadata", _MODULE_PATH)
metadata = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = metadata
_SPEC.loader.exec_module(metadata)


def test_extracts_update_time_from_data_description():
    text = "数据说明：交易日每天15点～16点之间入库。本接口是未复权行情"

    result = metadata.extract_update_metadata("daily", text, "url")

    assert result.update_time == "交易日每天15点～16点之间入库"
    assert result.update_frequency == "交易日每天"
    assert result.extraction_status == "extracted"


def test_extracts_update_frequency_from_update_frequency_label():
    text = "更新频率：每日。更新时间：交易日 19:00 后。"

    result = metadata.extract_update_metadata("fund_daily", text, "url")

    assert result.update_frequency == "每日"
    assert result.update_time == "交易日 19:00 后"


def test_marks_unknown_when_document_has_no_update_hint():
    result = metadata.extract_update_metadata("anns_d", "描述：获取全量公告数据", "url")

    assert result.update_frequency == "unknown"
    assert result.update_time == "unknown"
    assert result.extraction_status == "not_found"


def test_extracts_inline_next_day_update_sentence():
    text = "数据指标是分批入库，交易所于次日早8点30左右更新上一交易日的数据；另外，涉及海外的ETF数据更新会晚一些。"

    result = metadata.extract_update_metadata("etf_share_size", text, "url")

    assert result.update_time == "交易所于次日早8点30左右更新上一交易日的数据"
    assert result.update_frequency == "每日"


def test_extracts_realtime_frequency_from_description():
    text = "描述：获取ETF实时分钟数据，包括1~60min。数据实时更新。"

    result = metadata.extract_update_metadata("rt_min", text, "url")

    assert result.update_frequency == "实时"
    assert result.update_time == "数据实时更新"


def test_metadata_columns_are_fixed_contract():
    assert metadata.METADATA_COLUMNS == (
        "_tushare_update_time",
        "_tushare_update_frequency",
        "_tushare_doc_url",
        "_tushare_metadata_updated_at",
    )
