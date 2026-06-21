"""T-008 复权修复 Unit 测试.

AC: 除权日 return 不再因 close 跳变失真.

策略:
1. test_adjusted_kline_ex_date — 真实 PG 数据, 000060 在 2025-06-26 除权日,
   后复权 close 与原始 close 不同 (adj_applied=True), 且后复权收益与数学真值一致.
2. test_get_next_day_return_adjusted_vs_raw — 同一除权日单笔,
   adjusted return 与 raw return 显著不同 (复权消除了除权跳变失真).
3. test_adjusted_kline_no_adj_factor_fallback — adj_factor 缺失时退回原始价 (adj_applied=False).
4. test_get_next_day_return_no_adj_flag — adjusted=False 退回旧行为 (raw).

PG 依赖: 前两项需 docker-postgres-1 运行 + adj_factor 表有数据; 不可用时 skip.
"""
import os
import sys
import pytest

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

_TOOLS = os.path.join(_PROJ, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"


def _pg_available():
    try:
        from kronos_factors.pg_adapter import create_pg_adapter
        adapter = create_pg_adapter(PG_URL)
        if adapter is None:
            return False
        # ping
        adapter.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def db():
    if not _pg_available():
        pytest.skip("docker-postgres-1 未运行或 adj_factor 表不可用")
    os.environ["KRONOS_PG_URL"] = PG_URL
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(PG_URL)
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def test_adjusted_kline_ex_date(db):
    """000060 在 2025-06-26 除权日: 后复权 close != 原始 close, adj_applied=True."""
    from backtest_bi_trend import get_adjusted_kline
    # 6/25 除权前 (f=40.6661)
    adj_25 = get_adjusted_kline(db, "000060", "2025-06-25")
    raw_25 = db.execute(
        "SELECT close FROM daily_kline WHERE code=? AND trade_date=?",
        ("000060", "2025-06-25")
    ).fetchone()["close"]
    assert adj_25 is not None
    assert adj_25["adj_applied"] is True
    # 后复权 close 应大于原始 close (历史 factor < latest, ratio>1)
    assert adj_25["close"] > float(raw_25)
    # 复权公式验证: adj = raw * f_latest / f_t
    f = db.execute(
        "SELECT a.adj_factor AS f_t, (SELECT adj_factor FROM adj_factor WHERE code=? "
        "ORDER BY trade_date DESC LIMIT 1) AS f_latest FROM adj_factor a "
        "WHERE a.code=? AND a.trade_date=?",
        ("000060", "000060", "2025-06-25")
    ).fetchone()
    expected = float(raw_25) * float(f["f_latest"]) / float(f["f_t"])
    assert adj_25["close"] == pytest.approx(expected, rel=1e-6)


def test_get_next_day_return_adjusted_vs_raw(db):
    """000060 单笔跨除权日 (6/25 买 6/26 卖): adjusted 收益消除除权跳变失真, 与 raw 显著不同."""
    from backtest_bi_trend import get_next_day_return
    adj_ret, _ = get_next_day_return(db, "000060", "2025-06-25", adjusted=True)
    raw_ret, _ = get_next_day_return(db, "000060", "2025-06-25", adjusted=False)
    assert adj_ret is not None
    assert raw_ret is not None
    # 数学真值: (close_T+1 * f_T) / (close_T * f_T+1) - 1
    rows = db.execute(
        "SELECT a.trade_date, a.adj_factor, k.close FROM adj_factor a "
        "JOIN daily_kline k USING(code, trade_date) "
        "WHERE a.code='000060' AND a.trade_date IN ('2025-06-25','2025-06-26') "
        "ORDER BY a.trade_date"
    ).fetchall()
    e, x = rows[0], rows[1]
    truth = (float(x["close"]) * float(e["adj_factor"])
             / (float(e["close"]) * float(x["adj_factor"])) - 1) * 100
    assert adj_ret == pytest.approx(truth, abs=1e-4)
    # 复权后与原始必须有可观测差异 (除权跳变失真被修复), 差异应 > 0.1pp
    assert abs(adj_ret - raw_ret) > 0.1, (
        f"复权修复未生效: adj={adj_ret} raw={raw_ret} 差异过小"
    )


def test_adjusted_kline_no_adj_factor_fallback():
    """adj_factor 表/行缺失时, get_adjusted_kline 应退回原始价 (adj_applied=False), 不抛异常."""
    from backtest_bi_trend import get_adjusted_kline

    class _FakeRow(dict):
        def __getattr__(self, k):
            return self.get(k)

    class _FakeCursor:
        def __init__(self, row):
            self._row = row
        def fetchone(self):
            return self._row
        def fetchall(self):
            return []

    class _FakeDB:
        def execute(self, sql, params=()):
            # 模拟 daily_kline 有 close 但 adj_factor JOIN 为 NULL
            return _FakeCursor(_FakeRow({
                "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2,
                "f_t": None, "f_latest": None,
            }))

    out = get_adjusted_kline(_FakeDB(), "999999", "2099-01-01")
    assert out is not None
    assert out["close"] == 10.2  # 原始价
    assert out["adj_applied"] is False  # 未复权 (降级)


def test_get_next_day_return_no_adj_flag(db):
    """adjusted=False 退回旧行为: raw return == direct close ratio (无复权)."""
    from backtest_bi_trend import get_next_day_return
    raw_ret, _ = get_next_day_return(db, "000060", "2025-06-25", adjusted=False)
    rows = db.execute(
        "SELECT close FROM daily_kline WHERE code='000060' "
        "AND trade_date IN ('2025-06-25','2025-06-26') ORDER BY trade_date"
    ).fetchall()
    direct = (float(rows[1]["close"]) / float(rows[0]["close"]) - 1) * 100
    assert raw_ret == pytest.approx(direct, abs=1e-6)
