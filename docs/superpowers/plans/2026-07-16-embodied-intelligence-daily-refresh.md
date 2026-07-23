# Embodied Intelligence Daily Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立每日 19:30 自动刷新具身智能 L1–L8 产业链、补充证据约束的股票映射、排序证据变动并在有 P0–P2 变化时推送三个飞书群的可追溯流程。

**Architecture:** 使用 PostgreSQL 保存刷新游标、运行批次、变动指纹、排名快照和分群送达状态。Python 模块分别负责证据标准化、映射状态机、审计排名和变动发布，由单一 CLI 统一编排，再接入 data-service 现有调度器。

**Tech Stack:** Python 3.11、PostgreSQL/psycopg2、Alembic、pytest、现有 data-service scheduler、现有 `lark-cli`/Feishu 送达核验。

## Global Constraints

- 每日北京时间 19:30 运行，包括周末；每周日 20:30 执行全量一致性审计。
- 新映射统一进入 `candidate/pending_review`；只有一条 S 级或两条独立 A 级明确证据才可自动升级。
- 模糊表述、研报、媒体或关键词命中不能独立升级正式映射。
- 缺失值保持 `None`，不默认为 0；同一股票的多标签不简单累加。
- 只有 P0–P2 变动时才推送到 `ai_research_analysis`、`ai_research_test`、`fitness_group`。
- 只有获得真实 `message_id` 并通过送达核验才记为成功。
- 失败批次不得成为下次基线；不因单一数据源失败降级旧映射。
- 保留当前工作树里的无关改动，每次提交只暂存本任务文件。

---

## File Map

| File | Responsibility |
|---|---|
| `backend/alembic/versions/036_embodied_intelligence_daily_refresh.py` | 新增批次、游标、变动、Top3 快照和送达表 |
| `tools/embodied_refresh/models.py` | 共享数据类型、枚举和纯函数入参 |
| `tools/embodied_refresh/evidence.py` | 来源分级、模糊表述、指纹和商业化阶段 |
| `tools/embodied_refresh/mappings.py` | 映射状态机和原子持久化 |
| `tools/embodied_refresh/audit.py` | L1–L8 覆盖审计、重复/冲突检测、Top3 排名 |
| `tools/embodied_refresh/changes.py` | 快照差异、重要性评分、P0–P3 分级与消息渲染 |
| `tools/embodied_refresh/delivery.py` | 三群幂等发送、送达记录和失败重试 |
| `tools/run_embodied_daily_refresh.py` | dry-run/apply/audit 统一 CLI 编排 |
| `configs/scheduled_research.json` | 每日、每周与飞书失败补偿调度配置 |
| `services/data-service/app/scheduled_research.py` | 支持非交易日产业链任务和专用 CLI |
| `tools/tests/test_embodied_refresh_*.py` | 纯函数和 PostgreSQL 仓储单元测试 |
| `services/data-service/tests/test_scheduled_research.py` | 调度注册、周末运行和幂等测试 |

### Task 1: Persistence Schema and Repository Contracts

**Files:**
- Create: `backend/alembic/versions/036_embodied_intelligence_daily_refresh.py`
- Create: `tools/embodied_refresh/__init__.py`
- Create: `tools/embodied_refresh/models.py`
- Create: `tools/embodied_refresh/repository.py`
- Test: `tools/tests/test_embodied_refresh_repository.py`

**Interfaces:**
- Produces: `RefreshRun`, `SourceCursor`, `EvidenceChange`, `LeaderSnapshot`, `DeliveryRecord` dataclasses.
- Produces: `EmbodiedRefreshRepository.begin_run(run_date, mode)`, `load_success_baseline()`, `save_cursor()`, `save_changes()`, `finish_run()`.

- [ ] **Step 1: Write failing migration contract tests**

```python
def test_migration_defines_all_refresh_tables():
    source = Path("backend/alembic/versions/036_embodied_intelligence_daily_refresh.py").read_text()
    for table in (
        "embodied_refresh_runs", "embodied_source_cursors",
        "embodied_evidence_changes", "embodied_leader_snapshots",
        "embodied_delivery_records",
    ):
        assert table in source
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_repository.py -q`

Expected: FAIL because migration and repository files do not exist.

- [ ] **Step 3: Add migration with keys and idempotency constraints**

Create tables with these required unique keys:

