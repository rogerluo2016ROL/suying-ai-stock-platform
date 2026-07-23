"""search 单测（06）：keyword FTS + semantic 降级。"""

import sqlite3
import pytest

from codemap.builder import build
from codemap.search.keyword import search as kw_search
from codemap.search.semantic import embedding_available, search as sem_search


def _proj(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "auth.py").write_text("def login():\n    pass\n\ndef logout():\n    pass\n")
    build(tmp_path, tmp_path / "t.db")
    return sqlite3.connect(str(tmp_path / "t.db"))


def test_keyword_search_finds_function(tmp_path):
    db = _proj(tmp_path)
    res = kw_search("login", db)
    names = {r["name"] for r in res}
    assert "login" in names


def test_keyword_search_fallback_like(tmp_path):
    """FTS MATCH 特殊字符 → fallback LIKE 仍能找。"""
    db = _proj(tmp_path)
    res = kw_search("auth", db)
    assert any("auth" in r["file_path"] for r in res)


def test_semantic_degrades_to_keyword(tmp_path):
    """M5：embedding 未启用 → semantic 降级 keyword。"""
    db = _proj(tmp_path)
    assert embedding_available(db) is False
    results, source = sem_search("login", db)
    assert "keyword" in source
    assert any(r["name"] == "login" for r in results)


def test_embedding_available_requires_model(tmp_path, monkeypatch):
    """embeddings 表有数据但 sentence-transformers 未装 → False（降级 FTS）。"""
    from codemap.search import embedder
    db = _proj(tmp_path)
    monkeypatch.setattr(embedder, "model_available", lambda: False)
    # 即使塞了 embeddings 数据
    db.execute("INSERT INTO embeddings(node_id, model, vector, dim, built_at) "
               "VALUES ('function:x', 'm', X'00', 1, 'now')")
    assert embedding_available(db) is False


def test_embedding_available_true_when_model_and_data(tmp_path, monkeypatch):
    """模型可装 + embeddings 有数据 → True。"""
    from codemap.search import embedder
    db = _proj(tmp_path)
    monkeypatch.setattr(embedder, "model_available", lambda: True)
    db.execute("INSERT INTO embeddings(node_id, model, vector, dim, built_at) "
               "VALUES ('function:x', 'm', X'00', 1, 'now')")
    assert embedding_available(db) is True


def test_search_semantic_path(tmp_path, monkeypatch):
    """semantic 成功路径：mock 模型 + 查询向量与某节点同向 → 命中该节点。

    需 numpy（semantic extra）；dev extra 未装时跳过。"""
    np = pytest.importorskip("numpy")
    from codemap.search import embedder
    db = _proj(tmp_path)
    monkeypatch.setattr(embedder, "model_available", lambda: True)
    node = db.execute("SELECT id FROM nodes WHERE name='login'").fetchone()
    assert node, "夹具应有 login 节点"
    nid = node[0]
    vec = np.zeros(8, dtype=np.float32); vec[0] = 1.0
    db.execute("INSERT INTO embeddings(node_id, model, vector, dim, built_at) VALUES (?,?,?,?,?)",
               (nid, "test", vec.tobytes(), 8, "now"))
    qv = np.zeros(8, dtype=np.float32); qv[0] = 1.0
    monkeypatch.setattr(embedder, "embed_query", lambda q: qv)
    results, source = sem_search("任意查询（走 semantic）", db)
    assert "semantic" in source
    assert any(r["name"] == "login" for r in results)
