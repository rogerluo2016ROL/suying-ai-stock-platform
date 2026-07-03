import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import lark_bot
from app.routers.lark import router


def _event(text="/毕师傅硬核科技", chat_id="oc_ok", sender="ou_ok", message_type="text"):
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": "verify-token"},
        "event": {
            "sender": {"sender_id": {"open_id": sender}},
            "message": {
                "chat_id": chat_id,
                "message_type": message_type,
                "content": '{"text": "%s"}' % text,
            },
        },
    }


def test_parse_supported_commands():
    cmd = lark_bot.parse_command("/秋神午后 2026-07-03 top=10")
    assert cmd is not None
    assert cmd.mode == "leader_afternoon"
    assert cmd.trade_date == "2026-07-03"
    assert cmd.top_n == 10

    cmd = lark_bot.parse_command("/毕师傅硬核科技")
    assert cmd is not None
    assert cmd.mode == "bi_trend_launch"

    cmd = lark_bot.parse_command("@罗健的飞书 CLI /毕师傅硬核科技 top=5")
    assert cmd is not None
    assert cmd.mode == "bi_trend_launch"
    assert cmd.top_n == 5

    cmd = lark_bot.parse_command("/秋神午后选股")
    assert cmd is not None
    assert cmd.mode == "leader_afternoon"

    expected_modes = {
        "/秋神盘中": "leader_intraday",
        "/秋神尾盘": "leader_closing",
        "/大葱产业链": "supply_chain",
        "/竞价选债": "cb_auction_t0_v2_1",
        "/竞价选债V1": "cb_auction_t0",
        "/竞价选债V2": "cb_auction_t0_v2",
        "/竞价选债V21": "cb_auction_t0_v2_1",
    }
    for text, mode in expected_modes.items():
        cmd = lark_bot.parse_command(f"{text} date=2026-07-03 top=5")
        assert cmd is not None
        assert cmd.mode == mode
        assert cmd.trade_date == "2026-07-03"
        assert cmd.top_n == 5

    assert lark_bot.parse_command("秋神午后") is None
    assert lark_bot.parse_command("/未知") is None


def test_handle_message_respects_allowlists(monkeypatch):
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_allowed")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_allowed")

    result = lark_bot.handle_lark_message(_event(chat_id="oc_bad", sender="ou_allowed"))
    assert result == {"ignored": True, "reason": "not_allowed"}


def test_empty_user_allowlist_allows_group_members(monkeypatch):
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_allowed")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "")

    assert lark_bot.is_allowed_event("oc_allowed", "ou_other_member") is True


def test_handle_message_runs_and_sends(monkeypatch):
    sent = []
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")
    monkeypatch.setattr(lark_bot, "send_text_to_chat", lambda chat_id, text: sent.append((chat_id, text)))
    monkeypatch.setattr(lark_bot, "generate_poster_image", lambda result: None)
    monkeypatch.setattr(lark_bot, "refresh_before_run", lambda command: {"status": "ok", "elapsed": 0.1})
    monkeypatch.setattr(lark_bot, "write_markdown_report", lambda result, markdown: "/tmp/report.md")
    monkeypatch.setattr(
        lark_bot,
        "sync_markdown_to_lark_doc",
        lambda path, result: {"title": "测试报告", "url": "https://example.feishu.cn/docx/test"},
    )
    monkeypatch.setattr(
        lark_bot,
        "run_command",
        lambda command: {
            "mode": command.mode,
            "trade_date": "2026-07-03",
            "total_picks": 1,
            "picks": [
                {
                    "code": "300458",
                    "name": "全志科技",
                    "grade": "S",
                    "total_score": 74,
                    "close": 37.65,
                    "entry_reason": "启动信号: fresh_obv_breakout；硬科技: 半导体(core)",
                }
            ],
            "execution_plans": [
                {
                    "code": "300458",
                    "entry_price": 38.03,
                    "take_profit_full": 43.30,
                    "stop_loss_normal": 34.64,
                    "position": "6%",
                }
            ],
        },
    )

    result = lark_bot.handle_lark_message(_event())

    assert result["ignored"] is False
    assert result["mode"] == "bi_trend_launch"
    assert len(sent) == 2
    assert sent[0][0] == "oc_ok"
    assert "先更新必要数据" in sent[0][1]
    assert "全志科技" in sent[1][1]
    assert "选股日期: 2026-07-03" in sent[1][1]
    assert "文档: https://example.feishu.cn/docx/test" in sent[1][1]
    assert "本地原稿" not in sent[1][1]
    assert "/tmp/report.md" not in sent[1][1]
    assert result["doc_url"] == "https://example.feishu.cn/docx/test"


