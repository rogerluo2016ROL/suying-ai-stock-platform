"""embedding 生成与查询（06 §2/§3，D3 本地 sentence-transformers）。

模型 jinaai/jina-embeddings-v2-base-code（768 维，代码 + 自然语言 + 中文混合训练）。
**lazy import** sentence_transformers：未装（`uv sync --extra semantic`）→
`model_available()` False → semantic.py 降级 FTS，功能不中断。

embedding 输入：name + signature + file_path（确定性字段）。
**偏离 06 §2**：设计原定 summary + name，但 LLM summary 层（07 §5）未实现、summary 恒
None，故暂用确定性字段替代；summary 层落地后此处升级输入即可，存储/检索不变。
"""

from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache

MODEL = "jinaai/jina-embeddings-v2-base-code"
DIM = 768


def model_available() -> bool:
    """sentence_transformers 是否可 import（不触发模型下载）。"""
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


@lru_cache(maxsize=1)
def _encoder():
    """加载模型（首次调用触发 ~90MB 下载 + torch，后续复用）。"""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL)


def _node_text(name: str, signature: str | None, file_path: str) -> str:
    parts = [name]
    if signature:
        parts.append(signature)
    parts.append(file_path)
    return "\n".join(parts)


def embed_nodes(db: sqlite3.Connection, batch_size: int = 64) -> dict:
    """扫全部 nodes → 生成 embedding → upsert embeddings 表（幂等，ON CONFLICT 覆盖）。

    归一化向量（normalize_embeddings=True）→ 余弦相似度 = 点积，检索侧无需再除模。
    返回统计 dict；模型未装时 skipped 提示装 extra。
    """
    if not model_available():
        return {"embedded": 0, "skipped": "sentence-transformers 未装 — uv sync --extra semantic"}
    enc = _encoder()
    rows = db.execute("SELECT id, name, signature, file_path FROM nodes").fetchall()
    if not rows:
        return {"embedded": 0, "skipped": "无节点（先 codemap build）"}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        texts = [_node_text(r[1], r[2], r[3]) for r in batch]
        vecs = enc.encode(texts, normalize_embeddings=True)
        for (nid, *_), vec in zip(batch, vecs):
            db.execute(
                "INSERT INTO embeddings(node_id, model, vector, dim, built_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(node_id) DO UPDATE SET "
                "model=excluded.model, vector=excluded.vector, dim=excluded.dim, built_at=excluded.built_at",
                (nid, MODEL, vec.astype("float32").tobytes(), DIM, now),
            )
        n += len(batch)
    return {"embedded": n, "model": MODEL, "dim": DIM}


def embed_query(query: str):
    """查询文本 → 归一化向量（np.ndarray）。"""
    return _encoder().encode([query], normalize_embeddings=True)[0]
