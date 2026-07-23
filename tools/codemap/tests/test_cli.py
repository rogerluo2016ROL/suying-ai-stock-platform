"""cli 层 --out 落盘（_emit）测试 + main() 端到端测试（C2）。

C2 覆盖关键子命令：build / diff / understand / search。用 subprocess + ``python -m codemap.cli``
跑真实 CLI（保留 argparse 全链路 + 子命令分发 + 输出格式），断言 exit code 0 + 产出
（db 文件存在 / stdout 含预期 section / 文件落盘）。
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

from codemap.cli import _emit

# tests/ 目录到 tools/codemap/ 的相对路径（用于设 PYTHONPATH 让 subprocess 找到 codemap 包）
_CODEMAP_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _CODEMAP_ROOT / "src"


def _run_cli(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    """跑 ``python -m codemap.cli <args>`` 真实 CLI（subprocess，保留 argparse 全链路）。"""
    env = {**os.environ, "PYTHONPATH": str(_SRC_DIR)}
    return subprocess.run(
        [sys.executable, "-m", "codemap.cli", *args],
        cwd=str(cwd or _CODEMAP_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


# ---- _emit 辅助（原有）----

def test_emit_stdout(capsys):
    """未指定 --out → 走 stdout。"""
    _emit("hello", None)
    assert capsys.readouterr().out == "hello\n"


def test_emit_writes_file_and_creates_parents(tmp_path, capsys):
    """--out 指定 → 写文件，父目录自动建，stdout 只报路径。"""
    out = tmp_path / "docs" / "reviews" / "x-understand-2026-07-07.md"  # 父目录不存在
    _emit("# 理解地图\n...", str(out))
    cap = capsys.readouterr()
    assert out.read_text(encoding="utf-8") == "# 理解地图\n..."
    assert cap.out.startswith(f"wrote {out}")  # stdout 报落盘路径 + 字符数


# ---- main() 端到端：build / diff / understand / search（C2）----

def _setup_mini_repo(tmp_path: Path) -> Path:
    """建最小可建图的项目（pkg + 互相 import + 符号），供后续子命令复用。"""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text("VAL = 1\n\ndef use():\n    return VAL\n")
    (pkg / "use.py").write_text("from pkg.mod import VAL\nprint(VAL)\n")
    return tmp_path


def test_cli_build_e2e(tmp_path):
    """build 子命令：建图 → stdout 出 JSON stats，db 文件落盘。"""
    root = _setup_mini_repo(tmp_path)
    db = tmp_path / "t.db"
    r = _run_cli("build", str(root), "--db", str(db))
    assert r.returncode == 0, f"build failed: stderr={r.stderr}"
    # db 落盘
    assert db.is_file(), "build did not create db file"
    # stdout 是 JSON stats
    stats = json.loads(r.stdout)
    assert stats["files"] >= 2, f"stats.files wrong: {stats}"
    assert stats["symbols"] >= 1, f"stats.symbols wrong: {stats}"
    assert stats["imports"] >= 1, f"stats.imports wrong: {stats}"


def test_cli_understand_e2e(tmp_path):
    """understand 子命令：产出理解地图 markdown（含预期 section）。"""
    root = _setup_mini_repo(tmp_path)
    db = tmp_path / "t.db"
    _run_cli("build", str(root), "--db", str(db))  # 预置 db
    # 不带 --out → stdout
    r = _run_cli("understand", "--db", str(db))
    assert r.returncode == 0, f"understand failed: stderr={r.stderr}"
    assert "# 理解地图" in r.stdout, "understand stdout missing title"
    assert "## 子系统" in r.stdout, "understand stdout missing 子系统 section"
    assert "## 核心依赖" in r.stdout, "understand stdout missing 核心依赖 section"
    assert "## 风险点" in r.stdout, "understand stdout missing 风险点 section"
    # 带 --out → 落盘
    out = tmp_path / "docs" / "u.md"
    r2 = _run_cli("understand", "--db", str(db), "--out", str(out))
    assert r2.returncode == 0, f"understand --out failed: stderr={r2.stderr}"
    assert out.is_file(), "understand --out did not write file"
    content = out.read_text(encoding="utf-8")
    assert "# 理解地图" in content


def test_cli_search_e2e(tmp_path):
    """search 子命令：能搜到 build 出的符号（降级 keyword 路径，因未跑 embed）。"""
    root = _setup_mini_repo(tmp_path)
    db = tmp_path / "t.db"
    _run_cli("build", str(root), "--db", str(db))
    r = _run_cli("search", "use", "--db", str(db))
    assert r.returncode == 0, f"search failed: stderr={r.stderr}"
    # 必须有「来源」标签（keyword 降级 或 semantic）
    assert "[来源:" in r.stdout, f"search stdout missing source label: {r.stdout}"
    # use 函数必须被命中（FTS5 MATCH 或 LIKE fallback）
    assert "use" in r.stdout, f"search 'use' did not match function 'use': {r.stdout}"


def test_cli_diff_e2e(tmp_path):
    """diff 子命令：git diff 后跑 impact_report → JSON 含 changed/affected。"""
    # 需 git 仓（diff 走 git diff --name-only last..HEAD）
    _GIT_ENV = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }

    def _git(*args):
        subprocess.run(["git", *args], cwd=str(tmp_path), check=True, env=_GIT_ENV)

    root = _setup_mini_repo(tmp_path)
    _git("init", "-q")
    _git("add", ".")
    _git("commit", "-q", "-m", "init")
    db = tmp_path / "t.db"
    _run_cli("build", str(root), "--db", str(db))
    # 改 mod.py（use.py 反向依赖它）+ commit
    (tmp_path / "pkg" / "mod.py").write_text("VAL = 2\n\ndef use():\n    return VAL\n")
    _git("add", ".")
    _git("commit", "-q", "-m", "edit mod")
    # diff 默认 base=get_meta('git_commit')，会取 build 时存的 commit
    # CLI ``_changed`` 用 ``git -C .``（root 默认 '.'），故 cwd 须是 git 仓根
    r = _run_cli("diff", "--db", str(db), cwd=str(tmp_path))
    assert r.returncode == 0, f"diff failed: stderr={r.stderr}"
    report = json.loads(r.stdout)
    # 必须含 changed（mod.py）与 affected（use.py 反向依赖）
    assert "changed" in report and len(report["changed"]) >= 1, \
        f"diff report changed missing/empty: {report}"
    assert "affected" in report, f"diff report missing affected: {report}"
    # S3：reverse-dep 影响是 diff 核心价值，pin use.py 在 affected（不只查 key 存在）。
    # 回归：若未来 ``impact_report`` 返回 ``affected=[]``（reverse BFS 损坏），旧断言仍过。
    assert any("use.py" in str(a) for a in report["affected"]), \
        f"S3: reverse-dep use.py missing from affected: {report['affected']}"


def test_cli_help_returns_zero():
    """--help 退出 0（CLI 入口基本可用性）。"""
    r = _run_cli("--help")
    assert r.returncode == 0
    assert "codemap" in r.stdout.lower() or "deeply understand" in r.stdout.lower()