def test_handle_message_sends_poster_image(monkeypatch):
    sent = []
    images = []
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")
    monkeypatch.setattr(lark_bot, "send_text_to_chat", lambda chat_id, text: sent.append((chat_id, text)))
    monkeypatch.setattr(lark_bot, "send_image_to_chat", lambda chat_id, path: images.append((chat_id, path)))
    monkeypatch.setattr(lark_bot, "generate_poster_image", lambda result: "/tmp/poster.png")
    monkeypatch.setattr(lark_bot, "refresh_before_run", lambda command: {"status": "ok", "elapsed": 0.1})
    monkeypatch.setattr(lark_bot, "write_markdown_report", lambda result, markdown: "/tmp/report.md")
    monkeypatch.setattr(
        lark_bot,
        "sync_markdown_to_lark_doc",
        lambda path, result: {"title": "测试报告", "url": "https://example.feishu.cn/docx/test"},
    )
    monkeypatch.setattr(
        lark_bot,
        "run_command",
        lambda command: {
            "mode": command.mode,
            "trade_date": "2026-07-03",
            "total_picks": 1,
            "picks": [{"code": "603730", "name": "岱美股份", "industry": "汽车配件", "total_score": 99, "gain_pct": 8.63}],
        },
    )

    result = lark_bot.handle_lark_message(_event())

    assert result["ignored"] is False
    assert len(sent) == 2
    assert images == [("oc_ok", "/tmp/poster.png")]


def test_handle_flat_event_from_lark_cli_consume(monkeypatch):
    sent = []
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")
    monkeypatch.setattr(lark_bot, "send_text_to_chat", lambda chat_id, text: sent.append((chat_id, text)))
    monkeypatch.setattr(lark_bot, "generate_poster_image", lambda result: None)
    monkeypatch.setattr(lark_bot, "refresh_before_run", lambda command: {"status": "ok", "elapsed": 0.1})
    monkeypatch.setattr(lark_bot, "write_markdown_report", lambda result, markdown: "/tmp/report.md")
    monkeypatch.setattr(
        lark_bot,
        "sync_markdown_to_lark_doc",
        lambda path, result: {"title": "测试报告", "url": "https://example.feishu.cn/docx/test"},
    )
    monkeypatch.setattr(
        lark_bot,
        "run_command",
        lambda command: {"mode": command.mode, "trade_date": "2026-07-03", "total_picks": 0, "picks": []},
    )

    result = lark_bot.handle_lark_message(
        {
            "type": "im.message.receive_v1",
            "chat_id": "oc_ok",
            "sender_id": "ou_ok",
            "message_type": "text",
            "content": "/秋神午后",
        }
    )

    assert result["ignored"] is False
    assert result["mode"] == "leader_afternoon"
    assert len(sent) == 2


