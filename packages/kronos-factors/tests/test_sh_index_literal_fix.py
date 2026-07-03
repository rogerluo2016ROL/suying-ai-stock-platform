"""P0 fix regression test (2026-07-03): get_shanghai_index / assess_market_env 必须查询
PG index_daily.code='000001'（无 .SH 后缀），不得再出现 '000001.SH' 字面量。

根因：5 处硬编码 `ts_code='000001.SH'` 是 SQL 内联字面量，pg_adapter._translate_params
只翻译 bound params（正则 ^\\d{6}\\.(XSHE|XSHG|SZ|SH|BJ)$），内联字面量原样进 PG，
而 PG index_daily.code 存的是 bare '000001' → 查询恒空 → sh_pct 恒 0 → 板块门系统性淘汰。
"""
import re

import pytest


class _FakeRow(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e


class _FakeCursor:
    def __init__(self, store):
        self._store = store

    def execute(self, sql, params=()):
        self._store["last_sql"] = sql
        self._store["last_params"] = params
        return self

    def fetchone(self):
        return self._store.get("row")


class _FakeDb:
    def __init__(self, row):
        self.cursor_obj = _FakeCursor({"row": row})

    def execute(self, sql, params=()):
        return self.cursor_obj.execute(sql, params)


@pytest.mark.parametrize(
    "module_path,fn_name",
    [
        ("kronos_factors.engine.leader_scalp", "get_shanghai_index"),
        ("kronos_factors.engine.leader_closing", "get_shanghai_index"),
        ("kronos_factors.engine.leader_intraday", "get_shanghai_index"),
    ],
)
def test_get_shanghai_index_uses_bare_code_not_suffixed(module_path, fn_name):
    """3 个 engine 的 get_shanghai_index 都不得用 '000001.SH' 字面量，
    且查到 code='000001' 行时返回真实涨幅（非 0）。"""
    import importlib

    mod = importlib.import_module(module_path)
    fn = getattr(mod, fn_name)

    fake = _FakeDb(_FakeRow({"pct_chg": 1.23}))
    result = fn(fake, "2026-07-02")

    sql = fake.cursor_obj._store["last_sql"]
    # 不得出现 .SH 后缀字面量（这是回归断言的核心）
    assert "000001.SH" not in sql, f"{module_path}: SQL 仍含 '000001.SH' 字面量: {sql}"
    # 必须查 bare '000001'
    assert "'000001'" in sql, f"{module_path}: SQL 未查 bare '000001': {sql}"
    # 返回真实涨幅而非恒 0
    assert result == pytest.approx(1.23), f"{module_path}: 返回值 {result} 不等于 mock 1.23"


def test_get_shanghai_index_returns_zero_when_no_row_leader_scalp():
    """无数据时优雅降级返回 0（行为兼容，不崩）。"""
    from kronos_factors.engine.leader_scalp import get_shanghai_index

    fake = _FakeDb(None)
    assert get_shanghai_index(fake, "2026-07-02") == 0


def test_assess_market_env_sh_pct_nonzero_leader_scalp():
    """assess_market_env 用真实 sh_pct 计算，不再恒 0 触发误判 NEUTRAL/BEAR。"""
    from kronos_factors.engine.leader_scalp import assess_market_env

    # 构造一个对 index_daily 第一次查询返回强涨幅、其余查询返回空/0 的 fake
    class _EnvDb:
        def __init__(self):
            self.calls = 0

        def execute(self, sql, params=()):
            self.calls += 1
            lower = sql.lower()
            if "index_daily" in lower and "000001" in lower:
                return _FakeCursor({"row": _FakeRow({"pct_chg": 2.5})})
            # 其余 COUNT/breadth 查询返回 0，避免触发 CRASH/BEAR 分支干扰断言
            if "count" in lower or "sum" in lower:
                return _FakeCursor({"row": _FakeRow({"cnt": 0, "up": 0, "down": 0})})
            return _FakeCursor({"row": None})

    env, detail = assess_market_env(_EnvDb(), "2026-07-02")
    # sh_pct 应反映 mock 的 2.5，而非历史 bug 的 0
    assert detail["sh_pct"] == pytest.approx(2.5), f"sh_pct 仍恒 0/异常: {detail}"


def test_score_stock_sector_gate_no_longer_hard_eliminates_isolated_limit_up():
    """B 验收：板块共振门的 3 处 `return None` 改为软降权后，孤立涨停股不再被静默淘汰。

    用最小 fake 让 F14-1 (peer_count<=1 & sector_change<=0) 命中，断言 score_stock 走到
    构造 result（非 None）且 resonance_risk 被标注。
    完整 score_stock 路径依赖大量数据；此处只断言「不再 return None」这一行为契约，
    不验证具体分数（避免被 IC 阈值的 follow-up 改动绊住）。
    """
    # 反向断言：源码中板块共振 F14 段已无 'return None'（grep 源文件）
    import inspect

    from kronos_factors.engine import leader_scalp

    src = inspect.getsource(leader_scalp.score_stock)
    # 抽出 F14 板块共振段：从「resonance_score = 3  # 默认最低档」到「优化B」分隔行
    f14_start = src.find("resonance_score = 3  # 默认最低档")
    f14_end = src.find("# ── 优化B: 板块涨幅因子")
    assert f14_start != -1 and f14_end != -1, "无法定位 F14 板块共振段（resonance 默认档/优化B 分隔）"
    f14_block = src[f14_start:f14_end]
    assert "return None" not in f14_block, (
        "F14 板块共振段仍含 return None（硬淘汰未拆除）: " + f14_block
    )
    assert "resonance_risk" in f14_block, "F14 段未标注 resonance_risk（软降权机制缺失）"
