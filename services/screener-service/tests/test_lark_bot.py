import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import lark_bot
from app.routers.lark import router


def _event(text="@机器人 /毕师傅硬核科技", chat_id="oc_ok", sender="ou_ok", message_type="text"):
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
        "/产业链预期差": "supply_chain",
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


def test_parse_natural_language_model_commands():
    cmd = lark_bot.parse_message_command("@机器人 帮我跑今天秋神午后选股，并列出板块共振 top10")
    assert cmd is not None
    assert cmd.mode == "leader_afternoon"
    assert cmd.top_n == 10

    cmd = lark_bot.parse_message_command("准备跑竞价 T+0 选债 Top10")
    assert cmd is not None
    assert cmd.mode == "cb_auction_t0_v2_1"
    assert cmd.top_n == 10

    assert lark_bot.parse_message_command("用大葱产业链分析一下 603713") is None

    cmd = lark_bot.parse_message_command("跑大葱产业链 top10")
    assert cmd is not None
    assert cmd.mode == "supply_chain"

    cmd = lark_bot.parse_message_command("跑产业链预期差选股 top10")
    assert cmd is not None
    assert cmd.mode == "supply_chain"

    cmd = lark_bot.parse_message_command("跑毕师傅硬核科技趋势启动")
    assert cmd is not None
    assert cmd.mode == "bi_trend_launch"


def test_single_stock_model_indicator_analysis_is_research_qa_not_model_run():
    text = "@机器人 用毕师傅的硬核科技选股模型的指标分析新洁能这只股票"

    assert lark_bot.parse_message_command(text) is None
    assert lark_bot.is_investment_question(text) is True
    assert lark_bot._research_modes_for_question(text) == ["bi_trend_launch"]


def test_llm_intent_parser_distinguishes_single_stock_analysis(monkeypatch):
    monkeypatch.setattr(
        lark_bot,
        "ask_llm",
        lambda prompt: """
        {
          "intent": "single_stock_model_analysis",
          "is_investment_related": true,
          "needs_report": false,
          "target_stock": "新洁能",
          "stock_code": "",
          "model_hints": ["毕师傅"],
          "requested_tools": ["bi_trend_indicators"],
          "top_n": 10,
          "answer_mode": "stream",
          "reason": "用户要求用模型指标分析单股"
        }
        """,
    )

    plan = lark_bot.parse_intent_with_llm("用毕师傅的硬核科技选股模型的指标分析新洁能这只股票")

    assert plan["intent"] == "single_stock_model_analysis"
    assert plan["is_investment_related"] is True
    assert plan["needs_report"] is False
    assert plan["target_stock"] == "新洁能"
    assert lark_bot.command_from_intent(plan, "用毕师傅的硬核科技选股模型的指标分析新洁能这只股票") is None
    tools = lark_bot.build_tool_plan(plan, "用毕师傅的硬核科技选股模型的指标分析新洁能这只股票")
    assert tools[0]["tool"] == "bi_single_stock_diagnostic"
    assert tools[0]["target_stock"] == "新洁能"
    assert tools[0]["stock_code"] == "605111"
    assert len(tools) == 1


def test_llm_intent_parser_infers_target_stock_from_question_when_llm_misses_it(monkeypatch):
    monkeypatch.setattr(
        lark_bot,
        "ask_llm",
        lambda prompt: """
        {
          "intent": "stock_research",
          "is_investment_related": true,
          "needs_report": false,
          "target_stock": "",
          "stock_code": "",
          "model_hints": ["毕师傅"],
          "requested_tools": ["bi_trend_indicators"],
          "top_n": 10,
          "answer_mode": "stream",
          "reason": "用户要求分析股票"
        }
        """,
    )
    monkeypatch.setattr(
        lark_bot,
        "_infer_stock_from_question",
        lambda question: {"code": "605111", "name": "新洁能", "industry": "半导体"},
    )

    plan = lark_bot.parse_intent_with_llm("CLI 用毕师傅的硬核科技选股模型的指标分析新洁能这只股票")
    tools = lark_bot.build_tool_plan(plan, "CLI 用毕师傅的硬核科技选股模型的指标分析新洁能这只股票")

    assert plan["intent"] == "single_stock_model_analysis"
    assert plan["target_stock"] == "新洁能"
    assert plan["stock_code"] == "605111"
    assert tools[0]["tool"] == "bi_single_stock_diagnostic"
    assert tools[0]["target_stock"] == "新洁能"


