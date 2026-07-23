#!/usr/bin/env python3
"""通用产业链证据 LLM 重评 — 把 near_memory_chain_evidence.py 的流程参数化到任意链.

与近存计算链脚本的区别:
  - strong 关键词不手工按公司定制, 自动推导:
      industry_chain_templates.json 的 layers[].segments
      + supply_chains.json 的 layer_keywords (按模板中文名匹配)
      + business_tag_mapping 的 mapping_id 业务后缀 / tag_name
    过宽通用词 (半导体/科技/电子/设备/材料 等) 统一过滤。
  - 映射清单来自 business_tag_mapping (该 chain 的 pending_review/candidate)。
  - 候选文本以本地 PG 为主 (研报标题/公告标题/互动问答全文); 巨潮公告正文只对
    "标题级已有命中但 LLM 判不到 strong" 的公司补 (每链 ≤5 家, 每家 ≤3 篇)。
  - LLM 闸门复用 services/screener-service/app/llm_evidence_extract.py:
    relevant && names_company && strength=strong 才入库。

写库惯例 (与 near_memory 一致):
  事件 event_id 前缀 CER-<chain_id>-, source_id='chain_llm_review',
  GUC app.supply_chain_review_action='manual' + reviewer 齐全置 approved;
  映射 >=3 条 strong 或跨双源 -> verified 0.85, 否则 0.80; evidence_ids 合并。
  near_memory_computing 链已由专项脚本处理, 本脚本拒绝处理。

Usage:
  python tools/chain_evidence_llm_review.py --stats                      # 链覆盖统计表
  python tools/chain_evidence_llm_review.py --chain-id storage_chips     # dry-run
  python tools/chain_evidence_llm_review.py --chain-id storage_chips --chain-id lithography_equipment_chain --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ / "tools"))
from near_memory_chain_evidence import (  # noqa: E402
    _fetch_pdf_text,
    _load_dotenv,
    _to_date_str,
    extract_keyword_paragraphs,
    hit_kw,
    _cninfo_search_announcements,
)

DEFAULT_DSN = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
TEMPLATES_JSON = PROJ / "packages" / "kronos-factors" / "configs" / "industry_chain_templates.json"
SUPPLY_CHAINS_JSON = PROJ / "packages" / "kronos-factors" / "configs" / "supply_chains.json"

START_DATE = "2024-01-01"
MAX_LLM_CALLS = 600                 # 全局 LLM 预算 (单次运行, 跨链)
MAX_PARAGRAPHS_PER_COMPANY = 8      # 每映射候选段上限 (按公司聚合后)
MAX_FULLTEXT_COMPANIES_PER_CHAIN = 5
MAX_FULLTEXT_DOCS_PER_COMPANY = 3
MAX_FULLTEXT_PARAS_PER_COMPANY = 4

REVIEWER = "chain_evidence_llm_review.py 批量审核"
REVIEW_NOTE = "产业链证据通用 LLM 重评: 本地库标题/问答 + 巨潮正文, relevant+names_company+strong 级才置 approved"
SOURCE_ID = "chain_llm_review"
SKIP_CHAINS = {"near_memory_computing"}  # 已由 near_memory_chain_evidence.py 专项处理

# 过宽通用词: 命中等于没命中, 自动推导时剔除 (参考 near_memory 脚本不收录裸词的做法)
GENERIC_STOPWORDS = {
    "半导体", "科技", "电子", "技术", "设备", "材料", "产品", "服务", "制造", "智能",
    "系统", "股份", "有限", "公司", "产业链", "芯片", "集成电路", "新能源", "汽车",
    "机器人", "医药", "生物", "军工", "国防", "软件", "信息", "通信", "光电", "光学",
    "高端", "国产", "其他", "业务", "领域", "行业", "市场", "应用", "研发", "生产",
}
# mapping_id 中的层 token (解析业务后缀时剥掉)
LAYER_TOKENS = {
    "DEMAND", "TASK", "FOUNDATION", "CORE_PRODUCT", "INTEGRATION", "INFRASTRUCTURE",
    "SUPPORTING", "OPERATION", "COMMERCIALIZATION", "MAP",
}

# LLM 事件 confidence 上限 0.85
SOURCE_CONFIDENCE = {
    "announcement_fulltext": 0.85,
    "announcement": 0.80,
    "research_report": 0.80,
    "irm_qa_llm": 0.80,
}


# ── 关键词 / 业务描述自动推导 (纯函数, 可单测) ──
def is_generic_keyword(kw: str) -> bool:
    text = str(kw or "").strip()
    if not text:
        return True
    if text in GENERIC_STOPWORDS:
        return True
    if len(text) < 2:
        return True
    # 纯 ASCII 词至少 3 个字母 (保留 HBM/EDA/TSV/ADC/CRO, 去掉 AI/IC/3D 等裸词)
    if re.fullmatch(r"[A-Za-z0-9 .+/-]+", text) and len(re.sub(r"[^A-Za-z]", "", text)) < 3:
        return True
    return False


def parse_mapping_hint(mapping_id: str) -> str | None:
    """从 mapping_id 解析公司级业务后缀.
    'STOR-688072-FOUNDATION-薄膜沉积设备' -> '薄膜沉积设备'
    'EMB-301368.SZ-EI-L5-RV' / 'EMB-MAP-6699cefa29b9c3caa2' (编码/哈希型) -> None
    """
    parts = str(mapping_id or "").split("-")
    if len(parts) < 3:
        return None
    tail = parts[2:]  # 剥掉 链前缀 + code
    if tail and tail[0] in LAYER_TOKENS:
        tail = tail[1:]
    # 多段编码型后缀 (EI-L5-RV 之类): 剥掉纯大写编码段, 剥完即无业务含义
    if len(tail) > 1:
        tail = [t for t in tail if not re.fullmatch(r"[A-Z0-9]{1,5}", t)]
    hint = "-".join(tail).strip()
    if not hint or hint in LAYER_TOKENS or re.fullmatch(r"[A-Z0-9]{1,5}", hint):
        return None
    # 哈希/编码型后缀 (18C-L4-embodied_intelligence-6b06d57719 之类) 无业务含义
    if re.search(r"[0-9a-f]{10,}", hint):
        return None
    return hint


def split_hint_keywords(hint: str | None) -> list[str]:
    """业务后缀拆词: 按标点/斜杠切, 过滤通用词."""
    if not hint:
        return []
    tokens = re.split(r"[/、,，;；\s]+", hint)
    return [t for t in (x.strip() for x in tokens) if t and not is_generic_keyword(t)]


def load_chain_config(chain_id: str) -> dict:
    """模板 segments + supply_chains layer_keywords + 中文链名."""
    config = {"chain_name": chain_id, "segments": [], "layer_keywords": {}}
    if TEMPLATES_JSON.exists():
        data = json.loads(TEMPLATES_JSON.read_text(encoding="utf-8"))
        for tpl in data.get("templates", []):
            if tpl.get("template_id") != chain_id:
                continue
            name = str(tpl.get("name") or "")
            config["chain_name"] = re.sub(r"(复杂)?产业链路模板$", "", name) or chain_id
            segments: list[str] = []
            for layer in tpl.get("layers") or []:
                segments.extend(layer.get("segments") or [])
            config["segments"] = segments
            break
    if SUPPLY_CHAINS_JSON.exists():
        data = json.loads(SUPPLY_CHAINS_JSON.read_text(encoding="utf-8"))
        chain = (data.get("chains") or {}).get(config["chain_name"])
        if chain:
            config["layer_keywords"] = chain.get("layer_keywords") or {}
    return config


def derive_chain_keywords(config: dict, mappings: list[dict]) -> list[str]:
    """链级关键词: 模板 segments + layer_keywords + 映射 tag_name/业务后缀拆词, 过滤通用词."""
    kws: list[str] = []
    kws.extend(config.get("segments") or [])
    for words in (config.get("layer_keywords") or {}).values():
        kws.extend(words)
    for m in mappings:
        kws.extend(split_hint_keywords(m.get("tag_name")))
        kws.extend(split_hint_keywords(parse_mapping_hint(m.get("mapping_id"))))
    seen: dict[str, None] = {}
    for kw in kws:
        kw = str(kw or "").strip()
        if kw and not is_generic_keyword(kw):
            seen.setdefault(kw)
    return list(seen)


def build_business_desc(config: dict, hints: list[str]) -> str:
    """LLM 用的目标业务描述: 中文链名 + 该公司映射的业务后缀 (<=3 个)."""
    uniq = list(dict.fromkeys(h for h in hints if h))[:3]
    base = config.get("chain_name") or "目标产业链"
    if uniq:
        return f"{base}产业链相关业务，具体为：{'；'.join(uniq)}"
    return f"{base}产业链相关业务"


def is_confirmed_hit(result: dict | None) -> bool:
    """入库闸门: 相关 + 点名公司 + strong 级 (与 llm_evidence_extract.is_confirmed_hit 一致)."""
    if not result:
        return False
    return bool(result["relevant"] and result["names_company"] and result["strength"] == "strong")


def promotion_confidence(events: list[dict]) -> float:
    """映射转正档位: >=3 条 strong 或跨双源 -> 0.85, 否则 0.80."""
    src_types = {ev["source_type"] for ev in events}
    return 0.85 if (len(events) >= 3 or len(src_types) >= 2) else 0.80


# ── LLM 调用 (懒加载 llm_evidence_extract, 便于测试 monkeypatch) ──
def llm_extract(company_name: str, text: str, business_desc: str) -> dict | None:
    sys.path.insert(0, str(PROJ / "services" / "screener-service"))
    from app.llm_evidence_extract import extract_evidence

    return extract_evidence(company_name, text, business_desc)


# ── 本地 PG 候选采集 ──
def _ts_code(code: str) -> str:
    if code.startswith(("60", "68", "90")):
        return code + ".SH"
    if code.startswith(("4", "8")):
        return code + ".BJ"
    return code + ".SZ"


def collect_local_candidates(cur, code: str, kws: list[str]) -> list[dict]:
    """本地库候选: 研报标题 / 公告标题 / 互动问答全文, 命中链级关键词."""
    rows: list[dict] = []
    cur.execute(
        """
        SELECT pub_date, title, broker FROM research_reports_tushare
        WHERE code = %s AND pub_date >= %s AND coalesce(title, '') <> ''
        ORDER BY pub_date DESC LIMIT 300
        """,
        (code, START_DATE),
    )
    for r in cur.fetchall():
        title = str(r["title"] or "")
        if hit_kw(title, kws):
            rows.append({"source_type": "research_report", "date": _to_date_str(r["pub_date"]),
                         "title": title, "text": f"[{r['broker'] or ''}] {title}", "url": None})
    cur.execute(
        """
        SELECT pub_date, title, broker FROM research_reports
        WHERE split_part(code, '.', 1) = %s AND coalesce(title, '') <> ''
        ORDER BY pub_date DESC LIMIT 100
        """,
        (code,),
    )
    for r in cur.fetchall():
        title = str(r["title"] or "")
        if hit_kw(title, kws):
            rows.append({"source_type": "research_report", "date": _to_date_str(r["pub_date"]),
                         "title": title, "text": f"[{r['broker'] or ''}] {title}", "url": None})
    cur.execute(
        """
        SELECT ann_date, title FROM ts_raw_anns_d
        WHERE ts_code = %s AND ann_date >= %s AND coalesce(title, '') <> ''
        ORDER BY ann_date DESC LIMIT 400
        """,
        (_ts_code(code), START_DATE.replace("-", "")),
    )
    for r in cur.fetchall():
        title = str(r["title"] or "")
        if hit_kw(title, kws):
            rows.append({"source_type": "announcement", "date": _to_date_str(r["ann_date"]),
                         "title": title, "text": title, "url": None})
    cur.execute(
        """
        SELECT pub_date, question, answer FROM interact_qa
        WHERE code = %s AND pub_date >= %s
        ORDER BY pub_date DESC LIMIT 400
        """,
        (code, START_DATE),
    )
    for r in cur.fetchall():
        text = re.sub(r"\s+", " ", f"问: {r['question'] or ''} 答: {r['answer'] or ''}").strip()
        if hit_kw(text, kws):
            rows.append({"source_type": "irm_qa_llm", "date": _to_date_str(r["pub_date"]),
                         "title": str(r["question"] or "")[:80], "text": text[:600], "url": None})
    # 公告标题 > 互动问答 > 研报标题, 同级按日期倒序
    priority = {"announcement": 0, "irm_qa_llm": 1, "research_report": 2}
    rows.sort(key=lambda x: (priority[x["source_type"]], -(int(x["date"].replace("-", "") or 0))))
    return rows


def collect_fulltext_candidates(session, code: str, kws: list[str]) -> list[dict]:
    """巨潮正文补采 (仅 second pass): 定期报告/投关记录/问询回复, 每公司 <=3 篇 <=4 段."""
    content_kw = ["年度报告", "半年度报告", "投资者关系活动记录", "问询函", "回复"]
    noise_kw = ["摘要", "英文", "已取消", "关于召开", "关于举行", "关于参加"]
    try:
        anns = _cninfo_search_announcements(session, code)
    except Exception as e:
        print(f"    ⚠ 巨潮检索失败 [{code}]: {e.__class__.__name__}")
        return []
    candidates: list[dict] = []
    fetched = 0
    for ann in anns:
        if fetched >= MAX_FULLTEXT_DOCS_PER_COMPANY:
            break
        title = ann["title"]
        if any(n in title for n in noise_kw) or not any(k in title for k in content_kw):
            continue
        fetched += 1
        try:
            fulltext = _fetch_pdf_text(session, ann["pdf_url"])
        except Exception as e:
            print(f"    ⚠ 公告正文拉取失败 [{title[:40]}]: {e.__class__.__name__}")
            continue
        for para in extract_keyword_paragraphs(fulltext, kws, max_par=MAX_FULLTEXT_PARAS_PER_COMPANY):
            candidates.append({"source_type": "announcement_fulltext", "date": ann["date"],
                               "title": title, "text": para, "url": ann["pdf_url"]})
    return candidates


# ── 事件构造 ──
def build_event(chain_id: str, mapping: dict, para: dict, result: dict) -> dict:
    stage = result["stage"]
    payload = f"{chain_id}|{mapping['mapping_id']}|{para['source_type']}|{para['date']}|{para['title']}|{para['text'][:40]}"
    return {
        "event_id": f"CER-{chain_id}-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
        "mapping_id": mapping["mapping_id"],
        "code": mapping["code"],
        "node_id": mapping["node_id"],
        "event_date": para["date"] or None,
        "source_type": para["source_type"],
        "source_id": SOURCE_ID,
        "title": para["title"][:200],
        "excerpt": para["text"][:400],
        "original_url": para["url"],
        "evidence_type": "commercial_stage" if stage != "none" else "business_presence",
        "impact_dimensions": json.dumps({
            "growth": stage in {"small_batch", "mass_production", "order"},
            "profit": False, "moat": False, "risk": False,
            "research_stage": None,
            "commercial_stage": stage if stage != "none" else None,
            "tier": "strong",
            "llm_business": result["business"][:100],
            "llm_strength": result["strength"],
            "llm_reason": result["reason"][:100],
        }, ensure_ascii=False),
        "confidence": SOURCE_CONFIDENCE[para["source_type"]],
        "review_status": "approved",
        "review_note": REVIEW_NOTE,
    }


# ── 统计 (任务 1) ──
def print_stats(cur) -> None:
    cur.execute(
        """
        SELECT m.chain_id, count(*) AS mappings,
               count(*) FILTER (WHERE m.status='verified') AS verified,
               count(*) FILTER (WHERE m.status='pending_review') AS pending,
               count(*) FILTER (WHERE m.status='candidate') AS candidate,
               (SELECT count(*) FROM business_tag_evidence_events e
                 WHERE e.mapping_id IN (SELECT mapping_id FROM business_tag_mapping m2
                                         WHERE m2.chain_id = m.chain_id)
                   AND e.review_status = 'approved') AS approved_events
        FROM business_tag_mapping m GROUP BY m.chain_id
        ORDER BY approved_events ASC, mappings DESC
        """,
    )
    rows = [dict(r) for r in cur.fetchall()]
    print(f"{'chain_id':<44} {'映射':>5} {'verified':>8} {'pending':>7} {'candidate':>9} {'approved证据':>10}")
    for r in rows:
        print(f"{r['chain_id']:<44} {r['mappings']:>5} {r['verified']:>8} {r['pending']:>7} "
              f"{r['candidate']:>9} {r['approved_events']:>10}")
    zero = [r for r in rows if r["approved_events"] == 0 and r["mappings"] > 0]
    print(f"\n有映射但 0 approved 证据的链: {len(zero)} 条 (按映射数排序, 扩链候选):")
    for r in zero:
        actionable = r["pending"] + r["candidate"]
        print(f"  {r['chain_id']:<44} 映射 {r['mappings']:>4} (可处理 {actionable})")


# ── 主流程 ──
def review_chain(cur, session, chain_id: str, budget: dict, apply: bool) -> dict:
    if chain_id in SKIP_CHAINS:
        print(f"  跳过 {chain_id}: 已由 near_memory_chain_evidence.py 专项处理")
        return {"chain_id": chain_id, "skipped": True}
    cur.execute(
        """
        SELECT m.mapping_id, m.code, m.node_id, m.tag_name, m.status, m.evidence_ids,
               s.name AS company_name
        FROM business_tag_mapping m
        LEFT JOIN stocks s ON s.code = split_part(m.code, '.', 1)
        WHERE m.chain_id = %s AND m.status IN ('pending_review', 'candidate')
        ORDER BY m.code, m.mapping_id
        """,
        (chain_id,),
    )
    mappings = [dict(r) for r in cur.fetchall()]
    if not mappings:
        print(f"  {chain_id}: 无 pending_review/candidate 映射")
        return {"chain_id": chain_id, "mappings": 0}

    config = load_chain_config(chain_id)
    kws = derive_chain_keywords(config, mappings)
    print(f"\n══ {chain_id} ({config['chain_name']}): 待处理映射 {len(mappings)} 条, "
          f"推导关键词 {len(kws)} 个 ══")
    print(f"  关键词样例: {', '.join(kws[:15])}")

    by_code: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        by_code[m["code"]].append(m)
    # 预算截断: 映射多的公司优先
    companies = sorted(by_code.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    events: list[dict] = []
    hits_by_mapping: dict[str, list[dict]] = defaultdict(list)
    processed = skipped_budget = 0
    samples: dict[str, list[str]] = {"hit": [], "excluded": []}

    for code, maps in companies:
        if budget["used"] >= MAX_LLM_CALLS:
            skipped_budget += len(maps)
            continue
        name = maps[0].get("company_name") or code
        hints = [h for h in (parse_mapping_hint(m["mapping_id"]) for m in maps) if h]
        hints += [m["tag_name"] for m in maps if m.get("tag_name") and not re.search(r"[0-9a-f]{10,}", m["tag_name"])]
        business_desc = build_business_desc(config, hints)
        paras = collect_local_candidates(cur, code, kws)
        # 去重 + 每公司限量
        seen: set[str] = set()
        deduped: list[dict] = []
        for p in paras:
            key = hashlib.sha256((p["title"] + p["text"]).encode()).hexdigest()[:16]
            if key not in seen:
                seen.add(key)
                deduped.append(p)
        paras = deduped[:MAX_PARAGRAPHS_PER_COMPANY * min(len(maps), 2)]

        hit_count = mid_count = excluded = 0
        for p in paras:
            if budget["used"] >= MAX_LLM_CALLS:
                break
            budget["used"] += 1
            result = llm_extract(name, p["text"], business_desc)
            if is_confirmed_hit(result):
                hit_count += 1
                for m in maps:
                    ev = build_event(chain_id, m, p, result)
                    events.append(ev)
                    hits_by_mapping[m["mapping_id"]].append(ev)
                if len(samples["hit"]) < 3:
                    samples["hit"].append(
                        f"[{p['source_type']}] {p['date']} {p['title'][:40]} :: "
                        f"business={result['business'][:50]} stage={result['stage']} reason={result['reason'][:40]}")
            else:
                if result and result["relevant"] and result["names_company"]:
                    mid_count += 1
                excluded += 1
                if len(samples["excluded"]) < 3:
                    summary = (f"{p['date']} {p['title'][:36]} :: "
                               + (f"relevant={result['relevant']} names={result['names_company']} "
                                  f"strength={result['strength']} reason={result['reason'][:40]}"
                                  if result else "LLM调用失败/解析失败"))
                    samples["excluded"].append(summary)
        processed += 1
        if hit_count or mid_count:
            print(f"  {code} {name}: 段 {len(paras)}, 命中 {hit_count}, mid {mid_count}, 排除 {excluded}")

        # second pass: 标题级有命中 (mid) 但无 strong -> 补巨潮正文
        if hit_count == 0 and mid_count > 0 and budget["used"] < MAX_LLM_CALLS:
            fulltext_quota = budget.setdefault("fulltext_companies", {}).get(chain_id, 0)
            if fulltext_quota < MAX_FULLTEXT_COMPANIES_PER_CHAIN:
                budget["fulltext_companies"][chain_id] = fulltext_quota + 1
                ft_paras = collect_fulltext_candidates(session, code, kws)
                ft_hits = 0
                for p in ft_paras:
                    if budget["used"] >= MAX_LLM_CALLS:
                        break
                    budget["used"] += 1
                    result = llm_extract(name, p["text"], business_desc)
                    if is_confirmed_hit(result):
                        ft_hits += 1
                        for m in maps:
                            ev = build_event(chain_id, m, p, result)
                            events.append(ev)
                            hits_by_mapping[m["mapping_id"]].append(ev)
                        if len(samples["hit"]) < 3:
                            samples["hit"].append(
                                f"[announcement_fulltext] {p['date']} {p['title'][:40]} :: "
                                f"business={result['business'][:50]} stage={result['stage']} reason={result['reason'][:40]}")
                if ft_paras:
                    print(f"    ↳ 正文补采 {len(ft_paras)} 段, 命中 {ft_hits}")

    verdicts: list[tuple[dict, list[dict], float]] = []
    for m in mappings:
        evs = hits_by_mapping.get(m["mapping_id"], [])
        conf = promotion_confidence(evs) if evs else 0.0
        verdicts.append((m, evs, conf))

    print(f"\n  ── {chain_id} 小结: 处理公司 {processed} (预算跳过映射 {skipped_budget}), "
          f"新 approved 事件 {len(events)}, 可转正 {len(hits_by_mapping)}/{len(mappings)} ──")
    for s in samples["hit"][:1]:
        print(f"    命中样例: {s}")
    for s in samples["excluded"][:1]:
        print(f"    排除样例: {s}")

    if apply and events:
        cur.execute("SET app.supply_chain_review_action = 'manual'")
        insert_sql = """
            INSERT INTO business_tag_evidence_events (
                event_id, mapping_id, code, node_id, event_date, source_type,
                source_id, title, excerpt, original_url, evidence_type,
                impact_dimensions, confidence, review_status, reviewer,
                review_note, reviewed_at
            ) VALUES (
                %(event_id)s, %(mapping_id)s, %(code)s, %(node_id)s, %(event_date)s,
                %(source_type)s, %(source_id)s, %(title)s, %(excerpt)s,
                %(original_url)s, %(evidence_type)s, %(impact_dimensions)s::jsonb,
                %(confidence)s, %(review_status)s, %(reviewer)s,
                %(review_note)s, %(reviewed_at)s
            ) ON CONFLICT (event_id) DO NOTHING
        """
        inserted = 0
        for ev in events:
            ev["reviewer"] = REVIEWER
            ev["reviewed_at"] = datetime.now()
            cur.execute(insert_sql, ev)
            inserted += cur.rowcount
        for m, evs, conf in verdicts:
            if not evs:
                continue
            existing = m.get("evidence_ids")
            try:
                existing_ids = json.loads(existing) if isinstance(existing, str) else (existing or [])
            except json.JSONDecodeError:
                existing_ids = []
            evidence_ids = list(dict.fromkeys(list(existing_ids) + [ev["event_id"] for ev in evs]))[:50]
            cur.execute(
                """
                UPDATE business_tag_mapping
                SET status = 'verified', confidence = %s,
                    evidence_ids = %s::jsonb, updated_at = CURRENT_TIMESTAMP
                WHERE mapping_id = %s AND chain_id = %s
                """,
                (conf, json.dumps(evidence_ids, ensure_ascii=False), m["mapping_id"], chain_id),
            )
        print(f"    写库: 新事件 {inserted} 条, 转正 {len(hits_by_mapping)} 条映射")
    elif events and not apply:
        print("    dry-run: 未写库, 加 --apply 落库")

    return {
        "chain_id": chain_id,
        "mappings": len(mappings),
        "companies_processed": processed,
        "new_events": len(events),
        "new_verified": len(hits_by_mapping),
        "samples": samples,
    }


def main() -> int:
    global MAX_LLM_CALLS
    parser = argparse.ArgumentParser(description="通用产业链证据 LLM 重评")
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--stats", action="store_true", help="打印链覆盖统计表")
    parser.add_argument("--chain-id", action="append", dest="chain_ids", default=[],
                        help="目标链, 可多次指定")
    parser.add_argument("--apply", action="store_true", help="写库 (默认 dry-run)")
    parser.add_argument("--max-llm-calls", type=int, default=MAX_LLM_CALLS)
    args = parser.parse_args()

    MAX_LLM_CALLS = args.max_llm_calls

    conn = psycopg2.connect(args.pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.stats:
        print_stats(cur)
        conn.close()
        return 0
    if not args.chain_ids:
        print("❌ 需要 --chain-id 或 --stats")
        conn.close()
        return 1

    _load_dotenv(PROJ / "docker" / ".env.lark-bot")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("❌ 缺少 DEEPSEEK_API_KEY (docker/.env.lark-bot)")
        conn.close()
        return 1

    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/new/disclosure/detail",
    })
    budget = {"used": 0}
    results = []
    print(f"目标链 {args.chain_ids}, apply={args.apply}, LLM 预算 {MAX_LLM_CALLS}")
    for chain_id in args.chain_ids:
        results.append(review_chain(cur, session, chain_id, budget, args.apply))

    if args.apply:
        conn.commit()
        print("\n已提交事务")
    print(f"\nLLM 调用合计 {budget['used']} 次 (预算 {MAX_LLM_CALLS})")
    print("\n══ 汇总 ══")
    for r in results:
        if r.get("skipped"):
            continue
        print(f"  {r['chain_id']}: 映射 {r.get('mappings', 0)}, 处理公司 {r.get('companies_processed', 0)}, "
              f"新 approved 事件 {r.get('new_events', 0)}, 新 verified {r.get('new_verified', 0)}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
