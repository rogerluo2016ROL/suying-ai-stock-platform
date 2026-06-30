# 可转债底价安全垫选债模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 `cb_floor` 从混合技术打分，改造成“底价安全垫 + A 低溢价题材路线 + B 下修事件路线”的可解释选债模型，并用 1 周、2 周、4 周收益回测验证。

**Architecture:** 保留 `CbFloorEngine` 作为入口，但把硬过滤、字段取数、路线评分、结果解释、回测周期拆成清晰函数。第一版只使用当前 PG 已有字段；缺失字段不伪造，用 `missing_fields` 和 `proxy_fields` 明确标注。

**Tech Stack:** Python, PostgreSQL, psycopg2, pytest, existing `tools/codex-lowio.sh py` test wrapper.

## Global Constraints

- 永远不能用未来数据做当日选债。
- 评级 A 级或以上只作为硬门槛，不参与“评级越高分越高”。
- 正股财务意见必须是标准无保留；缺失时先降级到观察池，不能假设通过。
- 模型输出必须拆分 `route_a_theme`、`route_b_revision`、`combined_route`。
- 回测重点看入选后 1 周、2 周、4 周收益。
- 强赎实施中、临近到期不足 90 天、成交极低的转债不进入交易候选。

---

## 当前字段盘点

| 规则 | 当前字段 | 表 | 处理方式 |
|---|---|---|---|
| 当前价格与到期赎回价价差 5 元以内 | `cb_daily.close`, `cb_basic.maturity_call_price` | `cb_daily`, `cb_basic` | 直接使用；`maturity_call_price` 是文本，需解析数字 |
| 债券评级 A 级或以上 | `newest_rating`, `issue_rating` | `cb_basic` | 硬门槛，不加分 |
| 溢价率越低越好 | `cb_over_rate` | `cb_daily` | 路线 A 和转股弹性主因子 |
| 财务意见标准无保留 | `audit_result` | `fina_audit` | 按正股代码取最近年报审计意见 |
| 下修倒计时优先 | `reset_clause`, `cb_price_chg` | `cb_basic`, `cb_price_chg` | 第一版用条款文本 + 价格变更历史近似；精确倒计时需后续补专表 |
| 热门题材优先 | `concept`, `ths_daily` | `cb_concept`, `ths_daily` | 路线 A 题材热点 |
| 有下修历史优先 | `change_reason` | `cb_price_chg` | 直接使用 |
| 非国企控股优先 | 当前缺直接字段 | 缺失 | 第一版标记缺失，不伪造；后续补 `stock_profiles` 或控制人性质表 |
| 规模越小越好 | `remain_size` | `cb_basic` | 直接使用，设置小规模甜蜜区 |
| 到期时间剩余 3 年以内 | `maturity_date` | `cb_basic` | 硬门槛 |
| 股东质押率低 | `pledge_total_ratio` | `pledge_detail` | 按正股代码取最新公告 |
| 转债换手率越高越好 | `amount`, `vol`, `remain_size` | `cb_daily`, `cb_factor`, `cb_basic` | 当前无直接换手率，第一版用成交额/余额估算活跃度 |

---

### Task 1: 建立 cb_floor v3 评分结构和单元测试

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/cb_floor.py`
- Create: `packages/kronos-factors/tests/test_cb_floor_safety_cushion.py`

**Interfaces:**
- Produces: `_rating_passes(rating: str | None) -> bool`
- Produces: `_parse_maturity_call_price(raw: str | float | int | None) -> float | None`
- Produces: `_price_gap_score(close: float | None, maturity_call_price: float | None) -> tuple[bool, float, float | None]`
- Produces: `_days_to_maturity(maturity_date, today: date) -> int | None`

- [ ] **Step 1: Write failing tests for hard gates**

```python
from datetime import date

from kronos_factors.engine.cb_floor import CbFloorEngine


def test_rating_gate_accepts_a_and_above():
    assert CbFloorEngine._rating_passes("AAA")
    assert CbFloorEngine._rating_passes("AA+")
    assert CbFloorEngine._rating_passes("A")
    assert not CbFloorEngine._rating_passes("BBB")
    assert not CbFloorEngine._rating_passes("")
    assert not CbFloorEngine._rating_passes(None)


def test_parse_maturity_call_price_extracts_number_from_text():
    assert CbFloorEngine._parse_maturity_call_price("到期赎回价110元") == 110.0
    assert CbFloorEngine._parse_maturity_call_price("108.5") == 108.5
    assert CbFloorEngine._parse_maturity_call_price(None) is None


def test_price_gap_gate_requires_within_five_yuan():
    passed, score, gap = CbFloorEngine._price_gap_score(112.0, 110.0)
    assert passed is True
    assert gap == 2.0
    assert score > 0

    passed, score, gap = CbFloorEngine._price_gap_score(116.0, 110.0)
    assert passed is False
    assert gap == 6.0
    assert score == 0.0


