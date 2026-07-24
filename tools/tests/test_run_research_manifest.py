import argparse
import importlib.util
import json
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_research_pipeline", ROOT / "tools/run_research_pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pipeline
spec.loader.exec_module(pipeline)


def _args(**overrides):
    values = dict(official=False, strict_timeline=False, data_snapshot_id="", cutoff_time="",
                  model_version="v1", cost_bps=14)
    values.update(overrides)
    return argparse.Namespace(**values)


def test_research_manifest_records_dirty_non_strict_run(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "_git_state", lambda: {"commit": "abc123", "dirty": True})
    manifest = pipeline.build_run_manifest(
        args=_args(), model_key="bi_trend_launch", run_id="RUN-1", trade_date="2026-07-10",
        result={"status": "ok", "picks": [{"code": "000001"}]},
        parameters={"top_n": 20}, artifacts=[tmp_path / "result.json"],
    )
    assert manifest.official is False
    assert manifest.working_tree_dirty is True
    assert manifest.strict_timeline is False


def test_official_manifest_requires_clean_worktree(monkeypatch):
    monkeypatch.setattr(pipeline, "_git_state", lambda: {"commit": "abc123", "dirty": True})
    try:
        pipeline.build_run_manifest(
            args=_args(official=True, strict_timeline=True, data_snapshot_id="DS-1",
                       cutoff_time="2026-07-10T14:30:00"),
            model_key="x", run_id="RUN-2", trade_date="2026-07-10", result={"picks": []},
            parameters={}, artifacts=[],
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("dirty official run must exit 2")


def test_manifest_hashes_are_deterministic(monkeypatch):
    monkeypatch.setattr(pipeline, "_git_state", lambda: {"commit": "abc123", "dirty": False})
    kwargs = dict(args=_args(), model_key="x", run_id="RUN-3", trade_date="2026-07-10",
                  result={"picks": [{"code": "000002"}, {"code": "000001"}]},
                  parameters={"b": 2, "a": 1}, artifacts=[])
    one = pipeline.build_run_manifest(**kwargs)
    two = pipeline.build_run_manifest(**kwargs)
    assert one.parameters_hash == two.parameters_hash
    assert one.universe_hash == two.universe_hash


def test_git_state_is_conservative_when_git_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        pipeline.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("git")),
    )

    assert pipeline._git_state() == {"commit": "unavailable", "dirty": True}


def test_subprocess_timeout_is_recorded_without_aborting_pipeline(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["collector"], 120, output="partial", stderr="slow source")

    monkeypatch.setattr(pipeline.subprocess, "run", timeout)

    result = pipeline._run_subprocess(["collector"], timeout=120)

    assert result["returncode"] == 124
    assert result["status"] == "timeout"
    assert result["error"] == "subprocess timed out after 120s"
    assert "partial" in result["stdout_tail"]
    assert "slow source" in result["stderr_tail"]


def test_send_feishu_defaults_to_config():
    assert pipeline.resolve_send_feishu(
        _args(send_feishu=None), {"send_feishu_by_default": True}
    ) is True
    assert pipeline.resolve_send_feishu(
        _args(send_feishu=None), {"send_feishu_by_default": False}
    ) is False


def test_send_feishu_cli_overrides_config():
    assert pipeline.resolve_send_feishu(
        _args(send_feishu=True), {"send_feishu_by_default": False}
    ) is True
    assert pipeline.resolve_send_feishu(
        _args(send_feishu=False), {"send_feishu_by_default": True}
    ) is False


def test_parser_accepts_both_feishu_switches():
    parser = pipeline.build_parser()
    assert parser.parse_args(["--model", "short"]).send_feishu is None
    assert parser.parse_args(["--model", "short", "--send-feishu"]).send_feishu is True
    assert parser.parse_args(["--model", "short", "--no-send-feishu"]).send_feishu is False


def test_parser_accepts_explicit_afternoon_time_slot():
    args = pipeline.build_parser().parse_args(
        ["--model", "qishen_afternoon", "--time-slot", "14:00"]
    )
    assert args.time_slot == "14:00"


