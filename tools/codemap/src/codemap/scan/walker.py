"""文件遍历：尊重 .gitignore。

git 仓用 `git ls-files --cached --others --exclude-standard`（tracked + untracked，排除 gitignored）——
最准且自动跟随 .gitignore 更新。非 git 仓 fallback os.walk + 常见目录排除（粗粒度，够 M1）。
"""

from __future__ import annotations
import os
import subprocess
from pathlib import Path

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".venv", ".hg", ".svn",
    "node_modules", "__pycache__", ".pytest_cache",
    ".agf",            # DU 自身派生产物
    "dist", "build", ".eggs",
}


def walk(project_root: str | Path, exclude_dirs: set[str] | None = None) -> list[Path]:
    """遍历项目源文件（相对 project_root 的相对路径对应的绝对 Path）。

    git 仓 → git ls-files（尊重 .gitignore）；否则 → os.walk（排除 DEFAULT_EXCLUDE_DIRS）。
    返回排序后的文件列表（确定性，便于稳定测试 + 增量对比）。
    """
    root = Path(project_root).resolve()
    if (root / ".git").is_dir():
        files = _git_walk(root)
    else:
        files = _os_walk(root, exclude_dirs or DEFAULT_EXCLUDE_DIRS)
    return sorted(files)


def _git_walk(root: Path) -> list[Path]:
    """git ls-files --cached --others --exclude-standard。

    I4：git 损坏（坏 .git/HEAD、缺 git binary FileNotFoundError、非 git 仓误入此分支）
    → ``CalledProcessError`` / ``FileNotFoundError`` 不应传播致 build 崩溃，fallback
    ``_os_walk``（已存在的 os.walk 后备，与 walk() 的非 git 分支同路径）。
    S1：拓宽为 ``OSError`` —— 覆盖 ``FileNotFoundError`` + ``PermissionError``
    （git binary 不可执行 / 权限剥离容器），二者是 OSError 的兄弟子类、互不覆盖。
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return _os_walk(root, DEFAULT_EXCLUDE_DIRS)
    result = []
    for line in out.stdout.splitlines():
        if not line:
            continue
        p = root / line
        if p.is_file():
            result.append(p)
    return result


def _os_walk(root: Path, exclude_dirs: set[str]) -> list[Path]:
    """非 git fallback：os.walk 排除常见目录（不解析 .gitignore，粗粒度）。"""
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        # 原地改 dirnums 跳过排除目录（os.walk 惯例）
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for f in filenames:
            result.append(Path(dirpath) / f)
    return result
