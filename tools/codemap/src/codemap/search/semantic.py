"""语义检索（06 §1 / §5）：embedding 可选 + 三态降级。

D3 决策（2026-07-07）：本地 sentence-transformers（jina-code-v2）。装了 semantic extra
且跑了 `codemap embed` → semantic 余弦检索；否则降级 keyword（FTS5 → name LIKE）。
"""

from __future__ import annotations
import sqlite3

from codemap.search.keyword import search as keyword_search


def search(query: str, db: sqlite3.Connection, limit: int = 15) -> tuple[list[dict], str]:
    """返回 (结果, 来源标签)。三态降级：semantic 余弦 → keyword FTS → keyword LIKE。

    归一化向量（embedder 存时已 normalize）→ 点积 = 余弦，检索侧无需再除模。
    任何 semantic 路径异常（模型未装 / 表空 / encode 失败）→ 静默降级 keyword。
    """
    if embedding_available(db):
        try:
            import numpy as np
            from codemap.search.embedder import embed_query
            qv = embed_query(query)
            rows = db.execute("SELECT node_id, vector FROM embeddings").fetchall()
            if rows:
                mat = np.array([np.frombuffer(r[1], dtype=np.float32) for r in rows])
                ids = [r[0] for r in rows]
                sims = mat @ qv  # 归一化 → 点积即余弦
                top = np.argsort(-sims)[:limit]
                out, seen = [], set()
                for i in top:
                    nid = ids[i]
                    if nid in seen:
                        continue
                    node = db.execute(
                        "SELECT id, type, name, file_path FROM nodes WHERE id=?", (nid,)
                    ).fetchone()
                    if node:
                        out.append({"id": node[0], "type": node[1], "name": node[2], "file_path": node[3]})
                        seen.add(nid)
                if out:
                    return out, "semantic（jina-code-v2 余弦）"
        except Exception:
            pass  # 降级 keyword（模型未装 / encode 失败 / numpy 缺等）
    return keyword_search(query, db, limit), "keyword（semantic 未启用或失败，降级 FTS）"


def embedding_available(db: sqlite3.Connection) -> bool:
    """embeddings 表非空 且 sentence-transformers 可 import（不触发模型下载）。"""
    from codemap.search.embedder import model_available
    if not model_available():
        return False
    try:
        return db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] > 0
    except sqlite3.OperationalError:
        return False