def test_chat_targets_use_all_configured_groups_by_default():
    targets = pipeline.resolve_chat_targets(
        _args(chat_id=[]),
        {
            "chat_targets": [
                {"key": "analysis", "name": "AI 投研分析", "chat_id": "oc_a"},
                {"key": "test", "name": "AI 投研测试", "chat_id": "oc_b"},
                {"key": "fitness", "name": "一起减肥吧", "chat_id": "oc_c"},
            ]
        },
    )
    assert [item["chat_id"] for item in targets] == ["oc_a", "oc_b", "oc_c"]


def test_parser_accepts_repeated_chat_ids():
    args = pipeline.build_parser().parse_args(
        ["--model", "short", "--chat-id", "oc_a", "--chat-id", "oc_b"]
    )
    assert args.chat_id == ["oc_a", "oc_b"]


def test_extract_message_id_from_nested_response():
    assert pipeline.extract_message_id(
        {"code": 0, "data": {"message_id": "om_test"}}
    ) == "om_test"
    assert pipeline.extract_message_id(
        {"data": {"message": {"message_id": "om_nested"}}}
    ) == "om_nested"
    assert pipeline.extract_message_id({"code": 0}) == ""


def test_delivery_error_redacts_header_json_and_query_tokens():
    error = RuntimeError('Authorization: Bearer abc.def {"access_token":"json-secret"} https://x.test?a=1&tenant_token=query-secret')
    sanitized = pipeline.sanitize_delivery_error(error)
    for secret in ("abc.def", "json-secret", "query-secret"):
        assert secret not in sanitized


def test_auction_source_plan_uses_eastmoney_when_tushare_rows_are_empty():
    plan = pipeline.plan_cb_auction_fallback(
        {"limit_list_d": 0, "stk_auction_o": 0, "eastmoney_limit_pool": 0}
    )

    assert plan == {
        "collect_eastmoney_limit_pool": True,
        "collect_eastmoney_snapshot": True,
        "primary_source": "tushare_unavailable",
    }


def test_auction_source_plan_keeps_usable_tushare_data():
    plan = pipeline.plan_cb_auction_fallback(
        {"limit_list_d": 20, "stk_auction_o": 3000, "eastmoney_limit_pool": 0}
    )

    assert plan == {
        "collect_eastmoney_limit_pool": False,
        "collect_eastmoney_snapshot": False,
        "primary_source": "tushare",
    }


def test_registered_afternoon_mode_forwards_requested_time_slot(monkeypatch):
    captured = {}
    fake_router = types.ModuleType("app.routers.screener")

    def run_afternoon(mode, top_n, trade_date, time_slot="14:30"):
        captured["time_slot"] = time_slot
        return {"mode": mode, "picks": []}

    fake_router._run_afternoon_mode = run_afternoon
    for name in (
        "_run_bi_full_market_mode",
        "_run_bi_shifu_trend_mode",
        "_run_bi_trend_mode",
        "_run_cb_mode",
        "_run_leader_mode",
        "_run_multifactor_mode",
        "_run_supply_chain_mode",
        "_run_supply_chain_trend_launch_mode",
    ):
        setattr(fake_router, name, lambda *_args, **_kwargs: {})
    monkeypatch.setitem(sys.modules, "app.routers.screener", fake_router)

    pipeline._run_registered_mode(
        "leader_afternoon",
        10,
        "2026-07-14",
        time_slot="14:00",
    )

    assert captured["time_slot"] == "14:00"


def test_registered_bi_shifu_trend_uses_named_strategy_engine(monkeypatch):
    captured = {}
    fake_router = types.ModuleType("app.routers.screener")
    names = (
        "_run_afternoon_mode",
        "_run_bi_full_market_mode",
        "_run_bi_trend_mode",
        "_run_cb_mode",
        "_run_leader_mode",
        "_run_multifactor_mode",
        "_run_supply_chain_mode",
        "_run_supply_chain_trend_launch_mode",
    )
    for name in names:
        setattr(fake_router, name, lambda *_args, **_kwargs: {})
    fake_router._run_bi_shifu_trend_mode = lambda mode, top_n, trade_date: captured.update(
        {"mode": mode, "top_n": top_n, "trade_date": trade_date}
    ) or {"picks": []}
    monkeypatch.setitem(sys.modules, "app.routers.screener", fake_router)

    pipeline._run_registered_mode("bi_shifu_trend", 20, "2026-07-14")

    assert captured == {
        "mode": "bi_shifu_trend",
        "top_n": 20,
        "trade_date": "2026-07-14",
    }


