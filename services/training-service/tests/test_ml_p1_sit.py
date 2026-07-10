"""SIT — ML-P1 (audit-model-2026-06-22) 集成测试.

SIT 范围 (ML 角色 Output 表 SIT 行): 串接 ML-P1 六个修复的关键路径 —
  - M07: prediction-service load_state_dict strict=False + 异常分类
  - M08: backtest_bi_trend 单日口径标注"含前视仅对比用禁止披露"
  - M09: bi_trend_launch 个股教训阈值标 DEPRECATED
  - M10: onnx_optimizer.py 已删 (0 调用) + CLAUDE.md/设计文档删 ONNX 措辞
  - M11: dataset.py 加载校验 train max 时间 < val min 时间
  - M12: training_engine _evaluate_vs_production 显著性标注 + 最小信号门

纯代码契约校验, 无外部依赖 (PG/GPU).

Run: cd backend && .venv/bin/pytest tests/sit/test_ml_p1_sit.py -v
"""
import os
import pytest

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── M07: prediction load strict=False + 异常分类 ───────────────────────────

def test_m07_load_state_dict_strict_false():
    """M07: load_state_dict 用 strict=False + 记录 missing/unexpected keys."""
    src = _read(os.path.join(_PROJ, "services", "prediction-service", "app", "main.py"))
    assert "strict=False" in src, "load_state_dict 未用 strict=False (M07)"
    assert "missing" in src and "unexpected" in src, "未记录 missing/unexpected keys (M07)"
    # 异常分类: 区分 FileNotFoundError / RuntimeError 而非一把 except
    assert "FileNotFoundError" in src, "未细分 FileNotFoundError 异常分支 (M07)"
    assert "RuntimeError" in src, "未细分 RuntimeError 异常分支 (M07)"


# ── M08: 单日口径标注前视 ──────────────────────────────────────────────────

def test_m08_single_day_lookahead_warning():
    """M08: backtest_bi_trend 单日口径输出 + JSON summary 标注前视警告."""
    src = _read(os.path.join(_PROJ, "tools", "backtest_bi_trend.py"))
    assert "成交假设前视" in src, "单日口径未标注成交假设前视 (M08)"
    assert "禁止对外披露" in src, "未标注禁止对外披露 (M08)"
    assert "lookahead_warning" in src, "JSON summary 缺 lookahead_warning 字段 (M08)"


# ── M09: 个股教训阈值标 DEPRECATED ─────────────────────────────────────────

def test_m09_anecdote_thresholds_marked_deprecated():
    """M09: 审计点名的个股教训阈值标 DEPRECATED."""
    src = _read(os.path.join(_PROJ, "packages", "kronos-factors", "kronos_factors",
                             "engine", "bi_trend_launch.py"))
    # M09 点名的阈值应带 DEPRECATED 标签
    assert "DEPRECATED" in src, "bi_trend_launch 未标 DEPRECATED 阈值 (M09)"
    # 关键阈值 (OBV_NEGATIVE_SKIP, MARKET_BREADTH_WEAK, HIGH_VOL 倍率) 应有 DEPRECATED 注释
    assert "OBV_NEGATIVE_SKIP = True" in src and "DEPRECATED" in src.split("OBV_NEGATIVE_SKIP = True")[1][:200]
    assert "MARKET_BREADTH_WEAK = 25" in src and "DEPRECATED" in src.split("MARKET_BREADTH_WEAK = 25")[1][:200]


# ── M10: onnx_optimizer.py 删除 + ONNX 措辞清理 ────────────────────────────

def test_m10_onnx_optimizer_deleted():
    """M10: onnx_optimizer.py 已删除."""
    assert not os.path.exists(os.path.join(
        _PROJ, "services", "prediction-service", "app", "onnx_optimizer.py")), (
        "onnx_optimizer.py 未删除 (M10)")


def test_m10_onnx_wording_removed_from_tech_stack():
    """M10: CLAUDE.md Tech Stack 删除 ONNX Runtime 措辞."""
    src = _read(os.path.join(_PROJ, "CLAUDE.md"))
    tech_line = [l for l in src.splitlines() if "AI/ML" in l and "|" in l][0]
    assert "ONNX Runtime" not in tech_line, f"CLAUDE.md Tech Stack 仍含 ONNX Runtime (M10): {tech_line}"


def test_m10_onnx_no_callers():
    """M10: prediction-service 无任何 onnx_optimizer 调用."""
    import subprocess
    result = subprocess.run(
        ["grep", "-rl", "onnx_optimizer", os.path.join(_PROJ, "services", "prediction-service")],
        capture_output=True, text=True)
    # grep 返回非 0 表示无匹配 (期望), 或输出为空
    assert result.stdout.strip() == "", (
        f"prediction-service 仍有 onnx_optimizer 调用: {result.stdout}")


# ── M11: dataset.py 加载时间一致性校验 ─────────────────────────────────────

def test_m11_dataset_time_consistency_check():
    """M11: QlibDataset 加载 val 时校验 train max 时间 < val min 时间."""
    dataset_path = os.path.join(_PROJ, "Kronos", "Kronos-uat-bak", "src", "kronos", "finetune", "dataset.py")
    if not os.path.exists(dataset_path):
        pytest.skip("legacy Kronos-uat-bak finetune source is not shipped in this repository")
    src = _read(dataset_path)
    assert "_assert_no_time_overlap_with_train" in src, "dataset.py 缺时间一致性校验方法 (M11)"
    assert "train max datetime" in src or "val min datetime" in src, (
        "dataset.py 时间校验断言消息缺失 (M11)")


# ── M12: _evaluate_vs_production 显著性标注 + 最小信号门 ────────────────────

def test_m12_evaluate_significance_annotation():
    """M12: _evaluate_vs_production 标注点估计 + 最小信号门 + 统计检验 TODO."""
    src = _read(os.path.join(_PROJ, "services", "training-service", "app", "training_engine.py"))
    assert "NOT statistically significant" in src, (
        "_evaluate_vs_production 未标注非统计显著 (M12)")
    assert "MIN_SIGNAL_PCT" in src, "未加最小信号门 (M12)"
    assert "bootstrap" in src or "Diebold-Mariano" in src, (
        "未标注 bootstrap/Diebold-Mariano TODO (M12)")