```python
op.create_unique_constraint("uq_embodied_run_date_mode", "embodied_refresh_runs", ["run_date", "mode"])
op.create_unique_constraint("uq_embodied_cursor_source", "embodied_source_cursors", ["chain_id", "source_name"])
op.create_unique_constraint("uq_embodied_change_fingerprint", "embodied_evidence_changes", ["change_fingerprint"])
op.create_unique_constraint("uq_embodied_snapshot_rank", "embodied_leader_snapshots", ["run_id", "node_id", "rank"])
op.create_unique_constraint("uq_embodied_delivery_target", "embodied_delivery_records", ["change_batch_id", "chat_id"])
```

`embodied_refresh_runs.status` 允许 `running/success/data_success_delivery_incomplete/failed`；`embodied_delivery_records.status` 允许 `pending/confirmed/failed/unconfirmed`。

- [ ] **Step 4: Implement repository transaction boundaries**

```python
class EmbodiedRefreshRepository:
    def begin_run(self, run_date: date, mode: str) -> RefreshRun:
        """Insert a running batch or return the existing idempotent batch."""

    def load_success_baseline(self, before_run_id: str) -> RefreshRun | None:
        """Return the newest earlier run whose status is success."""

    def save_cursor(self, source_name: str, cursor_value: str, run_id: str) -> None:
        """Advance one successful source cursor after the mapping transaction commits."""

    def save_changes(self, changes: list[EvidenceChange]) -> int:
        """Insert unseen change fingerprints and return the inserted count."""

    def finish_run(self, run_id: str, status: str, summary: dict[str, Any]) -> None:
        """Persist terminal run status and structured summary."""
```

Use PostgreSQL `INSERT ON CONFLICT` only for cursor/current delivery state; run and change history remain append-only.

- [ ] **Step 5: Run repository tests and migration upgrade/downgrade in a test database**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_repository.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/036_embodied_intelligence_daily_refresh.py tools/embodied_refresh tools/tests/test_embodied_refresh_repository.py
git commit -m "feat: add embodied refresh persistence"
```

### Task 2: Evidence Normalization and Upgrade Gate

**Files:**
- Create: `tools/embodied_refresh/evidence.py`
- Test: `tools/tests/test_embodied_refresh_evidence.py`

**Interfaces:**
- Consumes: `RawEvidence` and `NormalizedEvidence` from `models.py`.
- Produces: `classify_source(source_type) -> EvidenceGrade`, `normalize_evidence(raw) -> NormalizedEvidence`, `can_auto_verify(events) -> bool`, `commercialization_stage(text) -> CommercializationStage`.

- [ ] **Step 1: Write failing evidence-grade and upgrade tests**

```python
def test_report_cannot_auto_verify_mapping():
    event = evidence("research", "公司布局人形机器人")
    assert classify_source(event.source_type) == EvidenceGrade.C
    assert can_auto_verify([event]) is False

def test_clear_annual_report_can_auto_verify_mapping():
    event = evidence("annual_report", "公司已批量交付机器人六维力传感器", node_id="EI-L5-FORCE")
    assert classify_source(event.source_type) == EvidenceGrade.S
    assert can_auto_verify([event]) is True

def test_two_independent_official_sources_can_auto_verify():
    assert can_auto_verify([official_web("src-a"), ir_record("src-b")]) is True
```

- [ ] **Step 2: Run tests and verify failure**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_evidence.py -q`

Expected: FAIL with missing classifiers.

- [ ] **Step 3: Implement explicit-source and explicit-relation rules**

```python
VAGUE_TERMS = ("布局", "关注", "可用于", "有望用于", "涉及概念")
RELATION_TERMS = ("供应", "定点", "交付", "量产", "订单", "收入", "客户验证", "主营")

def can_auto_verify(events: Sequence[NormalizedEvidence]) -> bool:
    clear = [e for e in events if e.node_id and e.event_date and e.has_explicit_relation]
    return any(e.grade == EvidenceGrade.S for e in clear) or len({e.source_id for e in clear if e.grade == EvidenceGrade.A}) >= 2
```

- [ ] **Step 4: Add fingerprint and stage-order tests**

Verify identical source content deduplicates, changed official content creates a new version, and `customer_validation -> mass_production` is an advance while the reverse is a downgrade candidate.

