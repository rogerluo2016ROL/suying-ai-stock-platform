"""sync_global_index 东财兜底逻辑测试.

背景: Tushare index_global 的美股指数在北京 7:50 常未更新前夜收盘 (实测滞后),
导致 8:00 美股早报的全球市场段显示上一交易日数据。东财快照作兜底源。
"""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.sync import us_market


def _em_payload(items):
    return json.dumps({"data": {"diff": items}}).encode()


def _em_item(secid, code, close, pct, ts):
    mkt, _ = secid.split(".", 1)
    return {"f12": code, "f13": int(mkt), "f2": close, "f3": pct, "f124": ts}


# 2026-08-11 04:00:10 北京 = 2026-08-10 16:00:10 ET (美股 8/10 收盘后)
TS_AFTER_CLOSE_ET = 1786392010
# 2026-08-10 22:00:00 北京 = 2026-08-10 10:00:00 ET (美股盘中)
TS_IN_SESSION_ET = 1786370400


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch, payload: bytes):
    monkeypatch.setattr(us_market.urllib.request, "urlopen",
                        lambda req, timeout=0: _FakeResp(payload))


def test_spot_after_close_accepted(monkeypatch):
    """美股收盘后的快照 → 返回, trade_date 为美东当日."""
    _patch_urlopen(monkeypatch, _em_payload([
        _em_item("100.NDX", "NDX", 26605.36, -0.32, TS_AFTER_CLOSE_ET),
        _em_item("100.DJIA", "DJIA", 53975.98, -0.11, TS_AFTER_CLOSE_ET),
    ]))
    rows = us_market.fetch_global_index_spot_eastmoney()
    assert ("IXIC", "2026-08-10", 26605.36, -0.32) in rows
    assert ("DJI", "2026-08-10", 53975.98, -0.11) in rows


def test_spot_in_session_dropped(monkeypatch):
    """盘中快照 (未完结 session) → 丢弃, 不把盘中价写成收盘."""
    _patch_urlopen(monkeypatch, _em_payload([
        _em_item("100.NDX", "NDX", 26700.0, 0.5, TS_IN_SESSION_ET),
        _em_item("100.SPX", "SPX", 7760.0, 0.1, TS_AFTER_CLOSE_ET),
    ]))
    rows = us_market.fetch_global_index_spot_eastmoney()
    codes = [r[0] for r in rows]
    assert "IXIC" not in codes
    assert "SPX" in codes


def test_spot_http_error_returns_empty(monkeypatch):
    monkeypatch.setattr(us_market.urllib.request, "urlopen",
                        MagicMock(side_effect=OSError("boom")))
    assert us_market.fetch_global_index_spot_eastmoney() == []


def _run_sync(monkeypatch, tushare_dates, em_items):
    """跑 sync_global_index, 返回所有 _pg_write 调用写入的行 (合并)."""
    pro = MagicMock()

    def _index_global(ts_code, start_date, end_date):
        dates = tushare_dates.get(ts_code, [])
        if not dates:
            return pd.DataFrame()
        return pd.DataFrame({
            "trade_date": dates,
            "close": [100.0] * len(dates),
            "pct_chg": [1.0] * len(dates),
        })

    pro.index_global.side_effect = _index_global
    monkeypatch.setattr(us_market, "_pro", lambda: pro)
    monkeypatch.setattr("app.sync.rate_limiter.rate_limit", lambda: None)
    _patch_urlopen(monkeypatch, _em_payload(em_items))

    written = []
    monkeypatch.setattr("app.sync.pg_writer._pg_write",
                        lambda table, cols, keys, rows: written.extend(rows) or len(rows))
    us_market.sync_global_index()
    return written


def test_fallback_fills_stale_us_index(monkeypatch):
    """Tushare 只到 8/7, 东财有 8/10 → 补写 8/10."""
    stale = ["20260806", "20260807"]
    written = _run_sync(
        monkeypatch,
        tushare_dates={c: stale for c in us_market.GLOBAL_INDEX_CODES},
        em_items=[_em_item("100.NDX", "NDX", 26605.36, -0.32, TS_AFTER_CLOSE_ET)],
    )
    assert ("IXIC", "2026-08-10", 26605.36, -0.32) in written


def test_fallback_skipped_when_tushare_fresh(monkeypatch):
    """Tushare 已有 8/10 → 东财同日期快照不写 (官方值优先)."""
    fresh = ["20260807", "20260810"]
    written = _run_sync(
        monkeypatch,
        tushare_dates={c: fresh for c in us_market.GLOBAL_INDEX_CODES},
        em_items=[_em_item("100.NDX", "NDX", 26605.36, -0.32, TS_AFTER_CLOSE_ET)],
    )
    ixic_rows = [r for r in written if r[0] == "IXIC"]
    assert all(r[1] != "2026-08-10" or r[2] == 100.0 for r in ixic_rows)
    assert ("IXIC", "2026-08-10", 26605.36, -0.32) not in written


def test_fallback_not_applied_to_asia_codes(monkeypatch):
    """东财快照请求只含美股 secids — 亚洲指数始终只走 Tushare."""
    assert set(us_market._EM_GLOBAL_SECIDS) == {"IXIC", "DJI", "SPX"}
