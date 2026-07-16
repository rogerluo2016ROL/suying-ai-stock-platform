from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

from embodied_refresh.evidence import (
    can_auto_verify,
    classify_source,
    commercialization_stage,
    normalize_evidence,
)
from embodied_refresh.models import (
    CommercializationStage,
    EvidenceGrade,
    RawEvidence,
)


TODAY = date(2026, 7, 17)


def evidence(
    source_type: str,
    content: str,
    *,
    source_id: str = "source-1",
    node_id: str | None = None,
):
    return normalize_evidence(
        RawEvidence(
            source_id=source_id,
            source_type=source_type,
            content=content,
            event_date=TODAY,
            node_id=node_id,
        )
    )


def test_report_cannot_auto_verify_mapping():
    event = evidence("research", "公司布局人形机器人")
    assert classify_source(event.source_type) == EvidenceGrade.C
    assert can_auto_verify([event]) is False


def test_clear_annual_report_can_auto_verify_mapping():
    event = evidence(
        "annual_report",
        "公司已批量交付机器人六维力传感器",
        node_id="EI-L5-FORCE",
    )
    assert classify_source(event.source_type) == EvidenceGrade.S
    assert can_auto_verify([event]) is True


def test_two_independent_official_sources_can_auto_verify():
    events = [
        evidence("official_web", "公司批量供应六维力传感器", source_id="src-a", node_id="EI-L5-FORCE"),
        evidence("ir_record", "公司已交付六维力传感器", source_id="src-b", node_id="EI-L5-FORCE"),
    ]
    assert can_auto_verify(events) is True


def test_same_source_content_has_same_fingerprint_but_changed_content_has_new_version():
    original = evidence("official_web", "公司已小批量交付", source_id="official-1", node_id="node-1")
    duplicate = evidence("official_web", "  公司已小批量交付  ", source_id="official-1", node_id="node-1")
    changed = evidence("official_web", "公司已批量交付", source_id="official-1", node_id="node-1")
    assert duplicate.fingerprint == original.fingerprint
    assert changed.fingerprint != original.fingerprint


def test_commercialization_stage_order_exposes_advance_and_downgrade_candidate():
    validation = commercialization_stage("产品已通过客户验证")
    production = commercialization_stage("产品已量产")
    assert validation == CommercializationStage.CUSTOMER_VALIDATION
    assert production == CommercializationStage.MASS_PRODUCTION
    assert production > validation
    assert validation < production


def test_missing_date_or_node_blocks_automatic_upgrade():
    raw = RawEvidence(
        source_id="filing-1",
        source_type="annual_report",
        content="公司已批量交付六维力传感器",
        event_date=None,
        node_id="node-1",
    )
    assert can_auto_verify([normalize_evidence(raw)]) is False


def test_vague_possible_use_does_not_become_explicit_supply_relation():
    event = evidence(
        "annual_report",
        "公司产品可用于人形机器人供应链",
        node_id="node-1",
    )
    assert event.has_explicit_relation is False
    assert can_auto_verify([event]) is False