def test_single_stock_model_analysis_context_includes_bi_diagnostic(monkeypatch):
    plan = {
        "intent": "single_stock_model_analysis",
        "is_investment_related": True,
        "needs_report": False,
        "target_stock": "新洁能",
        "stock_code": "605111",
        "model_hints": ["毕师傅"],
        "requested_tools": ["bi_trend_indicators"],
        "top_n": 10,
        "trade_date": "2026-07-07",
    }

    monkeypatch.setattr(
        lark_bot,
        "build_bi_single_stock_diagnostic",
        lambda intent_plan: {
            "tool": "bi_single_stock_diagnostic",
            "status": "ok",
            "stock": {"code": "605111", "name": "新洁能", "industry": "半导体"},
            "trade_date": "2026-07-07",
            "data_source": "daily_kline",
            "metrics": {
                "close": 79.74,
                "pct_chg": -0.77,
                "ma5": 83.29,
                "ma10": 84.92,
                "ma20": 76.02,
                "volume_ratio_5d": 0.58,
                "obv": 8448138.55,
                "adx": 58.26,
                "max_single_drop_5d": -9.57,
            },
            "gates": [
                {"gate": "硬科技行业门控", "passed": True},
                {"gate": "弱市 5 日内不能有单日跌幅超过 8%", "passed": False},
            ],
            "failed_gates": [{"gate": "弱市 5 日内不能有单日跌幅超过 8%", "passed": False}],
            "model_verdict": "fail",
        },
    )
    context = lark_bot.build_project_research_context("用毕师傅的硬核科技选股模型的指标分析新洁能这只股票", plan)

    assert context["tool_plan"][0]["tool"] == "bi_single_stock_diagnostic"
    assert context["diagnostics"][0]["stock"]["code"] == "605111"
    assert context["diagnostics"][0]["metrics"]["adx"] == 58.26
    assert context["diagnostics"][0]["failed_gates"][0]["gate"] == "弱市 5 日内不能有单日跌幅超过 8%"
    assert context["runs"] == []
    assert context["validation"]["warnings"] == []


def test_single_stock_model_analysis_uses_model_specific_diagnostic_tools():
    cases = [
        ("毕师傅", "bi_single_stock_diagnostic", "bi_trend_launch"),
        ("秋神午后", "leader_single_stock_diagnostic", "leader_afternoon"),
        ("大葱产业链", "supply_chain_single_stock_diagnostic", "supply_chain"),
    ]

    for hint, diagnostic_tool, mode in cases:
        plan = {
            "intent": "single_stock_model_analysis",
            "is_investment_related": True,
            "needs_report": False,
            "target_stock": "新洁能",
            "stock_code": "605111",
            "model_hints": [hint],
            "requested_tools": ["model_indicators"],
            "top_n": 10,
            "trade_date": "2026-07-07",
        }

        tools = lark_bot.build_tool_plan(plan, f"用{hint}模型分析新洁能")

        assert tools == [
            {
                "tool": diagnostic_tool,
                "mode": mode,
                "target_stock": "新洁能",
                "stock_code": "605111",
                "trade_date": "2026-07-07",
            }
        ]


def test_single_stock_model_analysis_can_also_run_model_when_requested():
    plan = {
        "intent": "single_stock_model_analysis",
        "is_investment_related": True,
        "needs_report": False,
        "target_stock": "新洁能",
        "stock_code": "605111",
        "model_hints": ["毕师傅"],
        "requested_tools": ["model_indicators"],
        "top_n": 10,
        "trade_date": "2026-07-07",
    }

    tools = lark_bot.build_tool_plan(plan, "用毕师傅模型分析新洁能，并列出Top10")

    assert tools[0]["tool"] == "bi_single_stock_diagnostic"
    assert tools[1]["tool"] == "model_run"
    assert tools[1]["mode"] == "bi_trend_launch"