- [ ] **Step 5: Run focused tests**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_evidence.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/embodied_refresh/evidence.py tools/tests/test_embodied_refresh_evidence.py
git commit -m "feat: enforce embodied evidence upgrade gates"
```

### Task 3: Incremental Source Refresh and Mapping State Machine

**Files:**
- Modify: `tools/repair_priority_supply_chains.py`
- Create: `tools/embodied_refresh/sources.py`
- Create: `tools/embodied_refresh/mappings.py`
- Test: `tools/tests/test_embodied_refresh_sources.py`
- Test: `tools/tests/test_embodied_refresh_mappings.py`

**Interfaces:**
- Consumes: repository cursor and existing `fetch_source_hits()` query patterns.
- Produces: `fetch_incremental_sources(pg_url, cursors) -> SourceRefreshResult` and `apply_mapping_changes(connection, evidence) -> MappingChangeSet`.

- [ ] **Step 1: Write failing source-cursor tests**

```python
def test_incremental_fetch_uses_each_source_cursor(fake_db):
    result = fetch_incremental_sources(fake_db, {"announcement": "2026-07-15", "interact_qa": "2026-07-14"})
    assert result.queries["announcement"].since == "2026-07-15"
    assert result.queries["interact_qa"].since == "2026-07-14"

def test_failed_source_does_not_advance_cursor():
    result = refresh_with_failure("research")
    assert "research" not in result.next_cursors
```

- [ ] **Step 2: Run tests and verify failure**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_sources.py tools/tests/test_embodied_refresh_mappings.py -q`

Expected: FAIL because incremental modules are missing.

- [ ] **Step 3: Extract reusable source queries without changing old CLI behavior**

Keep `repair_priority_supply_chains.py` backward compatible and move the embodied-specific query adapter behind:

```python
SOURCE_SPECS = {
    "announcement": SourceSpec("announcements", "ann_date"),
    "interact_qa": SourceSpec("interact_qa", "pub_date"),
    "research": SourceSpec("research_reports_tushare", "pub_date"),
    "profile": SourceSpec("stock_profiles", "updated_at"),
    "main_business": SourceSpec("fina_mainbz", "update_time"),
}
```

- [ ] **Step 4: Implement mapping transitions in one transaction**

```python
ALLOWED_TRANSITIONS = {
    "candidate": {"candidate", "verified", "weak_evidence", "rejected"},
    "verified": {"verified", "weak_evidence", "rejected"},
    "weak_evidence": {"candidate", "verified", "weak_evidence", "rejected"},
}
```

New mappings always use `candidate`; upgrade uses `can_auto_verify`; unavailable sources never emit downgrade changes. Persist `business_tag_pool_transition_log` or the existing compatible history table in the same transaction.

- [ ] **Step 5: Add rollback and ambiguous-node tests**

Test that a persistence error leaves mapping and transition history unchanged, and evidence matching two incompatible L5 nodes creates a review conflict rather than picking the first node.

- [ ] **Step 6: Run focused tests**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_sources.py tools/tests/test_embodied_refresh_mappings.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/repair_priority_supply_chains.py tools/embodied_refresh/sources.py tools/embodied_refresh/mappings.py tools/tests/test_embodied_refresh_sources.py tools/tests/test_embodied_refresh_mappings.py
git commit -m "feat: refresh embodied mappings incrementally"
```

### Task 4: L1–L8 Audit and Evidence-Constrained Top3

**Files:**
- Create: `tools/embodied_refresh/audit.py`
- Test: `tools/tests/test_embodied_refresh_audit.py`

**Interfaces:**
- Produces: `audit_chain(connection, run_id) -> ChainAudit` and `rank_node_leaders(candidates) -> list[LeaderSnapshot]`.

- [ ] **Step 1: Write failing coverage and ranking tests**

```python
def test_audit_reports_duplicate_ei_and_18c_nodes(sample_chain):
    audit = audit_chain(sample_chain)
    assert audit.duplicate_groups[0].canonical_node_id == "EI-L5-HARMONIC"

def test_missing_revenue_is_not_zero(sample_candidates):
    ranked = rank_node_leaders(sample_candidates)
    assert ranked[0].dimension_scores["revenue_realization"] is None

