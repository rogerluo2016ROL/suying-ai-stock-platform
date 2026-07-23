"""双指纹（03 §4 / 05 §3）：content_hash + structure_hash。

structure_hash 只看结构（符号 + import 规范化），不看注释/空白/字面量 → 改注释不触发结构重算。
"""

from __future__ import annotations
import hashlib
import json


def content_hash(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def structure_hash(symbols: list[dict], imports: list[dict]) -> str:
    """canonical(symbols + imports) → sha256。

    symbols: [{type, name, signature, start_line}, ...]
    imports: [{module, symbols, level}, ...]
    """
    syms = sorted(
        (s.get("type", ""), s.get("name", ""), s.get("signature", ""), s.get("start_line", 0))
        for s in symbols
    )
    imps = sorted(
        (i.get("module") or "", tuple(sorted(i.get("symbols") or ())), i.get("level", 0))
        for i in imports
    )
    payload = json.dumps({"symbols": syms, "imports": imps}, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()