def test_investment_answer_uses_feishu_readable_plain_tables(monkeypatch):
    context = {
        "question": "用毕师傅模型分析新洁能",
        "generated_at": "2026-07-07 23:30",
        "intent": {"intent": "single_stock_model_analysis", "target_stock": "新洁能"},
        "tool_plan": [{"tool": "bi_single_stock_diagnostic", "mode": "bi_trend_launch"}],
        "runs": [],
        "diagnostics": [
            {
                "tool": "bi_single_stock_diagnostic",
                "diagnostic_style": "毕师傅硬核科技 H1-H6 + 趋势启动门槛",
                "stock": {"code": "605111", "name": "新洁能"},
                "rubric_total_score": 29.2,
                "rubric_full_score": 50,
                "rubric": [
                    {"dimension": "H1 卡脖子紧迫度", "score": 7.0, "full_score": 10, "key_data": "行业 半导体"},
                ],
                "gates": [
                    {"gate": "收盘价站上 MA5", "passed": False, "value": 83.29, "note": "趋势启动要求短线重新站上均线"},
                ],
                "failed_gates": [
                    {"gate": "收盘价站上 MA5", "passed": False, "value": 83.29, "note": "趋势启动要求短线重新站上均线"},
                ],
            }
        ],
        "validation": {"warnings": ["目标股票未出现在本次项目模型返回的 Top 结果中，不能直接视为模型支持。"]},
    }

    monkeypatch.setattr(lark_bot, "build_project_research_context", lambda question, intent_plan=None: context)

    answer, _ = lark_bot.answer_investment_question("用毕师傅模型分析新洁能")

    assert "【H1-H6 评分】" in answer
    assert "H1 卡脖子紧迫度" in answer
    assert "7.0/10" in answer
    assert "【门槛诊断】" in answer
    assert "未过  收盘价站上 MA5" in answer
    assert "###" not in answer
    assert "**" not in answer
    assert "|---" not in answer


def test_investment_answer_with_model_runs_uses_plain_report_not_markdown(monkeypatch):
    context = {
        "question": "帮我分析一下今天的板块共振情况",
        "generated_at": "2026-07-07 23:43",
        "intent": {"intent": "sector_resonance"},
        "tool_plan": [{"tool": "model_run", "mode": "leader_afternoon"}],
        "diagnostics": [],
        "runs": [
            {
                "status": "ok",
                "mode": "leader_afternoon",
                "model_title": "秋神午后选股分析报告",
                "trade_date": "2026-07-07",
                "total_picks": 0,
                "top_picks": [],
                "resonance": ["- 暂无可统计的板块共振数据"],
            }
        ],
        "validation": {"warnings": []},
    }

    monkeypatch.setattr(lark_bot, "build_project_research_context", lambda question, intent_plan=None: context)

    answer, _ = lark_bot.answer_investment_question("帮我分析一下今天的板块共振情况")

    assert "📊 投研模型结果" in answer
    assert "模型：秋神午后选股分析报告" in answer
    assert "入选数量：0" in answer
    assert "暂无可统计的板块共振数据" in answer
    assert "**" not in answer
    assert "`" not in answer
    assert "###" not in answer


def test_sanitize_feishu_text_removes_markdown_noise():
    text = lark_bot._sanitize_feishu_text("**结论**：无入选\\n### 详情\\n- 模型 `leader_afternoon`")

    assert "**" not in text
    assert "###" not in text
    assert "`" not in text
    assert "结论：无入选" in text
    assert "· 模型 leader_afternoon" in text


def test_llm_intent_parser_can_request_model_report(monkeypatch):
    monkeypatch.setattr(
        lark_bot,
        "ask_llm",
        lambda prompt: '{"intent":"model_run","is_investment_related":true,"needs_report":true,"model_hints":["秋神午后"],"top_n":8}',
    )

    plan = lark_bot.parse_intent_with_llm("帮我跑秋神午后选股 top8")
    command = lark_bot.command_from_intent(plan, "帮我跑秋神午后选股 top8")

    assert command is not None
    assert command.mode == "leader_afternoon"
    assert command.top_n == 8


