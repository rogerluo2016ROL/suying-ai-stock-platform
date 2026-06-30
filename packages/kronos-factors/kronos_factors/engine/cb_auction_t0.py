"""竞价选债 T+0 model.

The model starts from stock limit-up auction events, maps trigger stocks to
THS concepts, and returns related convertible bonds sorted by theme relevance.
Risk fields are annotations only.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any


FD_AMOUNT_MIN = 1_000_000_000
AUCTION_FIRST_TIME_MAX = "09:30:00"

NOISE_CONCEPT_KEYWORDS = (
    "同花顺",
    "(A股)",
    "昨日",
    "百日",
    "首板",
    "重仓",
    "新高",
    "减持",
    "盈利",
    "股息",
    "估值",
    "动量",
    "大盘",
    "小盘",
    "主板",
    "全A",
    "均衡",
)
NOISE_CONCEPT_NAMES = {
    "浙江",
    "江苏",
    "广东",
    "上海",
    "北京",
    "深圳",
    "山东",
    "福建",
    "安徽",
    "四川",
    "湖北",
    "湖南",
    "河南",
    "河北",
}


def _normalize_stock_code(value: str | None) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    return raw.split(".", 1)[0] if "." in raw else raw


def _is_noise_concept(name: str | None) -> bool:
    if not name:
        return True
    text = str(name).strip()
    if text in NOISE_CONCEPT_NAMES:
        return True
    return any(keyword in text for keyword in NOISE_CONCEPT_KEYWORDS)


def _risk_notes(row: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    call_status = row.get("call_status") or ""
    premium_rate = row.get("premium_rate")
    cb_amount = row.get("cb_amount")
    remain_size = row.get("remain_size")
    delist_date = row.get("delist_date")

    if call_status in {"公告实施强赎", "公告提示强赎", "已满足强赎条件", "公告到期赎回"}:
        notes.append("强赎中" if call_status == "公告实施强赎" else call_status)
    if premium_rate is not None and float(premium_rate) >= 50:
        notes.append(f"高溢价{float(premium_rate):.1f}%")
    if cb_amount is not None and float(cb_amount) < 10_000_000:
        notes.append(f"成交额偏低{float(cb_amount) / 10_000:.1f}万")
    if remain_size is not None and float(remain_size) >= 1_000_000_000:
        notes.append(f"剩余规模{float(remain_size) / 100_000_000:.2f}亿")
    if delist_date:
        notes.append(f"退市日期{delist_date}")
    return notes


def _theme_score(row: dict[str, Any]) -> float:
    direct = 1000.0 if row.get("is_direct_trigger") else 0.0
    concept_hits = float(row.get("matched_concept_count") or 0) * 100.0
    trigger_count = float(row.get("trigger_stock_count_sum") or 0) * 10.0
    fd_amount = min(float(row.get("matched_fd_amount") or 0) / 100_000_000, 100.0)
    concept_size = float(row.get("concept_size_min") or 9999)
    narrow_bonus = max(0.0, 50.0 - min(concept_size, 50.0))
    return round(direct + concept_hits + trigger_count + fd_amount + narrow_bonus, 4)


class CbAuctionT0Engine:
    """竞价选债 T+0 engine."""

    def __init__(self, pg_url: str | None = None):
        self.pg_url = pg_url or os.environ.get(
            "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"
        )
        self._conn = None

    @property
    def db(self):
        if self._conn is None or getattr(self._conn, "closed", False):
            import psycopg2

            self._conn = psycopg2.connect(self.pg_url)
        return self._conn

    def close(self) -> None:
        if self._conn and not getattr(self._conn, "closed", True):
            self._conn.close()

    def _assemble_result(
        self,
        trade_date: str,
        triggers: list[dict[str, Any]],
        concepts: list[dict[str, Any]],
        raw_bonds: list[dict[str, Any]],
        top_n: int | None,
        rejections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        trigger_codes = {row["trigger_stock_code"] for row in triggers}
        merged: dict[str, dict[str, Any]] = {}

        for row in raw_bonds:
            cb_code = row["cb_code"]
            current = merged.get(cb_code)
            if current is None:
                current = dict(row)
                current["matched_concepts"] = sorted(set(row.get("matched_concepts") or []))
                current["trigger_sources"] = sorted(set(row.get("trigger_sources") or []))
                merged[cb_code] = current
            else:
                current["matched_concepts"] = sorted(
                    set(current.get("matched_concepts") or []) | set(row.get("matched_concepts") or [])
                )
                current["trigger_sources"] = sorted(
                    set(current.get("trigger_sources") or []) | set(row.get("trigger_sources") or [])
                )
                current["matched_concept_count"] = len(current["matched_concepts"])
                current["trigger_stock_count_sum"] = max(
                    int(current.get("trigger_stock_count_sum") or 0),
                    int(row.get("trigger_stock_count_sum") or 0),
                )
                current["matched_fd_amount"] = max(
                    float(current.get("matched_fd_amount") or 0),
                    float(row.get("matched_fd_amount") or 0),
                )
                current["concept_size_min"] = min(
                    int(current.get("concept_size_min") or 9999),
                    int(row.get("concept_size_min") or 9999),
                )

        bonds: list[dict[str, Any]] = []
        for row in merged.values():
            row["is_direct_trigger"] = _normalize_stock_code(row.get("stk_code")) in trigger_codes
            row["matched_concept_count"] = len(row.get("matched_concepts") or [])
            row["theme_score"] = _theme_score(row)
            row["risk_notes"] = _risk_notes(row)
            row["remain_size_yi"] = (
                round(float(row["remain_size"]) / 100_000_000, 2)
                if row.get("remain_size") is not None
                else None
            )
            row["code"] = row["cb_code"]
            row["name"] = row["cb_name"]
            row["relation_reason"] = self._relation_reason(row)
            bonds.append(row)

        bonds.sort(
            key=lambda row: (
                not row.get("is_direct_trigger"),
                -int(row.get("matched_concept_count") or 0),
                -int(row.get("trigger_stock_count_sum") or 0),
                -float(row.get("matched_fd_amount") or 0),
                int(row.get("concept_size_min") or 9999),
                row.get("cb_code") or "",
            )
        )
        if top_n:
            bonds = bonds[:top_n]

        return {
            "model": "cb_auction_t0",
            "trade_date": trade_date,
            "trigger_stocks": triggers,
            "concepts": concepts,
            "bonds": bonds,
            "rejections": rejections or [],
        }

    @staticmethod
    def _relation_reason(row: dict[str, Any]) -> str:
        concepts = "、".join(row.get("matched_concepts") or [])
        if row.get("is_direct_trigger"):
            return f"正股为触发股，命中{concepts}" if concepts else "正股为触发股"
        return f"命中{concepts}" if concepts else "命中触发概念"

    def run(self, top_n: int = 50, trade_date: str | None = None, **kwargs) -> dict[str, Any]:
        effective_date = trade_date or date.today().strftime("%Y-%m-%d")
        return {
            "model": "cb_auction_t0",
            "trade_date": effective_date,
            "trigger_stocks": [],
            "concepts": [],
            "bonds": [],
            "rejections": [],
        }
