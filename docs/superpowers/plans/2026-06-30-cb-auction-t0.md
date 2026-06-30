# 竞价选债 T+0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new `cb_auction_t0` model that starts from stock auction limit-up events, maps them to 同花顺概念, and returns related convertible bonds sorted by theme relevance.

**Architecture:** Add a new engine beside the existing `CbAuctionEngine` instead of changing old `cb_auction` behavior. The engine returns one structured result with `trigger_stocks`, `concepts`, `bonds`, and `rejections`; CLI and service code consume that same shape.

**Tech Stack:** Python 3, psycopg2, pytest, existing `packages/kronos-factors` package, existing low-I/O wrapper `bash tools/codex-lowio.sh py`.

## Global Constraints

- Use 同花顺概念 as the main sector source through `ths_member` and `ths_index`.
- Trigger stock requires `limit_list_d.limit_type = 'U'`.
- Auction-board cutoff is `first_time <= '09:30:00'`.
- Seal amount requires `fd_amount > 1_000_000_000`, in raw yuan units.
- Previous trading day cannot be a limit-up day for the same stock.
- Missing `fd_amount` rejects the trigger stock; do not estimate seal amount.
- Do not hard-filter bonds by call status, premium rate, turnover, remain size, or delist date.
- Sort bonds by theme relevance, not by trading convenience.
- Keep existing `CbAuctionEngine` behavior unchanged.
- Use focused tests through `bash tools/codex-lowio.sh py <pytest args>`.

---

## File Structure

Create:

- `packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py`  
  New engine. Owns DB access, trigger-stock fetch, concept fetch, bond fetch, ranking, risk notes, and final result assembly.

- `packages/kronos-factors/tests/test_cb_auction_t0.py`  
  Unit tests with patched fetch methods and small in-memory fixtures. These tests do not require PostgreSQL.

- `tools/cb_auction_t0_picks.py`  
  Command-line entry. Prints a readable table and writes JSON/CSV outputs under `outputs/cb_auction_t0/`.

Modify:

- `packages/kronos-factors/kronos_factors/engine/__init__.py`  
  Export `CbAuctionT0Engine`.

- `services/backtest-service/app/routes.py`  
  Add `cb_auction_t0` to the existing CB mode switch and adapt dict-shaped engine output to the list of bonds used by the backtest code.

No frontend file changes in this plan.

---

### Task 1: Add Pure Ranking And Risk Helpers

**Files:**
- Create: `packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py`
- Test: `packages/kronos-factors/tests/test_cb_auction_t0.py`

**Interfaces:**
- Produces: `_normalize_stock_code(value: str | None) -> str`
- Produces: `_is_noise_concept(name: str | None) -> bool`
- Produces: `_risk_notes(row: dict) -> list[str]`
- Produces: `_theme_score(row: dict) -> float`
- Produces: `CbAuctionT0Engine.run(top_n: int = 50, trade_date: str | None = None, **kwargs) -> dict`

- [ ] **Step 1: Write failing helper tests**

Add this test file:

```python
from kronos_factors.engine.cb_auction_t0 import (
    _is_noise_concept,
    _normalize_stock_code,
    _risk_notes,
    _theme_score,
)


def test_normalize_stock_code_handles_suffix_and_plain_code():
    assert _normalize_stock_code("300001.SZ") == "300001"
    assert _normalize_stock_code("600000") == "600000"
    assert _normalize_stock_code(None) == ""


def test_noise_concept_filter_removes_style_and_region_labels():
    assert _is_noise_concept("昨日涨停") is True
    assert _is_noise_concept("百日新高") is True
    assert _is_noise_concept("浙江") is True
    assert _is_noise_concept("机器人") is False
    assert _is_noise_concept("固态电池") is False


def test_risk_notes_are_annotations():
    row = {
        "call_status": "公告实施强赎",
        "premium_rate": 68.2,
        "cb_amount": 5_000_000,
        "remain_size": 1_800_000_000,
        "delist_date": "2026-07-05",
    }

    notes = _risk_notes(row)

    assert "强赎中" in notes
    assert "高溢价68.2%" in notes
    assert "成交额偏低500.0万" in notes
    assert "剩余规模18.00亿" in notes
    assert "退市日期2026-07-05" in notes


def test_theme_score_ignores_risk_fields():
    safe = {
        "is_direct_trigger": False,
        "matched_concept_count": 2,
        "trigger_stock_count_sum": 3,
        "matched_fd_amount": 2_000_000_000,
        "concept_size_min": 8,
        "premium_rate": 2.0,
        "call_status": "安全",
    }
    risky = dict(safe, premium_rate=80.0, call_status="公告实施强赎")

    assert _theme_score(safe) == _theme_score(risky)
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'kronos_factors.engine.cb_auction_t0'`.

