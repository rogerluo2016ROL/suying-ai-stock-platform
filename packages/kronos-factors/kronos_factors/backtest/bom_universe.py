"""Cutoff-aware BOM universe reconstruction helpers.

The OOS script uses these helpers to rebuild a company -> BOM node mapping from
cache snapshots that were visible at a historical cutoff. The functions are
pure DataFrame transforms so the universe rule is testable without PG access.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


NODE_KEYWORDS: dict[str, list[str]] = {
    "reducer": ["减速器", "谐波减速", "行星减速", "RV减速"],
    "motor": ["电机", "空心杯", "无框电机", "步进电机"],
    "bearing": ["轴承"],
    "controller": ["控制器", "运动控制", "控制系统"],
}


def _date_key(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return re.sub(r"\D", "", text)[:8]


def _code6(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)[-6:]


def _number(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def infer_embodied_node(text: str) -> str | None:
    """Infer the embodied-AI BOM node from a product/evidence text."""
    haystack = str(text or "")
    for node, keywords in NODE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return node
    return None


def _visible_rows(df: pd.DataFrame | None, code: str, date_col: str, cutoff_yyyymmdd: str) -> pd.DataFrame:
    if df is None or df.empty or "code6" not in df.columns or date_col not in df.columns:
        return pd.DataFrame()
    work = df.copy()
    work["_code6"] = work["code6"].map(_code6)
    work["_date_key"] = work[date_col].map(_date_key)
    return work[(work["_code6"] == code) & (work["_date_key"] <= cutoff_yyyymmdd)]


def has_visible_node_evidence(
    code: str,
    node: str,
    product: str,
    *,
    qa_df: pd.DataFrame | None,
    research_df: pd.DataFrame | None,
    cutoff_yyyymmdd: str,
) -> bool:
    """Return True when QA/research before cutoff mentions the node or product."""
    code = _code6(code)
    product = str(product or "")
    keywords = NODE_KEYWORDS.get(node, [])
    texts: list[str] = []

    qa = _visible_rows(qa_df, code, "trade_date", cutoff_yyyymmdd)
    for _, row in qa.iterrows():
        texts.append(f"{row.get('q', '')} {row.get('a', '')}")

    research = _visible_rows(research_df, code, "trade_date", cutoff_yyyymmdd)
    for _, row in research.iterrows():
        texts.append(f"{row.get('title', '')} {row.get('report_type', '')} {row.get('ind_name', '')}")

    for text in texts:
        if product and product in text:
            return True
        if any(keyword in text for keyword in keywords):
            return True
    return False


def build_cutoff_universe_from_cache(
    *,
    mainbz_df: pd.DataFrame,
    qa_df: pd.DataFrame | None,
    research_df: pd.DataFrame | None,
    cutoff_yyyymmdd: str,
    min_main_pct: float = 0.0,
    require_evidence: bool = False,
) -> dict[str, tuple[str, str, float]]:
    """Build {code6: (node, product, main_ratio_pct)} visible at cutoff.

    The latest `fina_mainbz` period at or before the cutoff is used per company.
    `bz_sales` is converted to a same-period product revenue share, avoiding the
    previous fixed-universe mode's current-snapshot and absolute-sales bias.
    """
    if mainbz_df.empty:
        return {}

    work = mainbz_df.copy()
    required = {"code6", "end_date", "bz_item", "bz_sales"}
    missing = required - set(work.columns)
    if missing:
        raise ValueError(f"mainbz_df missing columns: {sorted(missing)}")

    work["_code6"] = work["code6"].map(_code6)
    work["_end_key"] = work["end_date"].map(_date_key)
    work["_sales"] = work["bz_sales"].map(_number)
    visible = work[(work["_code6"] != "") & (work["_end_key"] != "") & (work["_end_key"] <= cutoff_yyyymmdd)]
    if visible.empty:
        return {}

    universe: dict[str, tuple[str, str, float]] = {}
    for code, group in visible.groupby("_code6"):
        latest_end = group["_end_key"].max()
        period = group[group["_end_key"] == latest_end].copy()
        total_sales = float(period["_sales"].clip(lower=0).sum())
        if total_sales <= 0:
            continue

        candidates: list[tuple[float, str, str, float]] = []
        for _, row in period.iterrows():
            product = str(row.get("bz_item") or "")
            node = infer_embodied_node(product)
            if not node:
                continue
            sales = max(float(row["_sales"]), 0.0)
            ratio = round(sales / total_sales * 100, 2)
            if ratio < min_main_pct:
                continue
            if require_evidence and not has_visible_node_evidence(
                code,
                node,
                product,
                qa_df=qa_df,
                research_df=research_df,
                cutoff_yyyymmdd=cutoff_yyyymmdd,
            ):
                continue
            candidates.append((sales, node, product, ratio))

        if candidates:
            _, node, product, ratio = max(candidates, key=lambda item: item[0])
            universe[code] = (node, product, ratio)

    return dict(sorted(universe.items()))