def test_multiple_tags_do_not_stack_add_score():
    ranked = rank_node_leaders(two_tags_same_company())
    assert len([row for row in ranked if row.code == "300503"]) == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_audit.py -q`

Expected: FAIL because audit functions are missing.

- [ ] **Step 3: Implement coverage and conflict audit**

Return coverage by layer, empty core nodes, duplicate semantic nodes, orphaned nodes, mappings with missing nodes, and `verified` mappings whose supporting evidence remains unapproved.

- [ ] **Step 4: Implement Top3 weighted scoring with eligibility split**

```python
LEADER_WEIGHTS = {
    "business_authenticity": 25,
    "commercialization": 20,
    "technology_moat": 15,
    "revenue_realization": 15,
    "node_importance": 10,
    "evidence_quality": 10,
    "competition_position": 5,
}
```

Normalize by available-weight coverage instead of treating missing dimensions as zero. Output `formal_top3` from `verified` and `watch_top3` with explicit candidate labels.

- [ ] **Step 5: Run focused tests**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_audit.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/embodied_refresh/audit.py tools/tests/test_embodied_refresh_audit.py
git commit -m "feat: audit embodied chain and rank leaders"
```

### Task 5: Change Scoring and Feishu Message Rendering

**Files:**
- Create: `tools/embodied_refresh/changes.py`
- Test: `tools/tests/test_embodied_refresh_changes.py`

**Interfaces:**
- Consumes: successful baseline snapshot plus current mapping/audit snapshot.
- Produces: `diff_snapshots(previous, current) -> list[EvidenceChange]`, `score_change(change) -> int`, `render_change_digest(batch) -> str`.

- [ ] **Step 1: Write failing scoring-boundary tests**

```python
@pytest.mark.parametrize((score, priority), [(85, "P0"), (84, "P1"), (70, "P1"), (69, "P2"), (50, "P2"), (49, "P3")])
def test_priority_boundaries(score, priority):
    assert priority_for_score(score) == priority

def test_failed_run_is_not_used_as_baseline(repository):
    assert repository.load_success_baseline().run_id == "last-success"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_changes.py -q`

Expected: FAIL because change functions are missing.

- [ ] **Step 3: Implement six-dimension importance score**

Use exact weights `source=25`, `commercialization=25`, `mapping_change=20`, `business_contribution=15`, `node_importance=10`, `freshness_crosscheck=5`; clamp to 0–100 and store factor detail.

- [ ] **Step 4: Implement deterministic digest rendering**

Render P0 then P1 then P2, each ordered by descending score and stable company code. Include cutoff time, counts, before/after status, stage, source, evidence date, remaining risk, L1–L8 coverage changes, and Top3 entry/exit reasons. Include the statement `重要性分数衡量产业证据变动，不表示股价上涨概率。`

- [ ] **Step 5: Add no-material-change and dedup tests**

Verify a P3-only batch renders no outbound message, and identical `change_fingerprint` is emitted once across reruns.

- [ ] **Step 6: Run focused tests**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_changes.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/embodied_refresh/changes.py tools/tests/test_embodied_refresh_changes.py
git commit -m "feat: score and render embodied evidence changes"
```

### Task 6: Idempotent Three-Group Delivery

**Files:**
- Create: `tools/embodied_refresh/delivery.py`
- Modify: `tools/run_research_pipeline.py`
- Test: `tools/tests/test_embodied_refresh_delivery.py`
- Test: `tools/tests/test_run_research_manifest.py`

**Interfaces:**
- Reuses: `extract_message_id`, `confirm_message_delivery`, and sender contract from `tools/run_research_pipeline.py`.
- Produces: `deliver_change_batch(repository, batch_id, targets, message, sender, confirmer) -> DeliverySummary`.

- [ ] **Step 1: Write failing delivery tests**

```python
def test_three_groups_require_individual_message_ids(fake_sender, repository):
    summary = deliver_change_batch(repository, "batch-1", TARGETS, "digest", fake_sender, always_confirm)
    assert summary.confirmed == 3
    assert all(row.message_id for row in repository.deliveries("batch-1"))

