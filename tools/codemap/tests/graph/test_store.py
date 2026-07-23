"""store.py 单测：建表 + upsert round-trip + 事务 + meta + 悬空边清理。"""

from codemap.graph.store import (
    init_db, upsert_file, upsert_node, upsert_edge,
    transaction, set_meta, get_meta, cleanup_orphan_edges,
)
from codemap.graph.model import FileRecord, NodeRecord, EdgeRecord


def test_round_trip(tmp_path):
    db = init_db(tmp_path / "t.db")
    upsert_file(db, FileRecord(path="src/a.py", language="python", category="code",
                               line_count=10, content_hash="h1"))
    upsert_file(db, FileRecord(path="src/b.py", language="python", category="code",
                               line_count=5, content_hash="h2"))
    upsert_node(db, NodeRecord(id="file:src/a.py", type="file", name="a.py", file_path="src/a.py"))
    upsert_node(db, NodeRecord(id="file:src/b.py", type="file", name="b.py", file_path="src/b.py"))
    upsert_edge(db, EdgeRecord(src="file:src/b.py", dst="file:src/a.py", type="imports"))
    db.commit()

    frow = db.execute("SELECT path, content_hash FROM files WHERE path='src/a.py'").fetchone()
    assert frow == ("src/a.py", "h1")
    erows = db.execute("SELECT src, dst, type FROM edges").fetchall()
    assert ("file:src/b.py", "file:src/a.py", "imports") in erows


def test_upsert_idempotent_overwrites(tmp_path):
    db = init_db(tmp_path / "t.db")
    upsert_file(db, FileRecord(path="a.py", language="python", category="code",
                               line_count=1, content_hash="h1"))
    upsert_file(db, FileRecord(path="a.py", language="python", category="code",
                               line_count=2, content_hash="h2"))
    db.commit()
    row = db.execute("SELECT line_count, content_hash FROM files WHERE path='a.py'").fetchone()
    assert row == (2, "h2")


def test_transaction_rollback(tmp_path):
    db = init_db(tmp_path / "t.db")
    try:
        with transaction(db):
            upsert_file(db, FileRecord(path="a.py", language="python", category="code",
                                       line_count=1, content_hash="h"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    cnt = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert cnt == 0  # 异常 → 回滚


def test_meta_get_set(tmp_path):
    db = init_db(tmp_path / "t.db")
    set_meta(db, "git_commit", "abc123")
    db.commit()
    assert get_meta(db, "git_commit") == "abc123"
    assert get_meta(db, "nonexistent") is None
    # 覆盖
    set_meta(db, "git_commit", "def456")
    db.commit()
    assert get_meta(db, "git_commit") == "def456"


def test_delete_node_cascades_edges(tmp_path):
    """删 node 时引用它的 edges 通过 ON DELETE CASCADE 自动删（FK 双向约束）。"""
    db = init_db(tmp_path / "t.db")
    upsert_file(db, FileRecord(path="a.py", language="python", category="code", line_count=1, content_hash="h1"))
    upsert_file(db, FileRecord(path="b.py", language="python", category="code", line_count=1, content_hash="h2"))
    upsert_node(db, NodeRecord(id="file:a.py", type="file", name="a", file_path="a.py"))
    upsert_node(db, NodeRecord(id="file:b.py", type="file", name="b", file_path="b.py"))
    upsert_edge(db, EdgeRecord(src="file:b.py", dst="file:a.py", type="imports"))
    db.execute("DELETE FROM nodes WHERE id='file:a.py'")  # → 边 (b→a) CASCADE 删
    assert db.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] == 1  # 只剩 b