def test_general_question_replies_directly_without_report(monkeypatch):
    sent = []
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")
    monkeypatch.setattr(lark_bot, "send_text_to_chat", lambda chat_id, text: sent.append((chat_id, text)))
    monkeypatch.setattr(lark_bot, "ask_llm", lambda question: "今天适合先确认日程安排。")
    monkeypatch.setattr(lark_bot, "write_markdown_report", lambda result, markdown: (_ for _ in ()).throw(AssertionError("普通问答不应生成 markdown")))
    monkeypatch.setattr(lark_bot, "sync_markdown_to_lark_doc", lambda path, result: (_ for _ in ()).throw(AssertionError("普通问答不应同步飞书文档")))

    result = lark_bot.handle_lark_message(_event("@机器人 今天下午我有什么安排？"))

    assert result["ignored"] is False
    assert result["mode"] == "general_qa"
    assert result["question"] == "今天下午我有什么安排？"
    assert len(sent) == 2
    assert "正在调用大模型分析" in sent[0][1]
    assert sent[1][1] == "今天适合先确认日程安排。"


def test_investment_question_uses_project_context_and_streams_answer(monkeypatch):
    sent = []
    captured = {}
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")
    monkeypatch.setenv("LARK_STREAM_CHUNK_CHARS", "18")
    monkeypatch.setenv("LARK_STREAM_CHUNK_DELAY_SEC", "0")
    monkeypatch.setattr(lark_bot, "send_text_to_chat", lambda chat_id, text: sent.append((chat_id, text)) or {"code": 0})
    monkeypatch.setattr(lark_bot, "write_markdown_report", lambda result, markdown: (_ for _ in ()).throw(AssertionError("投研问答不应生成 markdown")))
    monkeypatch.setattr(lark_bot, "sync_markdown_to_lark_doc", lambda path, result: (_ for _ in ()).throw(AssertionError("投研问答不应同步飞书文档")))

    def fake_run(command):
        captured.setdefault("modes", []).append(command.mode)
        return {
            "mode": command.mode,
            "trade_date": "2026-07-07",
            "total_picks": 1,
            "picks": [
                {
                    "code": "300000",
                    "name": "测试股份",
                    "industry": "具身智能",
                    "total_score": 88,
                    "entry_reason": "板块共振强",
                }
            ],
        }

    def fake_llm(prompt):
        captured["prompt"] = prompt
        return "结论：具身智能有模型上下文支持。\n依据：测试股份入选，评分较高。"

    monkeypatch.setattr(lark_bot, "run_command", fake_run)
    monkeypatch.setattr(lark_bot, "ask_llm", fake_llm)

    result = lark_bot.handle_lark_message(_event("@机器人 具身智能今天是不是共振很强？"))

    assert result["ignored"] is False
    assert result["mode"] == "research_qa"
    assert "leader_afternoon" in captured["modes"]
    assert len(sent) >= 2
    assert "正在理解意图并调用项目数据/模型" in sent[0][1]
    assert "📊 投研模型结果" in sent[1][1]
    assert "测试股份" in sent[1][1]
    assert "**" not in sent[1][1]


def test_investment_diagnostic_answer_is_sent_as_single_readable_message(monkeypatch):
    sent = []
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")
    monkeypatch.setattr(lark_bot, "send_text_to_chat", lambda chat_id, text: sent.append((chat_id, text)) or {"code": 0})
    monkeypatch.setattr(lark_bot, "parse_intent_with_llm", lambda question: {
        "intent": "single_stock_model_analysis",
        "is_investment_related": True,
        "needs_report": False,
        "target_stock": "新洁能",
        "stock_code": "605111",
        "model_hints": ["毕师傅"],
        "top_n": 10,
    })
    monkeypatch.setattr(lark_bot, "answer_investment_question", lambda question, intent_plan=None: (
        "📌 新洁能（605111）\n【H1-H6 评分】\n【门槛诊断】",
        {"diagnostics": [{"tool": "bi_single_stock_diagnostic"}]},
    ))

    result = lark_bot.handle_lark_message(_event("@机器人 用毕师傅模型分析新洁能"))

    assert result["mode"] == "research_qa"
    assert len(sent) == 2
    assert "正在理解意图并调用项目数据/模型" in sent[0][1]
    assert sent[1][1].startswith("📌 新洁能")
    assert not sent[1][1].startswith("(1/")


