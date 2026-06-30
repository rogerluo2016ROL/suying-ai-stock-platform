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
AUCTION_FIRST_TIME_MAX_COMPACT = "093000"

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
        trigger_codes = {_normalize_stock_code(row.get("trigger_stock_code")) for row in triggers}
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

        # 排序规则按题材相关性定义：直接触发优先，题材/触发权重高者靠前；theme_score 仅用于展示。
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
        if top_n is not None:
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

    @staticmethod
    def _date_keys(trade_date: str) -> tuple[str, str]:
        text = str(trade_date)[:10]
        return text, text.replace("-", "")

    def _fetch_effective_trade_date(self, cur, trade_date: str | None) -> str:
        if trade_date:
            return str(trade_date)[:10]
        cur.execute("SELECT MAX(trade_date) FROM limit_list_d WHERE limit_type = 'U'")
        row = cur.fetchone()
        return str(row[0])[:10] if row and row[0] else date.today().strftime("%Y-%m-%d")

    def _fetch_previous_trade_date(self, cur, trade_date: str) -> str | None:
        cur.execute(
            "SELECT MAX(trade_date) FROM daily_kline WHERE trade_date < %s",
            (trade_date,),
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0])[:10]

        cur.execute(
            "SELECT MAX(trade_date) FROM limit_list_d WHERE trade_date < %s",
            (trade_date,),
        )
        row = cur.fetchone()
        return str(row[0])[:10] if row and row[0] else None

    def _fetch_trigger_stocks(
        self,
        cur,
        trade_date: str,
        prev_trade_date: str | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        trade_key, trade_key_compact = self._date_keys(trade_date)
        prev_key, prev_key_compact = self._date_keys(prev_trade_date) if prev_trade_date else ("", "")

        cur.execute(
            """
            SELECT
                SPLIT_PART(l.ts_code, '.', 1) AS code,
                COALESCE(l.name, s.name, '') AS name,
                l.fd_amount,
                l.first_time,
                EXISTS (
                    SELECT 1
                    FROM limit_list_d p
                    WHERE (p.trade_date::text = %s OR REPLACE(p.trade_date::text, '-', '') = %s)
                      AND p.limit_type = 'U'
                      AND SPLIT_PART(p.ts_code, '.', 1)
                          = SPLIT_PART(l.ts_code, '.', 1)
                ) AS prev_was_limit_up
            FROM limit_list_d l
            LEFT JOIN stocks s ON s.code = SPLIT_PART(l.ts_code, '.', 1)
            WHERE (l.trade_date::text = %s OR REPLACE(l.trade_date::text, '-', '') = %s)
              AND l.limit_type = 'U'
              AND l.first_time IS NOT NULL
              AND LPAD(REPLACE(l.first_time, ':', ''), 6, '0') <= %s
              AND COALESCE(l.name, s.name, '') NOT LIKE '%%ST%%'
            ORDER BY l.fd_amount DESC NULLS LAST
            """,
            (prev_key, prev_key_compact, trade_key, trade_key_compact, AUCTION_FIRST_TIME_MAX_COMPACT),
        )

        triggers: list[dict[str, Any]] = []
        rejections: list[dict[str, Any]] = []
        for code, name, fd_amount, first_time, prev_was_limit_up in cur.fetchall():
            stock_code = _normalize_stock_code(code)
            if fd_amount is None:
                rejections.append({"code": stock_code, "name": name, "reason": "封单金额缺失"})
                continue
            fd_value = float(fd_amount)
            if fd_value <= FD_AMOUNT_MIN:
                rejections.append({"code": stock_code, "name": name, "reason": "封单金额不足10亿"})
                continue
            if prev_was_limit_up:
                rejections.append({"code": stock_code, "name": name, "reason": "昨日已涨停"})
                continue
            triggers.append(
                {
                    "trigger_stock_code": stock_code,
                    "trigger_stock_name": name,
                    "fd_amount": fd_value,
                    "fd_amount_yi": round(fd_value / 100_000_000, 2),
                    "first_time": first_time,
                    "prev_was_limit_up": False,
                }
            )
        return triggers, rejections

    def _fetch_concepts(
        self,
        cur,
        trigger_stocks: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not trigger_stocks:
            return [], []

        trigger_map = {row["trigger_stock_code"]: row for row in trigger_stocks}
        codes = list(trigger_map.keys())
        holders = ",".join(["%s"] * len(codes))
        cur.execute(
            f"""
            SELECT
                m.ts_code AS concept_code,
                i.name AS concept_name,
                SPLIT_PART(m.con_code, '.', 1) AS stock_code,
                COUNT(*) OVER (PARTITION BY m.ts_code) AS concept_size
            FROM ths_member m
            JOIN ths_index i ON i.ts_code = m.ts_code
            WHERE SPLIT_PART(m.con_code, '.', 1) IN ({holders})
              AND LEFT(m.ts_code, 3) IN ('881', '882', '883', '884', '885', '886')
            """,
            codes,
        )

        grouped: dict[str, dict[str, Any]] = {}
        rejections: list[dict[str, Any]] = []
        stocks_with_concepts: set[str] = set()
        for concept_code, concept_name, stock_code, concept_size in cur.fetchall():
            if _is_noise_concept(concept_name):
                continue
            stocks_with_concepts.add(stock_code)
            trigger = trigger_map[stock_code]
            item = grouped.setdefault(
                concept_code,
                {
                    "concept_code": concept_code,
                    "concept_name": concept_name,
                    "trigger_stock_count": 0,
                    "concept_fd_amount": 0.0,
                    "concept_fd_amount_yi": 0.0,
                    "trigger_sources": [],
                    "concept_size": int(concept_size or 9999),
                },
            )
            if stock_code not in item["trigger_sources"]:
                item["trigger_sources"].append(stock_code)
                item["trigger_stock_count"] += 1
                item["concept_fd_amount"] += float(trigger["fd_amount"])

        for item in grouped.values():
            item["trigger_sources"].sort()
            item["concept_fd_amount_yi"] = round(item["concept_fd_amount"] / 100_000_000, 2)

        for code, trigger in trigger_map.items():
            if code not in stocks_with_concepts:
                rejections.append(
                    {
                        "code": code,
                        "name": trigger["trigger_stock_name"],
                        "reason": "缺少同花顺概念",
                    }
                )

        return list(grouped.values()), rejections

    def _fetch_bonds(
        self,
        cur,
        trade_date: str,
        concepts: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not concepts:
            return [], []

        concept_map = {row["concept_code"]: row for row in concepts}
        concept_codes = list(concept_map.keys())
        holders = ",".join(["%s"] * len(concept_codes))
        cur.execute(
            f"""
            WITH latest_call AS (
                SELECT DISTINCT ON (ts_code) ts_code, is_call
                FROM cb_call
                ORDER BY ts_code, ann_date DESC NULLS LAST
            )
            SELECT
                b.ts_code AS cb_code,
                b.bond_short_name AS cb_name,
                SPLIT_PART(b.stk_code, '.', 1) AS stk_code,
                b.stk_short_name AS stk_name,
                m.ts_code AS concept_code,
                i.name AS concept_name,
                b.remain_size,
                b.delist_date,
                d.cb_over_rate,
                d.amount,
                lc.is_call
            FROM ths_member m
            JOIN ths_index i ON i.ts_code = m.ts_code
            JOIN cb_basic b ON SPLIT_PART(b.stk_code, '.', 1) = SPLIT_PART(m.con_code, '.', 1)
            LEFT JOIN cb_daily d ON d.ts_code = b.ts_code AND d.trade_date = %s
            LEFT JOIN latest_call lc ON lc.ts_code = b.ts_code
            WHERE m.ts_code IN ({holders})
              AND COALESCE(b.cb_type, 'CB') = 'CB'
            ORDER BY b.ts_code, m.ts_code
            """,
            [trade_date] + concept_codes,
        )

        raw: list[dict[str, Any]] = []
        seen_concept_with_bond: set[str] = set()
        for row in cur.fetchall():
            (
                cb_code,
                cb_name,
                stk_code,
                stk_name,
                concept_code,
                concept_name,
                remain_size,
                delist_date,
                premium_rate,
                cb_amount,
                call_status,
            ) = row
            concept = concept_map[concept_code]
            seen_concept_with_bond.add(concept_code)
            raw.append(
                {
                    "cb_code": cb_code,
                    "cb_name": cb_name or cb_code,
                    "stk_code": _normalize_stock_code(stk_code),
                    "stk_name": stk_name,
                    "matched_concepts": [concept_name],
                    "trigger_sources": list(concept["trigger_sources"]),
                    "matched_concept_count": 1,
                    "trigger_stock_count_sum": int(concept["trigger_stock_count"]),
                    "matched_fd_amount": float(concept["concept_fd_amount"]),
                    "concept_size_min": int(concept.get("concept_size") or 9999),
                    "premium_rate": float(premium_rate) if premium_rate is not None else None,
                    "cb_amount": float(cb_amount) if cb_amount is not None else None,
                    "remain_size": float(remain_size) if remain_size is not None else None,
                    "delist_date": str(delist_date) if delist_date else None,
                    "call_status": call_status or "安全",
                }
            )

        rejections = [
            {
                "concept_code": code,
                "concept_name": concept_map[code]["concept_name"],
                "reason": "概念下无转债",
            }
            for code in concept_codes
            if code not in seen_concept_with_bond
        ]
        return raw, rejections

    def run(self, top_n: int = 50, trade_date: str | None = None, **kwargs) -> dict[str, Any]:
        cur = self.db.cursor()
        effective_date = self._fetch_effective_trade_date(cur, trade_date)
        prev_trade_date = self._fetch_previous_trade_date(cur, effective_date)

        triggers, trigger_rejections = self._fetch_trigger_stocks(cur, effective_date, prev_trade_date)
        concepts, concept_rejections = self._fetch_concepts(cur, triggers)
        bonds, bond_rejections = self._fetch_bonds(cur, effective_date, concepts)

        return self._assemble_result(
            effective_date,
            triggers,
            concepts,
            bonds,
            top_n=top_n,
            rejections=trigger_rejections + concept_rejections + bond_rejections,
        )
