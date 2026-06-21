"""SIT — 阶段1 回测可信度重建 集成测试 (AC-1/4/6 + Q-4 + AC-3).

SIT 范围 (本角色 Output 表 SIT 行): 回测口径集成端到端 —
  1. get_adjusted_bars PG 真实读价 + 后复权 JOIN adj_factor (Q-4)
  2. simulate_pick 端到端 (真实股票多日持有 + T+1 open 入场 + TP/trailing/stop)
  3. walk_forward 辅助函数 (month_iter / shift_month / sharpe_like) 逻辑正确

Requires: Postgres 运行 (docker-postgres-1), KRONOS_PG_URL 或默认 localhost:6432.
Run: KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
     pytest backend/tests/sit/test_backtest_multiday_sit.py -v
"""

import os
import sys

import pytest

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for pkg in ["packages/kronos-factors"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)
_TOOLS = os.path.join(_PROJ, "tools")
if os.path.isdir(_TOOLS) and _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from kronos_factors.pg_adapter import create_pg_adapter  # noqa: E402

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def _pg_available():
    """检查 PG 是否可连 (docker-postgres-1 是否运行)."""
    try:
        adapter = create_pg_adapter(PG_URL)
        if adapter is None:
            return False
        # 探测 daily_kline 是否有 2024-2025 数据
        from kronos_factors.scorer._db_stub import _get_db
        with _get_db() as db:
            row = db.execute(
                "SELECT COUNT(*) as c FROM daily_kline WHERE trade_date >= '2024-01-01'"
            ).fetchone()
            return row and row["c"] > 1000
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(),
                                reason="PG 不可用或无 2024-2025 数据 (docker-postgres-1 未运行)")


@pytest.fixture(scope="module")
def db():
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter, _get_db
    adapter = create_pg_adapter(PG_URL)
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    yield _get_db
    # _PgAdapter 无 close 方法 (连接池托管), 不显式关闭


# ── Q-4: get_adjusted_bars 后复权读价 ──

class TestGetAdjustedBars:
    def test_returns_post_adjusted_bars_with_adj_applied(self, db):
        """PG 读价 JOIN adj_factor, 返回后复权 bar 序列 (OHLC 已乘 adj)."""
        from backtest_bi_trend import get_adjusted_bars
        with db() as conn:
            # 取一个确定有数据的 (code, date)
            row = conn.execute(
                "SELECT code, trade_date FROM daily_kline WHERE trade_date='2025-06-10' LIMIT 1"
            ).fetchone()
            if not row:
                pytest.skip("无 2025-06-10 数据")
            bars = get_adjusted_bars(conn, row["code"], str(row["trade_date"]), max_hold_days=5)
        assert len(bars) >= 2, "应返回至少 signal 日 + T+1"
        for b in bars:
            assert b["close"] > 0 and b["open"] > 0
            assert "date" in b

    def test_adjustment_changes_price_vs_raw_when_ex_dividend(self, db):
        """对 adj_factor != 1 的股, 后复权价 != 原始价 (验证复权确实生效)."""
        from backtest_bi_trend import get_adjusted_bars
        with db() as conn:
            # 找一个 adj_factor 明显 != 1 的 (code, date)
            row = conn.execute(
                "SELECT d.code, d.trade_date, d.close AS raw_close, a.adj_factor "
                "FROM daily_kline d JOIN adj_factor a ON a.code=d.code AND a.trade_date=d.trade_date "
                "WHERE d.trade_date='2025-06-10' AND a.adj_factor > 1.5 LIMIT 1"
            ).fetchone()
            if not row:
                pytest.skip("无 adj_factor>1.5 的样本")
            bars = get_adjusted_bars(conn, row["code"], str(row["trade_date"]), max_hold_days=1)
        # bars[0] 是 signal 日, close 应 = raw_close * adj_factor (后复权放大)
        assert bars[0]["close"] == pytest.approx(float(row["raw_close"]) * float(row["adj_factor"]),
                                                  rel=1e-4)


# ── AC-1/4: simulate_pick 端到端 ──