- [ ] **Step 3: Add helper implementation**

Create `packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py` with this starting content:

```python
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
    "同花顺", "(A股)", "昨日", "百日", "首板", "重仓", "新高", "减持",
    "盈利", "股息", "估值", "动量", "大盘", "小盘", "主板", "全A", "均衡",
)
NOISE_CONCEPT_NAMES = {
    "浙江", "江苏", "广东", "上海", "北京", "深圳", "山东",
    "福建", "安徽", "四川", "湖北", "湖南", "河南", "河北",
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
```

- [ ] **Step 4: Run helper tests**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```

Expected: PASS for the four helper tests.

- [ ] **Step 5: Commit**

```bash
git add packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py packages/kronos-factors/tests/test_cb_auction_t0.py
git commit -m "feat: add cb auction t0 helpers"
```

---

### Task 2: Build Result Assembly And Theme Sorting

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py`
- Modify: `packages/kronos-factors/tests/test_cb_auction_t0.py`

**Interfaces:**
- Consumes: `_theme_score(row: dict) -> float`
- Consumes: `_risk_notes(row: dict) -> list[str]`
- Produces: `CbAuctionT0Engine._assemble_result(trade_date: str, triggers: list[dict], concepts: list[dict], raw_bonds: list[dict], top_n: int | None) -> dict`

- [ ] **Step 1: Add failing assembly tests**

Append these tests:

```python
from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine


def test_assemble_result_sorts_by_theme_relevance_and_keeps_risky_bond():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    triggers = [
        {
            "trigger_stock_code": "300001",
            "trigger_stock_name": "触发科技",
            "fd_amount": 1_500_000_000,
            "fd_amount_yi": 15.0,
            "first_time": "09:25:00",
            "prev_was_limit_up": False,
        }
    ]
    concepts = [
        {
            "concept_code": "886001.TI",
            "concept_name": "机器人",
            "trigger_stock_count": 1,
            "concept_fd_amount": 1_500_000_000,
            "concept_fd_amount_yi": 15.0,
            "trigger_sources": ["300001"],
            "concept_size": 2,
        }
    ]
    raw_bonds = [
        {
            "cb_code": "123001.SZ",
            "cb_name": "触发转债",
            "stk_code": "300001",
            "stk_name": "触发科技",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_500_000_000,
            "concept_size_min": 2,
            "premium_rate": 85.0,
            "cb_amount": 1_000_000,
            "remain_size": 2_000_000_000,
            "call_status": "公告实施强赎",
            "delist_date": "2026-07-05",
        },
        {
            "cb_code": "123002.SZ",
            "cb_name": "跟随转债",
            "stk_code": "300002",
            "stk_name": "跟随科技",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_500_000_000,
            "concept_size_min": 2,
            "premium_rate": 3.0,
            "cb_amount": 80_000_000,
            "remain_size": 300_000_000,
            "call_status": "安全",
            "delist_date": None,
        },
    ]

    result = engine._assemble_result("2026-06-30", triggers, concepts, raw_bonds, top_n=10)

    assert [bond["cb_code"] for bond in result["bonds"]] == ["123001.SZ", "123002.SZ"]
    assert result["bonds"][0]["relation_reason"] == "正股为触发股，命中机器人"
    assert "强赎中" in result["bonds"][0]["risk_notes"]
    assert "高溢价85.0%" in result["bonds"][0]["risk_notes"]


def test_assemble_result_dedupes_same_bond_and_merges_concepts():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    triggers = []
    concepts = []
    raw_bonds = [
        {
            "cb_code": "123003.SZ",
            "cb_name": "多题材转债",
            "stk_code": "300003",
            "stk_name": "多题材",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_100_000_000,
            "concept_size_min": 6,
        },
        {
            "cb_code": "123003.SZ",
            "cb_name": "多题材转债",
            "stk_code": "300003",
            "stk_name": "多题材",
            "matched_concepts": ["减速器"],
            "trigger_sources": ["300004"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_200_000_000,
            "concept_size_min": 4,
        },
    ]

    result = engine._assemble_result("2026-06-30", triggers, concepts, raw_bonds, top_n=None)

    assert len(result["bonds"]) == 1
    assert result["bonds"][0]["matched_concepts"] == ["减速器", "机器人"]
    assert result["bonds"][0]["trigger_sources"] == ["300001", "300004"]
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```

