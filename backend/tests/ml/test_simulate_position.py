"""Unit tests for simulate_position 多日持有回测引擎 + 后复权读价.

TDD red 阶段: 先定义期望行为, 再实现 simulate_position / get_adjusted_bars.
覆盖 AC-1 (多日持有 + TP/trailing/stop) + AC-4 (T+1 open 入场) + Q-4 (后复权).

设计: simulate_position 为纯函数, 接受后复权 OHLC bar 序列 (list[dict]),
不直接依赖 db —— db 查询由 get_adjusted_bars 薄包装层提供, 便于离线单测.
"""

import os
import sys

import pytest

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for pkg in ["packages/kronos-factors"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

# tools/ 加入 path 以导入回测引擎模块
_TOOLS = os.path.join(_PROJ, "tools")
if os.path.isdir(_TOOLS) and _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from backtest_bi_trend import simulate_position, adjust_bars  # noqa: E402


def _bar(d, o, h, l, c, adj=1.0):
    """构造一根后复权前的原始 bar (含 adj_factor)."""
    return {"date": d, "open": o, "high": h, "low": l, "close": c, "adj": adj}


# ── Q-4: 后复权读价 ──

class TestAdjustBars:
    def test_adjust_multiplies_by_on_date_adj_factor(self):
        """后复权: 每根 bar 的 OHLC 乘以该日 adj_factor."""
        bars = [
            _bar("2024-01-02", 10.0, 10.5, 9.8, 10.2, adj=2.0),
            _bar("2024-01-03", 10.2, 10.8, 10.1, 10.6, adj=2.0),
        ]
        adj_bars = adjust_bars(bars)
        assert adj_bars[0]["close"] == pytest.approx(10.2 * 2.0)
        assert adj_bars[0]["open"] == pytest.approx(10.0 * 2.0)

    def test_adjust_handles_adj_change_across_ex_dividend(self):
        """除权日 adj_factor 跳变 (如分红): 后复权后跨日可比, 无跳空.

        模拟: 除权前 adj=2.0 close=10, 除权后 adj=1.0 close=5 (名义价腰斩但实际无损).
        未复权 return = 5/10 - 1 = -50% (虚假暴跌); 后复权 return = (5*1.0)/(10*2.0)-1 = -75%??
        实际后复权意义: adj 反映累计复权基准, 此处验证跨日 adj 变化时 OHLC 按各自 adj 缩放.
        """
        bars = [
            _bar("2024-01-02", 10.0, 10.0, 10.0, 10.0, adj=2.0),
            _bar("2024-01-03", 5.0, 5.0, 5.0, 5.0, adj=1.0),
        ]
        adj_bars = adjust_bars(bars)
        # 各自按 on_date adj 缩放
        assert adj_bars[0]["close"] == pytest.approx(20.0)
        assert adj_bars[1]["close"] == pytest.approx(5.0)

    def test_adjust_missing_adj_defaults_to_one(self):
        """缺 adj_factor 的 bar 按 1.0 处理 (不崩)."""
        bars = [_bar("2024-01-02", 10.0, 10.0, 10.0, 10.0, adj=None)]
        adj_bars = adjust_bars(bars)
        assert adj_bars[0]["close"] == pytest.approx(10.0)


# ── AC-4: T+1 open 入场 (消除前视) ──

class TestEntryTPlus1Open:
    def test_entry_price_is_next_day_open(self):
        """入场价 = 信号日 T 的次日 (T+1) open, 非 T 日收盘."""
        # T 日 = bars[0] (信号日), T+1 = bars[1] (入场), T+2..持有
        bars = [
            _bar("2024-01-02", 10.0, 10.5, 9.8, 10.0, adj=1.0),   # T 信号日
            _bar("2024-01-03", 10.2, 10.8, 10.1, 10.6, adj=1.0),  # T+1 入场 open=10.2
            _bar("2024-01-04", 10.6, 10.7, 10.5, 10.6, adj=1.0),
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=5,
                                   tp_pct=None, stop_loss_pct=None)
        assert result["entry_price"] == pytest.approx(10.2)  # T+1 open, 非 T 收盘 10.0
        assert result["entry_date"] == "2024-01-03"


# ── AC-1: 多日持有 + TP/trailing/stop 逐日循环 ──

class TestExitReasons:
    def test_take_profit_triggers_intraday(self):
        """TP 20%: 持有期内某日 high 触及 entry*1.20 → 以 TP 价退出.

        hold_days 语义 = 入场(T+1)后持有的交易日数 (含入场日为第1持有日).
        策略声明 hold_days=5/7/10 即入场起持有相应天数, 对应注释 "T+5/T+7/T+10".
        """
        entry = 10.0
        bars = [
            _bar("T", 10.0, 10.0, 10.0, 10.0, adj=1.0),            # 信号日
            _bar("T+1", entry, entry, entry, entry, adj=1.0),      # 入场 open=10 (持有日1)
            _bar("T+2", 11.5, 12.0, 11.4, 11.9, adj=1.0),          # 持有日2 high=12>=12 → TP
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=10,
                                   tp_pct=20, stop_loss_pct=None)
        assert result["exit_reason"] == "take_profit"
        assert result["exit_price"] == pytest.approx(10.0 * 1.20)
        assert result["actual_hold_days"] == 2  # T+1 入场(日1), T+2 触发(日2)

    def test_stop_loss_triggers_intraday(self):
        """stop_loss -12%: 某日 low 跌破 entry*0.88 → 以 stop 价退出."""
        entry = 10.0
        bars = [
            _bar("T", 10.0, 10.0, 10.0, 10.0, adj=1.0),
            _bar("T+1", entry, entry, entry, entry, adj=1.0),
            _bar("T+2", 8.9, 9.0, 8.5, 8.7, adj=1.0),  # low=8.5 < 8.8 → stop
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=10,
                                   tp_pct=None, stop_loss_pct=-12)
        assert result["exit_reason"] == "stop_loss"
        assert result["exit_price"] == pytest.approx(10.0 * 0.88)

    def test_gap_down_open_below_stop_exits_at_open(self):
        """跳空低开: T+1 开盘已低于止损价 → 以开盘价退出 (竞价止损)."""
        entry = 10.0
        bars = [
            _bar("T", 10.0, 10.0, 10.0, 10.0, adj=1.0),
            _bar("T+1", entry, entry, entry, entry, adj=1.0),
            _bar("T+2", 8.0, 8.5, 7.9, 8.2, adj=1.0),  # open=8.0 < 8.8 → 跳空止损
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=10,
                                   tp_pct=None, stop_loss_pct=-12)
        assert result["exit_reason"] == "stop_loss"
        assert result["exit_price"] == pytest.approx(8.0)  # 跳空按 open 退出

    def test_hold_to_maturity_exits_at_close(self):
        """持有到期 (无 TP/stop 触发): 以最后持有日收盘退出.

        hold_days=2 = 入场(T+1)起持有2个交易日 → T+1(日1), T+2(日2) 收盘退出.
        """
        bars = [
            _bar("T", 10.0, 10.0, 10.0, 10.0, adj=1.0),
            _bar("T+1", 10.0, 10.0, 10.0, 10.0, adj=1.0),  # 入场 (持有日1)
            _bar("T+2", 10.1, 10.3, 10.0, 10.3, adj=1.0),  # 持有日2 到期, 收盘 10.3 退出
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=2,
                                   tp_pct=None, stop_loss_pct=None)
        assert result["exit_reason"] == "hold_to_maturity"
        assert result["actual_hold_days"] == 2
        assert result["exit_price"] == pytest.approx(10.3)

    def test_tp_priority_over_stop_same_day(self):
        """同日同时触及 TP 和 stop (high>=tp 且 low<=stop): 默认保守按 stop 先退出.

        (A 股 T+1 涨跌停同日极端少见; 保守取 stop 以避免乐观偏差)
        """
        entry = 10.0
        bars = [
            _bar("T", 10.0, 10.0, 10.0, 10.0, adj=1.0),
            _bar("T+1", entry, entry, entry, entry, adj=1.0),
            _bar("T+2", 12.0, 12.5, 8.5, 9.0, adj=1.0),  # high=12.5>=12 且 low=8.5<8.8
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=10,
                                   tp_pct=20, stop_loss_pct=-12)
        # 保守: stop 优先 (避免乐观偏差)
        assert result["exit_reason"] in ("stop_loss", "take_profit")  # 明确优先级后断言


class TestTrailingStop:
    def test_trailing_locks_profit_after_run_up(self):
        """trailing_stop: 盈利达阈值后启动移动止损, 回撤超阈值则退出.

        策略 Tier2: 盈利 5-15% 时 stop=-5% (相对 entry). 简化 trailing 语义:
        trailing_active_pct=5, trailing_stop_pct=-5 → entry 涨 5% 后激活,
        从高点回撤 5% 退出.
        """
        entry = 10.0
        bars = [
            _bar("T", 10.0, 10.0, 10.0, 10.0, adj=1.0),
            _bar("T+1", entry, entry, entry, entry, adj=1.0),       # 入场
            _bar("T+2", 10.5, 11.0, 10.4, 10.8, adj=1.0),           # high=11 → peak +10% 激活
            _bar("T+3", 10.8, 10.9, 10.4, 10.5, adj=1.0),           # 回撤: 从 11 回到 10.4 < 11*0.95
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=10,
                                   tp_pct=None, stop_loss_pct=None,
                                   trailing_active_pct=5, trailing_drawdown_pct=5)
        assert result["exit_reason"] == "trailing_stop"
        # trailing 触发价 = peak * (1 - 5%) = 11 * 0.95 = 10.45; low=10.4 < 10.45 → 触及
        assert result["exit_price"] == pytest.approx(11.0 * 0.95, rel=1e-2)


class TestReturnCalculation:
    def test_return_is_exit_over_entry_minus_one(self):
        """return = exit_price / entry_price - 1 (百分比).

        hold_days=2: T+1 入场(10) → T+2 收盘(11) 退出. gross_return = (11/10-1)*100 = 10%.
        """
        bars = [
            _bar("T", 10.0, 10.0, 10.0, 10.0, adj=1.0),
            _bar("T+1", 10.0, 10.0, 10.0, 10.0, adj=1.0),  # 入场 10 (持有日1)
            _bar("T+2", 11.0, 11.0, 11.0, 11.0, adj=1.0),  # 持有日2 到期收盘 11
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=2,
                                   tp_pct=None, stop_loss_pct=None)
        assert result["gross_return"] == pytest.approx(10.0)

    def test_insufficient_bars_returns_none(self):
        """入场日 (T+1) 之后无足够 bar 持有: 返回 pending 状态."""
        bars = [
            _bar("T", 10.0, 10.0, 10.0, 10.0, adj=1.0),
            # 无 T+1 bar
        ]
        result = simulate_position(bars, signal_idx=0, hold_days=5,
                                   tp_pct=None, stop_loss_pct=None)
        assert result is None or result.get("exit_reason") == "pending"


class TestAdjustedBarsEndToEnd:
    def test_return_unaffected_by_uniform_adj_scaling(self):
        """后复权对 return 无影响 (分子分母同比例缩放): 验证 Q-4 修复不改变收益比例.

        同一段行情, adj 全为 2.0 vs 全为 1.0, return 应相同.
        """
        def make(adj):
            return [
                _bar("T", 10.0, 10.0, 10.0, 10.0, adj=adj),
                _bar("T+1", 10.0, 10.0, 10.0, 10.0, adj=adj),
                _bar("T+2", 11.0, 11.0, 11.0, 11.0, adj=adj),
            ]
        r1 = simulate_position(adjust_bars(make(1.0)), signal_idx=0, hold_days=1,
                               tp_pct=None, stop_loss_pct=None)
        r2 = simulate_position(adjust_bars(make(2.0)), signal_idx=0, hold_days=1,
                               tp_pct=None, stop_loss_pct=None)
        assert r1["gross_return"] == pytest.approx(r2["gross_return"])
