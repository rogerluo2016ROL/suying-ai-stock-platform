# Supply Chain Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable data foundation for the 大葱产业链解构选股模型 by generating full-chain BOM nodes, edges, company mappings, confidence/status labels, and a completeness report across all 10 configured chains.

**Architecture:** Add a pure foundation builder under `packages/kronos-factors` that reads `supply_chains.json` and stock/profile/report rows, then produces deterministic nodes, edges, BOM mappings, chain mappings, and report metrics. Add a CLI wrapper in `tools/` for dry-run and PG persistence. Update `SupplyChainEngine` and screener workbench enrichment to prefer persisted mapping data while preserving the existing keyword fallback.

**Tech Stack:** Python 3.10+, pytest, PostgreSQL via `psycopg2`, existing `kronos_factors.scorer._db_stub` and `pg_adapter`, existing FastAPI screener-service tests.

## Global Constraints

- Scope is data foundation only; do not change real-money trading, auto-trading, or broker code.
- First version must cover all 10 chains in `packages/kronos-factors/configs/supply_chains.json`.
- The implementation must support dry-run without writing PostgreSQL.
- Low-confidence mappings must be separated with `pending_review` or `weak_evidence`.
- Do not introduce an LLM dependency in this phase.
- Preserve existing `supply_chain` mode registration and `/supply-chain-bom` route.
- Do not revert unrelated dirty worktree changes.

---

## File Structure

- Create `packages/kronos-factors/kronos_factors/engine/supply_chain_foundation.py`
  - Pure functions for loading config, generating nodes/edges, scoring company-node matches, building reports, and preparing PG upsert rows.
- Create `packages/kronos-factors/tests/test_supply_chain_foundation.py`
  - Unit tests for node generation, edge generation, confidence/status rules, dry-run report shape, and no orphan edges.
- Create `tools/build_supply_chain_foundation.py`
  - CLI wrapper with `--dry-run`, `--persist`, `--chains`, `--min-confidence`, and `--report-path`.
- Create `services/screener-service/tests/test_supply_chain_foundation_api.py`
  - API-level tests that monkeypatch mapping-enriched candidates and assert workbench exposes mapping fields.
- Modify `packages/kronos-factors/kronos_factors/engine/supply_chain.py`
  - Prefer `company_chain_mapping` / `company_bom_mapping` rows when present; fallback to current keyword candidate generation when empty.
- Modify `services/screener-service/app/routers/screener.py`
  - Preserve current workbench payload, add mapping fields to candidate enrichment when available.
- Optionally modify `packages/kronos-factors/kronos_factors/engine/__init__.py`
  - Export foundation helpers only if tests or CLI need package-level import; otherwise leave untouched.

---

### Task 1: Pure Foundation Builder

**Files:**
- Create: `packages/kronos-factors/kronos_factors/engine/supply_chain_foundation.py`
- Test: `packages/kronos-factors/tests/test_supply_chain_foundation.py`

**Interfaces:**
- Consumes: `packages/kronos-factors/configs/supply_chains.json`
- Produces:
  - `load_supply_chain_config(path: str | Path | None = None) -> dict`
  - `build_foundation_catalog(config: dict, chains: list[str] | None = None) -> FoundationCatalog`
  - `score_company_mappings(catalog: FoundationCatalog, companies: list[CompanyText], min_confidence: float = 0.30) -> list[CompanyMapping]`
  - `build_foundation_report(catalog: FoundationCatalog, mappings: list[CompanyMapping]) -> dict`

- [ ] **Step 1: Write failing tests for catalog generation**

Add to `packages/kronos-factors/tests/test_supply_chain_foundation.py`:

```python
from kronos_factors.engine.supply_chain_foundation import (
    build_foundation_catalog,
    score_company_mappings,
    build_foundation_report,
)


def _sample_config():
    return {
        "chains": {
            "半导体": {
                "industries": ["半导体", "元器件"],
                "layers": ["材料", "设备", "制造", "封测", "设计"],
                "layer_keywords": {
                    "材料": ["光刻胶", "电子级玻璃布"],
                    "设备": ["刻蚀", "薄膜沉积"],
                    "制造": ["晶圆制造"],
                    "封测": ["封装测试"],
                    "设计": ["集成电路设计"],
                },
            },
            "AI算力": {
                "industries": ["通信设备", "软件服务"],
                "layers": ["硬件", "软件", "应用"],
                "layer_keywords": {
                    "硬件": ["光模块", "服务器"],
                    "软件": ["软件", "数据库"],
                    "应用": ["解决方案"],
                },
            },
        }
    }


def test_build_foundation_catalog_creates_chain_and_layer_nodes():
    catalog = build_foundation_catalog(_sample_config())
    node_ids = {node["node_id"] for node in catalog.nodes}

    assert "chain_semiconductor" in node_ids
    assert "semiconductor_materials" in node_ids
    assert "chain_ai_compute" in node_ids
    assert "ai_compute_hardware" in node_ids
    assert len(catalog.nodes) == 10


def test_build_foundation_catalog_creates_non_orphan_edges():
    catalog = build_foundation_catalog(_sample_config())
    node_ids = {node["node_id"] for node in catalog.nodes}

    assert len(catalog.edges) >= 8
    for edge in catalog.edges:
        assert edge["from_node_id"] in node_ids
        assert edge["to_node_id"] in node_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'kronos_factors.engine.supply_chain_foundation'`.

