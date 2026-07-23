"""dashboard 渲染（10 §4）：自包含静态 HTML（cytoscape CDN）。

节点大小编码入度（高扇入自动变大，一眼看出架构重心）；右侧侧边栏点节点显示
邻居列表（谁依赖它 / 它依赖谁）+ 入/出度。
"""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>codemap dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.30.0/dist/cytoscape.min.js"></script>
<style>
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,sans-serif;font-size:13px}
  #bar{padding:6px 10px;background:#f4f4f4;border-bottom:1px solid #ddd;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  #bar b{color:#36c}
  #search{padding:4px 8px;width:200px;border:1px solid #bbb;border-radius:4px;font-size:13px}
  .chip{cursor:pointer;padding:2px 9px;border:1px solid #999;border-radius:11px;background:#fff;font-size:11px;user-select:none;white-space:nowrap}
  .chip.off{opacity:.32;text-decoration:line-through}
  #legend{font-size:11px;color:#555;display:flex;gap:8px;flex-wrap:wrap}
  #legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:3px;vertical-align:middle}
  #hint{margin-left:auto;color:#999;font-size:11px}
  #main{display:flex;height:calc(100vh - 36px)}
  #cy{flex:1}
  #sidebar{width:300px;border-left:1px solid #ddd;background:#fafafa;overflow-y:auto;padding:10px}
  #sb-empty{color:#999;padding:20px 0;text-align:center}
  #sb-title{margin:0 0 4px;font-size:15px;color:#222;word-break:break-all}
  #sb-path{font-size:11px;color:#66d;background:#eef;padding:3px 6px;border-radius:3px;word-break:break-all;font-family:monospace}
  .stats{margin:8px 0;font-size:12px;color:#555}
  .stats b{color:#e80;font-size:14px}
  .section{margin-top:10px;font-size:12px;color:#555;border-top:1px solid #eee;padding-top:6px}
  .section .lbl{font-weight:bold;color:#333;margin-bottom:3px;display:block}
  .nb{padding:2px 6px;margin:2px 0;background:#fff;border:1px solid #e5e5e5;border-radius:3px;font-size:11px;cursor:pointer;word-break:break-all}
  .nb:hover{background:#eef;border-color:#99c}
  .nb.more{color:#999;font-style:italic}
</style></head><body>
<div id="bar">
  <b id="meta"></b>
  <input id="search" placeholder="搜索文件名…" />
  <span id="filters"></span>
  <span id="legend"></span>
  <span id="hint">hover 显名·点节点看详情·双击折叠·chip 过滤</span>
</div>
<div id="main">
  <div id="cy"></div>
  <aside id="sidebar"><div id="sb-empty">点节点看详情<br/>（邻居 + 入/出度）</div></aside>
</div>
<script>
const GRAPH = __GRAPH_JSON__;
const LABEL_THRESHOLD = __LABEL_THRESHOLD__;
const COLORS = {file:'#69b',function:'#7a7',class:'#e95',method:'#fc6',schema:'#a6f',service:'#9cf',config:'#bbb',module:'#9ae'};
const maxIn = GRAPH.maxIn || 50;
const cy = cytoscape({
  container: document.getElementById('cy'),
  elements: [...GRAPH.nodes, ...GRAPH.edges],
  style: [
    {selector:'node', style:{'background-color':'data(color)',
      'width':'mapData(indegree,0,'+maxIn+',14,46)','height':'mapData(indegree,0,'+maxIn+',14,46)',
      'label':'data(label)','font-size':10,'text-valign':'bottom','text-margin-y':3,
      'text-opacity':0,'text-background-color':'#fffbe6','text-background-opacity':0.9,'text-background-padding':1}},
    {selector:'node.hover', style:{'text-opacity':1}},
    {selector:'node.match', style:{'border-width':3,'border-color':'#e80','text-opacity':1}},
    {selector:'node.collapsed', style:{'border-width':3,'border-style':'dashed','border-color':'#333'}},
    {selector:'edge', style:{'width':1,'line-color':'#bbb','target-arrow-shape':'triangle','curve-style':'bezier','opacity':0.35}},
    {selector:'.faded', style:{'opacity':0.06}},
  ],
  layout: {name: 'cose', animate: false, nodeRepulsion: 10000, idealEdgeLength: 120, padding: 20}
});
// 关键大节点（高入度）始终显示文件名 label
cy.style().selector('__KEY_NODE_SELECTOR__').style({
  'text-opacity': 1,
  'font-size': 11,
  'font-weight': 'bold',
  'color': '#333',
  'text-background-color': '#fffbe6',
  'text-background-opacity': 0.95
}).update();
// 图例 + 类型过滤 chip
const present = [...new Set(GRAPH.nodes.map(n => n.data.type))].sort();
const activeTypes = new Set(present);
const filtersEl = document.getElementById('filters');
const legendEl = document.getElementById('legend');
present.forEach(t => {
  const c = COLORS[t] || '#888';
  const chip = document.createElement('span'); chip.className='chip'; chip.textContent=t; chip.style.borderColor=c;
  chip.onclick = () => {
    if (activeTypes.has(t)) { activeTypes.delete(t); chip.classList.add('off'); }
    else { activeTypes.add(t); chip.classList.remove('off'); }
    cy.nodes().forEach(n => n.style('display', activeTypes.has(n.data('type')) ? 'element' : 'none'));
  };
  filtersEl.appendChild(chip);
  const li = document.createElement('span'); li.innerHTML='<i style="background:'+c+'"></i>'+t;
  legendEl.appendChild(li);
});
// hover 显 label
cy.on('mouseover','node', e => e.target.addClass('hover'));
cy.on('mouseout','node', e => e.target.removeClass('hover'));
// 点节点 → 侧边栏详情
const sb = document.getElementById('sidebar');
function showDetail(n) {
  document.getElementById('meta').textContent = n.data('label') + ' [' + n.data('id') + ']';
  const incomers = n.incomers().nodes().sort((a,b)=>b.data('indegree')-a.data('indegree'));
  const outgoers = n.outgoers().nodes().sort((a,b)=>b.data('indegree')-a.data('indegree'));
  const nbHtml = (list, lim=30) => list.length ?
    list.slice(0,lim).map(x=>`<div class="nb" data-id="${x.data('id')}">${x.data('label')}</div>`).join('') +
    (list.length>lim?`<div class="nb more">… 还有 ${list.length-lim}</div>`:'') : '<div class="nb more">（无）</div>';
  sb.innerHTML = `<h3 id="sb-title">${n.data('label')}</h3>
    <div id="sb-path">${n.data('id').replace(/^\\w+:/,'')}</div>
    <div class="stats">入度 <b>${n.data('indegree')}</b> · 出度 <b>${n.data('outdegree')}</b> · 类型 ${n.data('type')}</div>
    <div class="section"><span class="lbl">被依赖（${incomers.length}）—— 谁指向它</span>${nbHtml(incomers)}</div>
    <div class="section"><span class="lbl">依赖（${outgoers.length}）—— 它指向谁</span>${nbHtml(outgoers)}</div>`;
  // 点邻居 → 跳转聚焦
  sb.querySelectorAll('.nb[data-id]').forEach(el => el.onclick = () => {
    const t = cy.getElementById(el.dataset.id);
    if (t.length) { cy.animate({center:{eles:t},zoom:1.5},{duration:250}); showDetail(t); t.addClass('hover'); setTimeout(()=>t.removeClass('hover'),800); }
  });
}
cy.on('tap','node', e => showDetail(e.target));
// 双击折叠
cy.on('dbltap','node', e => {
  const n = e.target; const nb = n.openNeighborhood().nodes();
  if (n.data('_collapsed')) { nb.show(); n.data('_collapsed',false); n.removeClass('collapsed'); }
  else { nb.hide(); n.data('_collapsed',true); n.addClass('collapsed'); }
});
// 搜索
const search = document.getElementById('search'); const meta = document.getElementById('meta');
const totalTxt = GRAPH.nodes.length + ' 节点 / ' + GRAPH.edges.length + ' 边';
search.oninput = () => {
  const q = search.value.trim().toLowerCase();
  cy.nodes().removeClass('match'); cy.elements().removeClass('faded');
  if (!q) { meta.textContent = totalTxt; return; }
  const m = cy.nodes().filter(n => n.data('label').toLowerCase().includes(q) || n.data('id').toLowerCase().includes(q));
  m.addClass('match'); cy.elements().not(m).not(m.connectedEdges()).addClass('faded');
  meta.textContent = '匹配 ' + m.length + ' / ' + cy.nodes().length;
  if (m.length && m.length <= 200) cy.animate({fit:{eles:m, padding:40}}, {duration:300});
};
meta.textContent = totalTxt;
</script></body></html>"""


def render(db_path: str | Path, out_path: str | Path, max_nodes: int = 2000,
           only_files: bool = False, label_threshold: int = 8) -> dict:
    """读 SQLite → 注入模板 → 写静态 HTML。返回 {nodes, edges, out}。

    only_files=True → 只渲染 file 节点 + imports 边（文件依赖图），过滤掉符号节点与
    contains/calls 边。节点注入 indegree/outdegree（入度驱动节点大小编码 + 侧边栏显示）。
    """
    db = sqlite3.connect(str(db_path))
    node_where = "WHERE type='file'" if only_files else ""
    edge_where = "AND type='imports'" if only_files else ""
    # N-6 修：degree 须基于**全图**边（截断前 GROUP BY 算），否则 max_nodes 截断掉的
    # importer 不计度数，真 hub 在截断后显示 < 真实入度 → 节点大小 / label_threshold 误判。
    in_deg = dict(db.execute(
        f"SELECT dst, COUNT(*) FROM edges "
        f"WHERE dst IN (SELECT id FROM nodes {node_where}) {edge_where} GROUP BY dst"
    ).fetchall())
    out_deg = dict(db.execute(
        f"SELECT src, COUNT(*) FROM edges "
        f"WHERE src IN (SELECT id FROM nodes {node_where}) {edge_where} GROUP BY src"
    ).fetchall())
    # 截断节点（LIMIT max_nodes），注入**全图** degree
    node_rows = db.execute(
        f"SELECT id, type, name FROM nodes {node_where} LIMIT ?", (max_nodes,)
    ).fetchall()
    node_ids = {r[0] for r in node_rows}
    nodes = [{"data": {"id": r[0], "label": r[2], "color": _color(r[1]), "type": r[1],
                       "indegree": in_deg.get(r[0], 0), "outdegree": out_deg.get(r[0], 0)}}
             for r in node_rows]
    # edges：截断集内（图渲染用；degree 已用全图算过，见上）
    edges = []
    if node_ids:
        ph = ",".join("?" * len(node_ids))
        for src, dst, etype in db.execute(
            f"SELECT src, dst, type FROM edges WHERE src IN ({ph}) AND dst IN ({ph}) {edge_where}",
            (*node_ids, *node_ids),
        ).fetchall():
            edges.append({"data": {"source": src, "target": dst, "label": etype}})
    max_in = max((n["data"]["indegree"] for n in nodes), default=1)
    graph = {
        "nodes": nodes,
        "edges": edges,
        "maxIn": max_in,
        "project": dict(db.execute(
            "SELECT key, value FROM meta WHERE key IN ('git_commit','analyzed_at')"
        ).fetchall()),
    }
    html = _TEMPLATE.replace("__GRAPH_JSON__", json.dumps(graph, ensure_ascii=False)).replace("__LABEL_THRESHOLD__", str(label_threshold)).replace("__KEY_NODE_SELECTOR__", f"node[indegree >= {label_threshold}]")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    return {"nodes": len(nodes), "edges": len(edges), "out": str(out_path)}


def _color(node_type: str) -> str:
    return {
        "file": "#69b", "function": "#7a7", "class": "#e95", "method": "#fc6",
        "schema": "#a6f", "service": "#9cf", "config": "#bbb", "module": "#9ae",
    }.get(node_type, "#888")