def test_handle_post_command_from_group_mention(monkeypatch):
    sent = []
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")
    monkeypatch.setattr(lark_bot, "send_text_to_chat", lambda chat_id, text: sent.append((chat_id, text)))
    monkeypatch.setattr(lark_bot, "generate_poster_image", lambda result: None)
    monkeypatch.setattr(lark_bot, "refresh_before_run", lambda command: {"status": "ok", "elapsed": 0.1})
    monkeypatch.setattr(lark_bot, "write_markdown_report", lambda result, markdown: "/tmp/report.md")
    monkeypatch.setattr(
        lark_bot,
        "sync_markdown_to_lark_doc",
        lambda path, result: {"title": "测试报告", "url": "https://example.feishu.cn/docx/test"},
    )
    monkeypatch.setattr(
        lark_bot,
        "run_command",
        lambda command: {"mode": command.mode, "trade_date": "2026-07-03", "total_picks": 0, "picks": []},
    )

    result = lark_bot.handle_lark_message(_event("@罗健的飞书 CLI /秋神午后选股 top=5", message_type="post"))

    assert result["ignored"] is False
    assert result["mode"] == "leader_afternoon"
    assert len(sent) == 2


def test_leader_factor_reason_is_generated():
    report = lark_bot.build_markdown_report(
        {
            "mode": "leader_afternoon",
            "trade_date": "2026-07-03",
            "picks": [
                {
                    "code": "300000",
                    "name": "测试股份",
                    "close": 12.34,
                    "gain_pct": 6.78,
                    "industry": "具身智能",
                    "total_score": 82.5,
                    "resonance_score": 91,
                    "sector_momentum_score": 88,
                    "capital_score": 73,
                    "peer_count": 12,
                }
            ],
        }
    )

    assert "主要因子:" in report
    assert "板块共振91.0" in report
    assert "具身智能" in report
    assert "## 一、数据更新时间和日期" in report
    assert "## 二、市场状态诊断" in report
    assert "## 三、选股清单" in report
    assert "## 四、板块共振" in report
    assert "## 五、风险提示" in report


def test_cb_auction_command_runs_and_sends_doc(monkeypatch):
    sent = []
    called = {}
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")
    monkeypatch.setattr(lark_bot, "send_text_to_chat", lambda chat_id, text: sent.append((chat_id, text)))
    monkeypatch.setattr(lark_bot, "generate_poster_image", lambda result: None)
    monkeypatch.setattr(lark_bot, "refresh_before_run", lambda command: {"status": "ok", "elapsed": 0.1})
    monkeypatch.setattr(lark_bot, "write_markdown_report", lambda result, markdown: "/tmp/cb-report.md")
    monkeypatch.setattr(
        lark_bot,
        "sync_markdown_to_lark_doc",
        lambda path, result: {"title": "竞价选债报告", "url": "https://example.feishu.cn/docx/cb"},
    )

    def fake_run(command):
        called["mode"] = command.mode
        return {
            "mode": command.mode,
            "trade_date": "2026-07-03",
            "total_picks": 1,
            "picks": [
                {
                    "code": "123001.SZ",
                    "name": "竞价转债",
                    "stk_code": "300001",
                    "stk_name": "触发科技",
                    "theme_score": 117.0,
                    "quality_tier": "A",
                    "matched_concepts": ["机器人", "具身智能"],
                    "relation_reason": "正股为触发股，命中机器人",
                }
            ],
        }

    monkeypatch.setattr(lark_bot, "run_command", fake_run)

    result = lark_bot.handle_lark_message(_event("/竞价选债 top=5"))

    assert result["ignored"] is False
    assert called["mode"] == "cb_auction_t0_v2_1"
    assert "竞价转债" in sent[1][1]
    assert "正股 300001 触发科技" in sent[1][1]
    assert "文档: https://example.feishu.cn/docx/cb" in sent[1][1]