- [ ] **Step 3: Implement dataclasses and catalog generation**

Create `packages/kronos-factors/kronos_factors/engine/supply_chain_foundation.py`:

```python
"""Data foundation builders for the 大葱产业链解构模型.

Pure helpers only: no database writes and no network access.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "supply_chains.json"


CHAIN_IDS = {
    "半导体": "semiconductor",
    "新能源": "new_energy",
    "AI算力": "ai_compute",
    "机器人": "robotics",
    "创新药": "innovative_drug",
    "新能源车": "new_energy_vehicle",
    "消费升级": "consumer_upgrade",
    "国防军工": "defense",
    "高端制造": "advanced_manufacturing",
    "周期资源": "cyclical_resources",
}

LAYER_IDS = {
    "材料": "materials",
    "设备": "equipment",
    "制造": "manufacturing",
    "封测": "packaging_test",
    "设计": "design",
    "光伏": "photovoltaic",
    "电池": "battery",
    "硬件": "hardware",
    "软件": "software",
    "应用": "application",
    "核心部件": "core_parts",
    "整机": "complete_machine",
    "集成": "integration",
    "CXO": "cxo",
    "原料药": "api",
    "创新药": "innovative_drug",
    "零部件": "parts",
    "整车": "vehicle",
    "品牌": "brand",
    "渠道": "channel",
    "主机厂": "prime_contractor",
    "分系统": "subsystem",
    "元器件": "components",
    "资源": "resources",
    "冶炼": "smelting",
    "加工": "processing",
}


@dataclass(frozen=True)
class FoundationCatalog:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    chain_lookup: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class CompanyText:
    code: str
    name: str
    industry: str = ""
    main_business: str = ""
    introduction: str = ""
    report_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompanyMapping:
    code: str
    node_id: str
    chain_id: str
    product_name: str | None
    confidence: float
    status: str
    evidence: list[str]
    evidence_gaps: list[str]
    mapping_source: str


def load_supply_chain_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else CONFIG_PATH
    return json.loads(config_path.read_text(encoding="utf-8"))


def _slug_chain(chain_name: str) -> str:
    return CHAIN_IDS.get(chain_name, re.sub(r"\\W+", "_", chain_name.lower()).strip("_"))


def _slug_layer(layer_name: str) -> str:
    return LAYER_IDS.get(layer_name, re.sub(r"\\W+", "_", layer_name.lower()).strip("_"))


def build_foundation_catalog(config: dict, chains: list[str] | None = None) -> FoundationCatalog:
    selected = set(chains or [])
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    chain_lookup: dict[str, dict[str, Any]] = {}

    for chain_name, chain_cfg in (config.get("chains") or {}).items():
        if selected and chain_name not in selected:
            continue
        chain_slug = _slug_chain(chain_name)
        root_id = f"chain_{chain_slug}"
        root = {
            "node_id": root_id,
            "theme_id": "future_industry_core",
            "chain_id": chain_slug,
            "parent_node_id": None,
            "level": "chain",
            "name": chain_name,
            "node_type": "industry",
            "keywords": list(chain_cfg.get("industries") or []),
            "policy_weight": 1.5,
        }
        nodes.append(root)
        chain_lookup[chain_name] = root

        previous_layer_id: str | None = None
        for layer in chain_cfg.get("layers") or []:
            layer_slug = _slug_layer(layer)
            node_id = f"{chain_slug}_{layer_slug}"
            keywords = list((chain_cfg.get("layer_keywords") or {}).get(layer) or [])
            nodes.append({
                "node_id": node_id,
                "theme_id": "future_industry_core",
                "chain_id": chain_slug,
                "parent_node_id": root_id,
                "level": "layer",
                "name": layer,
                "node_type": "layer",
                "keywords": keywords,
                "policy_weight": 1.5,
            })
            edges.append({
                "edge_id": f"edge_{root_id}_{node_id}",
                "from_node_id": root_id,
                "to_node_id": node_id,
                "relation": "contains",
            })
            if previous_layer_id:
                edges.append({
                    "edge_id": f"edge_{previous_layer_id}_{node_id}",
                    "from_node_id": previous_layer_id,
                    "to_node_id": node_id,
                    "relation": "upstream_to_downstream",
                })
            previous_layer_id = node_id

    return FoundationCatalog(nodes=nodes, edges=edges, chain_lookup=chain_lookup)
```

- [ ] **Step 4: Add mapping confidence tests**

Append to `packages/kronos-factors/tests/test_supply_chain_foundation.py`:

```python
def test_score_company_mappings_labels_verified_when_business_and_industry_match():
    catalog = build_foundation_catalog(_sample_config())
    companies = [
        {
            "code": "301526",
            "name": "国际复材",
            "industry": "元器件",
            "main_business": "电子级玻璃纤维和电子级玻璃布研发生产销售",
            "introduction": "",
            "report_titles": [],
        }
    ]

    mappings = score_company_mappings(catalog, companies, min_confidence=0.30)

    assert mappings
    best = mappings[0]
    assert best.code == "301526"
    assert best.node_id == "semiconductor_materials"
    assert best.confidence >= 0.85
    assert best.status == "verified"
    assert best.mapping_source == "main_business"


def test_score_company_mappings_keeps_weak_industry_match_separate():
    catalog = build_foundation_catalog(_sample_config())
    companies = [
        {
            "code": "000001",
            "name": "测试半导体",
            "industry": "半导体",
            "main_business": "",
            "introduction": "",
            "report_titles": [],
        }
    ]

    mappings = score_company_mappings(catalog, companies, min_confidence=0.30)

    assert mappings
    assert mappings[0].confidence == 0.30
    assert mappings[0].status == "weak_evidence"
    assert mappings[0].mapping_source == "industry"
```

- [ ] **Step 5: Implement mapping and reporting helpers**

Add below `build_foundation_catalog` in `supply_chain_foundation.py`:

```python
def _normalise_company(raw: CompanyText | dict[str, Any]) -> CompanyText:
    if isinstance(raw, CompanyText):
        return raw
    return CompanyText(
        code=str(raw.get("code") or ""),
        name=str(raw.get("name") or ""),
        industry=str(raw.get("industry") or ""),
        main_business=str(raw.get("main_business") or ""),
        introduction=str(raw.get("introduction") or ""),
        report_titles=tuple(str(t) for t in (raw.get("report_titles") or [])),
    )


def _evidence_gaps(status: str) -> list[str]:
    if status == "verified":
        return []
    return [
        "是否有明确客户或供应链认证",
        "是否有量产、扩产、订单或定点公告",
        "该产品收入占比是否足够高",
        "是否存在国产替代或卡脖子稀缺性证据",
    ]


def _status_for(confidence: float) -> str:
    if confidence >= 0.85:
        return "verified"
    if confidence >= 0.45:
        return "pending_review"
    return "weak_evidence"


def score_company_mappings(
    catalog: FoundationCatalog,
    companies: list[CompanyText | dict[str, Any]],
    min_confidence: float = 0.30,
) -> list[CompanyMapping]:
    by_code_node: dict[tuple[str, str], CompanyMapping] = {}
    for raw in companies:
        company = _normalise_company(raw)
        text_main = company.main_business
        text_intro = company.introduction
        text_reports = " ".join(company.report_titles)
        for node in catalog.nodes:
            if node["level"] == "chain":
                continue
            keywords = [str(k) for k in node.get("keywords") or [] if k]
            if not keywords:
                continue
            industry_hit = any(k in company.industry for k in node.get("keywords") or [])
            main_hits = [k for k in keywords if k in text_main]
            intro_hits = [k for k in keywords if k in text_intro]
            report_hits = [k for k in keywords if k in text_reports]

            confidence = 0.0
            source = ""
            evidence: list[str] = []
            if main_hits:
                confidence = 0.85 if industry_hit else 0.65
                source = "main_business"
                evidence = main_hits[:5]
            elif intro_hits:
                confidence = 0.80 if industry_hit else 0.65
                source = "introduction"
                evidence = intro_hits[:5]
            elif report_hits:
                confidence = 0.50
                source = "research_report"
                evidence = report_hits[:5]
            elif any(ind in company.industry for ind in node.get("keywords") or []):
                confidence = 0.30
                source = "industry"
                evidence = [company.industry]

            if confidence < min_confidence:
                continue

            mapping = CompanyMapping(
                code=company.code,
                node_id=node["node_id"],
                chain_id=node["chain_id"],
                product_name=evidence[0] if evidence else None,
                confidence=round(confidence, 2),
                status=_status_for(confidence),
                evidence=evidence,
                evidence_gaps=_evidence_gaps(_status_for(confidence)),
                mapping_source=source,
            )
            key = (mapping.code, mapping.node_id)
            prev = by_code_node.get(key)
            if prev is None or mapping.confidence > prev.confidence:
                by_code_node[key] = mapping

    return sorted(by_code_node.values(), key=lambda m: (-m.confidence, m.code, m.node_id))


def build_foundation_report(catalog: FoundationCatalog, mappings: list[CompanyMapping]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    chain_counts: dict[str, int] = {}
    mapped_nodes = {m.node_id for m in mappings}
    for mapping in mappings:
        status_counts[mapping.status] = status_counts.get(mapping.status, 0) + 1
        chain_counts[mapping.chain_id] = chain_counts.get(mapping.chain_id, 0) + 1
    return {
        "node_count": len(catalog.nodes),
        "edge_count": len(catalog.edges),
        "mapping_count": len(mappings),
        "status_counts": status_counts,
        "chain_counts": chain_counts,
        "empty_nodes": [n["node_id"] for n in catalog.nodes if n["level"] != "chain" and n["node_id"] not in mapped_nodes],
        "top_mappings": [
            {
                "code": m.code,
                "node_id": m.node_id,
                "chain_id": m.chain_id,
                "confidence": m.confidence,
                "status": m.status,
                "mapping_source": m.mapping_source,
            }
            for m in mappings[:20]
        ],
    }
```