Expected: FAIL with `AttributeError: 'CbAuctionT0Engine' object has no attribute '_assemble_result'`.

- [ ] **Step 3: Implement result assembly**

Add these methods inside `CbAuctionT0Engine`:

```python
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
                if row.get("remain_size") is not None else None
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
```

- [ ] **Step 4: Run assembly tests**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py packages/kronos-factors/tests/test_cb_auction_t0.py
git commit -m "feat: assemble cb auction t0 results"
```

---

### Task 3: Add PostgreSQL Fetch Pipeline

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py`
- Modify: `packages/kronos-factors/tests/test_cb_auction_t0.py`

**Interfaces:**
- Produces: `_fetch_effective_trade_date(cur, trade_date: str | None) -> str`
- Produces: `_fetch_previous_trade_date(cur, trade_date: str) -> str | None`
- Produces: `_fetch_trigger_stocks(cur, trade_date: str, prev_trade_date: str | None) -> tuple[list[dict], list[dict]]`
- Produces: `_fetch_concepts(cur, trigger_stocks: list[dict]) -> tuple[list[dict], list[dict]]`
- Produces: `_fetch_bonds(cur, trade_date: str, concepts: list[dict]) -> tuple[list[dict], list[dict]]`

- [ ] **Step 1: Add failing run orchestration test with patched fetchers**

Append this test:

```python
def test_run_assembles_fetcher_outputs_without_postgres(monkeypatch):
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")

    class DummyCursor:
        pass

    class DummyConn:
        closed = False

        def cursor(self):
            return DummyCursor()

        def close(self):
            self.closed = True

    engine._conn = DummyConn()
    monkeypatch.setattr(engine, "_fetch_effective_trade_date", lambda cur, trade_date: "2026-06-30")
    monkeypatch.setattr(engine, "_fetch_previous_trade_date", lambda cur, trade_date: "2026-06-29")
    monkeypatch.setattr(
        engine,
        "_fetch_trigger_stocks",
        lambda cur, trade_date, prev_trade_date: (
            [{
                "trigger_stock_code": "300001",
                "trigger_stock_name": "触发科技",
                "fd_amount": 1_500_000_000,
                "fd_amount_yi": 15.0,
                "first_time": "09:25:00",
                "prev_was_limit_up": False,
            }],
            [{"code": "300009", "reason": "封单金额缺失"}],
        ),
    )
    monkeypatch.setattr(
        engine,
        "_fetch_concepts",
        lambda cur, triggers: (
            [{
                "concept_code": "886001.TI",
                "concept_name": "机器人",
                "trigger_stock_count": 1,
                "concept_fd_amount": 1_500_000_000,
                "concept_fd_amount_yi": 15.0,
                "trigger_sources": ["300001"],
                "concept_size": 2,
            }],
            [],
        ),
    )
    monkeypatch.setattr(
        engine,
        "_fetch_bonds",
        lambda cur, trade_date, concepts: (
            [{
                "cb_code": "123001.SZ",
                "cb_name": "触发转债",
                "stk_code": "300001",
                "stk_name": "触发科技",
                "matched_concepts": ["机器人"],
                "trigger_sources": ["300001"],
                "matched_concept_count": 1,
                "trigger_stock_count_sum": 1,
                "matched_fd_amount": 1_500_000_000,
                "concept_size_min": 2,
            }],
            [],
        ),
    )

    result = engine.run(top_n=5)

    assert result["trade_date"] == "2026-06-30"
    assert result["trigger_stocks"][0]["trigger_stock_code"] == "300001"
    assert result["bonds"][0]["cb_code"] == "123001.SZ"
    assert result["rejections"] == [{"code": "300009", "reason": "封单金额缺失"}]
```

