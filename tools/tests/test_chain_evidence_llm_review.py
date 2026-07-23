"""通用产业链证据 LLM 重评 — 纯函数 + 闸门单测 (mock LLM, 不触网不触库)."""

import chain_evidence_llm_review as cer


# ── 关键词推导过滤 ──
def test_is_generic_keyword_filters_broad_terms():
    for kw in ["半导体", "科技", "电子", "设备", "材料", "芯片", "AI", "IC", "", "a"]:
        assert cer.is_generic_keyword(kw) is True


def test_is_generic_keyword_keeps_specific_terms():
    for kw in ["光刻胶", "HBM", "EDA", "TSV", "减速器", "GLP-1", "ADC", "CRO", "存储模组"]:
        assert cer.is_generic_keyword(kw) is False


def test_derive_chain_keywords_dedupes_and_filters():
    config = {
        "chain_name": "存储芯片",
        "segments": ["DRAM", "HBM", "半导体", "存储封测"],
        "layer_keywords": {"DRAM": ["DDR5", "内存"], "HBM": ["HBM3E"]},
    }
    mappings = [
        {"mapping_id": "STOR-688072-FOUNDATION-薄膜沉积设备", "tag_name": "底层支撑层"},
        {"mapping_id": "STOR-300346-FOUNDATION-光刻胶电子特气材料", "tag_name": "底层支撑层"},
    ]
    kws = cer.derive_chain_keywords(config, mappings)
    assert "DRAM" in kws and "HBM3E" in kws and "存储封测" in kws
    assert "半导体" not in kws  # 通用词被过滤
    assert len(kws) == len(set(kws))


# ── mapping_id 业务后缀解析 ──
def test_parse_mapping_hint_extracts_business_suffix():
    assert cer.parse_mapping_hint("STOR-688072-FOUNDATION-薄膜沉积设备") == "薄膜沉积设备"
    assert cer.parse_mapping_hint("INNOVA-300199-FOUNDATION-多肽原料药多肽药物") == "多肽原料药多肽药物"
    assert cer.parse_mapping_hint("LITHOG-300346-FOUNDATION-光刻胶电子特气材料") == "光刻胶电子特气材料"


def test_parse_mapping_hint_rejects_coded_or_hash_suffix():
    assert cer.parse_mapping_hint("EMB-301368.SZ-EI-L5-RV") is None
    assert cer.parse_mapping_hint("EMB-MAP-6699cefa29b9c3caa2") is None
    assert cer.parse_mapping_hint("X") is None


def test_split_hint_keywords():
    # 'RV' 为 2 字母裸词按通用词规则过滤, 业务含义由 '摆线减速器' 等承载
    assert cer.split_hint_keywords("RV/行星/摆线减速器") == ["行星", "摆线减速器"]
    assert cer.split_hint_keywords(None) == []


# ── 业务描述 ──
def test_build_business_desc_uses_chain_name_and_hints():
    desc = cer.build_business_desc({"chain_name": "存储芯片"}, ["存储封测模组制造", "薄膜沉积设备"])
    assert "存储芯片" in desc and "存储封测模组制造" in desc
    desc2 = cer.build_business_desc({"chain_name": "存储芯片"}, [])
    assert desc2 == "存储芯片产业链相关业务"


# ── LLM 闸门 (mock 结果) ──
def _res(relevant=True, names=True, strength="strong"):
    return {"relevant": relevant, "names_company": names, "business": "b",
            "stage": "none", "strength": strength, "reason": "r"}


def test_gate_requires_relevant_names_strong():
    assert cer.is_confirmed_hit(_res()) is True
    assert cer.is_confirmed_hit(_res(names=False)) is False
    assert cer.is_confirmed_hit(_res(relevant=False)) is False
    assert cer.is_confirmed_hit(_res(strength="mid")) is False
    assert cer.is_confirmed_hit(None) is False


# ── 转正档位 ──
def test_promotion_confidence_tiers():
    ev = lambda src: {"source_type": src}
    assert cer.promotion_confidence([ev("announcement")] * 3) == 0.85       # >=3 条
    assert cer.promotion_confidence([ev("announcement"), ev("irm_qa_llm")]) == 0.85  # 跨双源
    assert cer.promotion_confidence([ev("announcement")]) == 0.80
    assert cer.promotion_confidence([ev("irm_qa_llm"), ev("irm_qa_llm")]) == 0.80


# ── 事件构造 ──
def test_build_event_prefix_and_confidence_cap():
    mapping = {"mapping_id": "STOR-688072-FOUNDATION-薄膜沉积设备", "code": "688072", "node_id": "n"}
    para = {"source_type": "announcement_fulltext", "date": "2026-04-01", "title": "2025年年度报告",
            "text": "公司薄膜沉积设备用于存储晶圆厂", "url": "http://x"}
    result = {"relevant": True, "names_company": True, "business": "薄膜沉积设备",
              "stage": "mass_production", "strength": "strong", "reason": "年报明确"}
    ev = cer.build_event("storage_chips", mapping, para, result)
    assert ev["event_id"].startswith("CER-storage_chips-")
    assert ev["source_id"] == "chain_llm_review"
    assert ev["review_status"] == "approved"
    assert ev["confidence"] <= 0.85
    assert ev["evidence_type"] == "commercial_stage"


# ── dry-run 不写库 (假游标) ──
class FakeCur:
    """最小 psycopg2 cursor 替身: 按 SQL 关键词返回固定行, 记录所有 execute."""

    def __init__(self, mappings):
        self._mappings = mappings
        self.executed: list[str] = []
        self._result = []

    def execute(self, sql, params=None):
        self.executed.append(sql)
        if "FROM business_tag_mapping" in sql:
            self._result = [dict(m) for m in self._mappings]
        else:
            self._result = []
        self.rowcount = 0

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


def test_review_chain_dry_run_issues_no_writes(monkeypatch):
    mappings = [{
        "mapping_id": "STOR-688072-FOUNDATION-薄膜沉积设备", "code": "688072",
        "node_id": "storage_chips_foundation", "tag_name": "底层支撑层",
        "status": "pending_review", "evidence_ids": None, "company_name": "拓荆科技",
    }]
    cur = FakeCur(mappings)
    monkeypatch.setattr(cer, "llm_extract", lambda *a, **k: _res())
    budget = {"used": 0}
    result = cer.review_chain(cur, session=None, chain_id="storage_chips", budget=budget, apply=False)
    assert result["new_events"] >= 1 or result["mappings"] == 1
    writes = [s for s in cur.executed if "INSERT" in s or "UPDATE" in s or "SET app" in s]
    assert writes == [], f"dry-run 不应写库: {writes}"


def test_review_chain_skips_near_memory(monkeypatch):
    cur = FakeCur([])
    result = cer.review_chain(cur, session=None, chain_id="near_memory_computing",
                              budget={"used": 0}, apply=False)
    assert result.get("skipped") is True