def test_days_to_maturity():
    assert CbFloorEngine._days_to_maturity(date(2027, 6, 30), date(2026, 6, 30)) == 365
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_floor_safety_cushion.py -q`

Expected: FAIL because helper methods do not exist.

- [ ] **Step 3: Implement helpers**

Add static helpers to `CbFloorEngine` near existing factor scoring helpers.

```python
    @staticmethod
    def _rating_passes(rating: str | None) -> bool:
        if not rating:
            return False
        r = str(rating).upper().strip()
        return r.startswith(("AAA", "AA", "A"))

    @staticmethod
    def _parse_maturity_call_price(raw) -> float | None:
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        import re
        m = re.search(r"(\d+(?:\.\d+)?)", str(raw))
        return float(m.group(1)) if m else None

    @staticmethod
    def _price_gap_score(close, maturity_call_price) -> tuple[bool, float, float | None]:
        if close is None or maturity_call_price is None:
            return False, 0.0, None
        gap = float(close) - float(maturity_call_price)
        if gap < 0:
            return True, 100.0, round(gap, 2)
        if gap > 5:
            return False, 0.0, round(gap, 2)
        return True, max(0.0, 100.0 - gap * 20.0), round(gap, 2)

    @staticmethod
    def _days_to_maturity(maturity_date_, today: date) -> int | None:
        if maturity_date_ is None:
            return None
        if isinstance(maturity_date_, str):
            maturity_date_ = datetime.strptime(maturity_date_, "%Y-%m-%d").date()
        return (maturity_date_ - today).days
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_floor_safety_cushion.py -q`

Expected: PASS.

---

### Task 2: 拆分 A/B 两条路线评分

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/cb_floor.py`
- Test: `packages/kronos-factors/tests/test_cb_floor_safety_cushion.py`

**Interfaces:**
- Produces: `_route_a_theme_score(premium_score: float, theme_score: float, liquidity_score: float) -> float`
- Produces: `_route_b_revision_score(revision_countdown_score: float, revision_history_score: float, governance_score: float) -> float`
- Produces: `_combined_route(route_a: float, route_b: float) -> str`

- [ ] **Step 1: Write failing tests**

```python
def test_route_a_rewards_low_premium_theme_and_liquidity():
    score = CbFloorEngine._route_a_theme_score(
        premium_score=90.0,
        theme_score=80.0,
        liquidity_score=70.0,
    )
    assert score == 82.0


def test_route_b_rewards_revision_countdown_and_history():
    score = CbFloorEngine._route_b_revision_score(
        revision_countdown_score=90.0,
        revision_history_score=80.0,
        governance_score=60.0,
    )
    assert score == 79.0


def test_combined_route_labels():
    assert CbFloorEngine._combined_route(80, 78) == "A+B共振"
    assert CbFloorEngine._combined_route(80, 40) == "A低溢价题材"
    assert CbFloorEngine._combined_route(40, 80) == "B下修事件"
    assert CbFloorEngine._combined_route(50, 45) == "底价观察"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_floor_safety_cushion.py -q`

Expected: FAIL because route methods do not exist.

- [ ] **Step 3: Implement route helpers**

```python
    @staticmethod
    def _route_a_theme_score(premium_score: float, theme_score: float, liquidity_score: float) -> float:
        return round(premium_score * 0.35 + theme_score * 0.50 + liquidity_score * 0.15, 1)

    @staticmethod
    def _route_b_revision_score(
        revision_countdown_score: float,
        revision_history_score: float,
        governance_score: float,
    ) -> float:
        return round(revision_countdown_score * 0.50 + revision_history_score * 0.20 + governance_score * 0.30, 1)

    @staticmethod
    def _combined_route(route_a: float, route_b: float) -> str:
        if route_a >= 70 and route_b >= 70:
            return "A+B共振"
        if route_a >= 70:
            return "A低溢价题材"
        if route_b >= 70:
            return "B下修事件"
        return "底价观察"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_floor_safety_cushion.py -q`

Expected: PASS.

---

