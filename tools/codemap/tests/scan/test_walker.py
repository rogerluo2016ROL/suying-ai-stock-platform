"""walker.py 单测：git 模式尊重 .gitignore + 非 git fallback 排除默认目录。"""

import subprocess
from pathlib import Path

from codemap.scan.walker import walk


def test_git_walk_respects_gitignore(tmp_path):
    (tmp_path / "a.py").write_text("x=1")
    (tmp_path / ".gitignore").write_text(".venv/\nnode_modules/\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("y")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("z")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    files = walk(tmp_path)
    names = {p.name for p in files}
    assert "a.py" in names
    assert "lib.py" not in names    # .venv 被 gitignore 排除
    assert "pkg.js" not in names    # node_modules 被 gitignore 排除


def test_git_walk_includes_untracked(tmp_path):
    """--others 含未 commit 的文件（建图要扫当前工作区，不只 tracked）。"""
    (tmp_path / "tracked.py").write_text("x")
    (tmp_path / "untracked.py").write_text("y")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)

    files = walk(tmp_path)
    names = {p.name for p in files}
    assert "tracked.py" in names
    assert "untracked.py" in names  # untracked 也扫到


def test_os_walk_fallback_excludes_default_dirs(tmp_path):
    """非 git 仓：os.walk 排除 .venv / __pycache__ / .agf 等。"""
    (tmp_path / "a.py").write_text("x")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("y")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.pyc").write_text("z")
    # 不 git init

    files = walk(tmp_path)
    names = {p.name for p in files}
    assert "a.py" in names
    assert "lib.py" not in names
    assert "c.pyc" not in names


def test_walk_is_deterministic_sorted(tmp_path):
    """返回排序（稳定测试 + 增量对比）。"""
    for n in ["c.py", "a.py", "b.py"]:
        (tmp_path / n).write_text("x")
    files = walk(tmp_path)
    names = [p.name for p in files]
    assert names == sorted(names)


def test_git_walk_falls_back_when_git_ls_files_fails(tmp_path, monkeypatch):
    """I4：.git 存在但 ``git ls-files`` 失败 → 不应崩，走 os.walk fallback 仍产出文件。

    回归：``_git_walk`` 用 ``check=True``，git 损坏（坏 .git/HEAD、git binary 缺失
    FileNotFoundError）→ ``CalledProcessError`` 传播 → build 崩溃。
    修法：``_git_walk`` 包 try/except（CalledProcessError + FileNotFoundError）→ fallback
    ``_os_walk``（已存在的 os.walk 后备）。
    """
    # 先建一个有文件的「正常」目录 + .git/ 占位（让 walk() 误以为是 git 仓走 _git_walk）
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y")
    (tmp_path / ".git").mkdir()  # 占位 .git/，但内部损坏（无 HEAD / objects）

    # 让真实 git ls-files 失败：mock subprocess.run 抛 CalledProcessError
    import subprocess
    from codemap.scan import walker

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd[:3] == ["git", "-C", str(tmp_path)] and "ls-files" in cmd:
            raise subprocess.CalledProcessError(returncode=128, cmd=cmd)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(walker.subprocess, "run", fake_run)

    # 不应抛 —— 必须走 _os_walk fallback
    files = walk(tmp_path)
    names = {p.name for p in files}
    assert "a.py" in names, "I4: git ls-files failure dropped a.py (no fallback)"
    assert "b.py" in names, "I4: git ls-files failure dropped sub/b.py (no fallback)"


def test_git_walk_falls_back_when_git_binary_missing(tmp_path, monkeypatch):
    """I4：git binary 不存在（FileNotFoundError）→ 同样走 os.walk fallback 不崩。"""
    (tmp_path / "a.py").write_text("x")
    (tmp_path / ".git").mkdir()

    import subprocess
    from codemap.scan import walker

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if len(cmd) >= 1 and cmd[0] == "git":
            raise FileNotFoundError("[Errno 2] No such file or directory: 'git'")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(walker.subprocess, "run", fake_run)

    files = walk(tmp_path)
    names = {p.name for p in files}
    assert "a.py" in names, "I4: missing git binary dropped a.py (FileNotFoundError propagated)"


def test_git_walk_falls_back_when_git_binary_not_executable(tmp_path, monkeypatch):
    """S1：git binary 不可执行（PermissionError，权限剥离容器）→ 走 os.walk fallback 不崩。

    回归：``_git_walk`` 的 ``except (CalledProcessError, FileNotFoundError)`` 漏
    PermissionError。FileNotFoundError 与 PermissionError 是 OSError 的兄弟子类，
    互不覆盖 → PermissionError 传播致 build 崩溃（I4 要防的故障模式）。
    修法：拓宽为 ``except (CalledProcessError, OSError)``（OSError 覆盖两者）。
    """
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y")
    (tmp_path / ".git").mkdir()

    import subprocess
    from codemap.scan import walker

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if len(cmd) >= 1 and cmd[0] == "git":
            raise PermissionError("[Errno 13] Permission denied: 'git'")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(walker.subprocess, "run", fake_run)

    # 不应抛 —— 必须走 _os_walk fallback
    files = walk(tmp_path)
    names = {p.name for p in files}
    assert "a.py" in names, "S1: non-executable git binary dropped a.py (PermissionError propagated)"
    assert "b.py" in names, "S1: non-executable git binary dropped sub/b.py (PermissionError propagated)"
