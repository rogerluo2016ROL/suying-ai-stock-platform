# Mapped Company CAPEX Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a structured CAPEX evidence layer for all mapped companies and connect it to supply-chain candidate ranking.

**Architecture:** Add a dedicated PostgreSQL table keyed by `mapping_id` and `code`, validate manually or semi-automatically collected evidence before writing, then aggregate fresh approved records into candidate ranking. Keep source quote mandatory so direction and amount are evidence-backed.

**Tech Stack:** Alembic SQL migrations, Python validation/import tool, FastAPI ranking query, pytest/Vitest checks.

## Global Constraints

- No source quote, no formal CAPEX evidence row.
- CAPEX amount is optional; when missing, the record is direction evidence only.
- Do not infer pure AI CAPEX from total company CAPEX.
- Rejected business-tag mappings must not contribute to ranking.
- Ranking boost must be capped and explainable.

---

### Task 1: CAPEX Evidence Storage

**Files:**
- Create: `backend/alembic/versions/024_business_tag_capex_evidence.py`
- Modify: `services/screener-service/tests/test_supply_chain_v2_migration_contract.py`

**Interfaces:**
- Produces table `business_tag_capex_evidence`.
- Later tasks rely on columns `mapping_id`, `code`, `chain_id`, `capex_direction`, `mapped_layer_id`, `quote`, `review_status`, `confidence`, `as_of_date`.

**Steps:**
- [ ] Add migration with `CREATE TABLE IF NOT EXISTS business_tag_capex_evidence`.
- [ ] Include indexes on `mapping_id`, `code`, `chain_id`, `review_status`, and `as_of_date`.
- [ ] Add migration contract assertions for table and required indexes.
- [ ] Run `bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py -q`.

### Task 2: CAPEX Evidence Validator And Importer

**Files:**
- Create: `tools/business_tag_capex_evidence.py`
- Create: `tools/tests/test_business_tag_capex_evidence.py`
- Create: `docs/data-templates/business-tag-capex-evidence.template.json`

**Interfaces:**
- Produces `load_records(path) -> list[dict]`.
- Produces `validate_records(records) -> dict`.
- Produces CLI `--input`, `--pg-url`, `--dry-run`, `--emit-template`.

**Steps:**
- [ ] Add tests for accepting a valid direction evidence row.
- [ ] Add tests for rejecting missing `quote`.
- [ ] Add tests for rejecting missing `mapping_id`, `code`, or `capex_direction`.
- [ ] Add importer with upsert by `capex_evidence_id`.
- [ ] Run `bash tools/codex-lowio.sh py tools/tests/test_business_tag_capex_evidence.py -q`.

### Task 3: Candidate Ranking Integration

**Files:**
- Modify: `tools/build_supply_chain_candidate_ranking.py`
- Modify: `services/screener-service/app/routers/screener.py`
- Modify: `tools/tests/test_supply_chain_candidate_ranking.py`
- Modify: `services/screener-service/tests/test_chain_api.py`

**Interfaces:**
- Candidate rows expose `company_capex_evidence`.
- `score_parts` includes `company_capex_evidence`.
- Ranking boost is capped at 3 points.

**Steps:**
- [ ] Aggregate approved CAPEX records by `mapping_id`.
- [ ] Score individual-company CAPEX evidence using amount presence, direction match, freshness, confidence, and layer match.
- [ ] Add fields to aggregated ranking output.
- [ ] Run ranking unit tests and candidate API tests.

### Task 4: Verification And Sample

**Files:**
- Create: `docs/data-templates/business-tag-capex-evidence.ai-compute-sample.json`

**Interfaces:**
- Sample file validates but is not automatically treated as truth unless imported.

**Steps:**
- [ ] Add one sample row for an AI compute mapping with explicit placeholder source fields.
- [ ] Run validator in dry-run mode.
- [ ] Run focused backend, tool, frontend typecheck, and diff checks.