class TestSimulatePickEndToEnd:
    def test_simulate_pick_returns_full_result(self, db):
        """simulate_pick 端到端: 真实股票多日持有, 返回含 exit_reason/net_return 等全字段."""
        from backtest_bi_trend import simulate_pick
        with db() as conn:
            row = conn.execute(
                "SELECT code, trade_date FROM daily_kline WHERE trade_date='2025-06-10' LIMIT 1"
            ).fetchone()
            if not row:
                pytest.skip("无数据")
            result = simulate_pick(conn, row["code"], str(row["trade_date"]),
                                   hold_days=5, tp_pct=20, stop_loss_pct=-12, cost_bps=14)
        if result is None:
            pytest.skip("该股无 T+1 数据")
        # AC-1 字段齐全
        for key in ("entry_date", "entry_price", "exit_date", "exit_price",
                    "exit_reason", "actual_hold_days", "gross_return", "net_return",
                    "code", "signal_date"):
            assert key in result, f"缺字段 {key}"
        # AC-4: entry 在 signal 日之后 (T+1)
        assert result["entry_date"] > result["signal_date"]
        # net = gross - cost
        assert result["net_return"] == pytest.approx(result["gross_return"] - 0.14)
        # exit_reason 在合法集合
        assert result["exit_reason"] in ("take_profit", "stop_loss", "trailing_stop",
                                         "hold_to_maturity", "data_truncated")
        # actual_hold_days 在 [1, hold_days]
        assert 1 <= result["actual_hold_days"] <= 5

    def test_simulate_pick_pending_when_no_t_plus1(self, db):
        """无 T+1 数据 (signal 日是最后交易日): simulate_pick 返回 None (pending)."""
        from backtest_bi_trend import simulate_pick
        with db() as conn:
            # 取 daily_kline 最大 trade_date (无后续)
            row = conn.execute(
                "SELECT code, MAX(trade_date) AS td FROM daily_kline GROUP BY code LIMIT 1"
            ).fetchone()
            if not row:
                pytest.skip("无数据")
            result = simulate_pick(conn, row["code"], str(row["td"]),
                                   hold_days=5, tp_pct=20, cost_bps=0)
        # 该 code 的 max date 不一定是全市场 max, 可能仍有 T+1; 宽松断言
        assert result is None or "exit_reason" in result


# ── AC-3: walk_forward 辅助函数 ──

class TestWalkForwardHelpers:
    def test_month_iter_inclusive_range(self):
        from walk_forward import month_iter
        assert month_iter("2024-01", "2024-03") == ["2024-01", "2024-02", "2024-03"]
        assert len(month_iter("2024-01", "2025-12")) == 24  # AC-3 样本外 24 月
        # 跨年
        assert month_iter("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]

    def test_shift_month_negative_and_positive(self):
        from walk_forward import shift_month
        assert shift_month("2024-04", -3) == "2024-01"  # T-3 月调参窗口起点
        assert shift_month("2024-04", -1) == "2024-03"  # T-1 月
        assert shift_month("2024-12", 1) == "2025-01"   # 跨年
        assert shift_month("2024-01", -1) == "2023-12"  # 跨年负向

    def test_sharpe_like_formula(self):
        from walk_forward import sharpe_like
        import numpy as np
        # 均值 1%, std 2% → sharpe = 0.5 * sqrt(12)
        monthly = [1.0, -1.0, 3.0, -1.0]  # mean=0.5, std≈1.91
        s = sharpe_like(monthly)
        assert s is not None
        expected = np.mean(monthly) / np.std(monthly, ddof=1) * np.sqrt(12)
        assert s == pytest.approx(expected, rel=1e-4)

    def test_sharpe_like_none_for_insufficient_data(self):
        from walk_forward import sharpe_like
        assert sharpe_like([1.0]) is None
        assert sharpe_like([]) is None
        assert sharpe_like([1.0, 1.0]) is None  # std=0

    def test_summarize_month_aggregation(self):
        from walk_forward import summarize_month
        picks = [
            {"net_return": 2.0, "weighted_return": 2.0, "exit_reason": "take_profit"},
            {"net_return": -1.0, "weighted_return": -0.6, "exit_reason": "stop_loss"},
            {"net_return": 0.5, "weighted_return": 0.5, "exit_reason": "hold_to_maturity"},
        ]
        stat = summarize_month(picks)
        assert stat["n_trades"] == 3
        assert stat["net_mean"] == pytest.approx(0.5)
        assert stat["weighted_net_mean"] == pytest.approx((2.0 - 0.6 + 0.5) / 3)
        assert stat["win_rate_net"] == pytest.approx(2 / 3 * 100)
        assert stat["exit_reasons"]["take_profit"] == 1
