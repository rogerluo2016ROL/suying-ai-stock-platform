"""Behavioral unit tests for M01-A/C (audit-model-2026-06-22, tech-lead 评估 §3).

walk_forward 的 M01 流程护栏:
  - M01-A: --strict-timeline 启用 + 策略 commit 日期 > 样本外起始月 → sys.exit(2)
  - M01-C: 工作区 dirty → sys.exit(2) (始终强制, 不受 flag 控制)

这是对 code-reviewer-ml W-2 的直接回应 (M01 原只有契约字符串校验, 无行为级测试).
直接驱动纯函数 _timeline_guard_decision + 一个 main() 级 end-to-end (subprocess mock
验证 sys.exit 真触发), 不依赖 PG / GPU.

Run: cd services/training-service && pytest tests/test_walk_forward_timeline.py -v
"""
import os
import sys

import pytest

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_TOOLS = os.path.join(_PROJ, "tools")
for _p in [_TOOLS, os.path.join(_PROJ, "packages", "kronos-factors"),
           os.path.join(_PROJ, "packages", "kronos-core"),
           os.path.join(_PROJ, "packages", "kronos-data")]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# walk_forward 顶部 import backtest_bi_trend (tools/), 需 tools/ 在 sys.path.
from walk_forward import _timeline_guard_decision  # noqa: E402


# ── _timeline_guard_decision 纯函数: 三种场景 ────────────────────────────────

def test_guard_clean_commit_before_start_strict_passes():
    """(a) clean + commit 日期 ≤ start + strict → 放行."""
    info = {"path": "bi_trend_launch.py", "commit": "abc123", "date": "2023-11-01",
            "dirty": False, "subject": "V5.9 baseline", "error": None}
    decision = _timeline_guard_decision(info, start_month="2024-01", strict=True)
    assert decision["exit"] is False, f"clean + 早 commit + strict 应放行, got {decision}"


def test_guard_clean_commit_after_start_strict_exits():
    """(b) clean + commit 日期 > start + strict → exit code 2 (M01-A)."""
    info = {"path": "bi_trend_launch.py", "commit": "def456", "date": "2026-06-10",
            "dirty": False, "subject": "V13 in-sample tuned", "error": None}
    decision = _timeline_guard_decision(info, start_month="2024-01", strict=True)
    assert decision["exit"] is True, "clean + 晚 commit + strict 应阻断"
    assert decision["code"] == 2, "M01-A 应 exit code 2"
    # 错误信息含关键诊断: commit 日期 / 起始月 / 泄露 / --strict-timeline 提示
    msg = decision["message"]
    assert "2026-06-10" in msg and "2024-01" in msg, "M01-A 错误信息未含 commit 日期/起始月"
    assert "时序泄露" in msg or "泄漏" in msg, "M01-A 错误信息未提时序泄露"
    assert "--strict-timeline" in msg, "M01-A 错误信息未提示去掉 flag"


def test_guard_dirty_always_exits_regardless_of_strict():
    """(c) dirty → exit 2, 无论 strict (M01-C 始终强制)."""
    info_dirty = {"path": "bi_trend_launch.py", "commit": "abc123", "date": "2023-11-01",
                  "dirty": True, "subject": "V5.9 baseline", "error": None}
    # strict=False 也应阻断
    d1 = _timeline_guard_decision(info_dirty, start_month="2024-01", strict=False)
    assert d1["exit"] is True and d1["code"] == 2, "dirty + 非 strict 应阻断 (M01-C 始终强制)"
    # strict=True 同样阻断
    d2 = _timeline_guard_decision(info_dirty, start_month="2024-01", strict=True)
    assert d2["exit"] is True and d2["code"] == 2, "dirty + strict 应阻断"
    # 错误信息含 dirty 诊断
    assert "dirty" in d1["message"].lower() or "未提交" in d1["message"], (
        "M01-C 错误信息未提 dirty/未提交修改")
    # 即使 commit 日期早于 start, dirty 仍优先阻断 (M01-C 优先于 M01-A)
    assert "2024-01" not in d1["message"].split("dirty")[0], (
        "dirty 阻断信息不应混入时序泄露诊断")


def test_guard_dirty_takes_precedence_over_late_commit():
    """dirty + 晚 commit + strict → 仍报 dirty (M01-C 优先)."""
    info = {"path": "bi_trend_launch.py", "commit": "def456", "date": "2026-06-10",
            "dirty": True, "subject": "V13", "error": None}
    d = _timeline_guard_decision(info, start_month="2024-01", strict=True)
    assert d["exit"] is True and d["code"] == 2
    # dirty 阻断信息 (M01-C), 不应是时序泄露信息 (M01-A)
    assert "M01-C" in d["message"], "dirty + 晚 commit 应优先报 M01-C (dirty)"


