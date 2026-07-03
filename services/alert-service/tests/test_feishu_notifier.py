"""feishu_notifier 单测 — mock lark client，不真实调飞书。"""
import os
import pytest
from app import feishu_notifier


@pytest.fixture(autouse=True)
def reset_client():
    """每用例重置单例 client + env。"""
    feishu_notifier._client = None
    old_env = dict(os.environ)
    for k in ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_CHAT_ID", "FEISHU_ENABLED"]:
        os.environ.pop(k, None)
    yield
    os.environ.clear()
    os.environ.update(old_env)


def test_is_enabled_no_env():
    assert feishu_notifier.is_enabled() is False


def test_is_enabled_with_env():
    os.environ["FEISHU_APP_ID"] = "cli_test"
    os.environ["FEISHU_APP_SECRET"] = "secret_test"
    os.environ["FEISHU_CHAT_ID"] = "oc_test"
    assert feishu_notifier.is_enabled() is True


def test_is_enabled_explicit_false():
    os.environ["FEISHU_APP_ID"] = "cli_test"
    os.environ["FEISHU_APP_SECRET"] = "secret_test"
    os.environ["FEISHU_CHAT_ID"] = "oc_test"
    os.environ["FEISHU_ENABLED"] = "false"
    assert feishu_notifier.is_enabled() is False


def test_notify_disabled_returns_false():
    ok, msg = feishu_notifier.notify(level="info", title="t", message="m")
    assert ok is False
    assert "disabled" in msg


class _MockResp:
    def __init__(self, success=True, code=0, msg="ok"):
        self._ok = success
        self.code = code
        self.msg = msg

    def success(self):
        return self._ok


class _MockMessage:
    def __init__(self, resp):
        self._resp = resp

    def create(self, req):
        return self._resp


class _MockIm:
    def __init__(self, resp):
        self.v1 = type("V1", (), {"message": _MockMessage(resp)})()


class _MockClient:
    def __init__(self, resp):
        self.im = _MockIm(resp)


def _enable_env():
    os.environ["FEISHU_APP_ID"] = "cli_test"
    os.environ["FEISHU_APP_SECRET"] = "secret_test"
    os.environ["FEISHU_CHAT_ID"] = "oc_test"


def test_notify_success(monkeypatch):
    _enable_env()
    monkeypatch.setattr(feishu_notifier, "get_client", lambda: _MockClient(_MockResp(success=True)))
    ok, msg = feishu_notifier.notify(
        level="urgent", title="买入信号", message="600519 触发",
        code="600519", score=85.5, extra={"模式": "leader_scalp"},
    )
    assert ok is True
    assert msg == "ok"


def test_notify_failure(monkeypatch):
    _enable_env()
    monkeypatch.setattr(feishu_notifier, "get_client",
                        lambda: _MockClient(_MockResp(success=False, code=99991663, msg="invalid chat_id")))
    ok, msg = feishu_notifier.notify(level="info", title="t", message="m")
    assert ok is False
    assert "99991663" in msg


def test_notify_exception_safe(monkeypatch):
    _enable_env()

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(feishu_notifier, "send_alert_card", boom)
    ok, msg = feishu_notifier.notify(level="info", title="t", message="m")
    assert ok is False
    assert "exception" in msg


def test_send_alert_card_builds_interactive_payload(monkeypatch):
    """验证 send_alert_card 构造 interactive 卡片（含 header template + fields）。"""
    _enable_env()
    captured = {}

    class _CaptureMsg:
        def create(self, req):
            captured["receive_id_type"] = req.receive_id_type
            captured["msg_type"] = req.request_body.msg_type
            captured["content"] = req.request_body.content
            captured["receive_id"] = req.request_body.receive_id
            return _MockResp(success=True)

    class _CaptureIm:
        v1 = type("V1", (), {"message": _CaptureMsg()})

    class _CaptureClient:
        im = _CaptureIm()

    monkeypatch.setattr(feishu_notifier, "get_client", lambda: _CaptureClient())
    ok, _ = feishu_notifier.send_alert_card(
        level="urgent", title="买入", message="600519", code="600519", score=90.0,
    )
    assert ok is True
    import json
    assert captured["receive_id_type"] == "chat_id"
    assert captured["receive_id"] == "oc_test"
    assert captured["msg_type"] == "interactive"
    card = json.loads(captured["content"])
    assert card["header"]["template"] == "red"  # urgent → red
    assert card["config"]["wide_screen_mode"] is True
