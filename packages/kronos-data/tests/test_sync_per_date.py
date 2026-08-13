"""`_sync_per_date` 通用同步骨架的 mock 测试（不依赖 Tushare / 真实 DB）。

验证骨架的核心逻辑：按交易日循环 → api_call 拉取 → row_mapper 映射 →
_insert_rows 写入 → commit/close → 返回统计。用 mock 隔离所有外部依赖。
"""
from unittest import mock

import pandas as pd

import kronos_data.etl as etl


def _fake_df():
    return pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ"], "close": [10.0, 20.0]})


def test_sync_per_date_loops_maps_and_returns_counts():
    calls = []

    def api_call(pro, d):
        calls.append(d)
        return _fake_df()

    def row_mapper(r, d):
        return (r["ts_code"], d)

    fake_db = mock.MagicMock()

    with mock.patch.object(etl, "_get_pro", return_value=object()), \
         mock.patch.object(etl, "_get_trade_dates", return_value=["20260101", "20260102"]), \
         mock.patch.object(etl, "_get_etl_db", return_value=fake_db), \
         mock.patch.object(etl, "clean_before_write"), \
         mock.patch.object(etl, "_rate_limit"), \
         mock.patch.object(etl, "_insert_rows", return_value=2) as ins:
        result = etl._sync_per_date(
            "test_table", api_call, ["code", "trade_date"], row_mapper, days_back=2,
            clean=True,
        )

    assert result == {"status": "ok", "table": "test_table", "fetched": 4, "written": 4}
    assert calls == ["20260101", "20260102"]
    assert ins.call_count == 2
    fake_db.commit.assert_called_once()
    fake_db.close.assert_called_once()


def test_sync_per_date_skips_when_no_token():
    with mock.patch.object(etl, "_get_pro", return_value=None):
        result = etl._sync_per_date("t", lambda p, d: None, ["c"], lambda r, d: ())
    assert result == {"status": "skipped", "reason": "no Tushare token"}


def test_sync_per_date_skips_empty_df_and_no_commit():
    with mock.patch.object(etl, "_get_pro", return_value=object()), \
         mock.patch.object(etl, "_get_trade_dates", return_value=["20260101"]), \
         mock.patch.object(etl, "_get_etl_db", return_value=mock.MagicMock()) as db, \
         mock.patch.object(etl, "_rate_limit"), \
         mock.patch.object(etl, "_insert_rows") as ins:
        result = etl._sync_per_date(
            "t", lambda p, d: pd.DataFrame(), ["c"], lambda r, d: (), days_back=1,
            commit=False,
        )
    assert result["fetched"] == 0
    ins.assert_not_called()
    db.commit.assert_not_called()
