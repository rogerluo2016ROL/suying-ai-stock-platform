"""图谱常用只读查询（去 understand / onboard 的逐字重复；03 §1）。

name LIKE fallback 有意不收进来——keyword.py 与 context_builder.py 各自投影不同列
（前者 id/type/name/file_path，后者 id/name），强行统一会改行为，不是干净去重。
"""
from __future__ import annotations

import sqlite3


def high_fan_in(db: sqlite3.Connection, limit: int = 10) -> list:
    """入边最多（被最多文件 import）的 dst 节点 + 计数，降序。"""
    return db.execute(
        "SELECT dst, COUNT(*) c FROM edges WHERE type='imports' "
        "GROUP BY dst ORDER BY c DESC LIMIT ?",
        (limit,),
    ).fetchall()


def complex_nodes(db: sqlite3.Connection, limit: int = 10) -> list:
    """复杂度 = complex 的符号节点（id, name, file_path）。"""
    return db.execute(
        "SELECT id, name, file_path FROM nodes WHERE complexity='complex' LIMIT ?",
        (limit,),
    ).fetchall()
