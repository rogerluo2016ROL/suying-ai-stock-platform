"""变更影响分析（05 §1）：反向 import 边 BFS + blast radius + 风险评分。

边方向（05 §1.1）：imports 边 src=importer（依赖方），dst=imported（被依赖方）。
改了 B → 反向找 ``WHERE dst=B`` 的所有 src（谁 import 我）→ BFS N-hop。
"""

from __future__ import annotations
import sqlite3


def analyze_impact(changed_files: list[str], db: sqlite3.Connection, hop: int = 2) -> dict:
    """changed_files（相对路径）→ 反向 import 边 BFS → 受影响节点（N-hop）。"""
    changed_ids = {f"file:{f}" for f in changed_files}
    affected: dict[str, int] = {}  # node_id -> hop_reached
    frontier = list(changed_ids)
    for level in range(1, hop + 1):
        if not frontier:
            break
        ph = ",".join("?" * len(frontier))
        rows = db.execute(
            f"SELECT DISTINCT src FROM edges WHERE dst IN ({ph}) AND type='imports'",
            frontier,
        ).fetchall()
        next_frontier: list[str] = []
        for (importer,) in rows:
            if importer not in changed_ids and importer not in affected:
                affected[importer] = level
                next_frontier.append(importer)
        frontier = next_frontier
    return {"changed": sorted(changed_ids), "affected": affected}


def risk_score(node_id: str, db: sqlite3.Connection) -> tuple[str, int]:
    """fan_in × complexity → 高/中/低。"""
    fan_in = db.execute(
        "SELECT COUNT(*) FROM edges WHERE dst=? AND type='imports'", (node_id,)
    ).fetchone()[0]
    row = db.execute("SELECT complexity FROM nodes WHERE id=?", (node_id,)).fetchone()
    complexity = (row[0] if row else None) or "moderate"
    weight = {"simple": 1, "moderate": 2, "complex": 3}.get(complexity, 2)
    score = fan_in * weight
    level = "高" if score >= 9 else "中" if score >= 3 else "低"
    return level, score


def impact_report(changed_files: list[str], db: sqlite3.Connection, hop: int = 2) -> dict:
    """影响分析 + 每个受影响节点的风险评分。"""
    res = analyze_impact(changed_files, db, hop)
    scored = []
    for node_id, h in res["affected"].items():
        level, score = risk_score(node_id, db)
        scored.append({"node": node_id, "hop": h, "risk": level, "score": score})
    scored.sort(key=lambda x: -x["score"])
    return {"changed": res["changed"], "affected": scored,
            "blast_radius": len(res["changed"]) + len(scored)}