def test_guard_clean_late_commit_non_strict_passes():
    """非 strict + clean + 晚 commit → 放行 (D 模式过渡兜底, main 里给软警告)."""
    info = {"path": "bi_trend_launch.py", "commit": "def456", "date": "2026-06-10",
            "dirty": False, "subject": "V13", "error": None}
    d = _timeline_guard_decision(info, start_month="2024-01", strict=False)
    assert d["exit"] is False, "非 strict + clean 应放行 (软警告由 main 处理)"


# ── main() 级 end-to-end: mock subprocess.run 验证 sys.exit 真触发 ──────────

class _FakeCompleted:
    """模拟 subprocess.run 返回值 (按 args 调用顺序返回不同结果)."""
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def _build_subprocess_mock(date, dirty, commit="abc123def456"):
    """构造 mock subprocess.run: 让 _git_strategy_commit 读到指定 date/dirty.

    _git_strategy_commit 依次调用:
      git rev-parse --show-toplevel  → repo_root
      git log -1 --format=%H -- rel  → commit
      git log -1 --format=%s commit → subject
      git show -s --format=%cI commit → date
      git status --porcelain -- rel  → dirty (非空=dirty)
    """
    cmdstr = lambda cmd: " ".join(cmd)

    def fake_run(cmd, **kwargs):
        s = cmdstr(cmd)
        if "rev-parse" in cmd:
            return _FakeCompleted(stdout=_PROJ + "\n")
        if "log" in s and "--format=%H" in s:
            return _FakeCompleted(stdout=commit + "\n")
        if "log" in s and "--format=%s" in s:
            return _FakeCompleted(stdout="fake commit subject\n")
        if "show" in s and "--format=%cI" in s:
            return _FakeCompleted(stdout=date + "T12:00:00+0800\n")
        if "status" in s and "--porcelain" in s:
            return _FakeCompleted(stdout=(" M file.py\n" if dirty else ""))
        return _FakeCompleted(stdout="")
    return fake_run


def test_main_strict_late_commit_exits_2(monkeypatch, capsys):
    """main() 级: --strict-timeline + commit 日期晚于 start → sys.exit(2)."""
    import walk_forward as wf
    # commit 日期 2026-06-10 > start 2024-01, clean
    monkeypatch.setattr(wf.subprocess, "run", _build_subprocess_mock("2026-06-10", dirty=False))
    # 跳过真实回测: setup_db / 回测循环不应触达 (guard 在它们之前)
    monkeypatch.setattr(wf, "setup_db", lambda: None)
    monkeypatch.setattr(sys, "argv", ["walk_forward.py", "--start", "2024-01",
                                      "--end", "2024-02", "--strict-timeline"])
    with pytest.raises(SystemExit) as exc:
        wf.main()
    assert exc.value.code == 2, "M01-A strict + 晚 commit 应 exit 2"
    out = capsys.readouterr().out
    assert "M01-A" in out and "2026-06-10" in out, "main 输出未含 M01-A 诊断"


def test_main_dirty_always_exits_2(monkeypatch, capsys):
    """main() 级: dirty → sys.exit(2), 无 --strict-timeline 也阻断 (M01-C)."""
    import walk_forward as wf
    # commit 日期早于 start (2023-11 < 2024-01), 但 dirty
    monkeypatch.setattr(wf.subprocess, "run", _build_subprocess_mock("2023-11-01", dirty=True))
    monkeypatch.setattr(wf, "setup_db", lambda: None)
    monkeypatch.setattr(sys, "argv", ["walk_forward.py", "--start", "2024-01",
                                      "--end", "2024-02"])  # 无 --strict-timeline
    with pytest.raises(SystemExit) as exc:
        wf.main()
    assert exc.value.code == 2, "M01-C dirty 应 exit 2 (无 strict)"
    out = capsys.readouterr().out
    assert "M01-C" in out and "dirty" in out.lower(), "main 输出未含 M01-C dirty 诊断"


def test_main_non_strict_late_commit_passes_with_warning(monkeypatch, capsys):
    """main() 级: 无 --strict-timeline + 晚 commit → 放行 + 软警告 (D 兜底)."""
    import walk_forward as wf
    # commit 晚于 start, clean, 无 strict → guard 应放行, main 打软警告后继续.
    monkeypatch.setattr(wf.subprocess, "run", _build_subprocess_mock("2026-06-10", dirty=False))
    monkeypatch.setattr(wf, "setup_db", lambda: None)
    # 跳过真实回测循环: month_iter 返回空 → 循环 0 次, 不触达 PG.
    monkeypatch.setattr(wf, "month_iter", lambda start, end: [])
    monkeypatch.setattr(sys, "argv", ["walk_forward.py", "--start", "2024-01",
                                      "--end", "2024-02"])  # 无 --strict-timeline
    wf.main()  # 不应 raise SystemExit
    out = capsys.readouterr().out
    assert "警告" in out and "2026-06-10" in out, "非 strict 晚 commit 应打软警告"
    assert "不可作样本外结论" in out, "软警告应明确结果不可作样本外结论"
