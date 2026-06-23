"""M15: bi_trend_launch.py 拆分 — params 提取回归门（AC-3 部分达成）.

audit-model-2026-06-22 §M15：2168 行单文件违反单一职责。本 commit 部分达成：
把全部可调参数常量（WEIGHTS / GRADE_THRESHOLDS / MIN_OBV_DAYS / POSITION_REGIME
等约 100+ 个）提取到 params.py，bi_trend_launch.py 通过 re-export 保持
向后兼容（外部 `from bi_trend_launch import WEIGHTS` 不破）。

函数级拆分（factors.py / scoring.py / screening.py）标 follow-up——
score_bi_trend / _score_bi_trend_arrays / run_bi_screening 深度互调且引用
上百个常量，需先补集成测试覆盖再拆，否则回归风险高（见 team-lead 授权
"高风险逻辑拆分若需先补测试可标 follow-up"）。

回归门：断言 bi_trend_launch 仍 re-export 全部公共常量 + 仍 importable。
"""
import kronos_factors.engine.bi_trend_launch as btl
from kronos_factors.engine import params


# 这些常量必须在 bi_trend_launch 仍可直接访问（向后兼容 re-export）
SHARED_CONSTANTS = [
    "WEIGHTS", "GRADE_THRESHOLDS", "MIN_OBV_DAYS", "OBV_NEGATIVE_SKIP",
    "HARD_TECH_ONLY", "HARD_TECH_INDUSTRY_KW", "POSITION_REGIME", "SIGNAL_WEIGHT",
    "SELL_MAX_STOP_LOSS", "SELL_TRAILING_TIER5_STOP", "WEAK_MARKET_S_ONLY",
    "TIME_STOP_DAYS", "CHASE_PENALTY_OBV_DAYS_EXTREME",
]


def test_params_module_exists_and_has_constants():
    assert hasattr(params, "WEIGHTS"), "params.py 必须含 WEIGHTS（M15 提取目标）"
    assert hasattr(params, "POSITION_REGIME")
    assert hasattr(params, "GRADE_THRESHOLDS")


def test_bi_trend_launch_reexports_constants():
    """提取后 bi_trend_launch 仍 re-export 全部公共常量（向后兼容）."""
    missing = [name for name in SHARED_CONSTANTS if not hasattr(btl, name)]
    assert not missing, (
        f"bi_trend_launch 向后兼容 re-export 缺失: {missing}"
    )


def test_params_and_launch_are_same_object():
    """bi_trend_launch 的常量必须与 params 的同一对象（不是拷贝漂移）."""
    for name in ["WEIGHTS", "POSITION_REGIME", "GRADE_THRESHOLDS"]:
        assert getattr(btl, name) is getattr(params, name), (
            f"{name} 在 bi_trend_launch 与 params 不是同一对象——re-export 链断了"
        )


def test_key_functions_still_importable():
    """函数级拆分未进行（follow-up），核心函数仍在 bi_trend_launch."""
    for fn in ["score_bi_trend", "run_bi_screening", "_score_bi_trend_arrays",
               "generate_bi_plan", "calc_obv", "calc_wr", "check_sell_signal"]:
        assert hasattr(btl, fn), f"{fn} 必须仍在 bi_trend_launch（函数拆分是 follow-up）"
