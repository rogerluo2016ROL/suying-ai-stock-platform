"""build_business_segments_from_fina 匹配/占比逻辑单测(mock 行,不连库)。"""
import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[3] / "tools" / "build_business_segments_from_fina.py"
SPEC = importlib.util.spec_from_file_location("build_business_segments_from_fina", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def seg(biz_item, biz_income, ratio=None):
    return {"biz_item": biz_item, "biz_income": biz_income, "revenue_ratio": ratio}


def test_tag_core_strips_prefix_and_suffix():
    assert MODULE.tag_core("Token出口候选：公司业务标签：AI服务器业务") == "ai服务器"
    assert MODULE.tag_core("存储芯片") == "存储芯片"
    assert MODULE.tag_core("高速光模块产品") == "高速光模块"
    assert MODULE.tag_core("") == ""


def test_item_core_strips_suffix_and_parenthetical():
    assert MODULE.item_core("其他业务(地区)") == "其他"
    assert MODULE.item_core("服务器") == "服务器"
    assert MODULE.item_core("医疗器械产品") == "医疗器械"


def test_match_segment_bidirectional_containment():
    segments = [seg("服务器", 100.0), seg("运营商网络", 200.0)]
    # tag 包含 biz_item 核心词
    assert MODULE.match_segment("Token出口候选：公司业务标签：AI服务器业务", segments) is segments[0]
    # biz_item 包含 tag 核心词
    assert MODULE.match_segment("运营商网络", segments) is segments[1]


def test_match_segment_shared_keyword_two_chars():
    segments = [seg("闪存芯片", 50.0), seg("家电", 60.0)]
    # 共享 "闪存"/"芯片" 等 ≥2 字非通用词
    assert MODULE.match_segment("存储芯片", segments) is segments[0]


def test_match_segment_rejects_noise_and_generic():
    # 噪声 biz_item(其他/地区类)不参与匹配
    segments = [seg("其他业务(地区)", 10.0), seg("中国大陆", 20.0)]
    assert MODULE.match_segment("其他业务", segments) is None
    # 仅靠通用词("电子")共现不算匹配
    segments = [seg("消费电子", 10.0)]
    assert MODULE.match_segment("电子设备", segments) is None
    # 完全无关不匹配
    assert MODULE.match_segment("创新药", segments) is None


def test_match_segment_prefers_containment_over_substring():
    segments = [seg("存储模组", 10.0), seg("存储器", 20.0)]
    # "存储模组" 被 tag 包含(包含规则);"存储器" 仅共享 "存储" 2 字 → 包含规则优先
    assert MODULE.match_segment("存储模组", segments) is segments[0]


def test_build_segments_from_rows_latest_period_and_ratio():
    rows = [
        {"code": "000063", "end_date": "2025-12-31", "biz_item": "运营商网络", "biz_income": 80.0, "biz_type": "P"},
        {"code": "000063", "end_date": "2025-12-31", "biz_item": "消费者业务", "biz_income": 20.0, "biz_type": "P"},
        # 旧报告期应被忽略
        {"code": "000063", "end_date": "2025-06-30", "biz_item": "旧业务", "biz_income": 999.0, "biz_type": "P"},
        # 地区行不参与
        {"code": "000063", "end_date": "2025-12-31", "biz_item": "中国大陆", "biz_income": 100.0, "biz_type": "D"},
        # 无 P 行回退 I
        {"code": "688110", "end_date": "2025-12-31", "biz_item": "集成电路", "biz_income": 30.0, "biz_type": "I"},
        {"code": "688110", "end_date": "2025-12-31", "biz_item": "其他", "biz_income": 10.0, "biz_type": "I"},
    ]
    result = MODULE.build_segments_from_rows(rows)
    zte = result["000063"]
    assert len(zte) == 2
    by_item = {s["biz_item"]: s for s in zte}
    assert by_item["运营商网络"]["revenue_ratio"] == 0.8
    assert by_item["消费者业务"]["revenue_ratio"] == 0.2
    assert all(s["end_date"] == "2025-12-31" for s in zte)
    assert all(s["segment_id"].startswith("FSEG-") for s in zte)
    fallback = result["688110"]
    assert {s["biz_type"] for s in fallback} == {"I"}
    assert len(fallback) == 2


def test_longest_common_substring():
    assert MODULE.longest_common_substring("存储芯片", "闪存芯片") == "芯片"
    assert MODULE.longest_common_substring("abc", "def") == ""
