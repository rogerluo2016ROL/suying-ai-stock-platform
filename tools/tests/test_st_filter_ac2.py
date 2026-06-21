"""AC-2 幸存者偏差修复 — st_history JOIN 后置过滤单元测试.

铁律: 不动 strategy engine, 仅 backtest 工具层 (tools/) 加 T 日戴帽过滤.
验证:
  - get_st_codes_on 返回 T 日处于 [start_date, end_date) 区间的 code
  - run_backtest_day(st_filter=True) 剔除 ST, st_filter=False 保留全部
  - 边界: end_date IS NULL (仍戴帽), end_date <= trade_date (已摘帽不应剔除)
"""
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeRow(dict):
    """兼容 dict 风格行 (PG 适配后)."""


def _make_db(st_rows):
    """构造 mock db: execute(...).fetchall() 返回 st_rows."""
    db = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = [FakeRow(r) for r in st_rows]
    db.execute.return_value = cur
    return db


def test_get_st_codes_on_basic():
    """st_history 含 2 条区间, T 日处于活跃区间, 返回 2 个 code."""
    from backtest_bi_trend import get_st_codes_on
    db = _make_db([
        {"code": "000518"},
        {"code": "600360"},
    ])
    codes = get_st_codes_on(db, "2025-06-20")
    assert codes == {"000518", "600360"}
    # SQL 应同时带 start_date<=? AND (end_date IS NULL OR end_date>?)
    sql = db.execute.call_args[0][0]
    assert "start_date <= ?" in sql
    assert "end_date IS NULL OR end_date > ?" in sql


def test_get_st_codes_on_empty():
    """T 日无戴帽股 (rows 空), 返回空集合."""
    from backtest_bi_trend import get_st_codes_on
    db = _make_db([])
    codes = get_st_codes_on(db, "2018-01-01")
    assert codes == set()


def test_run_backtest_day_st_filter_on_removes_st():
    """st_filter=True: top_picks 内 ST 股被剔除, n_st_removed 计数."""
    import backtest_bi_trend as mod

    fake_top = [
        {"code": "000001", "grade": "A"},
        {"code": "000518", "grade": "B"},  # ST 当日
        {"code": "600360", "grade": "C"},  # *ST 当日
        {"code": "603001", "grade": "S"},
    ]

    # mock run_bi_screening
    orig_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    fake_module = MagicMock()
    fake_module.run_bi_screening = MagicMock(
        return_value=(fake_top, [{"code": "x"}] * 100, {"breadth": 30})
    )

    # mock get_st_codes_on 直接覆盖
    original_get = mod.get_st_codes_on
    mod.get_st_codes_on = lambda db, td: {"000518", "600360"}

    # mock the engine import inside run_backtest_day
    sys.modules["kronos_factors.engine.bi_trend_launch"] = fake_module
    try:
        db = MagicMock()
        r = mod.run_backtest_day(db, "2025-06-20", top_n=10, st_filter=True)
        codes = {p["code"] for p in r["top_picks"]}
        assert codes == {"000001", "603001"}
        assert r["n_st_removed"] == 2
    finally:
        mod.get_st_codes_on = original_get
        del sys.modules["kronos_factors.engine.bi_trend_launch"]


def test_run_backtest_day_st_filter_off_keeps_all():
    """st_filter=False: 不过滤, n_st_removed=0, top 全保留 (单日口径回归用)."""
    import backtest_bi_trend as mod

    fake_top = [
        {"code": "000001"}, {"code": "000518"}, {"code": "600360"}, {"code": "603001"}
    ]
    fake_module = MagicMock()
    fake_module.run_bi_screening = MagicMock(
        return_value=(fake_top, [], {})
    )
    sys.modules["kronos_factors.engine.bi_trend_launch"] = fake_module
    try:
        r = mod.run_backtest_day(MagicMock(), "2025-06-20", top_n=10, st_filter=False)
        assert len(r["top_picks"]) == 4
        assert r["n_st_removed"] == 0
    finally:
        del sys.modules["kronos_factors.engine.bi_trend_launch"]


def test_get_st_codes_on_boundary_already_removed():
    """边界: end_date < trade_date (已摘帽) 的股不应被列入.

    SQL 已用 end_date > ? 严格大于过滤 (摘帽日当天算非 ST), DB 不会返回该行.
    这里只测 mock 的 contract.
    """
    from backtest_bi_trend import get_st_codes_on
    # DB 已按 SQL where 过滤好, 返回空
    db = _make_db([])
    codes = get_st_codes_on(db, "2025-12-31")
    assert codes == set()