def test_group_message_without_mention_is_ignored(monkeypatch):
    monkeypatch.setenv("LARK_ALLOWED_CHAT_IDS", "oc_ok")
    monkeypatch.setenv("LARK_ALLOWED_USER_OPEN_IDS", "ou_ok")

    result = lark_bot.handle_lark_message(_event("跑秋神午后选股"))

    assert result == {"ignored": True, "reason": "bot_not_mentioned"}


def test_send_text_falls_back_to_lark_cli_without_app_credentials(monkeypatch):
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = '{"code":0,"data":{"message_id":"om_test"}}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)
    monkeypatch.setattr(lark_bot.subprocess, "run", fake_run)

    result = lark_bot.send_text_to_chat("oc_ok", "测试消息")

    assert result["code"] == 0
    assert captured["cmd"][:5] == ["lark-cli", "im", "+messages-send", "--as", "bot"]
    assert "--chat-id" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--chat-id") + 1] == "oc_ok"
    assert captured["cmd"][captured["cmd"].index("--text") + 1] == "测试消息"


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
            "content": "@机器人 /秋神午后",
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


def test_group_reply_contains_market_resonance_top10_and_doc():
    result = {
        "mode": "leader_afternoon",
        "trade_date": "2026-07-14",
        "market_strength": {
            "status": "ok",
            "snapshot_time": "2026-07-14 14:00:00",
            "advancers": 3200,
            "decliners": 1500,
            "median_pct": 1.2,
        },
        "sector_resonance": [{"sector": "半导体", "count": 4, "score": 88}],
        "picks": [
            {"code": f"00000{i}", "name": f"股票{i}", "total_score": 90 - i}
            for i in range(10)
        ],
    }

    text = lark_bot._format_group_reply(
        result,
        {"title": "报告", "url": "https://example/doc"},
    )

    assert "市场强弱" in text
    assert "上涨 3200" in text
    assert "板块共振" in text
    assert "半导体" in text
    assert "10. 000009 股票9" in text
    assert "https://example/doc" in text


def test_cb_group_reply_labels_eastmoney_fallback_source():
    text = lark_bot._format_group_reply(
        {
            "mode": "cb_auction_t0_v2_1",
            "trade_date": "2026-07-14",
            "picks": [],
            "pipeline": {"data_source": "eastmoney_fallback"},
            "no_result_reason": "没有转债通过门槛",
        },
        {"title": "选债报告", "url": "https://example/doc"},
    )

    assert "数据源: 东方财富备用口径" in text


def test_stock_markdown_uses_real_market_strength_when_available():
    report = lark_bot.build_markdown_report(
        {
            "mode": "leader_afternoon",
            "trade_date": "2026-07-14",
            "picks": [],
            "market_strength": {
                "status": "ok",
                "snapshot_time": "2026-07-14 14:00:00",
                "coverage": 4800,
                "advancers": 3200,
                "decliners": 1500,
                "flat": 100,
                "median_pct": 1.2,
                "above_5pct": 180,
                "below_minus_5pct": 20,
            },
        }
    )

    assert "上涨家数" in report
    assert "3200" in report
    assert "2026-07-14 14:00:00" in report


def test_lark_cli_bot_init_passes_secret_via_stdin(monkeypatch):
    calls = []

    class Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setenv("LARK_CLI_INIT_BOT", "true")
    monkeypatch.setenv("LARK_APP_ID", "app-test")
    monkeypatch.setenv("LARK_APP_SECRET", "secret-test")
    monkeypatch.setattr(lark_bot, "_LARK_CLI_BOT_READY", False)
    monkeypatch.setattr(
        lark_bot.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)) or Proc(),
    )

    lark_bot._ensure_lark_cli_bot_config()

    command, kwargs = calls[0]
    assert "secret-test" not in command
    assert kwargs["input"] == "secret-test\n"
    assert "--app-secret-stdin" in command


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

    result = lark_bot.handle_lark_message(_event("@机器人 /竞价选债 top=5"))

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
