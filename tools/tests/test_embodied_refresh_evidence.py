from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

from embodied_refresh.evidence import (
    FINGERPRINT_VERSION,
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
    publisher_id: str | None = None,
    event_date: date | None = TODAY,
    valid_until: date | None = None,
    is_valid: bool = True,
):
    return normalize_evidence(
        RawEvidence(
            source_id=source_id,
            source_type=source_type,
            content=content,
            event_date=event_date,
            node_id=node_id,
            publisher_id=publisher_id,
            valid_until=valid_until,
            is_valid=is_valid,
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
        evidence("official_web", "公司批量供应六维力传感器", source_id="src-a", publisher_id="issuer-a", node_id="EI-L5-FORCE"),
        evidence("ir_record", "公司已交付六维力传感器", source_id="src-b", publisher_id="issuer-b", node_id="EI-L5-FORCE"),
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


def test_two_a_sources_for_different_nodes_cannot_combine_votes():
    events = [
        evidence("official_web", "公司已供应传感器", source_id="a", node_id="node-a"),
        evidence("ir_record", "公司已交付减速器", source_id="b", node_id="node-b"),
    ]
    assert can_auto_verify(events, as_of=TODAY) is False


def test_same_publisher_republished_as_two_source_ids_counts_once():
    events = [
        evidence("official_web", "公司已供应传感器", source_id="crawl-a", publisher_id="issuer-1", node_id="node-a"),
        evidence("ir_record", "公司已交付传感器", source_id="crawl-b", publisher_id="issuer-1", node_id="node-a"),
    ]
    assert events[0].canonical_source_id == "issuer-1"
    assert can_auto_verify(events, as_of=TODAY) is False


def test_negative_or_withdrawn_sentence_never_supports_relation_or_stage():
    for text in (
        "公司尚未量产机器人传感器",
        "公司没有形成相关收入",
        "公司不供应人形机器人客户",
        "相关订单已取消并终止交付",
    ):
        event = evidence("annual_report", text, node_id="node-a")
        assert event.has_explicit_relation is False
        assert event.stage == CommercializationStage.CONCEPT_RELATED
        assert can_auto_verify([event], as_of=TODAY) is False


def test_local_negation_near_relation_or_stage_keyword_is_respected():
    for text in (
        "公司未量产机器人传感器",
        "公司未交付机器人传感器",
        "公司无订单",
        "公司尚无订单",
        "公司并未供应人形机器人客户",
        "公司并未向客户供应传感器",
        "公司不存在相关订单",
        "公司不存在任何相关订单",
    ):
        event = evidence("annual_report", text, node_id="node-a")
        assert event.has_explicit_relation is False, text
        assert event.stage == CommercializationStage.CONCEPT_RELATED, text

    positive = evidence("annual_report", "公司不但已量产，而且已批量交付", node_id="node-a")
    assert positive.has_explicit_relation is True
    assert positive.stage == CommercializationStage.MASS_PRODUCTION


def test_vague_sentence_is_not_unlocked_by_unrelated_income_sentence():
    event = evidence(
        "annual_report",
        "公司布局人形机器人传感器。公司主营业务去年实现收入。",
        node_id="node-a",
    )
    assert event.has_explicit_relation is False
    assert event.stage == CommercializationStage.CONCEPT_RELATED


def test_future_expired_and_explicitly_invalid_evidence_cannot_upgrade():
    future = evidence("annual_report", "公司已批量交付", node_id="node-a", event_date=date(2026, 7, 18))
    expired = evidence("annual_report", "公司已批量交付", node_id="node-a", valid_until=date(2026, 7, 16))
    invalid = evidence("annual_report", "公司已批量交付", node_id="node-a", is_valid=False)
    assert can_auto_verify([future], as_of=TODAY) is False
    assert can_auto_verify([expired], as_of=TODAY) is False
    assert can_auto_verify([invalid], as_of=TODAY) is False


def test_explicit_valid_false_alias_cannot_upgrade():
    raw = RawEvidence(
        source_id="filing-1",
        source_type="annual_report",
        content="公司已批量交付六维力传感器",
        event_date=TODAY,
        node_id="node-a",
        valid=False,
    )
    assert normalize_evidence(raw).valid is False
    assert can_auto_verify([normalize_evidence(raw)], as_of=TODAY) is False


def test_fingerprint_declares_hash_contract_version():
    event = evidence("official_web", "公司已小批量交付", node_id="node-a")
    assert event.fingerprint_version == FINGERPRINT_VERSION
    assert event.fingerprint.startswith(f"{FINGERPRINT_VERSION}:")


def test_weak_commercial_phrases_do_not_overstate_stage():
    assert commercialization_stage("公司签订了框架协议") < CommercializationStage.CONFIRMED_ORDER
    assert commercialization_stage("行业产能释放") < CommercializationStage.MASS_PRODUCTION
    assert commercialization_stage("公司收入占比提升") < CommercializationStage.SIGNIFICANT_REVENUE_SHARE


def test_revenue_share_requires_ratio_and_explicit_significant_improvement():
    assert commercialization_stage("该业务收入占比达到12%") == CommercializationStage.REVENUE_RECOGNITION
    assert commercialization_stage("该业务收入占比显著提升至12%") == CommercializationStage.SIGNIFICANT_REVENUE_SHARE
    assert commercialization_stage("该业务收入占比大幅提升") < CommercializationStage.SIGNIFICANT_REVENUE_SHARE


def test_two_a_records_without_trusted_publisher_identity_do_not_combine():
    events = [
        evidence("official_web", "公司已供应传感器", source_id="crawl-a", node_id="node-a"),
        evidence("ir_record", "公司已交付传感器", source_id="crawl-b", node_id="node-a"),
    ]
    assert events[0].canonical_source_id is None
    assert can_auto_verify(events, as_of=TODAY) is False


def test_optional_string_fields_are_stripped_and_empty_values_become_none():
    normalized = normalize_evidence(
        RawEvidence(
            source_id=" crawl ",
            source_type=" official_web ",
            content="公司已供应传感器",
            event_date=TODAY,
            node_id="  ",
            source_url="  ",
            publisher_id="  ",
            canonical_source_id="  ",
        )
    )
    assert normalized.node_id is None
    assert normalized.source_url is None
    assert normalized.publisher_id is None
    assert normalized.canonical_source_id is None