- [ ] **Step 2: Run test and confirm it fails**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```

Expected: FAIL because `run()` does not call the new fetch methods.

- [ ] **Step 3: Implement run orchestration**

Replace `run()` with:

```python
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
```

- [ ] **Step 4: Add PostgreSQL fetch methods**

Add these methods to `CbAuctionT0Engine`:

```python
    @staticmethod
    def _date_keys(trade_date: str) -> tuple[str, str]:
        text = str(trade_date)[:10]
        return text, text.replace("-", "")

    def _fetch_effective_trade_date(self, cur, trade_date: str | None) -> str:
        if trade_date:
            return str(trade_date)[:10]
        cur.execute("SELECT MAX(trade_date) FROM limit_list_d WHERE limit_type='U'")
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

    def _fetch_trigger_stocks(self, cur, trade_date: str, prev_trade_date: str | None):
        trade_key, trade_key_compact = self._date_keys(trade_date)
        prev_key, prev_key_compact = self._date_keys(prev_trade_date) if prev_trade_date else ("", "")

        cur.execute(
            """
            SELECT
                SPLIT_PART(COALESCE(l.ts_code, l.code), '.', 1) AS code,
                COALESCE(l.name, s.name, '') AS name,
                l.fd_amount,
                l.first_time,
                EXISTS (
                    SELECT 1 FROM limit_list_d p
                    WHERE (p.trade_date::text = %s OR REPLACE(p.trade_date::text, '-', '') = %s)
                      AND p.limit_type = 'U'
                      AND SPLIT_PART(COALESCE(p.ts_code, p.code), '.', 1)
                          = SPLIT_PART(COALESCE(l.ts_code, l.code), '.', 1)
                ) AS prev_was_limit_up
            FROM limit_list_d l
            LEFT JOIN stocks s ON s.code = SPLIT_PART(COALESCE(l.ts_code, l.code), '.', 1)
            WHERE (l.trade_date::text = %s OR REPLACE(l.trade_date::text, '-', '') = %s)
              AND l.limit_type = 'U'
              AND COALESCE(l.first_time, '') <= %s
              AND COALESCE(l.name, s.name, '') NOT LIKE '%%ST%%'
            ORDER BY l.fd_amount DESC NULLS LAST
            """,
            (prev_key, prev_key_compact, trade_key, trade_key_compact, AUCTION_FIRST_TIME_MAX),
        )

        triggers: list[dict[str, Any]] = []
        rejections: list[dict[str, Any]] = []
        for code, name, fd_amount, first_time, prev_was_limit_up in cur.fetchall():
            stock_code = _normalize_stock_code(code)
            if fd_amount is None:
                rejections.append({"code": stock_code, "name": name, "reason": "封单金额缺失"})
                continue
            if float(fd_amount) <= FD_AMOUNT_MIN:
                rejections.append({"code": stock_code, "name": name, "reason": "封单金额不足10亿"})
                continue
            if prev_was_limit_up:
                rejections.append({"code": stock_code, "name": name, "reason": "昨日已涨停"})
                continue
            triggers.append({
                "trigger_stock_code": stock_code,
                "trigger_stock_name": name,
                "fd_amount": float(fd_amount),
                "fd_amount_yi": round(float(fd_amount) / 100_000_000, 2),
                "first_time": first_time,
                "prev_was_limit_up": False,
            })
        return triggers, rejections