def test_confirm_message_delivery_falls_back_to_bot_chat_query(monkeypatch):
    calls = []

    class FakeProc:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "read_users" in cmd:
            return FakeProc(1, '{"ok":false}')
        return FakeProc(0, '{"items":[{"message_id":"om_test"}]}')

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    assert pipeline.confirm_message_delivery("oc_test", "om_test", attempts=1) is True
    assert calls[1][:5] == [
        "lark-cli", "im", "+chat-messages-list", "--as", "bot",
    ]


def test_confirm_message_delivery_uses_sender_read_status_before_chat_history(monkeypatch):
    calls = []

    class FakeProc:
        returncode = 0
        stdout = '{"ok":true,"data":{"items":[]}}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeProc()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    assert pipeline.confirm_message_delivery("oc_test", "om_test", attempts=1) is True
    assert calls == [[
        "lark-cli", "im", "messages", "read_users", "--as", "bot",
        "--message-id", "om_test", "--user-id-type", "open_id",
        "--page-size", "1", "--format", "json",
    ]]


def test_deliver_feishu_messages_continues_after_one_chat_fails(monkeypatch, tmp_path):
    sent = []

    def fake_one(**kwargs):
        sent.append(kwargs["chat_id"])
        if kwargs["chat_id"] == "oc_bad":
            raise RuntimeError("send failed")
        return {
            "push_status": "confirmed",
            "chat_id": kwargs["chat_id"],
            "message_id": "om_" + kwargs["chat_id"],
        }

    monkeypatch.setattr(pipeline, "deliver_feishu_message", fake_one)
    state = pipeline.deliver_feishu_messages(
        run_dir=tmp_path,
        result={"pipeline": {}},
        targets=[
            {"key": "a", "name": "A", "chat_id": "oc_ok"},
            {"key": "b", "name": "B", "chat_id": "oc_bad"},
            {"key": "c", "name": "C", "chat_id": "oc_ok2"},
        ],
        message="test",
        sender=lambda *_args: {},
        attempts=1,
    )

    assert sent == ["oc_ok", "oc_bad", "oc_ok2"]
    assert state["status"] == "partial_delivery"
    assert len(state["deliveries"]) == 3


def test_multi_delivery_does_not_resend_when_message_id_was_returned(monkeypatch, tmp_path):
    sent = []
    result = {"pipeline": {}}

    def unconfirmed(**kwargs):
        sent.append(kwargs["chat_id"])
        result["pipeline"]["feishu_delivery"] = {
            "push_status": "unconfirmed",
            "chat_id": kwargs["chat_id"],
            "message_id": "om_sent",
            "error": "message_not_found_in_chat",
        }
        raise RuntimeError("unconfirmed")

    monkeypatch.setattr(pipeline, "deliver_feishu_message", unconfirmed)

    state = pipeline.deliver_feishu_messages(
        run_dir=tmp_path,
        result=result,
        targets=[{"key": "a", "name": "A", "chat_id": "oc_a"}],
        message="test",
        sender=lambda *_args: {},
        attempts=3,
    )

    assert sent == ["oc_a"]
    assert state["deliveries"][0]["message_id"] == "om_sent"
    assert state["deliveries"][0]["push_status"] == "unconfirmed"


def test_confirm_message_delivery_falls_back_to_user_when_bot_cannot_read(monkeypatch):
    identities = []

    class FakeProc:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(cmd, **kwargs):
        identity = cmd[cmd.index("--as") + 1]
        identities.append(identity)
        if identity == "bot":
            return FakeProc(1, '{"ok":false,"error":{"code":230027}}')
        return FakeProc(0, '{"data":{"messages":[{"message_id":"om_test"}]}}')

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    assert pipeline.confirm_message_delivery("oc_test", "om_test", attempts=1) is True
    assert identities == ["bot", "bot", "user"]


