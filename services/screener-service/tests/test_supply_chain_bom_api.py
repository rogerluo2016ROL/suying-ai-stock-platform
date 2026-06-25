import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "kronos-factors"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers.screener import router
import app.routers.screener as screener_router
from kronos_factors.engine.supply_chain_bom_v5 import DIM_WEIGHTS as V5_DIM_WEIGHTS


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_supply_chain_bom_schema_table_names_are_stable():
    migration = REPO_ROOT / "backend" / "alembic" / "versions" / "012_supply_chain_bom_v4.py"
    text = migration.read_text(encoding="utf-8")
    expected = {
        "policy_sources",
        "policy_themes",
        "supply_chain_bom_nodes",
        "supply_chain_bom_edges",
        "company_bom_mapping",
        "company_evidence",
        "supply_chain_scores",
        "manual_overrides",
    }
    for table in expected:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text


def test_supply_chain_bom_seed_contains_future_industry_core():
    seed = REPO_ROOT / "packages" / "kronos-factors" / "configs" / "supply_chain_bom_v4.json"
    text = seed.read_text(encoding="utf-8")
    for keyword in ("未来产业主攻方向", "量子科技", "生物制造", "具身智能", "第六代移动通信"):
        assert keyword in text


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_supply_chain_themes_endpoint_returns_themes():
    r = _client().get("/api/v1/screener/supply-chain/themes")
    assert r.status_code == 200
    body = r.json()
    assert "themes" in body
    assert any(t["name"] == "未来产业主攻方向" for t in body["themes"])


def test_supply_chain_bom_endpoint_returns_nodes_and_edges():
    r = _client().get("/api/v1/screener/supply-chain/bom")
    assert r.status_code == 200
    body = r.json()
    assert "nodes" in body
    assert "edges" in body
    assert any(n["node_id"] == "embodied_ai_core" for n in body["nodes"])