```

Add concept and bond fetchers:

```python
    def _fetch_concepts(self, cur, trigger_stocks: list[dict[str, Any]]):
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
                SPLIT_PART(m.con_code, '.', 1) AS stock_code
            FROM ths_member m
            JOIN ths_index i ON i.ts_code = m.ts_code
            WHERE SPLIT_PART(m.con_code, '.', 1) IN ({holders})
              AND LEFT(m.ts_code, 3) IN ('881','882','883','884','885','886')
            """,
            codes,
        )

        grouped: dict[str, dict[str, Any]] = {}
        rejections: list[dict[str, Any]] = []
        stocks_with_concepts: set[str] = set()
        for concept_code, concept_name, stock_code in cur.fetchall():
            if _is_noise_concept(concept_name):
                continue
            stocks_with_concepts.add(stock_code)
            trigger = trigger_map[stock_code]
            item = grouped.setdefault(concept_code, {
                "concept_code": concept_code,
                "concept_name": concept_name,
                "trigger_stock_count": 0,
                "concept_fd_amount": 0.0,
                "concept_fd_amount_yi": 0.0,
                "trigger_sources": [],
                "concept_size": 9999,
            })
            if stock_code not in item["trigger_sources"]:
                item["trigger_sources"].append(stock_code)
                item["trigger_stock_count"] += 1
                item["concept_fd_amount"] += float(trigger["fd_amount"])

        for item in grouped.values():
            item["trigger_sources"].sort()
            item["concept_fd_amount_yi"] = round(item["concept_fd_amount"] / 100_000_000, 2)

        for code, trigger in trigger_map.items():
            if code not in stocks_with_concepts:
                rejections.append({
                    "code": code,
                    "name": trigger["trigger_stock_name"],
                    "reason": "缺少同花顺概念",
                })

        return list(grouped.values()), rejections

    def _fetch_bonds(self, cur, trade_date: str, concepts: list[dict[str, Any]]):
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
                cb_code, cb_name, stk_code, stk_name, concept_code, concept_name,
                remain_size, delist_date, premium_rate, cb_amount, call_status,
            ) = row
            concept = concept_map[concept_code]
            seen_concept_with_bond.add(concept_code)
            raw.append({
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
            })

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
```

- [ ] **Step 5: Run tests**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py packages/kronos-factors/tests/test_cb_auction_t0.py
git commit -m "feat: add cb auction t0 data pipeline"
```

---

### Task 4: Add CLI And Export Files

**Files:**
- Create: `tools/cb_auction_t0_picks.py`
- Modify: `packages/kronos-factors/tests/test_cb_auction_t0.py`

**Interfaces:**
- Produces: `main(argv: list[str] | None = None) -> int`
- Produces: `write_outputs(result: dict, output_dir: str) -> tuple[str, str]`

- [ ] **Step 1: Add failing CLI export test**

Append this test:

```python
def test_cli_write_outputs_creates_json_and_csv(tmp_path):
    import importlib.util
    from pathlib import Path

    tool_path = Path("tools/cb_auction_t0_picks.py")
    spec = importlib.util.spec_from_file_location("cb_auction_t0_picks", tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = {
        "trade_date": "2026-06-30",
        "trigger_stocks": [],
        "concepts": [],
        "bonds": [{
            "cb_code": "123001.SZ",
            "cb_name": "触发转债",
            "stk_code": "300001",
            "stk_name": "触发科技",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "theme_score": 111.0,
            "premium_rate": 85.0,
            "cb_amount": 1_000_000,
            "remain_size_yi": 20.0,
            "call_status": "公告实施强赎",
            "risk_notes": ["强赎中", "高溢价85.0%"],
            "relation_reason": "正股为触发股，命中机器人",
        }],
        "rejections": [],
    }

    json_path, csv_path = module.write_outputs(result, str(tmp_path))

    assert Path(json_path).exists()
    assert Path(csv_path).exists()
    assert "触发转债" in Path(csv_path).read_text(encoding="utf-8-sig")
```

- [ ] **Step 2: Run test and confirm it fails**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py::test_cli_write_outputs_creates_json_and_csv -q
```

Expected: FAIL because `tools/cb_auction_t0_picks.py` does not exist.

- [ ] **Step 3: Add CLI tool**

Create `tools/cb_auction_t0_picks.py`:

```python
#!/usr/bin/env python3
"""Run 竞价选债 T+0 model and export results."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "kronos-factors"))

from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="竞价选债 T+0 模型")
    parser.add_argument("trade_date", nargs="?", help="交易日，格式 YYYY-MM-DD")
    parser.add_argument("--top-n", type=int, default=50, help="最多输出转债数量")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "cb_auction_t0"))
    parser.add_argument("--json-only", action="store_true", help="只输出 JSON 路径")
    return parser


