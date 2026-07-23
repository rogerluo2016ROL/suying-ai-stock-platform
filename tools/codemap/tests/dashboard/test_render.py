"""dashboard.render 单测（10）。"""

from pathlib import Path

from codemap.builder import build
from codemap.dashboard.render import render


def test_render_produces_self_contained_html(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "mod.py").write_text("def foo():\n    pass\n")
    (tmp_path / "app" / "util.py").write_text("from app import mod\n")
    build(tmp_path, tmp_path / "t.db")

    out = tmp_path / "dash.html"
    stats = render(tmp_path / "t.db", out)
    assert stats["nodes"] >= 3   # __init__ + mod + util + foo
    assert out.is_file()

    html = out.read_text(encoding="utf-8")
    # 自包含 cytoscape
    assert "cytoscape" in html
    assert "const GRAPH = " in html
    # 注入了图谱数据（含节点 label）
    assert "foo" in html
    # 节点/边计数
    assert "节点" in html


def test_render_creates_parent_dir(tmp_path):
    (tmp_path / "x.py").write_text("x = 1\n")
    build(tmp_path, tmp_path / "t.db")
    out = tmp_path / "sub" / "nest" / "dash.html"
    render(tmp_path / "t.db", out)
    assert out.is_file()


def test_render_only_files_filters_to_file_deps(tmp_path):
    """only_files=True → 只 file 节点 + imports 边（过滤符号节点 + contains 边）。"""
    import json, re
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "mod.py").write_text("def foo():\n    pass\n")  # 符号 foo 应被过滤
    (tmp_path / "app" / "util.py").write_text("from app import mod\n")
    build(tmp_path, tmp_path / "t.db")
    out = tmp_path / "files.html"
    stats = render(tmp_path / "t.db", out, only_files=True)
    g = json.loads(re.search(r'const GRAPH = ({.*?});', out.read_text(encoding="utf-8"), re.S).group(1))
    assert {n["data"]["type"] for n in g["nodes"]} == {"file"}    # 无符号节点
    assert {e["data"]["label"] for e in g["edges"]} == {"imports"}  # 无 contains
    assert stats["nodes"] == 3                                     # __init__ + mod + util
    assert stats["edges"] == 1                                     # util → __init__


def test_render_has_legend_and_collapse(tmp_path):
    """dashboard 含颜色图例 + 双击折叠邻居交互。"""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "mod.py").write_text("def foo():\n    pass\n")
    build(tmp_path, tmp_path / "t.db")
    html = render(tmp_path / "t.db", tmp_path / "dash.html").get("out")
    html = open(html, encoding="utf-8").read()
    assert 'id="legend"' in html        # 图例容器
    assert "dbltap" in html             # 双击事件
    assert ".collapsed" in html or "collapsed" in html  # 折叠态样式


def test_render_node_indegree_injected(tmp_path):
    """节点注入 indegree/outdegree + graph.maxIn（驱动节点大小编码 + 侧边栏）。"""
    import json, re
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("import a\n")
    (tmp_path / "c.py").write_text("import a\n")
    build(tmp_path, tmp_path / "t.db")
    out = render(tmp_path / "t.db", tmp_path / "d.html")["out"]
    g = json.loads(re.search(r"const GRAPH = ({.*?});", open(out, encoding="utf-8").read(), re.S).group(1))
    by_id = {n["data"]["id"]: n["data"] for n in g["nodes"]}
    assert by_id["file:a.py"]["indegree"] == 2     # b + c → a
    assert by_id["file:b.py"]["outdegree"] == 1
    assert g["maxIn"] == 2


def test_mermaid_and_dot_exports(tmp_path):
    """mermaid/dot 导出图代码（GitHub 渲染 / graphviz 渲染）。"""
    import sqlite3
    from codemap.dashboard.export import mermaid, dot
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("import a\n")
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    mm = mermaid(db)
    assert "```mermaid" in mm and "graph LR" in mm and "-->" in mm
    dt = dot(db)
    assert "digraph G" in dt and "->" in dt


def test_render_label_threshold_for_high_indegree_nodes(tmp_path):
    """高入度节点默认显示文件名 label：threshold=2 时 indegree>=2 的节点样式 text-opacity=1。"""
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("import a\n")
    (tmp_path / "c.py").write_text("import a\n")
    build(tmp_path, tmp_path / "t.db")
    out = tmp_path / "dash.html"
    render(tmp_path / "t.db", out, label_threshold=2)
    html = out.read_text(encoding="utf-8")
    assert "const LABEL_THRESHOLD = 2;" in html
    assert "node[indegree >= 2]" in html
    assert "'text-opacity': 1" in html


def test_render_label_threshold_default_injected(tmp_path):
    """默认 label_threshold=8 会被注入模板。"""
    (tmp_path / "a.py").write_text("x = 1\n")
    build(tmp_path, tmp_path / "t.db")
    out = tmp_path / "dash.html"
    render(tmp_path / "t.db", out)
    assert "const LABEL_THRESHOLD = 8;" in out.read_text(encoding="utf-8")


def test_render_degree_uses_full_graph_not_truncated_subset(tmp_path):
    """N-6：节点入度须基于**全图**边，非截断子集——否则被 max_nodes 截断掉的 importer 不计
    度数，真 hub（入度 N）在截断后显示 < N → 节点大小 / label_threshold 误判。"""
    import re
    # hub.py 被 12 个 importer import（真入度 12）；'hub' 字母序最前，确保进截断集
    for i in range(12):
        (tmp_path / f"z{i}.py").write_text("import hub\n")
    (tmp_path / "hub.py").write_text("x = 1\n")
    build(tmp_path, tmp_path / "t.db")
    out = tmp_path / "dash.html"
    render(tmp_path / "t.db", out, max_nodes=5, only_files=True)  # 截断到 5（hub + 4 importer）
    html = out.read_text(encoding="utf-8")
    m = re.search(r'"id":\s*"file:hub\.py"[^}]*"indegree":\s*(\d+)', html)
    assert m, "N-6: file:hub.py node not in truncated render"
    assert int(m.group(1)) == 12, (
        f"N-6: hub.py true indegree should be 12 (full-graph degree), got {m.group(1)} (truncated-subset bug)")
