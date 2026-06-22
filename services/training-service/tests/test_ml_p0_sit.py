"""SIT — ML-P0 (audit-model-2026-06-22) 集成测试.

SIT 范围 (ML 角色 Output 表 SIT 行): 串接 ML-P0 六个修复的关键路径 —
  - M01: walk_forward 显式记录策略 commit (避免未来参数测过去)
  - M02: bi_trend_launch 推回调参前统一参数 (hold=5/tp=15/stop=-10, 无网格搜索注释)
  - M03: pg_adapter.get_kline end_date 过滤 (真实 PG 验证 batch_date 不返回未来 K 线)
  - M04: training_engine Kronos 分支禁用 + _prepare_training_data 不 fallback 合成
  - M05: prediction-service lifespan checkpoint 状态 metric (base_public)
  - M06: training_engine _group_split_masks 无横截面泄露 (详 test_group_split.py)

真实 PG 部分 (M03 端到端) 用 skip 守护: PG 未运行时跳过, 不算失败.
其余为纯代码契约校验, 无外部依赖.

Run: cd backend && .venv/bin/pytest tests/sit/test_ml_p0_sit.py -v
"""
import os
import sys
import importlib

import pytest

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for pkg in ["packages/kronos-factors"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)
# 注意: 不把 services/training-service 加入 sys.path — 它有 app 包, 会与 backend/app 冲突
# (污染同 session 其它 backend 测试的 app 解析). M04 测试用文件读 + AST, 不需 import.
_SVC = os.path.join(_PROJ, "services", "training-service")


# ── M02: bi_trend_launch 推回调参前参数 + 删除调参残留注释 ──────────────────

def test_m02_bi_trend_unified_hold_params():
    """M02: run_bi_screening 返回的 pick 应使用统一 V5.9 调参前参数."""
    from kronos_factors.engine.bi_trend_launch import run_bi_screening
    import inspect
    src = inspect.getsource(run_bi_screening)
    # 推回的统一参数应在源码中
    assert '"hold_days"] = 5' in src, "hold_days=5 (V5.9 基线) 未找到"
    assert '"take_profit"] = 15' in src, "take_profit=15 (V5.9 基线) 未找到"
    assert '"stop_loss"] = -10' in src, "stop_loss=-10 (V5.9 基线) 未找到"
    assert '"weight"] = 1.0' in src, "weight=1.0 (无 S 级降权) 未找到"


def test_m02_bi_trend_no_insample_annotations():
    """M02: bi_trend_launch.py 全文无'网格搜索/H1数据/个股教训'调参残留注释."""
    src_path = os.path.join(_PROJ, "packages", "kronos-factors", "kronos_factors",
                            "engine", "bi_trend_launch.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    forbidden = ["网格搜索", "H1数据", "H1 数据", "川金诺", "立昂微", "新易盛",
                 "中富通", "鼎通", "中天科技", "光库科技"]
    found = [kw for kw in forbidden if kw in src]
    assert not found, f"bi_trend_launch.py 仍含调参残留注释: {found}"


# ── M01: walk_forward 显式记录策略 commit ──────────────────────────────────