def write_outputs(result: dict, output_dir: str) -> tuple[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trade_date = result.get("trade_date") or "unknown"
    json_path = out_dir / f"{trade_date}_cb_auction_t0.json"
    csv_path = out_dir / f"{trade_date}_cb_auction_t0.csv"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    fields = [
        "cb_code", "cb_name", "stk_code", "stk_name", "theme_score",
        "matched_concepts", "trigger_sources", "relation_reason",
        "premium_rate", "cb_amount", "remain_size_yi", "call_status", "risk_notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for bond in result.get("bonds", []):
            row = {key: bond.get(key) for key in fields}
            row["matched_concepts"] = "、".join(bond.get("matched_concepts") or [])
            row["trigger_sources"] = "、".join(bond.get("trigger_sources") or [])
            row["risk_notes"] = "；".join(bond.get("risk_notes") or [])
            writer.writerow(row)
    return str(json_path), str(csv_path)


def print_summary(result: dict) -> None:
    print(f"竞价选债 T+0 | {result.get('trade_date')}")
    print(f"触发股票: {len(result.get('trigger_stocks', []))} | 概念: {len(result.get('concepts', []))} | 转债: {len(result.get('bonds', []))}")
    print("-" * 120)
    print(f"{'#':<3} {'转债':<12} {'正股':<10} {'题材分':>7} {'概念':<24} {'风险提示'}")
    for idx, bond in enumerate(result.get("bonds", [])[:50], 1):
        concepts = "、".join(bond.get("matched_concepts") or [])[:24]
        risks = "；".join(bond.get("risk_notes") or [])
        print(f"{idx:<3} {bond.get('cb_name',''):<12} {bond.get('stk_name',''):<10} {bond.get('theme_score', 0):>7.1f} {concepts:<24} {risks}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = CbAuctionT0Engine(pg_url=os.environ.get("KRONOS_PG_URL"))
    try:
        result = engine.run(trade_date=args.trade_date, top_n=args.top_n)
    finally:
        engine.close()

    json_path, csv_path = write_outputs(result, args.output_dir)
    if args.json_only:
        print(json_path)
    else:
        print_summary(result)
        print(f"\nJSON: {json_path}")
        print(f"CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI export test**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py::test_cli_write_outputs_creates_json_and_csv -q
```

Expected: PASS.

- [ ] **Step 5: Run focused test file**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/cb_auction_t0_picks.py packages/kronos-factors/tests/test_cb_auction_t0.py
git commit -m "feat: add cb auction t0 cli"
```

---

### Task 5: Register Engine And Backtest-Service Mode

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/__init__.py`
- Modify: `services/backtest-service/app/routes.py`
- Test: `packages/kronos-factors/tests/test_cb_auction_t0.py`

**Interfaces:**
- Produces: `CbAuctionT0Engine` export from `kronos_factors.engine`
- Produces: `run_cb_backtest(mode="cb_auction_t0")` support

- [ ] **Step 1: Add failing export test**

Append this test:

```python
def test_engine_package_exports_cb_auction_t0():
    from kronos_factors.engine import CbAuctionT0Engine

    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    assert engine.pg_url == "postgresql://unit/unit"
```

- [ ] **Step 2: Run export test and confirm it fails**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py::test_engine_package_exports_cb_auction_t0 -q
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Export the engine**

Modify `packages/kronos-factors/kronos_factors/engine/__init__.py`:

```python
from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine
```

Add this item to `__all__`:

```python
"CbAuctionT0Engine",
```

- [ ] **Step 4: Add service mode support**

Modify `services/backtest-service/app/routes.py` inside `run_cb_backtest`:

```python
        engine_cls = {
            "cb_floor": "CbFloorEngine",
            "cb_intraday": "CbIntradayEngine",
            "cb_auction": "CbAuctionEngine",
            "cb_auction_t0": "CbAuctionT0Engine",
        }
```

Replace the engine construction block with:

```python
                if mode == "cb_floor":
                    from kronos_factors.engine.cb_floor import CbFloorEngine
                    engine = CbFloorEngine()
                elif mode == "cb_intraday":
                    from kronos_factors.engine.cb_intraday import CbIntradayEngine
                    engine = CbIntradayEngine()
                elif mode == "cb_auction_t0":
                    from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine
                    engine = CbAuctionT0Engine()
                else:
                    from kronos_factors.engine.cb_auction import CbAuctionEngine
                    engine = CbAuctionEngine()

                raw_result = engine.run(trade_date=str(sel_date), top_n=top_n)
                engine.close()
                picks = raw_result.get("bonds", []) if isinstance(raw_result, dict) else raw_result
```

Keep the later return shape unchanged. The backtest loop already reads `pk.get("code")`, and Task 2 added `code` as an alias of `cb_code`.

- [ ] **Step 5: Run tests and compile checks**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
python -m py_compile services/backtest-service/app/routes.py
```

Expected: tests PASS, compile command exits 0.

- [ ] **Step 6: Commit**

```bash
git add packages/kronos-factors/kronos_factors/engine/__init__.py services/backtest-service/app/routes.py packages/kronos-factors/tests/test_cb_auction_t0.py
git commit -m "feat: register cb auction t0 mode"
```

---

### Task 6: Add Smoke Commands And Current-Day Run Notes

**Files:**
- Modify: `docs/superpowers/specs/2026-06-30-cb-auction-t0-design.md`

**Interfaces:**
- Consumes: CLI `tools/cb_auction_t0_picks.py`
- Produces: documented smoke commands for current day and historical replay

- [ ] **Step 1: Add failing documentation check**

Run:

```bash
rg -n "cb_auction_t0_picks.py|20 个交易日|KRONOS_PG_URL" docs/superpowers/specs/2026-06-30-cb-auction-t0-design.md
```

Expected: the command does not find all three terms.

- [ ] **Step 2: Add implementation notes to the spec**

Append this section to `docs/superpowers/specs/2026-06-30-cb-auction-t0-design.md`:

````markdown
## 实现后的运行命令

当前日清单：

```bash
KRONOS_PG_URL="postgresql://kronos:kronos@localhost:6432/kronos" \
python tools/cb_auction_t0_picks.py 2026-06-30 --top-n 50
```

历史日期回放：

```bash
for d in 2026-06-10 2026-06-11 2026-06-12; do
  KRONOS_PG_URL="postgresql://kronos:kronos@localhost:6432/kronos" \
  python tools/cb_auction_t0_picks.py "$d" --top-n 50 --json-only
done
```

20 个交易日验证时，先确认 PostgreSQL 已启动，且 `limit_list_d`、`ths_member`、`ths_index`、`cb_basic`、`cb_daily`、`cb_call` 均有目标日期附近数据。
````

- [ ] **Step 3: Run documentation check**

Run:

```bash
rg -n "cb_auction_t0_picks.py|20 个交易日|KRONOS_PG_URL" docs/superpowers/specs/2026-06-30-cb-auction-t0-design.md
```

Expected: all three terms appear.

- [ ] **Step 4: Run focused tests**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
python -m py_compile tools/cb_auction_t0_picks.py services/backtest-service/app/routes.py
```

Expected: tests PASS, compile commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-06-30-cb-auction-t0-design.md
git commit -m "docs: add cb auction t0 run commands"
```

---

## Final Verification

Run the low-I/O test suite for the new model:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```

Compile changed Python entry points:

```bash
python -m py_compile \
  packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py \
  tools/cb_auction_t0_picks.py \
  services/backtest-service/app/routes.py
```

If PostgreSQL is running on `localhost:6432`, run one smoke command:

```bash
KRONOS_PG_URL="postgresql://kronos:kronos@localhost:6432/kronos" \
python tools/cb_auction_t0_picks.py 2026-06-30 --top-n 50
```

Expected smoke behavior:

- The command prints trigger stock, concept, and bond counts.
- The command writes JSON and CSV files under `outputs/cb_auction_t0/`.
- Risky bonds still appear in the CSV with risk notes.
- Rejections include missing seal amount, seal amount below 10 亿, yesterday limit-up, missing concept, or concept without bonds.

If PostgreSQL is not running, report that the unit tests passed and the DB smoke test could not run because `localhost:6432` refused the connection.

## Self-Review

- Spec coverage: Tasks 1-3 implement trigger stock rules, THS concept mapping, bond list generation, risk notes, and theme sorting. Task 4 adds export. Task 5 adds service mode. Task 6 records run commands.
- Placeholder scan: The plan contains no unresolved markers or deferred implementation slots.
- Type consistency: `CbAuctionT0Engine.run()` returns a dict; service code adapts dict output with `raw_result.get("bonds", [])`. Bonds include both `cb_code` and `code`.