def test_supply_chain_node_endpoint_returns_company_candidates(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_query_supply_chain_node_companies",
        lambda node_id: [{
            "code": "688001",
            "name": "测试科技",
            "rank": 1,
            "rating": "A",
            "trade_signal": "启动",
            "product_name": "关节模组",
            "material_name": "高精密减速器",
        }],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/node/embodied_ai_core")
    assert r.status_code == 200
    body = r.json()
    assert body["companies"][0]["code"] == "688001"
    assert body["companies"][0]["trade_signal"] == "启动"


def test_supply_chain_company_endpoint_returns_company_drilldown(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_query_supply_chain_company_detail",
        lambda code: {
            "code": code,
            "rank": 1,
            "rating": "A",
            "trade_signal": "启动",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["未来产业主攻方向", "具身智能", "核心部件"],
            "products": ["关节模组"],
            "materials": ["高精密减速器"],
            "financial_indicators": {"revenue_growth": 28.5, "profit_growth": 31.2},
            "moat_evidence": [{"evidence_type": "patent", "summary": "核心专利覆盖关键工艺"}],
            "evidence": [],
        },
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/company/688001")
    assert r.status_code == 200
    body = r.json()
    assert body["products"] == ["关节模组"]
    assert body["financial_indicators"]["profit_growth"] == 31.2
    assert body["moat_evidence"][0]["evidence_type"] == "patent"


def test_supply_chain_workbench_returns_candidate_pool_with_model_context(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [{
            "code": "300308",
            "name": "中际旭创",
            "chain": "AI算力",
            "layer": "硬件",
            "score": 72.4,
            "rating": "B",
            "trade_signal": "观察",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["AI算力", "硬件"],
            "company_product_map": {"products": ["高速光模块"], "materials": ["光芯片"]},
            "commercialization_stage": "规模推广",
            "commercialization_cycle": "业绩兑现",
            "resonance": {
                "policy": "强",
                "commercialization": "量产放量",
                "performance": "高增长",
                "market": "趋势确认",
                "summary": "政策、商业化、业绩、市场四维共振",
            },
            "selection_reason": "AI算力硬件核心环节，产品已规模推广，业绩高增长。",
            "dimension_scores": {
                "policy": 12.0,
                "bom": 14.0,
                "chokepoint": 13.0,
                "growth": 15.0,
                "profit": 8.0,
                "commercialization": 13.0,
                "market": 5.0,
            },
            "moat_signals": ["行业龙头", "技术壁垒"],
            "financial_indicators": {"revenue_growth": 192.1, "profit_growth": 571.8, "roe": 17.5, "gross_margin": 46.1},
        }],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10")
    assert r.status_code == 200
    body = r.json()
    assert body["model"]["name"] == "大葱产业链解构选股模型 V5"
    assert body["model"]["version"] == "5.0"
    assert body["candidate_count"] == 1
    candidate = body["candidates"][0]
    assert candidate["code"] == "300308"
    assert candidate["selection_reason"].startswith("AI算力硬件核心环节")
    assert candidate["commercialization_stage"] == "规模推广"
    assert candidate["commercialization_cycle"] == "业绩兑现"
    assert candidate["resonance"]["summary"] == "政策、商业化、业绩、市场四维共振"
    assert candidate["dimension_scores"]["commercialization"] == 13.0


def test_supply_chain_workbench_model_dimensions_match_v5_scorer(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10")

    assert r.status_code == 200
    dimensions = {
        item["key"]: item["weight"]
        for item in r.json()["model"]["score_dimensions"]
    }
    assert dimensions == V5_DIM_WEIGHTS


def test_supply_chain_workbench_filters_candidates_by_selected_node(monkeypatch):
    fake_candidates = [
        {
            "code": "688017",
            "name": "绿的谐波",
            "chain": "机器人",
            "layer": "减速器",
            "score": 78.5,
            "rating": "A",
            "trade_signal": "启动",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["未来产业主攻方向", "具身智能", "中游", "减速器"],
            "products": ["谐波减速器"],
            "materials": ["高精密轴承材料"],
            "commercialization_stage": "量产爬坡",
            "commercialization_cycle": "量产启动",
            "resonance": {"summary": "政策、商业化、业绩三维共振"},
            "selection_reason": "绿的谐波卡位具身智能减速器节点，量产爬坡阶段。",
            "dimension_scores": {"policy": 13.0, "bom": 14.0, "commercialization": 13.0},
        },
        {
            "code": "300308",
            "name": "中际旭创",
            "chain": "AI算力",
            "layer": "高速光模块",
            "score": 72.4,
            "rating": "B",
            "trade_signal": "观察",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["未来产业主攻方向", "AI算力", "硬件", "高速光模块"],
            "products": ["高速光模块"],
            "materials": ["光芯片"],
            "commercialization_stage": "规模推广",
            "commercialization_cycle": "业绩兑现",
            "resonance": {"summary": "政策、商业化、业绩、市场四维共振"},
            "selection_reason": "中际旭创卡位AI算力光模块节点。",
            "dimension_scores": {"policy": 12.0, "bom": 13.0, "commercialization": 14.0},
        },
    ]
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: fake_candidates,
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10&node_id=embodied_ai_core")

    assert r.status_code == 200
    body = r.json()
    assert body["selected_node_thesis"]["node_id"] == "embodied_ai_core"
    assert body["selected_node_thesis"]["name"] == "具身智能"
    assert body["node_candidate_count"] == 1
    assert [c["code"] for c in body["node_candidate_companies"]] == ["688017"]
    assert body["node_candidate_companies"][0]["matched_node_id"] == "embodied_ai_core"
    assert body["node_candidate_companies"][0]["matched_node_name"] == "具身智能"
    assert "中际旭创" not in [c["name"] for c in body["node_candidate_companies"]]


def test_supply_chain_workbench_keeps_empty_node_pool_when_mapping_missing(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [{
            "code": "300308",
            "name": "中际旭创",
            "chain": "AI算力",
            "layer": "高速光模块",
            "score": 72.4,
            "rating": "B",
            "trade_signal": "观察",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["未来产业主攻方向", "AI算力", "硬件", "高速光模块"],
            "products": ["高速光模块"],
            "materials": ["光芯片"],
            "commercialization_stage": "规模推广",
            "commercialization_cycle": "业绩兑现",
            "resonance": {"summary": "政策、商业化、业绩、市场四维共振"},
            "selection_reason": "中际旭创卡位AI算力光模块节点。",
            "dimension_scores": {"policy": 12.0},
        }],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10&node_id=quantum_core")

    assert r.status_code == 200
    body = r.json()
    assert body["selected_node_thesis"]["node_id"] == "quantum_core"
    assert body["node_candidate_count"] == 0
    assert body["node_candidate_companies"] == []
    assert body["selected_node_thesis"]["mapping_status"] == "missing_company_mapping"
    assert body["selected_node_thesis"]["mapping_message"] == "该节点缺少公司映射证据"


def test_research_ingestion_status_distinguishes_local_report_catalog(monkeypatch):
    monkeypatch.delenv("SUPPLY_CHAIN_REPORT_AUTO_INGEST", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        screener_router,
        "_query_research_report_freshness",
        lambda: {"latest_pub_date": "2026-06-09", "row_count": 115106},
        raising=False,
    )

    status = screener_router._query_research_ingestion_status()

    assert status["auto_collection_status"] == "local_catalog_available"
    assert status["llm_auto_extract_enabled"] is False
    assert status["source_latest_pub_date"] == "2026-06-09"
    assert status["source_row_count"] == 115106
    assert "Tushare研报库已接入" in status["message"]


def test_supply_chain_workbench_returns_market_freshness_and_report_ingestion_status(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [{
            "code": "300308",
            "name": "中际旭创",
            "chain": "AI算力",
            "layer": "高速光模块",
            "score": 72.4,
            "rating": "B",
            "trade_signal": "观察",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["未来产业主攻方向", "AI算力", "硬件", "高速光模块"],
            "products": ["高速光模块"],
            "materials": ["光芯片"],
            "commercialization_stage": "规模推广",
            "commercialization_cycle": "业绩兑现",
            "resonance": {"summary": "政策、商业化、业绩、市场四维共振"},
            "selection_reason": "中际旭创卡位AI算力光模块节点。",
            "dimension_scores": {"policy": 12.0},
        }],
        raising=False,
    )
    monkeypatch.setattr(
        screener_router,
        "_query_latest_market_snapshots",
        lambda codes, trade_date=None: {
            "300308": {
                "last_trade_date": "2026-06-22",
                "last_price": 128.56,
                "last_change_pct": 3.21,
            },
        },
        raising=False,
    )
    monkeypatch.setattr(
        screener_router,
        "_query_supply_chain_data_freshness",
        lambda: {
            "market": {"latest_trade_date": "2026-06-22", "row_count": 8563922},
            "research_reports": {"latest_pub_date": "2026-06-09", "row_count": 115106},
            "broker_recommend": {"latest_month": "202606", "row_count": 17347},
        },
        raising=False,
    )
    monkeypatch.setattr(
        screener_router,
        "_query_research_ingestion_status",
        lambda: {
            "auto_collection_status": "local_catalog_available",
            "llm_auto_extract_enabled": False,
            "manual_extract_available": True,
            "source_latest_pub_date": "2026-06-09",
            "source_row_count": 115106,
            "message": "Tushare研报库已接入，最新研报日期 2026-06-09，但LLM批量抽取和图谱写入调度尚未开启。",
        },
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10")

    assert r.status_code == 200
    body = r.json()
    candidate = body["candidates"][0]
    assert candidate["last_trade_date"] == "2026-06-22"
    assert candidate["last_price"] == 128.56
    assert candidate["last_change_pct"] == 3.21
    assert body["data_freshness"]["market"]["latest_trade_date"] == "2026-06-22"
    assert body["data_freshness"]["research_reports"]["latest_pub_date"] == "2026-06-09"
    assert body["research_ingestion"]["auto_collection_status"] == "local_catalog_available"
    assert body["research_ingestion"]["llm_auto_extract_enabled"] is False
    assert body["research_ingestion"]["source_row_count"] == 115106


def test_supply_chain_workbench_returns_upstream_influence_observation_pool(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [],
        raising=False,
    )
    monkeypatch.setattr(
        screener_router,
        "_query_upstream_influence_candidates",
        lambda limit=50, trade_date=None: [{
            "code": "300522",
            "name": "世名科技",
            "industry": "染料涂料",
            "candidate_source": "upstream_influence",
            "pool_status": "观察池",
            "upstream_node": "功能色浆/纳米材料",
            "impact_role": "上游功能材料",
            "downstream_chains": ["显示材料", "新材料", "高端制造"],
            "influence_paths": ["世名科技 → 功能色浆/纳米材料 → 显示材料"],
            "selection_reason": "世名科技不因染料涂料行业被排除，先进入上游影响观察池。",
        }],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10")

    assert r.status_code == 200
    body = r.json()
    assert body["upstream_influence_count"] == 1
    candidate = body["upstream_influence_candidates"][0]
    assert candidate["code"] == "300522"
    assert candidate["pool_status"] == "观察池"
    assert "显示材料" in candidate["downstream_chains"]
    assert candidate["influence_paths"][0] == "世名科技 → 功能色浆/纳米材料 → 显示材料"


def test_supply_chain_company_endpoint_falls_back_to_candidate_pool(monkeypatch):
    monkeypatch.setattr(screener_router, "_query_supply_chain_company_detail", lambda code: None)
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [{
            "code": "300308",
            "name": "中际旭创",
            "rank": 3,
            "rating": "B",
            "trade_signal": "观察",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["AI算力", "硬件"],
            "products": ["高速光模块"],
            "materials": ["光芯片"],
            "financial_indicators": {"revenue_growth": 192.1, "profit_growth": 571.8},
            "moat_evidence": [{"evidence_type": "moat_signal", "summary": "行业龙头"}],
            "selection_reason": "高速光模块核心公司，量产推广阶段。",
            "commercialization_stage": "规模推广",
            "resonance": {"summary": "政策、商业化、业绩共振"},
        }],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/company/300308")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "中际旭创"
    assert body["products"] == ["高速光模块"]
    assert body["selection_reason"] == "高速光模块核心公司，量产推广阶段。"
    assert body["commercialization_stage"] == "规模推广"
    assert body["resonance"]["summary"] == "政策、商业化、业绩共振"


def test_supply_chain_extract_endpoint_disables_without_llm_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    r = _client().post(
        "/api/v1/screener/supply-chain/extract",
        json={"text": "公司公告：具身智能关节模组已小批量交付", "source": {"title": "测试公告"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "disabled"
    assert "Missing API key" in body["reason"]
    assert "DEEPSEEK_API_KEY" in body["reason"]


def test_supply_chain_extract_endpoint_returns_records_preview(monkeypatch):
    def fake_extract(text, source, provider="deepseek"):
        return {
            "status": "ok",
            "policy_theme": "未来产业主攻方向",
            "bom_nodes": ["具身智能"],
            "companies": [{"code": "688001", "name": "测试科技"}],
            "products": ["关节模组"],
            "materials": ["高精密减速器"],
            "evidence": [{"summary": "小批量交付", "confidence": 0.8, "source_type": "announcement"}],
        }

    monkeypatch.setattr("app.llm_supply_chain.extract_supply_chain_facts", fake_extract)

    r = _client().post(
        "/api/v1/screener/supply-chain/extract",
        json={"text": "公司公告：具身智能关节模组已小批量交付", "source": {"title": "测试公告"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["persisted"] is False
    assert body["records"]["mappings"][0]["code"] == "688001"
    assert body["records"]["evidence"][0]["status"] == "pending_review"


def test_supply_chain_research_ingest_disables_without_llm_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        screener_router,
        "_query_recent_research_reports",
        lambda limit=5, keyword=None: [{
            "code": "688001",
            "pub_date": "2026-06-09",
            "title": "测试研报_具身智能关节模组量产验证_20260609.pdf",
            "broker": "测试证券",
            "rating": "买入",
            "target_price": 88.0,
        }],
        raising=False,
    )

    r = _client().post("/api/v1/screener/supply-chain/research/ingest", json={"limit": 5})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "disabled"
    assert "Missing API key" in body["reason"]
    assert "DEEPSEEK_API_KEY" in body["reason"]
    assert body["report_count"] == 1


def test_supply_chain_research_ingest_extracts_recent_reports(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(
        screener_router,
        "_query_recent_research_reports",
        lambda limit=5, keyword=None: [{
            "code": "688001",
            "pub_date": "2026-06-09",
            "title": "测试研报_具身智能关节模组量产验证_20260609.pdf",
            "broker": "测试证券",
            "rating": "买入",
            "target_price": 88.0,
        }],
        raising=False,
    )

    def fake_extract(text, source, provider="deepseek"):
        assert "具身智能关节模组量产验证" in text
        assert source["source_type"] == "tushare_research_report"
        return {
            "status": "ok",
            "policy_theme": "未来产业主攻方向",
            "bom_nodes": ["具身智能"],
            "companies": [{"code": "688001", "name": "测试科技"}],
            "products": ["关节模组"],
            "materials": ["高精密减速器"],
            "commercialization_stage": "量产",
            "evidence": [{"summary": "研报提到量产验证", "confidence": 0.8, "source_type": "research_report"}],
        }

    monkeypatch.setattr("app.llm_supply_chain.extract_supply_chain_facts", fake_extract)

    r = _client().post("/api/v1/screener/supply-chain/research/ingest", json={"limit": 5, "persist": False})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["scanned"] == 1
    assert body["extracted"] == 1
    assert body["persisted"] is False
    assert body["reports"][0]["records"]["mappings"][0]["code"] == "688001"