def test_m01_walk_forward_records_strategy_commit():
    """M01: walk_forward.py 必须有 _git_strategy_commit + A/C 护栏 + 导出 JSON 含 strategy_commit.

    tech-lead 评估 (docs/reviews/m01-techlead-assessment-2026-06-22.md §3) 推 A+C:
      - _git_strategy_commit 记录 commit (原 M01 基础)
      - --strict-timeline flag + _timeline_guard_decision (M01-A 硬阻断时序泄露)
      - dirty 始终 exit(2) (M01-C, 不受 flag 控制)
    行为级验证见 test_walk_forward_timeline.py; 此处为契约层 (防修复标记被删).
    """
    src_path = os.path.join(_PROJ, "tools", "walk_forward.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert "def _git_strategy_commit" in src, "walk_forward 缺少 _git_strategy_commit 函数"
    assert '"strategy_commit"' in src, "walk_forward 导出 JSON 未记录 strategy_commit"
    assert "M01" in src, "walk_forward 未标注 M01 修复说明"
    # M01-A: --strict-timeline flag + guard 决策函数
    assert "--strict-timeline" in src, "walk_forward 缺 --strict-timeline flag (M01-A)"
    assert "def _timeline_guard_decision" in src, "walk_forward 缺 _timeline_guard_decision 函数 (M01-A/C)"
    assert "sys.exit" in src, "walk_forward guard 未用 sys.exit 硬阻断 (M01-A/C)"


# ── M03: pg_adapter end_date (单测见 test_pg_adapter_end_date.py, 此处校验接口一致) ──

def test_m03_pg_adapter_end_date_signature():
    """M03: get_kline / get_kline_df 签名含 end_date 参数."""
    import inspect
    from kronos_factors.pg_adapter import _PgAdapter
    from kronos_factors.base import DBAdapter, MarketDataAdapter
    sig_kline = inspect.signature(_PgAdapter.get_kline)
    sig_kdf = inspect.signature(_PgAdapter.get_kline_df)
    assert "end_date" in sig_kline.parameters, "get_kline 缺 end_date 参数"
    assert "end_date" in sig_kdf.parameters, "get_kline_df 缺 end_date 参数"
    # 抽象基类接口也同步
    assert "end_date" in inspect.signature(DBAdapter.get_kline).parameters
    assert "end_date" in inspect.signature(MarketDataAdapter.get_kline_df).parameters


# ── M03 真实 PG 端到端 (可选, PG 未运行则 skip) ─────────────────────────────

def _pg_available():
    try:
        from kronos_factors.pg_adapter import create_pg_adapter
        adapter = create_pg_adapter(os.environ.get(
            "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
        return adapter is not None
    except Exception:
        return False


@pytest.mark.skipif(not _pg_available(), reason="PG 未运行 (docker-postgres-1), 跳过 M03 端到端")
def test_m03_end_date_no_future_kline_e2e():
    """M03 端到端: get_kline(end_date=早日期) 不返回晚于 end_date 的 K 线."""
    from kronos_factors.pg_adapter import create_pg_adapter
    adapter = create_pg_adapter(os.environ.get(
        "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    # 取一只一定有数据的股票 (任意 6 位代码), end_date 设为 2020-06-30
    df = adapter.get_kline("000001", lookback=400, end_date="2020-06-30")
    if df is None or len(df) == 0:
        pytest.skip("000001 在 2020-06-30 前无数据 (数据源未覆盖该时段)")
    max_date = df["trade_date"].max()
    assert str(max_date) <= "2020-06-30", (
        f"M03 泄漏: end_date=2020-06-30 但返回了 {max_date} 的 K 线")


# ── M04: training_engine Kronos 禁用 + 不 fallback 合成 ─────────────────────

def _training_engine_src():
    """读 training_engine.py 源码 (避免 backend/app 包名冲突, 用文件读)."""
    src_path = os.path.join(_SVC, "app", "training_engine.py")
    with open(src_path, encoding="utf-8") as f:
        return f.read()


def test_m04_kronos_training_disabled():
    """M04: _train_kronos_sync 必须显式 raise NotImplementedError (不再 sleep 假训练).

    用 AST 解析函数节点, 确认实际代码路径 (非 docstring/字符串) 不含 time.sleep 调用,
    且函数体第一条语句是 raise NotImplementedError.
    """
    import ast
    src_path = os.path.join(_SVC, "app", "training_engine.py")
    tree = ast.parse(open(src_path, encoding="utf-8").read())
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_train_kronos_sync":
            fn = node
            break
    assert fn is not None, "未找到 _train_kronos_sync 函数"
    # 函数体第一条非 docstring 语句应是 raise NotImplementedError
    body = [s for s in fn.body if not isinstance(s, ast.Expr)]
    assert body, "_train_kronos_sync 函数体为空"
    first = body[0]
    assert isinstance(first, ast.Raise), "_train_kronos_sync 第一条语句应是 raise (M04)"
    # 全函数体不应有任何 time.sleep 调用 (AST 层, 排除字符串)
    has_sleep = any(
        isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "sleep"
        for n in ast.walk(fn)
    )
    assert not has_sleep, "_train_kronos_sync 仍含 time.sleep 假训练调用 (M04)"


def test_m04_prepare_data_raises_without_synthetic_fallback():
    """M04: _prepare_training_data 主路径 (allow_synthetic=False) 找不到数据应抛异常."""
    src = _training_engine_src()
    marker = "def _prepare_training_data"
    idx = src.find(marker)
    assert idx >= 0, "未找到 _prepare_training_data 函数"
    fn_body = src[idx:idx + 2000]
    assert "allow_synthetic" in fn_body, "_prepare_training_data 缺 allow_synthetic 参数 (M04)"
    assert "allow_synthetic: bool = False" in fn_body, (
        "allow_synthetic 默认必须 False (主训练路径禁止 fallback 合成, M04)")
    assert "raise FileNotFoundError" in fn_body, (
        "_prepare_training_data 找不到数据应抛 FileNotFoundError (M04)")


def test_m04_auto_deploy_blocked_in_mock_mlflow():
    """M04: _execute_training 在非 live MLflow 下抑制 auto_deploy."""
    src_path = os.path.join(_PROJ, "services", "training-service", "app",
                            "training_engine.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert "MLFLOW_MODE != \"live\"" in src, "auto-deploy 未加 live MLflow 安全门 (M04)"
    assert "auto_deploy_skipped" in src, "缺少 auto_deploy 跳过的事件上报 (M04)"


# ── M05: prediction-service lifespan checkpoint 状态 metric ────────────────

def test_m05_prediction_lifespan_checkpoint_status():
    """M05: main.py 必须有 _model_checkpoint_status metric + health 暴露."""
    src_path = os.path.join(_PROJ, "services", "prediction-service", "app", "main.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert "_model_checkpoint_status" in src, "prediction-service 缺 checkpoint 状态 metric (M05)"
    assert "base_public" in src, "缺 base_public 状态标注 (M05)"
    assert "checkpoint_status" in src, "health endpoint 未暴露 checkpoint_status (M05)"


def test_m05_adr005_wording_public_kronos():
    """M05: ADR-005 措辞改为'基于公开 Kronos-mini 托管推理'."""
    adr_path = os.path.join(_PROJ, "docs", "adr", "005-stock-diagnosis.md")
    with open(adr_path, encoding="utf-8") as f:
        src = f.read()
    assert "Kronos-mini" in src and "托管推理" in src, "ADR-005 未改为公开 Kronos-mini 托管推理措辞 (M05)"
