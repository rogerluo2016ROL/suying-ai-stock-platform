"""阶段三B 单测:版本治理(版本保留/晋升门槛/版本解析)与标定调权逻辑。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


register = _load("register_supply_chain_expectation_gap_model")
promote = _load("promote_supply_chain_model")
calibrate = _load("calibrate_supply_chain_scores")


class _ScriptedCursor:
    """按预设队列依次返回查询结果的假 cursor。"""

    def __init__(self, results: list):
        self._results = list(results)
        self.queries: list[str] = []

    def execute(self, query, params=None):
        self.queries.append(query)

    def fetchone(self):
        return self._results.pop(0) if self._results else None

    def fetchall(self):
        result = self._results.pop(0) if self._results else []
        return result


# ---------- 版本保留 ----------

def test_next_version_tag_first_version_uses_base_tag() -> None:
    assert register.next_version_tag(0) == "v1.0"


def test_next_version_tag_appends_sequence_suffix() -> None:
    assert register.next_version_tag(1) == "v1.0-r2"
    assert register.next_version_tag(4) == "v1.0-r5"


def test_resolve_active_version_prefers_production() -> None:
    cur = _ScriptedCursor([
        {"id": 9, "model_name": register.MODEL_KEY, "version_tag": "v1.0-r2", "stage": "production", "is_current": True},
    ])
    row, fell_back = register.resolve_active_version(cur)
    assert row["version_tag"] == "v1.0-r2"
    assert fell_back is False
    assert len(cur.queries) == 1  # 命中 production 后不再查 is_current


def test_resolve_active_version_falls_back_to_current_staging() -> None:
    cur = _ScriptedCursor([
        None,  # 无 production
        {"id": 7, "model_name": register.MODEL_KEY, "version_tag": "v1.0", "stage": "staging", "is_current": True},
    ])
    row, fell_back = register.resolve_active_version(cur)
    assert row["version_tag"] == "v1.0"
    assert fell_back is True


def test_resolve_active_version_none_when_empty() -> None:
    cur = _ScriptedCursor([None, None])
    row, fell_back = register.resolve_active_version(cur)
    assert row is None
    assert fell_back is True


# ---------- 晋升门槛 ----------

_THRESHOLDS = dict(promote.DEFAULT_THRESHOLDS)
_GOOD_VERSION = {"snapshot_count": 25, "win_rate": 55.0, "mean_return": 1.2}
_GOOD_BACKTEST = {"conclusion": None, "by_hold_days": {}}


def test_gates_pass_when_all_criteria_met() -> None:
    verdict = promote.evaluate_promotion_gates(_GOOD_VERSION, _GOOD_BACKTEST, _THRESHOLDS)
    assert verdict["ok"] is True
    assert all(item["ok"] for item in verdict["checks"].values())


def test_gates_reject_low_snapshot_count() -> None:
    verdict = promote.evaluate_promotion_gates({**_GOOD_VERSION, "snapshot_count": 5}, _GOOD_BACKTEST, _THRESHOLDS)
    assert verdict["ok"] is False
    assert verdict["checks"]["snapshot_count"]["ok"] is False
    assert verdict["checks"]["win_rate"]["ok"] is True


def test_gates_reject_null_win_rate() -> None:
    verdict = promote.evaluate_promotion_gates({**_GOOD_VERSION, "win_rate": None}, _GOOD_BACKTEST, _THRESHOLDS)
    assert verdict["ok"] is False
    assert verdict["checks"]["win_rate"]["ok"] is False


def test_gates_reject_zero_mean_return() -> None:
    # mean_return 必须严格 > 0,等于 0 不达标
    verdict = promote.evaluate_promotion_gates({**_GOOD_VERSION, "mean_return": 0.0}, _GOOD_BACKTEST, _THRESHOLDS)
    assert verdict["ok"] is False
    assert verdict["checks"]["mean_return"]["ok"] is False


def test_gates_reject_no_qualifying_candidates_conclusion() -> None:
    verdict = promote.evaluate_promotion_gates(
        _GOOD_VERSION, {"conclusion": "no_qualifying_candidates"}, _THRESHOLDS,
    )
    assert verdict["ok"] is False
    assert verdict["checks"]["backtest_conclusion"]["ok"] is False


def test_gates_reject_missing_backtest() -> None:
    verdict = promote.evaluate_promotion_gates(_GOOD_VERSION, None, _THRESHOLDS)
    assert verdict["ok"] is False
    assert verdict["checks"]["backtest_conclusion"]["ok"] is False


def test_gates_reject_missing_version_row() -> None:
    verdict = promote.evaluate_promotion_gates(None, _GOOD_BACKTEST, _THRESHOLDS)
    assert verdict["ok"] is False


def test_gates_thresholds_are_configurable() -> None:
    relaxed = {"min_snapshots": 0, "min_win_rate": 10.0, "min_mean_return": -5.0}
    verdict = promote.evaluate_promotion_gates(
        {"snapshot_count": 2, "win_rate": 12.0, "mean_return": -1.0},
        _GOOD_BACKTEST,
        relaxed,
    )
    assert verdict["ok"] is True


# ---------- 标定调权逻辑 ----------

def test_suggest_weights_no_change_when_no_receiver() -> None:
    suggestion = calibrate.suggest_weights(
        {"growth": 0.24, "profit": 0.18, "moat": 0.22, "stage": 0.16, "evidence": 0.14, "prosperity": 0.06},
        {"growth_score": -0.02, "profit_score": -0.01, "moat_score": None, "stage_score": None,
         "evidence_score": None, "prosperity_score": None},
        {"growth_score": -0.01, "profit_score": -0.02, "moat_score": None, "stage_score": None,
         "evidence_score": None, "prosperity_score": None},
    )
    assert suggestion["changed"] is False
    assert suggestion["weights"]["growth"] == 0.24
    assert set(suggestion["insufficient"]) == {"moat", "stage", "evidence", "prosperity"}


def test_suggest_weights_redistributes_from_dual_negative_to_dual_positive() -> None:
    suggestion = calibrate.suggest_weights(
        {"growth": 0.24, "profit": 0.18, "moat": 0.22, "stage": 0.16, "evidence": 0.14, "prosperity": 0.06},
        {"growth_score": -0.05, "profit_score": 0.03, "moat_score": 0.06, "stage_score": -0.02,
         "evidence_score": 0.04, "prosperity_score": 0.01},
        {"growth_score": -0.04, "profit_score": 0.02, "moat_score": 0.05, "stage_score": -0.01,
         "evidence_score": 0.03, "prosperity_score": 0.02},
    )
    assert suggestion["changed"] is True
    assert set(suggestion["down"]) == {"growth", "stage"}
    assert set(suggestion["up"]) == {"profit", "moat", "evidence", "prosperity"}
    # growth/stage 减半,总量归一化到 1.0
    assert suggestion["weights"]["growth"] < 0.24 / 1.0
    assert abs(sum(suggestion["weights"].values()) - 1.0) < 1e-6
    # 接收方权重按训练 IC 比例增加
    assert suggestion["weights"]["moat"] > suggestion["weights"]["prosperity"]


def test_suggest_weights_no_change_when_sign_flips_between_windows() -> None:
    # 训练窗 >0 但验证窗 <=0(符号不一致)→ 不接收也不让权
    suggestion = calibrate.suggest_weights(
        {"growth": 0.24, "profit": 0.18, "moat": 0.22, "stage": 0.16, "evidence": 0.14, "prosperity": 0.06},
        {"growth_score": 0.05, "profit_score": -0.03, "moat_score": -0.02, "stage_score": 0.01,
         "evidence_score": -0.01, "prosperity_score": -0.02},
        {"growth_score": -0.02, "profit_score": -0.02, "moat_score": -0.03, "stage_score": -0.01,
         "evidence_score": -0.02, "prosperity_score": -0.01},
    )
    assert suggestion["changed"] is False


def test_daily_rank_ics_returns_none_on_zero_variance() -> None:
    pairs = [(50.0, 1.0), (50.0, -2.0), (50.0, 0.5)] * 10
    assert calibrate._daily_rank_ics(pairs) is None


def test_daily_rank_ics_returns_none_on_insufficient_pairs() -> None:
    pairs = [(1.0, 1.0), (2.0, -1.0)]
    assert calibrate._daily_rank_ics(pairs) is None


def test_daily_rank_ics_detects_monotone_relation() -> None:
    pairs = [(float(i), float(30 - i) * 0.5) for i in range(30)]
    ic = calibrate._daily_rank_ics(pairs)
    assert ic is not None and ic == -1.0