def test_successful_group_is_not_resent_on_retry(partial_sender, repository):
    deliver_change_batch(repository, "batch-2", TARGETS, "digest", partial_sender, always_confirm)
    deliver_change_batch(repository, "batch-2", TARGETS, "digest", partial_sender, always_confirm)
    assert partial_sender.calls["oc_success"] == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_delivery.py tools/tests/test_run_research_manifest.py -q`

Expected: FAIL because batch delivery is missing.

- [ ] **Step 3: Extract delivery verification helpers without changing existing pipeline behavior**

Keep all existing public functions compatible. Move reusable send/confirm behavior behind dependency-injected callables so tests do not contact Feishu.

- [ ] **Step 4: Implement persistent per-chat idempotency and retry schedule**

Persist `attempt_count` and `next_retry_at`; failed or unconfirmed targets become due after 5, 15, and 30 minutes. A separate non-blocking compensation invocation scans due rows every 5 minutes, so no process sleeps while waiting. Before every send, query `(change_batch_id, chat_id)`; skip a row already marked `confirmed`. Set overall status to `data_success_delivery_incomplete` until all three rows are confirmed.

- [ ] **Step 5: Run focused tests**

Run: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_delivery.py tools/tests/test_run_research_manifest.py -q`

Expected: PASS with existing research-delivery tests unchanged.

- [ ] **Step 6: Commit**

```bash
git add tools/embodied_refresh/delivery.py tools/run_research_pipeline.py tools/tests/test_embodied_refresh_delivery.py tools/tests/test_run_research_manifest.py
git commit -m "feat: deliver embodied changes idempotently"
```

### Task 7: Unified CLI and Scheduled Jobs

**Files:**
- Create: `tools/run_embodied_daily_refresh.py`
- Modify: `configs/scheduled_research.json`
- Modify: `services/data-service/app/scheduled_research.py`
- Modify: `services/data-service/tests/test_scheduled_research.py`
- Test: `tools/tests/test_run_embodied_daily_refresh.py`

**Interfaces:**
- Produces CLI: `python tools/run_embodied_daily_refresh.py --mode dry-run|apply|audit --as-of-date YYYY-MM-DD [--send-feishu]`.
- Produces scheduled task IDs: `embodied_daily_refresh_1930`, `embodied_weekly_audit_2030`, and `embodied_delivery_retry_5m`.

- [ ] **Step 1: Write failing CLI orchestration tests**

```python
def test_dry_run_never_writes_or_sends(orchestrator):
    result = orchestrator.run(mode="dry-run", as_of_date="2026-07-16")
    assert result.persisted is False
    assert result.delivery_attempted is False

def test_p3_only_apply_does_not_send(orchestrator):
    result = orchestrator.run(mode="apply", changes=[change(priority="P3")])
    assert result.delivery_attempted is False
```

- [ ] **Step 2: Write failing scheduler tests**

Assert config contains:

```python
("embodied_daily_refresh_1930", "30 19 * * *", "embodied_daily_refresh")
("embodied_weekly_audit_2030", "30 20 * * 0", "embodied_weekly_audit")
("embodied_delivery_retry_5m", "*/5 * * * *", "embodied_delivery_retry")
```

Also assert `calendar_scope="all_days"` bypasses `is_open_trading_day`, while the four trading strategies retain their current trading-day gate. The retry task invokes `--mode retry-delivery`, processes only rows whose `next_retry_at <= now()`, and never sends a row already marked `confirmed`.

- [ ] **Step 3: Run tests and verify failure**

Run: `bash tools/codex-lowio.sh py tools/tests/test_run_embodied_daily_refresh.py -q`

Run: `bash tools/codex-lowio.sh py services/data-service/tests/test_scheduled_research.py -q`

Expected: both focused suites FAIL on missing task support.

- [ ] **Step 4: Implement CLI transaction sequence**

Sequence: begin run -> load cursors -> refresh sources -> normalize evidence -> apply mapping transaction -> audit/rank -> diff successful baseline -> persist changes/snapshot -> conditionally deliver -> persist cursors only for successful sources -> finish run. On mapping failure, rollback and do not deliver.

- [ ] **Step 5: Extend scheduler command routing**

Add `task["runner"] == "embodied_refresh"` support that builds the dedicated CLI command rather than `run_research_pipeline.py`. Add `calendar_scope`; default remains `trading_days`, embodied tasks use `all_days`.

- [ ] **Step 6: Run focused tests**

Run: `bash tools/codex-lowio.sh py tools/tests/test_run_embodied_daily_refresh.py -q`

Run: `bash tools/codex-lowio.sh py services/data-service/tests/test_scheduled_research.py -q`

Expected: PASS; existing four task assertions updated to seven tasks without changing their cron values.

- [ ] **Step 7: Commit**

