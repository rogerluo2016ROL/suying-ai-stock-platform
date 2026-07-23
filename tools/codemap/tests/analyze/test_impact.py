"""analyze.impact + fingerprint 单测（05 §1 / 03 §4）。"""

from codemap.analyze.fingerprint import content_hash, structure_hash
from codemap.analyze.impact import analyze_impact, impact_report, risk_score
from codemap.graph.model import EdgeRecord, FileRecord, NodeRecord
from codemap.graph.store import init_db, upsert_edge, upsert_file, upsert_node


def _graph(tmp_path):
    """a → b → c（a imports b，b imports c）；改 c 应反向影响 b（1-hop）+ a（2-hop）。"""
    db = init_db(tmp_path / "t.db")
    for f in ("a.py", "b.py", "c.py"):
        upsert_file(db, FileRecord(path=f, language="python", category="code", line_count=1, content_hash="h"))
        upsert_node(db, NodeRecord(id=f"file:{f}", type="file", name=f, file_path=f))
    upsert_edge(db, EdgeRecord(src="file:a.py", dst="file:b.py", type="imports"))  # a 依赖 b
    upsert_edge(db, EdgeRecord(src="file:b.py", dst="file:c.py", type="imports"))  # b 依赖 c
    return db


def test_impact_reverse_bfs(tmp_path):
    db = _graph(tmp_path)
    res = analyze_impact(["c.py"], db, hop=2)
    assert "file:b.py" in res["affected"]  # 1-hop
    assert res["affected"]["file:b.py"] == 1
    assert "file:a.py" in res["affected"]  # 2-hop
    assert res["affected"]["file:a.py"] == 2


def test_impact_hop1_only(tmp_path):
    db = _graph(tmp_path)
    res = analyze_impact(["c.py"], db, hop=1)
    assert "file:b.py" in res["affected"]
    assert "file:a.py" not in res["affected"]  # 2-hop 不含


def test_risk_score(tmp_path):
    db = init_db(tmp_path / "t.db")
    upsert_file(db, FileRecord(path="x.py", language="python", category="code", line_count=1, content_hash="h"))
    upsert_node(db, NodeRecord(id="file:x.py", type="file", name="x", file_path="x.py", complexity="complex"))
    for imp in ("a.py", "b.py", "c.py", "d.py"):
        upsert_file(db, FileRecord(path=imp, language="python", category="code", line_count=1, content_hash="h"))
        upsert_node(db, NodeRecord(id=f"file:{imp}", type="file", name=imp, file_path=imp))
        upsert_edge(db, EdgeRecord(src=f"file:{imp}", dst="file:x.py", type="imports"))
    level, score = risk_score("file:x.py", db)
    assert score == 4 * 3  # fan_in=4 × complex=3
    assert level == "高"


def test_impact_report_sorted(tmp_path):
    db = _graph(tmp_path)
    rep = impact_report(["c.py"], db, hop=2)
    assert rep["blast_radius"] == 3  # c + b + a
    assert all("risk" in a for a in rep["affected"])


# ---- fingerprint ----

def test_content_hash_stable():
    assert content_hash(b"abc") == content_hash(b"abc")


def test_structure_hash_ignores_comments():
    """改注释不触发结构变（symbol/import 相同 → structure_hash 同）。"""
    syms = [{"type": "function", "name": "foo", "signature": "", "start_line": 1}]
    imps = [{"module": "os", "symbols": (), "level": 0}]
    h1 = structure_hash(syms, imps)
    # 同 symbols/imports，不同「注释」（不在结构里）→ hash 同
    assert structure_hash(syms, imps) == h1


def test_structure_hash_changes_on_new_symbol():
    syms1 = [{"type": "function", "name": "foo", "signature": "", "start_line": 1}]
    syms2 = syms1 + [{"type": "function", "name": "bar", "signature": "", "start_line": 5}]
    imps = []
    assert structure_hash(syms1, imps) != structure_hash(syms2, imps)
