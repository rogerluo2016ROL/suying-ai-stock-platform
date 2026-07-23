"""SQLite 存储层：建表 + upsert + 事务 + meta。

SSOT: docs/design/deeply-understand/03-data-model.md §1 schema.sql
"""

from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .model import EdgeRecord, FileRecord, NodeRecord

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """打开/创建 SQLite 库并建表（IF NOT EXISTS，幂等）。WAL 模式 + autocommit。

    autocommit（isolation_level=None）：单条 upsert 立即持久，FK 检查可见先前写入；
    批量原子写用 ``transaction()``（显式 BEGIN/COMMIT）。
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """显式事务（autocommit 模式下）；任何异常 ROLLBACK，否则 COMMIT（05 §2.5 幂等/崩溃恢复）。"""
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_file(conn: sqlite3.Connection, rec: FileRecord) -> None:
    conn.execute(
        """INSERT INTO files(path, language, category, line_count, content_hash, structure_hash, analyzed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET
             language=excluded.language, category=excluded.category,
             line_count=excluded.line_count, content_hash=excluded.content_hash,
             structure_hash=excluded.structure_hash, analyzed_at=excluded.analyzed_at""",
        (rec.path, rec.language, rec.category, rec.line_count,
         rec.content_hash, rec.structure_hash, rec.analyzed_at or _now_iso()),
    )


def upsert_node(conn: sqlite3.Connection, rec: NodeRecord) -> None:
    conn.execute(
        """INSERT INTO nodes(id, type, name, file_path, signature, start_line, end_line, complexity, summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             type=excluded.type, name=excluded.name, file_path=excluded.file_path,
             signature=excluded.signature, start_line=excluded.start_line,
             end_line=excluded.end_line, complexity=excluded.complexity, summary=excluded.summary""",
        (rec.id, rec.type, rec.name, rec.file_path, rec.signature,
         rec.start_line, rec.end_line, rec.complexity, rec.summary),
    )


def upsert_edge(conn: sqlite3.Connection, rec: EdgeRecord) -> None:
    """upsert 边。**调用方须保证 src/dst 节点已存在**（build 层 ``_safe_edge`` 用 node_ids
    集合校验），否则 sqlite FK 约束失败会回滚整个 Pass 2 事务。"""
    conn.execute(
        """INSERT INTO edges(src, dst, type, weight, detail)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(src, dst, type) DO UPDATE SET
             weight=excluded.weight, detail=excluded.detail""",
        (rec.src, rec.dst, rec.type, rec.weight, rec.detail),
    )


def delete_nodes_for_file(conn: sqlite3.Connection, file_path: str) -> int:
    """删某文件的所有节点 + file record（增量重提取前，05 §2.2）。

    引用这些节点的 edges 通过 ``ON DELETE CASCADE`` 自动删。
    返回删的节点数。
    """
    cur = conn.execute("DELETE FROM nodes WHERE file_path=?", (file_path,))
    conn.execute("DELETE FROM files WHERE path=?", (file_path,))
    return cur.rowcount


def cleanup_orphan_edges(conn: sqlite3.Connection) -> int:
    """删悬空边（引用不存在节点的边）。"""
    cur = conn.execute(
        """DELETE FROM edges WHERE src NOT IN (SELECT id FROM nodes)
           OR dst NOT IN (SELECT id FROM nodes)""")
    return cur.rowcount


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    cur = conn.execute("SELECT value FROM meta WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else None
