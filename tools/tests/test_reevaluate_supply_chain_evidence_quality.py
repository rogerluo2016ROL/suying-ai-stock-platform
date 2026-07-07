import importlib.util
import sys
from datetime import date
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "reevaluate_supply_chain_evidence_quality.py"
_SPEC = importlib.util.spec_from_file_location("reevaluate_supply_chain_evidence_quality", _SCRIPT_PATH)
module = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = module
_SPEC.loader.exec_module(module)


def event(**kwargs):
    defaults = {
        "event_id": "EV-1",
        "event_date": date(2026, 1, 1),
        "source_type": "announcement",
        "source_id": "cninfo",
        "title": "中标公告",
        "excerpt": "公司中标 AI 智慧城市平台项目",
        "original_url": "http://static.cninfo.com.cn/finalpage/2026-01-01/1234567890.PDF",
        "evidence_type": "commercial_stage",
        "confidence": 0.8,
        "review_status": "approved",
        "impact_dimensions": {},
    }
    defaults.update(kwargs)
    return module.EvidenceEvent(**defaults)


def test_duplicate_key_merges_same_pdf_and_announcement_id():
    first = event(original_url="http://static.cninfo.com.cn/finalpage/2026-01-01/1234567890.PDF")
    second = event(
        event_id="EV-2",
        original_url="http://www.cninfo.com.cn/new/disclosure/detail?announcementId=1234567890",
    )

    unique = module.group_unique_events([first, second])

    assert len(unique) == 1


def test_evidence_quality_penalizes_pending_only_story():
    pending = [
        event(
            event_id=f"P-{idx}",
            source_type="irm_qa",
            evidence_type="customer_validation",
            review_status="pending_review",
            original_url="",
        )
        for idx in range(5)
    ]

    score, detail, issues = module.assess_evidence_quality(pending)

    assert score < 35
    assert detail["approved_count"] == 0
    assert "没有已审核证据" in issues


def test_strong_approved_evidence_scores_above_weak_watch():
    score, detail, issues = module.assess_evidence_quality([
        event(evidence_type="commercial_stage", review_status="approved"),
        event(
            event_id="EV-2",
            source_type="government_project",
            evidence_type="business_presence",
            original_url="http://static.cninfo.com.cn/finalpage/2025-12-31/2222222222.PDF",
        ),
    ])

    assert score >= 55
    assert detail["strong_evidence_count"] == 1
    assert "缺少已审核强证据：订单/中标/量产/收入毛利/专利标准等" not in issues


def test_label_fit_flags_ai_compute_software_without_compute_evidence():
    label_score, issues, detail = module.assess_label_fit(
        chain_id="ai_compute",
        tag_name="公司业务标签：基础软件/算力调度软件业务",
        l1_l8_path=[],
        unique_events=[
            event(excerpt="公司中标低空飞行管理服务平台，应用于无人机和智慧城市应急救援")
        ],
        revenue_ratio=None,
        gross_profit_ratio=None,
    )

    assert label_score < 55
    assert detail["application_hits"] > 0
    assert any("基础软件/算力调度" in issue for issue in issues)


def test_industry_ai_application_label_keeps_low_altitude_evidence_in_watch_area():
    label_score, issues, detail = module.assess_label_fit(
        chain_id="ai_compute",
        tag_name="公司业务标签：行业AI应用业务",
        l1_l8_path=[],
        unique_events=[
            event(excerpt="神思智飞赋予无人机和机器狗感知、认知、决策能力，服务低空应急救援和智慧城市")
        ],
        revenue_ratio=None,
        gross_profit_ratio=None,
    )

    assert label_score >= 50
    assert detail["application_hits"] > 0
    assert any("不是 AI 算力基础设施" in issue for issue in issues)


def test_ai_chip_label_requires_chip_specific_evidence():
    label_score, issues, detail = module.assess_label_fit(
        chain_id="ai_compute",
        tag_name="公司业务标签：AI芯片/芯片业务",
        l1_l8_path=[],
        unique_events=[
            event(excerpt="公司智慧医疗和城市大脑项目应用人工智能算法，提升政务服务效率")
        ],
        revenue_ratio=None,
        gross_profit_ratio=None,
    )

    assert label_score < 45
    assert detail["required_hits_AI芯片/芯片"] == 0
    assert any("AI芯片/芯片业务" in issue for issue in issues)