```bash
git add tools/run_embodied_daily_refresh.py configs/scheduled_research.json services/data-service/app/scheduled_research.py services/data-service/tests/test_scheduled_research.py tools/tests/test_run_embodied_daily_refresh.py
git commit -m "feat: schedule embodied chain refresh daily"
```

### Task 8: Staging Refresh, Mapping Supplement, and Real Delivery Acceptance

**Files:**
- Create: `docs/superpowers/uat/2026-07-16-embodied-intelligence-daily-refresh.md`
- Generated runtime evidence: `outputs/embodied_refresh/<run-id>/result.json`

**Interfaces:**
- Consumes the CLI and scheduled configuration from Task 7.
- Produces one accepted database batch, refreshed mappings, audit report, Top3 snapshot, and delivery metadata when material changes exist.

- [ ] **Step 1: Apply migration and capture pre-refresh baseline**

Run:

```bash
cd backend && DATABASE_SYNC_URL=postgresql+psycopg2://kronos:kronos@localhost:6432/kronos ../.venv/bin/alembic upgrade 036
```

Expected: Alembic reports upgrade `035 -> 036`. Then query counts by mapping status, evidence review status, L1–L8 coverage, duplicate node groups, and current Top3, and save the exact results in the UAT document.

- [ ] **Step 2: Run dry-run with current date**

Run:

```bash
python tools/run_embodied_daily_refresh.py --mode dry-run --as-of-date 2026-07-16
```

Expected: result identifies source cutoffs, candidate mapping changes, evidence changes, coverage gaps, duplicate nodes, and P0–P3 counts; database counts and Feishu remain unchanged.

- [ ] **Step 3: Review unsafe candidates before apply**

Reject or keep pending any candidate based only on a D source, vague language, conflicting nodes, or missing company/product/time. Record each exclusion reason in the UAT document; do not hand-edit a candidate to `verified`.

- [ ] **Step 4: Run apply and verify database invariants**

Run:

```bash
python tools/run_embodied_daily_refresh.py --mode apply --as-of-date 2026-07-16 --send-feishu
```

Expected: new candidates are `candidate/pending_review`; qualifying authoritative mappings upgrade through transition history; no duplicate evidence fingerprint; unavailable sources do not trigger downgrades.

- [ ] **Step 5: Verify three-group delivery only if P0–P2 exist**

If material changes exist, verify exactly three confirmed delivery rows with non-empty `message_id`, one for each configured chat. If only P3 or no changes exist, verify zero outbound delivery rows and record that no-message behavior as the accepted result; do not fabricate a material change merely to force a send.

- [ ] **Step 6: Run an identical second apply to prove idempotency**

Run the same command again.

Expected: zero new evidence fingerprints, zero new mapping transitions, unchanged Top3 snapshot content, and zero duplicate Feishu messages.

- [ ] **Step 7: Run all focused suites and low-I/O regression checks**

Run each separately to avoid shared `app` import collisions:

```bash
bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_repository.py tools/tests/test_embodied_refresh_evidence.py tools/tests/test_embodied_refresh_sources.py tools/tests/test_embodied_refresh_mappings.py tools/tests/test_embodied_refresh_audit.py tools/tests/test_embodied_refresh_changes.py tools/tests/test_embodied_refresh_delivery.py tools/tests/test_run_embodied_daily_refresh.py -q
bash tools/codex-lowio.sh py services/data-service/tests/test_scheduled_research.py -q
bash tools/codex-lowio.sh py tools/tests/test_repair_priority_supply_chains.py tools/tests/test_run_research_manifest.py -q
```

Expected: all three processes PASS.

- [ ] **Step 8: Commit acceptance evidence**

```bash
git add docs/superpowers/uat/2026-07-16-embodied-intelligence-daily-refresh.md
git commit -m "docs: verify embodied refresh delivery"
```

## Final Verification Checklist

- [ ] `git diff --check` reports no whitespace errors for task files.
- [ ] `git status --short` confirms no unrelated file is staged.
- [ ] Local PostgreSQL shows one successful baseline and no failed-run baseline promotion.
- [ ] Current mappings and evidence changes can be traced to source IDs and dates.
- [ ] L1–L8 coverage, duplicates, conflicts, formal Top3, and watch Top3 are present in `result.json`.
- [ ] No P0–P2 means no Feishu call; material changes mean three confirmed `message_id` values.
- [ ] Repeating the same apply produces no duplicate evidence, transition, snapshot change, or message.