- [ ] **Step 6: Run Task 1 tests**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add packages/kronos-factors/kronos_factors/engine/supply_chain_foundation.py packages/kronos-factors/tests/test_supply_chain_foundation.py
git commit -m "feat: add supply chain foundation builder"
```

---

### Task 2: Dry-Run CLI And Completeness Report

**Files:**
- Create: `tools/build_supply_chain_foundation.py`
- Modify: `packages/kronos-factors/tests/test_supply_chain_foundation.py`

**Interfaces:**
- Consumes:
  - `load_supply_chain_config`
  - `build_foundation_catalog`
  - `score_company_mappings`
  - `build_foundation_report`
- Produces:
  - CLI JSON report at `outputs/supply_chain_foundation_report.json`
  - `collect_company_texts(pg_url: str) -> list[dict]`

- [ ] **Step 1: Add a test for report thresholds using the real config**

Append to `packages/kronos-factors/tests/test_supply_chain_foundation.py`:

```python
from pathlib import Path
from kronos_factors.engine.supply_chain_foundation import load_supply_chain_config


def test_real_config_catalog_meets_first_phase_node_and_edge_thresholds():
    config = load_supply_chain_config(Path(__file__).resolve().parents[1] / "configs" / "supply_chains.json")
    catalog = build_foundation_catalog(config)
    report = build_foundation_report(catalog, [])

    assert report["node_count"] >= 35
    assert report["edge_count"] >= 30
```

- [ ] **Step 2: Run test and confirm failure if catalog lacks thresholds**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py::test_real_config_catalog_meets_first_phase_node_and_edge_thresholds -v
```

Expected: PASS if Task 1 catalog generation already covers all 10 chains; otherwise FAIL with the exact count mismatch.

- [ ] **Step 3: Implement CLI skeleton**

Create `tools/build_supply_chain_foundation.py`:

```python
#!/usr/bin/env python3
"""Build 大葱产业链 data-foundation nodes, edges, mappings and report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "kronos-factors"))

from kronos_factors.engine.supply_chain_foundation import (  # noqa: E402
    build_foundation_catalog,
    build_foundation_report,
    load_supply_chain_config,
    score_company_mappings,
)


def collect_company_texts(pg_url: str) -> list[dict[str, Any]]:
    import psycopg2

    conn = psycopg2.connect(pg_url, connect_timeout=5)
    cur = conn.cursor()
    cur.execute("""
        SELECT s.code, s.name, s.industry,
               COALESCE(p.main_business, '') AS main_business,
               COALESCE(p.introduction, '') AS introduction
        FROM stocks s
        LEFT JOIN stock_profiles p ON p.code = s.code
        WHERE s.is_st = 0 AND s.name NOT LIKE '%ST%'
    """)
    companies = {
        str(code): {
            "code": str(code),
            "name": name or "",
            "industry": industry or "",
            "main_business": main_business or "",
            "introduction": introduction or "",
            "report_titles": [],
        }
        for code, name, industry, main_business, introduction in cur.fetchall()
    }
    cur.execute("""
        SELECT code, title
        FROM research_reports_tushare
        WHERE code IS NOT NULL AND code != 'nan'
        ORDER BY pub_date DESC
        LIMIT 50000
    """)
    seen: dict[str, int] = {}
    for code, title in cur.fetchall():
        code = str(code)
        if code not in companies or seen.get(code, 0) >= 5:
            continue
        companies[code]["report_titles"].append(str(title or ""))
        seen[code] = seen.get(code, 0) + 1
    cur.close()
    conn.close()
    return list(companies.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Generate report without writing PostgreSQL")
    parser.add_argument("--persist", action="store_true", help="Write generated rows to PostgreSQL")
    parser.add_argument("--chains", nargs="*", default=None, help="Optional Chinese chain names to include")
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--report-path", default="outputs/supply_chain_foundation_report.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.persist and args.dry_run:
        raise SystemExit("--persist and --dry-run cannot be used together")
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    config = load_supply_chain_config()
    catalog = build_foundation_catalog(config, chains=args.chains)
    companies = collect_company_texts(pg_url)
    mappings = score_company_mappings(catalog, companies, min_confidence=args.min_confidence)
    report = build_foundation_report(catalog, mappings)
    report.update({
        "dry_run": not args.persist,
        "persisted": False,
        "min_confidence": args.min_confidence,
    })

    report_path = REPO_ROOT / args.report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI dry-run**

Run:

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python3 tools/build_supply_chain_foundation.py --dry-run --report-path outputs/supply_chain_foundation_report.json
```

