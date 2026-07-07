from pathlib import Path


JAVA_FILE = Path(__file__).resolve().parents[2] / (
    "chatbi-workspace/backend-java/cockpit-screen-system/src/main/java/"
    "com/ds/cockpit/screen/system/service/chatbi/impl/ChatBIOrchestratorServiceImpl.java"
)
ROUTER_FILE = Path(__file__).resolve().parents[2] / (
    "chatbi-workspace/backend-java/cockpit-screen-system/src/main/java/"
    "com/ds/cockpit/screen/system/service/chatbi/impl/RuleIntentRouter.java"
)
TOOL_GATEWAY_FILE = Path(__file__).resolve().parents[2] / (
    "chatbi-workspace/backend-java/cockpit-screen-system/src/main/java/"
    "com/ds/cockpit/screen/system/service/chatbi/impl/HttpToolGatewayClient.java"
)


def test_stock_model_run_table_shows_reassessment_fields():
    source = JAVA_FILE.read_text(encoding="utf-8")

    assert "可靠预期差" in source
    assert "证据质量" in source
    assert "标签匹配" in source
    assert "复评状态" in source
    assert "reliability_adjusted_gap_score" in source
    assert "evidence_quality_score" in source
    assert "label_fit_score" in source
    assert "reassessment_status" in source


def test_expectation_gap_question_routes_to_stock_model_run():
    source = ROUTER_FILE.read_text(encoding="utf-8")

    assert "产业链预期差" in source
    assert "预期差模型" in source
    assert 'new IntentResult("stock_model_run"' in source


def test_expectation_gap_question_runs_supply_chain_mode():
    source = TOOL_GATEWAY_FILE.read_text(encoding="utf-8")

    assert "预期差" in source
    assert 'modes.add("supply_chain")' in source