def test_write_delivery_state_updates_both_run_files(tmp_path):
    result = {"pipeline": {"model_key": "short"}}
    pipeline._write_json(tmp_path / "pipeline.json", {"status": "ok"})
    state = {
        "push_status": "confirmed",
        "chat_id": "oc_test",
        "message_id": "om_test",
    }

    pipeline.write_delivery_state(tmp_path, result, state)

    stored_result = json.loads((tmp_path / "result.json").read_text())
    stored_pipeline = json.loads((tmp_path / "pipeline.json").read_text())
    assert stored_result["pipeline"]["feishu_delivery"] == state
    assert stored_pipeline["feishu_delivery"] == state


def test_lark_doc_failure_is_recorded_without_aborting_delivery(tmp_path):
    result = {"pipeline": {}}

    doc = pipeline.try_sync_lark_doc(
        lambda _path, _result: (_ for _ in ()).throw(RuntimeError("permission denied")),
        tmp_path / "report.md",
        result,
        tmp_path,
    )

    assert doc == {}
    assert result["pipeline"]["lark_doc"]["status"] == "failed"
    assert "permission denied" in result["pipeline"]["lark_doc"]["error"]
    assert json.loads((tmp_path / "result.json").read_text())["pipeline"]["lark_doc"]["status"] == "failed"


def test_deliver_feishu_message_records_confirmed_state(monkeypatch, tmp_path):
    result = {"pipeline": {"model_key": "short"}}
    pipeline._write_json(tmp_path / "pipeline.json", {"status": "ok"})
    monkeypatch.setattr(
        pipeline,
        "confirm_message_delivery",
        lambda chat_id, message_id: True,
    )

    state = pipeline.deliver_feishu_message(
        run_dir=tmp_path,
        result=result,
        chat_id="oc_test",
        message="功能测试",
        sender=lambda chat_id, text: {"data": {"message_id": "om_test"}},
    )

    assert state["push_status"] == "confirmed"
    assert state["message_id"] == "om_test"


def test_deliver_feishu_message_records_unconfirmed_and_raises(monkeypatch, tmp_path):
    result = {"pipeline": {"model_key": "short"}}
    pipeline._write_json(tmp_path / "pipeline.json", {"status": "ok"})
    monkeypatch.setattr(
        pipeline,
        "confirm_message_delivery",
        lambda chat_id, message_id: False,
    )

    with pytest.raises(RuntimeError, match="未确认送达"):
        pipeline.deliver_feishu_message(
            run_dir=tmp_path,
            result=result,
            chat_id="oc_test",
            message="功能测试",
            sender=lambda chat_id, text: {"data": {"message_id": "om_test"}},
        )

    state = json.loads((tmp_path / "pipeline.json").read_text())["feishu_delivery"]
    assert state["push_status"] == "unconfirmed"


def test_deliver_feishu_message_records_missing_message_id(monkeypatch, tmp_path):
    result = {"pipeline": {"model_key": "short"}}
    pipeline._write_json(tmp_path / "pipeline.json", {"status": "ok"})

    with pytest.raises(RuntimeError, match="消息 ID"):
        pipeline.deliver_feishu_message(
            run_dir=tmp_path,
            result=result,
            chat_id="oc_test",
            message="功能测试",
            sender=lambda chat_id, text: {"code": 0},
        )

    state = json.loads((tmp_path / "pipeline.json").read_text())["feishu_delivery"]
    assert state["push_status"] == "unconfirmed"
    assert state["message_id"] == ""


def test_deliver_feishu_message_records_send_failure(tmp_path):
    result = {"pipeline": {"model_key": "short"}}
    pipeline._write_json(tmp_path / "pipeline.json", {"status": "ok"})

    def fail_sender(chat_id, text):
        raise RuntimeError("send failed")

    with pytest.raises(RuntimeError, match="send failed"):
        pipeline.deliver_feishu_message(
            run_dir=tmp_path,
            result=result,
            chat_id="oc_test",
            message="功能测试",
            sender=fail_sender,
        )

    state = json.loads((tmp_path / "pipeline.json").read_text())["feishu_delivery"]
    assert state["push_status"] == "failed"
    assert state["message_id"] == ""