### Task 3: 将 run() 改成新权重并输出解释字段

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/cb_floor.py`
- Test: `packages/kronos-factors/tests/test_cb_floor_safety_cushion.py`

**Interfaces:**
- Produces output keys: `route`, `route_a_score`, `route_b_score`, `floor_safety_score`, `equity_flex_score`, `theme_hot_score`, `liquidity_score`, `governance_score`, `missing_fields`, `risk_flags`

- [ ] **Step 1: Extend SQL query**

Modify the main query to include:

```sql
cb.maturity_call_price,
cb.reset_clause,
fa.audit_result,
pd.pledge_total_ratio
```

Join rules:

```sql
LEFT JOIN LATERAL (
    SELECT audit_result
    FROM fina_audit fa
    WHERE fa.code = SPLIT_PART(cb.stk_code, '.', 1)
    ORDER BY fa.end_date DESC NULLS LAST, fa.ann_date DESC NULLS LAST
    LIMIT 1
) fa ON TRUE
LEFT JOIN LATERAL (
    SELECT pledge_total_ratio
    FROM pledge_detail pd
    WHERE pd.code = SPLIT_PART(cb.stk_code, '.', 1)
    ORDER BY pd.ann_date DESC NULLS LAST
    LIMIT 1
) pd ON TRUE
```

- [ ] **Step 2: Replace total score formula**

Use the user-approved weights:

```python
total = (
    floor_safety_score * 0.45
    + equity_flex_score * 0.25
    + theme_hot_score * 0.10
    + liquidity_score * 0.10
    + governance_score * 0.10
    + call_penalty
)
```

- [ ] **Step 3: Apply hard filters**

Inside each row loop:

```python
rating = newest_rating or issue_rating or ""
if not self._rating_passes(rating):
    continue

if audit_result and "标准无保留" not in str(audit_result):
    continue

days_left = self._days_to_maturity(maturity_date_, date.today())
if days_left is None or days_left > 365 * 3 or days_left < 90:
    continue

maturity_call = self._parse_maturity_call_price(maturity_call_price)
gap_pass, price_gap_score, price_gap = self._price_gap_score(close, maturity_call)
if not gap_pass:
    continue
```

- [ ] **Step 4: Add missing/proxy field reporting**

For each pick:

```python
missing_fields = []
proxy_fields = []
if not audit_result:
    missing_fields.append("audit_result")
if pledge_total_ratio is None:
    missing_fields.append("pledge_total_ratio")
proxy_fields.append("turnover_rate uses amount/remain_size proxy")
proxy_fields.append("revision_countdown uses reset_clause and cb_price_chg proxy")
missing_fields.append("ownership_nature")
```

- [ ] **Step 5: Run targeted smoke**

Run:

`python3 -m py_compile packages/kronos-factors/kronos_factors/engine/cb_floor.py`

Expected: no output.

Run:

`bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_floor_safety_cushion.py -q`

Expected: PASS.

---

### Task 4: 增加 1/2/4 周回测命令

**Files:**
- Modify: `tools/cb_backtest.py`
- Test: `packages/kronos-factors/tests/test_cb_floor_safety_cushion.py`

**Interfaces:**
- Produces CLI option: `--forward-days 5,10,20`
- Produces report columns: `return_1w_pct`, `return_2w_pct`, `return_4w_pct`, `hit_1w`, `hit_2w`, `hit_4w`

- [ ] **Step 1: Inspect existing CLI**

Run:

`python3 tools/cb_backtest.py --help`

Expected: command prints current backtest options.

- [ ] **Step 2: Add multi-horizon returns**

In the backtest loop, for each selected date and each pick, calculate close-to-close returns at 5, 10, and 20 trading days after selection. Use available trading dates from `cb_daily`; if the exact future index is out of range, skip that sample.

- [ ] **Step 3: Print separated route results**

Aggregate by:

```python
route in ("A低溢价题材", "B下修事件", "A+B共振", "底价观察")
```

and print average return / hit rate for 1w, 2w, 4w.

- [ ] **Step 4: Run recent data backtest**

Run:

`python3 tools/cb_backtest.py --mode cb_floor --top-n 20 --forward-days 5,10,20`

Expected: report includes 1w, 2w, 4w sections and route grouping.

---

### Task 5: 输出每日候选池报告

**Files:**
- Modify: `tools/cb_today_picks.py`

**Interfaces:**
- Produces display columns: `route`, `price_gap`, `premium_rate`, `maturity_days_left`, `pledge_total_ratio`, `route_a_score`, `route_b_score`, `risk_flags`

- [ ] **Step 1: Add route-aware columns**

Update `cb_today_picks.py` so daily output clearly separates:

```text
A低溢价题材
B下修事件
A+B共振
底价观察
```

- [ ] **Step 2: Add plain-language reasons**

Each pick should include:

```text
入选原因: 价差2.1元 / 溢价率8.5% / 机器人概念活跃 / 有下修历史
风险提示: 审计字段缺失 / 控股属性缺失 / 质押率偏高
```

- [ ] **Step 3: Run daily pick smoke**

Run:

`python3 tools/cb_today_picks.py --mode cb_floor --top-n 20`

Expected: output has separated route sections and no traceback.

---

## Self-Review

- Spec coverage: 覆盖用户 12 条规则；评级改为硬门槛；A/B 两条路线拆分；权重为 45/25/10/10/10；回测周期为 1/2/4 周。
- Placeholder scan: No TBD/TODO placeholders remain.
- Type consistency: Helper names are defined before use; route labels match report grouping.
- Known gap: 非国企控股目前缺直接字段，第一版只能标缺失，不能编造。