Expected: exit code 0 and JSON printed with `node_count >= 35`, `edge_count >= 30`, and `mapping_count >= 150`.

- [ ] **Step 5: Inspect report with jq-free Python**

Run:

```bash
python3 - <<'PY'
import json
r=json.load(open('outputs/supply_chain_foundation_report.json'))
print(r['node_count'], r['edge_count'], r['mapping_count'], r['status_counts'])
assert r['node_count'] >= 35
assert r['edge_count'] >= 30
assert r['mapping_count'] >= 150
PY
```

Expected: prints counts and exits 0.

- [ ] **Step 6: Commit Task 2**

```bash
git add tools/build_supply_chain_foundation.py packages/kronos-factors/tests/test_supply_chain_foundation.py outputs/supply_chain_foundation_report.json
git commit -m "feat: add supply chain foundation dry run"
```

---

### Task 3: PostgreSQL Persistence

**Files:**
- Modify: `tools/build_supply_chain_foundation.py`
- Modify: `packages/kronos-factors/tests/test_supply_chain_foundation.py`

**Interfaces:**
- Produces:
  - `persist_foundation(pg_url: str, catalog: FoundationCatalog, mappings: list[CompanyMapping]) -> dict`
  - Upserts into `supply_chain_bom_nodes`, `supply_chain_bom_edges`, `company_bom_mapping`, `company_chain_mapping`

- [ ] **Step 1: Add row conversion tests**

Append to `packages/kronos-factors/tests/test_supply_chain_foundation.py`:

```python
from kronos_factors.engine.supply_chain_foundation import mapping_to_pg_rows


def test_mapping_to_pg_rows_contains_bom_and_chain_rows():
    catalog = build_foundation_catalog(_sample_config())
    mapping = score_company_mappings(catalog, [{
        "code": "301526",
        "name": "国际复材",
        "industry": "元器件",
        "main_business": "电子级玻璃布",
        "introduction": "",
        "report_titles": [],
    }])[0]

    rows = mapping_to_pg_rows(mapping)

    assert rows["company_bom_mapping"]["code"] == "301526"
    assert rows["company_bom_mapping"]["status"] == "verified"
    assert rows["company_chain_mapping"]["policy_match_score"] >= 80
    assert rows["company_chain_mapping"]["evidence"]["mapping_source"] == "main_business"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py::test_mapping_to_pg_rows_contains_bom_and_chain_rows -v
```

Expected: FAIL with `ImportError` or `NameError` for `mapping_to_pg_rows`.

- [ ] **Step 3: Implement row conversion helper**

Add to `supply_chain_foundation.py`:

```python
def mapping_to_pg_rows(mapping: CompanyMapping) -> dict[str, dict[str, Any]]:
    evidence_payload = {
        "confidence": mapping.confidence,
        "status": mapping.status,
        "evidence": mapping.evidence,
        "evidence_gaps": mapping.evidence_gaps,
        "mapping_source": mapping.mapping_source,
    }
    score = round(mapping.confidence * 100, 1)
    return {
        "company_bom_mapping": {
            "mapping_id": f"auto_{mapping.code}_{mapping.node_id}",
            "code": mapping.code,
            "node_id": mapping.node_id,
            "product_name": mapping.product_name,
            "material_name": None,
            "evidence_ids": [],
            "confidence": mapping.confidence,
            "status": mapping.status,
        },
        "company_chain_mapping": {
            "code": mapping.code,
            "node_id": mapping.node_id,
            "main_pct": None,
            "policy_match_score": score,
            "chokepoint_score": 0,
            "evidence": evidence_payload,
            "three_factors": {},
            "trade_signal": "观察",
        },
    }
```

- [ ] **Step 4: Add `persist_foundation` to CLI**

In `tools/build_supply_chain_foundation.py`, import `mapping_to_pg_rows` and add:

```python
def persist_foundation(pg_url: str, catalog, mappings: list) -> dict[str, int]:
    import psycopg2
    from psycopg2.extras import Json
    from kronos_factors.engine.supply_chain_foundation import mapping_to_pg_rows

    conn = psycopg2.connect(pg_url, connect_timeout=5)
    cur = conn.cursor()
    node_count = edge_count = bom_count = chain_count = 0
    for node in catalog.nodes:
        cur.execute("""
            INSERT INTO supply_chain_bom_nodes
                (node_id, theme_id, chain_id, parent_node_id, level, name, node_type, keywords, policy_weight)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (node_id) DO UPDATE SET
                theme_id=EXCLUDED.theme_id,
                chain_id=EXCLUDED.chain_id,
                parent_node_id=EXCLUDED.parent_node_id,
                level=EXCLUDED.level,
                name=EXCLUDED.name,
                node_type=EXCLUDED.node_type,
                keywords=EXCLUDED.keywords,
                policy_weight=EXCLUDED.policy_weight
        """, (
            node["node_id"], node["theme_id"], node["chain_id"], node["parent_node_id"],
            node["level"], node["name"], node["node_type"], node["keywords"], node["policy_weight"],
        ))
        node_count += 1
    for edge in catalog.edges:
        cur.execute("""
            INSERT INTO supply_chain_bom_edges (edge_id, from_node_id, to_node_id, relation)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (edge_id) DO UPDATE SET
                from_node_id=EXCLUDED.from_node_id,
                to_node_id=EXCLUDED.to_node_id,
                relation=EXCLUDED.relation
        """, (edge["edge_id"], edge["from_node_id"], edge["to_node_id"], edge["relation"]))
        edge_count += 1
    for mapping in mappings:
        rows = mapping_to_pg_rows(mapping)
        bom = rows["company_bom_mapping"]
        cur.execute("""
            INSERT INTO company_bom_mapping
                (mapping_id, code, node_id, product_name, material_name, evidence_ids, confidence, status, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
            ON CONFLICT (mapping_id) DO UPDATE SET
                product_name=EXCLUDED.product_name,
                material_name=EXCLUDED.material_name,
                evidence_ids=EXCLUDED.evidence_ids,
                confidence=EXCLUDED.confidence,
                status=EXCLUDED.status,
                updated_at=CURRENT_TIMESTAMP
        """, (
            bom["mapping_id"], bom["code"], bom["node_id"], bom["product_name"], bom["material_name"],
            bom["evidence_ids"], bom["confidence"], bom["status"],
        ))
        bom_count += 1
        chain = rows["company_chain_mapping"]
        cur.execute("""
            INSERT INTO company_chain_mapping
                (code, node_id, main_pct, policy_match_score, chokepoint_score, evidence, three_factors, trade_signal)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (code, node_id) DO UPDATE SET
                main_pct=EXCLUDED.main_pct,
                policy_match_score=EXCLUDED.policy_match_score,
                chokepoint_score=EXCLUDED.chokepoint_score,
                evidence=EXCLUDED.evidence,
                three_factors=EXCLUDED.three_factors,
                trade_signal=EXCLUDED.trade_signal
        """, (
            chain["code"], chain["node_id"], chain["main_pct"], chain["policy_match_score"],
            chain["chokepoint_score"], Json(chain["evidence"]), Json(chain["three_factors"]), chain["trade_signal"],
        ))
        chain_count += 1
    conn.commit()
    cur.close()
    conn.close()
    return {
        "nodes": node_count,
        "edges": edge_count,
        "company_bom_mapping": bom_count,
        "company_chain_mapping": chain_count,
    }
```

Update `main()` before writing the report:

```python
    if args.persist:
        report["persist_counts"] = persist_foundation(pg_url, catalog, mappings)
        report["persisted"] = True
    else:
        report["persisted"] = False
```

- [ ] **Step 5: Run unit tests**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py -v
```

Expected: PASS.

- [ ] **Step 6: Run persistence smoke**

Run:

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python3 tools/build_supply_chain_foundation.py --persist --report-path outputs/supply_chain_foundation_report.json
```

Expected: exit code 0 and report includes `persisted: true`, `persist_counts.company_chain_mapping >= 150`, `persist_counts.company_bom_mapping >= 150`.

- [ ] **Step 7: Verify PG counts**

Run:

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python3 - <<'PY'
import os, psycopg2
conn=psycopg2.connect(os.environ['KRONOS_PG_URL'])
cur=conn.cursor()
for t in ['supply_chain_bom_nodes','supply_chain_bom_edges','company_bom_mapping','company_chain_mapping']:
    cur.execute(f'select count(*) from {t}')
    print(t, cur.fetchone()[0])
cur.close(); conn.close()
PY
```

Expected: `supply_chain_bom_nodes >= 35`, `supply_chain_bom_edges >= 30`, `company_bom_mapping >= 150`, `company_chain_mapping >= 150`.

- [ ] **Step 8: Commit Task 3**

```bash
git add packages/kronos-factors/kronos_factors/engine/supply_chain_foundation.py packages/kronos-factors/tests/test_supply_chain_foundation.py tools/build_supply_chain_foundation.py outputs/supply_chain_foundation_report.json
git commit -m "feat: persist supply chain foundation"
```

---

### Task 4: SupplyChainEngine Mapping-First Candidate Pool

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/supply_chain.py`
- Test: `packages/kronos-factors/tests/test_supply_chain_foundation.py`

**Interfaces:**
- Consumes persisted `company_chain_mapping` and `company_bom_mapping`.
- Produces Top30 picks containing:
  - `node_id`
  - `node_name`
  - `mapping_confidence`
  - `mapping_status`
  - `mapping_source`
  - `evidence_gaps`

- [ ] **Step 1: Add a focused helper test**

Append to `packages/kronos-factors/tests/test_supply_chain_foundation.py`:

```python
from kronos_factors.engine.supply_chain import _merge_mapping_context


def test_merge_mapping_context_adds_mapping_fields_without_overwriting_score():
    pick = {"code": "301526", "name": "国际复材", "total_score": 71.0}
    context = {
        "301526": {
            "node_id": "semiconductor_materials",
            "node_name": "材料",
            "mapping_confidence": 0.85,
            "mapping_status": "verified",
            "mapping_source": "main_business",
            "evidence_gaps": [],
        }
    }

    merged = _merge_mapping_context(pick, context)

    assert merged["total_score"] == 71.0
    assert merged["node_id"] == "semiconductor_materials"
    assert merged["mapping_confidence"] == 0.85
    assert merged["mapping_status"] == "verified"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py::test_merge_mapping_context_adds_mapping_fields_without_overwriting_score -v
```

Expected: FAIL with `ImportError` for `_merge_mapping_context`.

- [ ] **Step 3: Add mapping context helpers to `supply_chain.py`**

Add near the top-level helper section in `packages/kronos-factors/kronos_factors/engine/supply_chain.py`:

```python
def _merge_mapping_context(pick: dict, mapping_context: dict[str, dict]) -> dict:
    enriched = dict(pick)
    context = mapping_context.get(str(pick.get("code") or ""))
    if not context:
        enriched.setdefault("mapping_source", "fallback_keyword")
        enriched.setdefault("mapping_status", "weak_evidence")
        enriched.setdefault("evidence_gaps", ["缺少公司到产业链节点的正式映射"])
        return enriched
    enriched.update({
        "node_id": context.get("node_id"),
        "node_name": context.get("node_name"),
        "mapping_confidence": context.get("mapping_confidence"),
        "mapping_status": context.get("mapping_status"),
        "mapping_source": context.get("mapping_source"),
        "evidence_gaps": context.get("evidence_gaps") or [],
    })
    return enriched
```

Inside `SupplyChainEngine.run`, after loading PG datasets and before final `picks` sorting, load mapping context:

```python
            mapping_context = {}
            try:
                cur.execute("""
                    SELECT c.code, c.node_id, n.name AS node_name,
                           b.confidence, b.status, c.evidence
                    FROM company_chain_mapping c
                    LEFT JOIN company_bom_mapping b ON b.code = c.code AND b.node_id = c.node_id
                    LEFT JOIN supply_chain_bom_nodes n ON n.node_id = c.node_id
                """)
                for code, node_id, node_name, confidence, status, evidence in cur.fetchall():
                    evidence = evidence or {}
                    mapping_context[str(code)] = {
                        "node_id": node_id,
                        "node_name": node_name,
                        "mapping_confidence": float(confidence or 0),
                        "mapping_status": status or evidence.get("status") or "pending_review",
                        "mapping_source": evidence.get("mapping_source") or "company_chain_mapping",
                        "evidence_gaps": evidence.get("evidence_gaps") or [],
                    }
            except Exception:
                mapping_context = {}
```

After `picks = [score_company_v4(p) for p in seen.values()]`, enrich:

```python
        picks = [_merge_mapping_context(p, mapping_context if "mapping_context" in locals() else {}) for p in picks]
```

- [ ] **Step 4: Run helper test**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py::test_merge_mapping_context_adds_mapping_fields_without_overwriting_score -v
```

Expected: PASS.

- [ ] **Step 5: Run model smoke**

Run:

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos PYTHONPATH=packages/kronos-factors .venv/bin/python - <<'PY'
from kronos_factors.pg_adapter import create_pg_adapter
from kronos_factors.scorer._db_stub import set_db_adapter
from kronos_factors.engine.supply_chain import SupplyChainEngine
set_db_adapter(create_pg_adapter())
picks=SupplyChainEngine().run(top_n=30, trade_date='2026-06-25').picks
print(len(picks), picks[0].keys())
assert len(picks) == 30
assert 'mapping_status' in picks[0]
PY
```

Expected: prints `30` and candidate keys including `mapping_status`.

- [ ] **Step 6: Commit Task 4**

```bash
git add packages/kronos-factors/kronos_factors/engine/supply_chain.py packages/kronos-factors/tests/test_supply_chain_foundation.py
git commit -m "feat: use supply chain mappings in screener"
```

---

### Task 5: Workbench API Fields And End-To-End Verification

**Files:**
- Modify: `services/screener-service/app/routers/screener.py`
- Create: `services/screener-service/tests/test_supply_chain_foundation_api.py`
- Modify: `docs/superpowers/specs/2026-06-25-supply-chain-data-foundation-design.md` only if actual implementation intentionally changes a named output field.

**Interfaces:**
- Consumes model picks enriched by Task 4.
- Produces API candidates with:
  - `node_id`
  - `node_name`
  - `mapping_confidence`
  - `mapping_status`
  - `mapping_source`
  - `evidence_gaps`

- [ ] **Step 1: Write API test**

Create `services/screener-service/tests/test_supply_chain_foundation_api.py`:

```python
import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "kronos-factors"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers.screener import router
import app.routers.screener as screener_router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_workbench_candidates_include_mapping_context(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [{
            "code": "301526",
            "name": "国际复材",
            "chain": "半导体",
            "layer": "材料",
            "score": 71.0,
            "rating": "B",
            "trade_signal": "观察",
            "node_id": "semiconductor_materials",
            "node_name": "材料",
            "mapping_confidence": 0.85,
            "mapping_status": "verified",
            "mapping_source": "main_business",
            "evidence_gaps": [],
        }],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10")

    assert r.status_code == 200
    candidate = r.json()["candidates"][0]
    assert candidate["node_id"] == "semiconductor_materials"
    assert candidate["node_name"] == "材料"
    assert candidate["mapping_confidence"] == 0.85
    assert candidate["mapping_status"] == "verified"
    assert candidate["mapping_source"] == "main_business"
    assert candidate["evidence_gaps"] == []
```

- [ ] **Step 2: Run test and verify failure if fields are dropped**

Run:

```bash
cd services/screener-service && ../../.venv/bin/pytest tests/test_supply_chain_foundation_api.py -v
```

Expected: FAIL if `_sanitize_picks` or `_enrich_supply_chain_candidate` strips mapping fields.

- [ ] **Step 3: Preserve mapping fields in router enrichment**

In `services/screener-service/app/routers/screener.py`, update the candidate enrichment helper that builds workbench candidates so it copies:

```python
for key in (
    "node_id",
    "node_name",
    "mapping_confidence",
    "mapping_status",
    "mapping_source",
    "evidence_gaps",
):
    if key in pick:
        enriched[key] = pick[key]
```

If the file already has an allowed-key sanitizer, add these six keys to that allowlist instead of adding a second copy loop.

- [ ] **Step 4: Run API tests**

Run:

```bash
cd services/screener-service && ../../.venv/bin/pytest tests/test_supply_chain_foundation_api.py tests/test_supply_chain_bom_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full supply-chain verification commands**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py tests/test_chain_deconstruct.py -v
```

Expected: PASS.

Run:

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos PYTHONPATH=packages/kronos-factors:services/screener-service .venv/bin/python - <<'PY'
from kronos_factors.pg_adapter import create_pg_adapter
from kronos_factors.scorer._db_stub import set_db_adapter
from kronos_factors.engine.supply_chain import SupplyChainEngine
set_db_adapter(create_pg_adapter())
picks=SupplyChainEngine().run(top_n=30, trade_date='2026-06-25').picks
mapped=sum(1 for p in picks if p.get('mapping_source') != 'fallback_keyword')
print({'count': len(picks), 'mapped': mapped, 'top': picks[:3]})
assert len(picks) == 30
assert mapped >= 1
PY
```

Expected: PASS and printed dict has `count: 30`.

- [ ] **Step 6: Commit Task 5**

```bash
git add services/screener-service/app/routers/screener.py services/screener-service/tests/test_supply_chain_foundation_api.py
git commit -m "feat: expose supply chain mapping context"
```

---

## Final Verification

- [ ] Run all focused tests:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_foundation.py tests/test_chain_deconstruct.py -v
cd ../../services/screener-service && ../../.venv/bin/pytest tests/test_supply_chain_foundation_api.py tests/test_supply_chain_bom_api.py -v
```

Expected: all PASS.

- [ ] Generate and persist latest foundation:

```bash
cd /Users/rogerluo/程序目录/K线大模型
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python3 tools/build_supply_chain_foundation.py --persist --report-path outputs/supply_chain_foundation_report.json
```

Expected: report contains `persisted: true`, `node_count >= 35`, `edge_count >= 30`, `mapping_count >= 150`.

- [ ] Run final model smoke:

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos PYTHONPATH=packages/kronos-factors .venv/bin/python - <<'PY'
from kronos_factors.pg_adapter import create_pg_adapter
from kronos_factors.scorer._db_stub import set_db_adapter
from kronos_factors.engine.supply_chain import SupplyChainEngine
set_db_adapter(create_pg_adapter())
picks=SupplyChainEngine().run(top_n=30, trade_date='2026-06-25').picks
for p in picks[:10]:
    print(p.get('code'), p.get('name'), p.get('chain'), p.get('node_name'), p.get('mapping_status'), p.get('mapping_confidence'))
assert all('mapping_status' in p for p in picks)
PY
```

Expected: Top10 rows print mapping status/confidence and assertion passes.

## Self-Review

- Spec coverage: The plan covers all design goals: 10-chain catalog generation, BOM nodes, edges, company BOM mappings, company chain mappings, confidence/status, evidence gaps, report output, model fallback, and API exposure.
- Placeholder scan: No `TBD`, `TODO`, `implement later`, or undefined future tasks remain.
- Type consistency: `FoundationCatalog`, `CompanyText`, `CompanyMapping`, `mapping_to_pg_rows`, and `_merge_mapping_context` are defined before downstream tasks consume them.
- Scope check: The plan stays inside data foundation, model enrichment, and workbench API fields; it does not touch trading, auto-trading, or LLM extraction.
