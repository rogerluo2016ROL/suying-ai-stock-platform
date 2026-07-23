"""海外市场早报 (morning_brief) 单元测试 — 不依赖 PG / LLM / 外网."""
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.domains.morning_brief import service as brief
from app import lark_bot


def _stocks():
    return [
        {"code": "A", "name": "甲半导体", "pct_chg": 12.0, "amount": 3e8},
        {"code": "B", "name": "乙芯片", "pct_chg": 9.0, "amount": 2e8},
        {"code": "C", "name": "丙晶圆", "pct_chg": 7.0, "amount": 1e8},
        {"code": "D", "name": "丁医药", "pct_chg": 6.0, "amount": 9e7},
        {"code": "E", "name": "戊机器人", "pct_chg": 5.0, "amount": 5e7},
        {"code": "F", "name": "丁医药二", "pct_chg": 4.5, "amount": 6e7},
        {"code": "PENNY", "name": "仙股", "pct_chg": 300.0, "amount": 1e5},  # 低流动性应被过滤
    ]


def test_pick_hot_filters_illiquid_penny_spikes():
    hot = brief._pick_hot(_stocks(), top_n=10, min_pct=3.0, min_amount=5e6)
    codes = [s["code"] for s in hot]
    assert "PENNY" not in codes
    assert codes[0] == "A"  # 涨幅榜优先


def test_pick_hot_merges_gainers_and_amount_leaders():
    stocks = _stocks() + [{"code": "BIG", "name": "巨头", "pct_chg": 0.5, "amount": 9e9}]
    hot = brief._pick_hot(stocks, top_n=10, min_pct=3.0, min_amount=5e6)
    assert "BIG" in [s["code"] for s in hot]  # 成交额榜入选 (涨幅不达标也行)


def test_build_resonance_clusters_by_sector():
    hot = _stocks()[:6]
    sectors = {"A": "半导体", "B": "半导体", "C": "半导体",
               "D": "医药", "E": "机器人", "F": "医药"}
    resonance = brief._build_resonance(hot, sectors, min_cluster=2)
    assert [r["sector"] for r in resonance] == ["半导体", "医药"]
    assert resonance[0]["hot_count"] == 3
    # 板块标签回写到 picks
    assert hot[0]["sector"] == "半导体"


def test_select_news_top10_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(brief, "_llm_chat", lambda *a, **k: None)
    news = [{"pub_time": f"2026-07-22 07:{59-i:02d}", "source": "sina",
             "content": f"新闻{i}"} for i in range(20)]
    top10 = brief._select_news_top10(news, market_focus="美国")
    assert len(top10) == 10
    assert top10[0]["rank"] == 1
    assert top10[0]["market"] == "全球"  # 降级路径默认标签


def test_select_news_top10_llm_path(monkeypatch):
    monkeypatch.setattr(
        brief, "_llm_chat",
        lambda *a, **k: '[{"idx": 2, "title": "英伟达发布新GPU", "summary": "算力升级",'
                        ' "market": "美国", "tags": ["AI算力", "半导体"]}]')
    news = [{"pub_time": "2026-07-22 07:00", "source": "jin10", "content": "旧闻"},
            {"pub_time": "2026-07-22 07:30", "source": "sina", "content": "英伟达发布会"}]
    top = brief._select_news_top10(news, market_focus="美国")
    assert len(top) == 1
    assert top[0]["title"] == "英伟达发布新GPU"
    assert top[0]["pub_time"] == "2026-07-22 07:30"


def _fake_result():
    return {
        "status": "success",
        "mode": "us_morning_brief",
        "brief_type": "us_morning",
        "trade_date": "2026-07-21",
        "picks": [{"code": "NVDA", "name": "英伟达", "pct_chg": 5.2,
                   "amount": 3e10, "sector": "半导体"}],
        "total_picks": 1,
        "sector_resonance": [{"sector": "半导体", "hot_count": 3, "avg_pct": 4.2,
                              "total_amount": 5e10, "stocks": ["英伟达(+5.2%)"]}],
        "news_top10": [{"rank": 1, "title": "测试新闻", "summary": "摘要",
                        "market": "美国", "tags": ["半导体"],
                        "pub_time": "2026-07-22 07:30", "source": "sina"}],
        "market_strength": {"indices": [{"ts_code": "IXIC", "name": "纳斯达克",
                                         "trade_date": "2026-07-21",
                                         "close": 25000.0, "pct_chg": 1.5}],
                            "snapshot_time": "2026-07-22T08:00:00"},
        "data_source": "tushare",
    }


def test_translate_names_to_chinese(monkeypatch):
    monkeypatch.setattr(
        brief, "_llm_chat",
        lambda *a, **k: '{"NVDA": "英伟达", "005930": "三星电子"}')
    hot = [
        {"code": "NVDA", "name": "NVIDIA Corp"},
        {"code": "005930", "name": "삼성전자"},
        {"code": "CPHI", "name": "惠普森医药"},  # 已中文, 不应被翻译
    ]
    brief._translate_names_to_chinese(hot, "us")
    assert hot[0]["name"] == "英伟达" and hot[0]["name_origin"] == "NVIDIA Corp"
    assert hot[1]["name"] == "三星电子"
    assert hot[2]["name"] == "惠普森医药" and "name_origin" not in hot[2]


def test_translate_names_llm_failure_keeps_original(monkeypatch):
    monkeypatch.setattr(brief, "_llm_chat", lambda *a, **k: None)
    hot = [{"code": "X", "name": "Unknown Corp"}]
    brief._translate_names_to_chinese(hot, "us")
    assert hot[0]["name"] == "Unknown Corp"


def test_needs_translation():
    assert brief._needs_translation("NVIDIA Corp")
    assert brief._needs_translation("삼성전자")
    assert not brief._needs_translation("英伟达")
    assert not brief._needs_translation("")


def test_brief_markdown_report_sections():
    md = lark_bot.build_brief_markdown_report(_fake_result())
    for section in ["数据更新时间和日期", "全球市场概览", "板块共振",
                    "热门股清单", "热点财经新闻 Top10", "免责声明"]:
        assert section in md
    assert "英伟达" in md and "纳斯达克" in md


def test_brief_group_reply_via_dispatcher():
    reply = lark_bot._format_group_reply(_fake_result(), {"url": "http://x", "title": "T"})
    assert "板块共振" in reply and "热点新闻" in reply
    assert "英伟达" in reply and "选股日期" not in reply  # 报告型措辞


def test_brief_doc_xml_and_poster():
    result = _fake_result()
    xml = lark_bot.build_brief_lark_doc_xml_report(result)
    assert xml.startswith("<h1>") and "热点财经新闻 Top10" in xml
    svg = lark_bot.build_brief_poster_svg(result)
    assert svg.startswith("<svg") and "板块共振" in svg and "英伟达" in svg
    # 空结果不崩
    empty = {**result, "picks": [], "sector_resonance": [], "news_top10": [],
             "market_strength": {}}
    assert "无" in lark_bot.build_brief_markdown_report(empty)
    lark_bot.build_brief_poster_svg(empty)