def test_cb_markdown_report_includes_observation_and_trace():
    report = lark_bot.build_markdown_report(
        {
            "mode": "cb_auction_t0_v2_1",
            "trade_date": "2026-07-03",
            "picks": [
                {
                    "code": "123001.SZ",
                    "name": "竞价转债",
                    "stk_code": "300001",
                    "stk_name": "触发科技",
                    "theme_score": 117.0,
                    "quality_tier": "A",
                    "matched_fd_amount": 800000000,
                    "matched_concepts": ["机器人"],
                    "relation_reason": "正股为触发股，命中机器人",
                }
            ],
            "observation_picks": [
                {
                    "code": "123002.SZ",
                    "name": "观察转债",
                    "stk_code": "300002",
                    "stk_name": "观察科技",
                    "theme_score": 88.0,
                    "quality_tier": "B",
                    "observation_reason": "非A档观察",
                    "matched_concepts": ["具身智能"],
                }
            ],
            "process_summary": {
                "trigger_stock_count": 3,
                "concept_count": 2,
                "main_pick_count": 1,
                "observation_pick_count": 1,
                "rejection_count": 4,
            },
            "screening_trace": [{"step": "触发股筛选", "status": "ok", "input_count": 10, "output_count": 3}],
        }
    )

    assert "# 竞价 T+0 选债 V2.1 稳健版分析报告" in report
    assert "## 一、数据更新时间和日期" in report
    assert "## 二、市场状态诊断" in report
    assert "## 三、选债清单" in report
    assert "### 主买清单" in report
    assert "123001.SZ" in report
    assert "8.00亿" in report
    assert "### 观察池" in report
    assert "## 四、板块/概念共振" in report
    assert "## 五、风险提示" in report
    assert "筛选过程: 触发股 3 只，概念 2 个，主买 1 只，观察 1 只，剔除 4 条" in report


def test_lark_doc_xml_contains_whiteboard():
    xml = lark_bot.build_lark_doc_xml_report(
        {
            "mode": "leader_afternoon",
            "trade_date": "2026-07-03",
            "data_refresh": {"status": "ok", "elapsed": 0.1},
            "picks": [
                {
                    "code": "300000",
                    "name": "测试股份",
                    "close": 12.34,
                    "gain_pct": 6.78,
                    "industry": "具身智能",
                    "total_score": 82.5,
                    "resonance_score": 91,
                    "sector_momentum_score": 88,
                    "capital_score": 73,
                    "peer_count": 12,
                }
            ],
        }
    )

    assert '<whiteboard type="svg">' in xml
    assert "<svg" in xml
    assert "序号" in xml
    assert "名称" in xml
    assert "板块" in xml
    assert "评分" in xml
    assert "涨幅" in xml
    assert "一、数据更新时间和日期" in xml
    assert "二、市场状态诊断" in xml
    assert "三、选股清单" in xml


def test_lark_doc_create_uses_report_folder(monkeypatch):
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = '{"data":{"document":{"url":"https://example.feishu.cn/docx/x","document_id":"x"}}}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(lark_bot.subprocess, "run", fake_run)
    monkeypatch.setenv("LARK_REPORT_FOLDER_TOKEN", "folder_token_test")
    result = {
        "mode": "leader_afternoon",
        "trade_date": "2026-07-03",
        "data_refresh": {"status": "ok", "elapsed": 0.1},
        "picks": [],
    }
    path = lark_bot.write_markdown_report(result, lark_bot.build_markdown_report(result))

    doc = lark_bot.sync_markdown_to_lark_doc(path, result)

    assert doc["url"] == "https://example.feishu.cn/docx/x"
    assert "--parent-token" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--parent-token") + 1] == "folder_token_test"


def test_lark_url_verification_checks_token(monkeypatch):
    monkeypatch.setenv("LARK_EVENT_VERIFICATION_TOKEN", "verify-token")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    ok = client.post(
        "/api/v1/lark/events",
        json={"type": "url_verification", "token": "verify-token", "challenge": "abc"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"challenge": "abc"}

    bad = client.post(
        "/api/v1/lark/events",
        json={"type": "url_verification", "token": "bad", "challenge": "abc"},
    )
    assert bad.status_code == 403
