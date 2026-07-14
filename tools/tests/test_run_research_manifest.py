import argparse
import importlib.util
import json
import sys
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


def test_extract_message_id_from_nested_response():
    assert pipeline.extract_message_id(
        {"code": 0, "data": {"message_id": "om_test"}}
    ) == "om_test"
    assert pipeline.extract_message_id(
        {"data": {"message": {"message_id": "om_nested"}}}
    ) == "om_nested"
    assert pipeline.extract_message_id({"code": 0}) == ""


def test_confirm_message_delivery_uses_bot_chat_query(monkeypatch):
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = '{"items":[{"message_id":"om_test"}]}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    assert pipeline.confirm_message_delivery("oc_test", "om_test", attempts=1) is True
    assert seen["cmd"][:5] == [
        "lark-cli", "im", "+chat-messages-list", "--as", "bot",
    ]


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
    assert identities == ["bot", "user"]


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
