#!/usr/bin/env python3
"""近存计算链 — 证据采集 + 映射保守转正.

复用 bom_expand_evidence.py 的抽取惯例 (CHOKEPOINT_KW / COMMERCIALIZATION_KW),
但数据源全部走本地 PG 已有表, 不调 tushare API:

  1. research_reports_tushare (+ research_reports)  — 研报标题, code 精确匹配
  2. ts_raw_anns_d + announcements                  — 公告标题
  3. interact_qa                                    — 互动易/e互动 问答全文
  4. stock_news_tushare                             — 新闻 (按公司名匹配, 该表无个股 code)

相关性分两级:
  strong : 命中公司专属近存计算业务词 (COMPANY_KW, 如 澜起-CXL/MXC, 拓荆-混合键合)
  theme  : 仅命中链级主题词 (THEME_KW, 如 HBM/存算一体/先进封装)

事件落 business_tag_evidence_events (event_id 前缀 NMC-EV-, 可幂等重跑):
  approved       = strong 级 且 来源为 研报/公告 (对应"研报/公告点名该公司相关业务")
  pending_review = 其余 (互动问答/新闻/仅主题命中)

映射转正 (保守): 仅当 mapping 有 >=1 条 approved 事件时
  status -> 'verified', confidence -> 0.80 (>=3 条 approved 或跨研报+公告双源 -> 0.85)
  evidence_ids 写入 approved 事件 id; 无 approved 证据的映射保持 pending_review 不动。

同时为 approved 映射写 business_tag_stage_tracking (NMC-ST- 前缀),
供 supply_chain_data_collection_center.py refresh-expectation-scores 计分。

所有写入均限定 chain_id='near_memory_computing' 的 39 条 mapping 及 NMC- 前缀行,
不触碰其他链数据。

Usage:
  python tools/near_memory_chain_evidence.py --dry-run     # 只 SELECT + 打印, 不写库
  python tools/near_memory_chain_evidence.py               # 写库

阶段二A — LLM 结构化重评 (公告正文 + 互动问答):
  python tools/near_memory_chain_evidence.py --llm-review            # dry-run, 只打印
  python tools/near_memory_chain_evidence.py --llm-review --apply    # 写库

  流程: 对 status='pending_review' 的映射, 从 ts_raw_anns_d 筛标题含业务关键词的
  公告 (每公司 <=10 条, 2024 至今, 本地 ts_raw_anns_d 收录稀疏, 故走巨潮 webapi
  hisAnnouncement/query 直接检索), 下载 PDF -> pdftotext 拉正文,
  截取含关键词段落 (每篇 <=5 段), 加上互动问答证据段落, 逐段过 DeepSeek 结构化抽取
  (services/screener-service/app/llm_evidence_extract.py)。relevant && names_company
  && strength=strong 的段落写成新证据事件 (NMC-EV- 前缀, source_type=
  announcement_fulltext / irm_qa_llm, confidence <= 0.85, GUC 'manual' 审核惯例置
  approved), 对应映射升 verified (0.80/0.85 档)。LLM 判不相关的段落不入库, 打印摘要
  供人工核对。LLM 调用总预算 MAX_LLM_CALLS=300。
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
DEFAULT_DSN = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

THEME_ID = "future_industry_near_memory_computing"
CHAIN_ID = "near_memory_computing"
START_DATE = "2024-01-01"
MAX_EVENTS_PER_MAPPING_SOURCE = 25
# 触发器 guard_supply_chain_manual_review (migration 033) 要求 approved 事件必须
# 在显式审核事务中写入: 会话 GUC=manual + reviewer/review_note/reviewed_at 齐全。
REVIEWER = "near_memory_chain_evidence.py 批量审核"
REVIEW_NOTE = "近存计算链本地库关键词审核: 仅研报/公告标题命中公司专属业务词的strong级证据转正, 见 outputs/near_memory_chain_evidence_*.csv"

# ── 公司专属近存计算业务词 (strong 级证据) ──
COMPANY_KW: dict[str, list[str]] = {
    "688008": ["CXL", "MXC", "内存接口", "互连芯片", "Retimer", "MRCD", "MDB", "CKD", "内存扩展", "内存池化", "DDR5", "内存模组配套"],
    "603986": ["存算一体", "DRAM", "利基存储", "利基型存储", "NOR", "DDR4", "DDR3"],
    "688416": ["存算一体", "存内计算", "ReRAM", "阻变", "MRAM", "CiM", "存算"],
    "301308": ["HBM", "存储模组", "企业级存储", "eSSD", "RDIMM", "内存条", "UFS", "eMMC", "主控芯片"],
    "688525": ["HBM", "存储模组", "晶圆级封装", "eSSD", "RDIMM", "内存条", "UFS", "eMMC", "存储封测",
               "AI端侧", "端侧AI", "端侧存储", "先进封测"],
    "000977": ["AI服务器", "智算", "HBM", "推理服务器", "内存池化", "CXL"],
    "601138": ["AI服务器", "GB200", "GPU服务器", "AI算力", "英伟达"],
    "603019": ["智算", "AI服务器", "算力中心", "国产算力", "AI基础设施", "算力", "海光", "液冷"],
    "002409": ["前驱体", "HBM", "High-K", "high-k", "电子特气"],
    "002156": ["先进封装", "2.5D", "3D封装", "Chiplet", "HBM", "封测", "芯粒"],
    "002185": ["先进封装", "TSV", "3D封装", "Chiplet", "HBM", "封测"],
    "600584": ["XDFOI", "先进封装", "2.5D", "3D封装", "HBM", "Chiplet", "SiP", "封测"],
    "688362": ["先进封装", "HBM", "2.5D", "Chiplet", "SiP", "封测"],
    "301269": ["3D IC", "3DIC", "先进封装", "Chiplet", "芯粒"],
    "688206": ["3D IC", "3DIC", "先进封装", "建库", "良率提升"],
    "688521": ["UCIe", "Chiplet", "芯粒", "HBM", "2.5D", "先进封装", "IP授权"],
    "002371": ["TSV", "先进封装", "HBM", "键合"],
    "688012": ["TSV", "深硅刻蚀", "先进封装", "HBM"],
    "688072": ["混合键合", "键合设备", "晶圆键合", "先进封装", "HBM"],
    "688120": ["CMP", "减薄", "先进封装", "HBM", "抛光", "划切"],
    "688082": ["电镀", "清洗", "TSV", "先进封装", "HBM", "铜互连"],
    "688300": ["硅微粉", "封装填料", "Low-α", "Lowα", "球硅", "HBM", "先进封装", "低介电"],
    "688733": ["Low-α", "Lowα", "球形氧化铝", "封装材料", "HBM", "先进封装"],
    "002436": ["IC载板", "封装基板", "FCBGA", "BT载板", "ABF"],
    "002916": ["IC载板", "封装基板", "FCBGA", "BT载板", "ABF", "高速板"],
    "603773": ["玻璃基板", "TGV", "玻璃通孔", "先进封装"],
}

# ── 链级主题词 (theme 级证据) ──
THEME_KW = [
    "HBM", "高带宽内存", "存算一体", "存内计算", "近存计算", "近内存计算", "近数据处理",
    "CXL", "内存池化", "混合键合", "3D堆叠", "存储墙", "PIM", "AiM",
    "先进封装", "2.5D", "3D封装", "TSV", "Chiplet", "芯粒", "UCIe", "玻璃基板", "TGV",
]

# ── 复用 bom_expand_evidence.py 的抽取惯例 ──
CHOKEPOINT_KW = [
    "国产替代", "进口替代", "打破垄断", "自主可控", "突破封锁", "卡脖子",
    "唯一", "独家", "首家", "稀缺", "寡头", "垄断",
    "定点", "认证", "进入供应链", "客户验证", "供应商", "合格供方",
    "替代进口", "海外替代", "国产化率",
]
COMMERCIALIZATION_KW = {
    "样品/研发": ["样品", "试制", "研发中", "预研", "开发中", "送样", "打样"],
    "小批量": ["小批量", "小批", "试产", "中试", "初步交付"],
    "量产": ["量产", "批量生产", "规模化", "批量交付", "规模交付", "稳定出货"],
    "放量/订单": ["订单", "产能释放", "扩产", "放量", "满产", "需求旺盛", "供不应求"],
}
# 商业化阶段 → 评分管线 C 级 (对齐 supply_chain_evidence_pipeline 的 C1-C4)
STAGE_TO_COMMERCIAL = {"样品/研发": "C1", "小批量": "C2", "量产": "C3", "放量/订单": "C4"}
COMMERCIAL_RANK = {"C0": 0, "C1": 1, "C2": 2, "C3": 3, "C4": 4}


def _upper(text: str) -> str:
    return str(text or "").upper()


def hit_kw(text: str, kws: list[str]) -> list[str]:
    up = _upper(text)
    return [kw for kw in kws if kw.upper() in up]


def stage_hits(text: str) -> list[str]:
    return [s for s, kws in COMMERCIALIZATION_KW.items() if any(kw in str(text or "") for kw in kws)]


def best_commercial_stage(all_texts: list[str]) -> str:
    best = "C0"
    for t in all_texts:
        for s in stage_hits(t):
            c = STAGE_TO_COMMERCIAL[s]
            if COMMERCIAL_RANK[c] > COMMERCIAL_RANK[best]:
                best = c
    return best


def best_research_stage(all_texts: list[str]) -> str:
    joined = " ".join(all_texts)
    if any(k in joined for k in ["进入供应链", "定点", "客户验证", "合格供方"]):
        return "R5"
    if any(k in joined for k in ["送样", "认证", "导入"]):
        return "R4"
    if "样品" in joined or "打样" in joined:
        return "R2"
    return "R1"


def _event_id(mapping_id: str, source_type: str, ev_date: str, title: str) -> str:
    payload = f"{CHAIN_ID}|{mapping_id}|{source_type}|{ev_date}|{title[:80]}"
    return "NMC-EV-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _to_date_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


# ── 采集: 单公司多来源 ──
def collect_company(cur, code: str, name: str) -> list[dict]:
    """返回 [{source_type, date, title, excerpt, url}], 未做关键词过滤."""
    rows: list[dict] = []

    # 1) 研报 (tushare 表 + 本地 research_reports)
    cur.execute(
        """
        SELECT pub_date, title, broker FROM research_reports_tushare
        WHERE code = %s AND pub_date >= %s AND coalesce(title, '') <> ''
        ORDER BY pub_date DESC LIMIT 300
        """,
        (code, START_DATE),
    )
    for r in cur.fetchall():
        rows.append({"source_type": "research_report", "date": _to_date_str(r["pub_date"]),
                     "title": str(r["title"] or ""), "excerpt": f"[{r['broker'] or ''}] {r['title'] or ''}", "url": None})
    cur.execute(
        """
        SELECT pub_date, title, broker FROM research_reports
        WHERE split_part(code, '.', 1) = %s AND coalesce(title, '') <> ''
        ORDER BY pub_date DESC LIMIT 100
        """,
        (code,),
    )
    for r in cur.fetchall():
        rows.append({"source_type": "research_report", "date": _to_date_str(r["pub_date"]),
                     "title": str(r["title"] or ""), "excerpt": f"[{r['broker'] or ''}] {r['title'] or ''}", "url": None})

    # 2) 公告 (ts_raw_anns_d 全历史 + announcements 近月)
    suffix = ".SH" if code.startswith(("6", "9")) else (".BJ" if code.startswith(("4", "8")) else ".SZ")
    if code.startswith(("60", "68", "90")):
        suffix = ".SH"
    cur.execute(
        """
        SELECT ann_date, title, url FROM ts_raw_anns_d
        WHERE ts_code = %s AND ann_date >= %s AND coalesce(title, '') <> ''
        ORDER BY ann_date DESC LIMIT 400
        """,
        (code + suffix, START_DATE.replace("-", "")),
    )
    for r in cur.fetchall():
        rows.append({"source_type": "announcement", "date": _to_date_str(r["ann_date"]),
                     "title": str(r["title"] or ""), "excerpt": str(r["title"] or ""), "url": r["url"]})
    cur.execute(
        """
        SELECT ann_date, title FROM announcements
        WHERE code = %s AND coalesce(title, '') <> ''
        ORDER BY ann_date DESC LIMIT 200
        """,
        (code,),
    )
    for r in cur.fetchall():
        rows.append({"source_type": "announcement", "date": _to_date_str(r["ann_date"]),
                     "title": str(r["title"] or ""), "excerpt": str(r["title"] or ""), "url": None})

    # 3) 互动问答
    cur.execute(
        """
        SELECT pub_date, question, answer FROM interact_qa
        WHERE code = %s AND pub_date >= %s
        ORDER BY pub_date DESC LIMIT 400
        """,
        (code, START_DATE),
    )
    for r in cur.fetchall():
        q, a = str(r["question"] or ""), str(r["answer"] or "")
        rows.append({"source_type": "interact_qa", "date": _to_date_str(r["pub_date"]),
                     "title": q[:80], "excerpt": (q[:120] + " | " + a[:180]).strip(" |"), "url": None})

    # 4) 个股新闻 (表无 code, 按公司名匹配标题/正文)
    if name and len(name) >= 3:
        cur.execute(
            """
            SELECT pub_time, title, content, source FROM stock_news_tushare
            WHERE pub_time >= %s
              AND (coalesce(title, '') LIKE %s OR coalesce(content, '') LIKE %s)
            ORDER BY pub_time DESC LIMIT 200
            """,
            (START_DATE, f"%{name}%", f"%{name}%"),
        )
        for r in cur.fetchall():
            rows.append({"source_type": "stock_news", "date": _to_date_str(r["pub_time"]),
                         "title": str(r["title"] or ""), "excerpt": (str(r["title"] or "") + " " + str(r["content"] or "")[:200]).strip(),
                         "url": None})
    return rows


def classify(code: str, item: dict) -> dict | None:
    """关键词过滤 + 分级. 返回 None 表示与近存计算无关."""
    text = item["title"] + " " + item["excerpt"]
    strong_hits = hit_kw(text, COMPANY_KW.get(code, []))
    theme_hits = hit_kw(text, THEME_KW)
    if not strong_hits and not theme_hits:
        return None
    tier = "strong" if strong_hits else "theme"
    stages = stage_hits(text)
    choke = hit_kw(text, CHOKEPOINT_KW)
    approved = tier == "strong" and item["source_type"] in {"research_report", "announcement"}
    confidence = {
        ("strong", "research_report"): 0.85, ("strong", "announcement"): 0.85,
        ("strong", "interact_qa"): 0.75, ("strong", "stock_news"): 0.65,
        ("theme", "research_report"): 0.70, ("theme", "announcement"): 0.70,
        ("theme", "interact_qa"): 0.60, ("theme", "stock_news"): 0.50,
    }[(tier, item["source_type"])]
    item.update({
        "tier": tier, "strong_hits": strong_hits, "theme_hits": theme_hits,
        "stages": stages, "chokepoint": choke,
        "review_status": "approved" if approved else "pending_review",
        "confidence": confidence,
    })
    return item


def build_event(mapping: dict, item: dict) -> dict:
    if item["stages"]:
        evidence_type = "commercial_stage"
    elif item["chokepoint"]:
        evidence_type = "business_presence"
    else:
        evidence_type = "business_presence"
    return {
        "event_id": _event_id(mapping["mapping_id"], item["source_type"], item["date"], item["title"]),
        "mapping_id": mapping["mapping_id"],
        "code": mapping["code"],
        "node_id": mapping["node_id"],
        "event_date": item["date"] or None,
        "source_type": item["source_type"],
        "source_id": f"near_memory_local_{item['source_type']}",
        "title": item["title"][:200],
        "excerpt": item["excerpt"][:400],
        "original_url": item["url"],
        "evidence_type": evidence_type,
        "impact_dimensions": json.dumps({
            "growth": bool(item["stages"]),
            "profit": False,
            "moat": bool(item["chokepoint"]),
            "risk": False,
            "research_stage": None,
            "commercial_stage": STAGE_TO_COMMERCIAL.get(item["stages"][0]) if item["stages"] else None,
            "tier": item["tier"],
            "strong_hits": item["strong_hits"][:6],
            "theme_hits": item["theme_hits"][:6],
        }, ensure_ascii=False),
        "confidence": item["confidence"],
        "review_status": item["review_status"],
        "review_note": "near_memory_chain_evidence 本地库关键词采集",
    }


# ── 阶段二A: LLM 结构化重评 (公告正文 + 互动问答) ──
LLM_REVIEWER = "near_memory_chain_evidence.py LLM重评审核"
LLM_REVIEW_NOTE = "近存计算链阶段二A: 公告正文/互动问答经 DeepSeek 结构化抽取, relevant+names_company+strong 级才置 approved"
MAX_LLM_CALLS = 300
MAX_ANN_PER_COMPANY = 10
MAX_PARAGRAPHS_PER_DOC = 5
MAX_QA_PER_COMPANY = 20
# 标题预筛: 业务关键词命中, 或定期报告/投关记录等内容型公告 (业务描述在正文里)
FULLTEXT_CONTENT_TITLE_KW = ["年度报告", "半年度报告", "投资者关系活动记录", "业绩说明会", "调研"]
FULLTEXT_TITLE_NOISE_KW = ["摘要", "英文", "已取消", "关于召开", "关于举行", "关于参加"]
# 恒烁股份 (688416) 特别约束: 存算一体证据必须明确提到 存算一体/存内计算/CIM,
# NOR 存储周期/涨价类证据不算 (预筛 + LLM prompt 双重把关)。
CIM_REQUIRED_KW = ["存算一体", "存内计算", "CIM", "存算"]
CIM_STRICT_CODES = {"688416"}

# 各 pending 公司映射的目标业务描述 (喂给 LLM 的 business_desc)
TARGET_BUSINESS: dict[str, str] = {
    "688416": "存算一体/存内计算(CIM)芯片，基于 NOR 闪存的存内计算架构（含底层存储介质支撑与相关研发任务）。"
              "注意：仅描述 NOR 存储周期、涨价、利基存储行情的内容不算证据，必须明确提到存算一体、存内计算或 CIM。",
    "301269": "3D IC / 先进封装 EDA 工具，面向 Chiplet、2.5D/3D 堆叠、HBM 封装的设计与仿真",
    "688012": "TSV 深硅刻蚀设备，用于 HBM、2.5D/3D 先进封装",
    "688733": "Low-α 球形氧化铝等先进封装填料，用于 HBM / 高端封装（低放射性、低介电封装材料）",
    "688206": "3D IC 仿真 EDA、先进封装建库与良率提升",
}

LLM_EVENT_CONFIDENCE = {"announcement_fulltext": 0.85, "irm_qa_llm": 0.80}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """pdftotext 优先 (host /opt/homebrew/bin/pdftotext), 缺则退回 pypdf."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(pdf_bytes)
        pdf_path = Path(f.name)
    txt_path = Path(str(pdf_path) + ".txt")
    try:
        proc = subprocess.run(
            ["pdftotext", str(pdf_path), str(txt_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if proc.returncode == 0 and txt_path.exists():
            return txt_path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        pass
    finally:
        pdf_path.unlink(missing_ok=True)
        txt_path.unlink(missing_ok=True)
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""


def extract_keyword_paragraphs(text: str, keywords: list[str], max_par: int = MAX_PARAGRAPHS_PER_DOC,
                               window: int = 280) -> list[str]:
    """以关键词命中点为中心截取窗口段落, 合并重叠窗口, 每篇最多 max_par 段."""
    if not text:
        return []
    up = text.upper()
    spans: list[tuple[int, int]] = []
    for kw in keywords:
        k = kw.upper()
        start = 0
        while True:
            i = up.find(k, start)
            if i < 0:
                break
            spans.append((max(0, i - window), min(len(text), i + len(k) + window)))
            start = i + len(k)
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    paragraphs: list[str] = []
    for s, e in merged:
        seg = re.sub(r"\s+", " ", text[s:e]).strip()
        if len(seg) >= 30:
            paragraphs.append(seg[:600])
        if len(paragraphs) >= max_par:
            break
    return paragraphs


def _fetch_pdf_text(session, pdf_url: str) -> str:
    resp = session.get(pdf_url, timeout=30)
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
        return ""
    return _extract_pdf_text(resp.content)


def _cninfo_search_announcements(session, code: str, page_size: int = 30) -> list[dict]:
    """巨潮 webapi 直接检索该公司 2024 至今公告 (本地 ts_raw_anns_d 收录稀疏时兜底).
    返回 [{date, title, pdf_url}]."""
    top = session.post(
        "http://www.cninfo.com.cn/new/information/topSearch/query",
        data={"keyWord": code, "maxNum": 10}, timeout=20,
    )
    org_id = ""
    for item in top.json() or []:
        if str(item.get("code")) == code:
            org_id = str(item.get("orgId") or "")
            break
    column = "sse" if code.startswith(("60", "68", "90")) else ("bj" if code.startswith(("4", "8")) else "szse")
    stock = f"{code},{org_id}" if org_id else code
    se_date = f"{START_DATE}~{date.today().strftime('%Y-%m-%d')}"
    rows: list[dict] = []
    for page in range(1, 13):  # 翻页扫 2024 至今公告 (单页 30 条, 最多 12 页)
        resp = session.post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data={
                "pageNum": page, "pageSize": page_size, "column": column, "tabName": "fulltext",
                "plate": "", "stock": stock, "searchkey": "", "secid": "", "category": "",
                "trade": "", "seDate": se_date, "sortName": "", "sortType": "", "isHLtitle": "false",
            },
            timeout=20,
        )
        anns = (resp.json() or {}).get("announcements") or []
        if not anns:
            break
        for ann in anns:
            adjunct = str(ann.get("adjunctUrl") or "").strip().lstrip("/")
            if not adjunct:
                continue
            title = re.sub(r"<[^>]+>", "", str(ann.get("announcementTitle") or ""))
            ts = ann.get("announcementTime")
            ann_date = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if isinstance(ts, (int, float)) else ""
            rows.append({"date": ann_date, "title": title,
                         "pdf_url": f"http://static.cninfo.com.cn/{adjunct}"})
    return rows


def collect_fulltext_candidates(session, code: str) -> list[dict]:
    """公告正文通道: 巨潮 webapi 检索标题含业务关键词或为定期报告/投关记录的内容型公告
    (<=10 条, 2024至今), 拉 PDF 正文截取关键词段落."""
    kws = COMPANY_KW.get(code, []) + THEME_KW
    try:
        anns = _cninfo_search_announcements(session, code)
    except Exception as e:
        print(f"    ⚠ 巨潮检索失败 [{code}]: {e.__class__.__name__}")
        return []
    candidates: list[dict] = []
    fetched = 0
    for ann in anns:
        if fetched >= MAX_ANN_PER_COMPANY:
            break
        title = ann["title"]
        if any(n in title for n in FULLTEXT_TITLE_NOISE_KW):
            continue
        if not hit_kw(title, kws) and not any(k in title for k in FULLTEXT_CONTENT_TITLE_KW):
            continue
        fetched += 1
        try:
            fulltext = _fetch_pdf_text(session, ann["pdf_url"])
        except Exception as e:
            print(f"    ⚠ 公告正文拉取失败 [{title[:40]}]: {e.__class__.__name__}")
            continue
        if not fulltext:
            print(f"    ⚠ 公告正文为空 [{title[:40]}]")
            continue
        for para in extract_keyword_paragraphs(fulltext, kws):
            candidates.append({
                "source_type": "announcement_fulltext",
                "date": ann["date"],
                "title": title,
                "text": para,
                "url": ann["pdf_url"],
            })
    return candidates


def collect_qa_candidates(cur, code: str) -> list[dict]:
    """互动问答证据段落: 命中业务关键词的问答对 (<=20 条)."""
    kws = COMPANY_KW.get(code, []) + THEME_KW
    cur.execute(
        """
        SELECT pub_date, question, answer FROM interact_qa
        WHERE code = %s AND pub_date >= %s
        ORDER BY pub_date DESC LIMIT 400
        """,
        (code, START_DATE),
    )
    candidates: list[dict] = []
    for r in cur.fetchall():
        q, a = str(r["question"] or ""), str(r["answer"] or "")
        text = re.sub(r"\s+", " ", f"问: {q} 答: {a}").strip()
        if not hit_kw(text, kws):
            continue
        candidates.append({
            "source_type": "irm_qa_llm",
            "date": _to_date_str(r["pub_date"]),
            "title": q[:80],
            "text": text[:600],
            "url": None,
        })
        if len(candidates) >= MAX_QA_PER_COMPANY:
            break
    return candidates


def build_llm_event(mapping: dict, para: dict, result: dict) -> dict:
    stage = result["stage"]
    return {
        "event_id": _event_id(mapping["mapping_id"], para["source_type"], para["date"],
                              para["title"] + "|" + para["text"][:40]),
        "mapping_id": mapping["mapping_id"],
        "code": mapping["code"],
        "node_id": mapping["node_id"],
        "event_date": para["date"] or None,
        "source_type": para["source_type"],
        "source_id": "near_memory_llm_review",
        "title": para["title"][:200],
        "excerpt": para["text"][:400],
        "original_url": para["url"],
        "evidence_type": "commercial_stage" if stage != "none" else "business_presence",
        "impact_dimensions": json.dumps({
            "growth": stage in {"small_batch", "mass_production", "order"},
            "profit": False,
            "moat": False,
            "risk": False,
            "research_stage": None,
            "commercial_stage": stage if stage != "none" else None,
            "tier": "strong",
            "llm_business": result["business"][:100],
            "llm_strength": result["strength"],
            "llm_reason": result["reason"][:100],
        }, ensure_ascii=False),
        "confidence": LLM_EVENT_CONFIDENCE[para["source_type"]],
        "review_status": "approved",
        "review_note": LLM_REVIEW_NOTE,
    }


def llm_review(args) -> int:
    """对 pending_review 映射跑 LLM 结构化重评. 默认 dry-run, --apply 写库."""
    sys.path.insert(0, str(PROJ / "services" / "screener-service"))
    from app.llm_evidence_extract import extract_evidence, is_confirmed_hit

    _load_dotenv(PROJ / "docker" / ".env.lark-bot")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("❌ 缺少 DEEPSEEK_API_KEY (docker/.env.lark-bot)")
        return 1

    import requests

    conn = psycopg2.connect(args.pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT m.mapping_id, m.code, m.node_id, m.tag_name, m.confidence, m.status,
               m.evidence_ids, s.name AS company_name
        FROM business_tag_mapping m
        LEFT JOIN stocks s ON s.code = split_part(m.code, '.', 1)
        WHERE m.chain_id = %s AND m.status = 'pending_review'
        ORDER BY m.code, m.node_id
        """,
        (CHAIN_ID,),
    )
    pendings = [dict(r) for r in cur.fetchall()]
    if not pendings:
        print("✅ 无 pending_review 映射, 无需重评")
        conn.close()
        return 0
    by_code: dict[str, list[dict]] = defaultdict(list)
    for m in pendings:
        by_code[m["code"]].append(m)
    print(f"pending_review 映射 {len(pendings)} 条, 涉及公司 {len(by_code)} 家, "
          f"apply={args.apply}, LLM 预算 {MAX_LLM_CALLS} 次\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/new/disclosure/detail",
    })

    llm_calls = 0
    events: list[dict] = []
    hits_by_mapping: dict[str, list[dict]] = defaultdict(list)
    seen_para: set[str] = set()

    for code, maps in sorted(by_code.items()):
        name = maps[0].get("company_name") or code
        business_desc = TARGET_BUSINESS.get(code)
        if not business_desc:
            print(f"  {code} {name}: 无目标业务描述, 跳过")
            continue
        fulltext = collect_fulltext_candidates(session, code)
        qa = collect_qa_candidates(cur, code)
        paras = fulltext + qa
        # 恒烁特别预筛: 必须明确提到 存算一体/存内计算/CIM
        if code in CIM_STRICT_CODES:
            before = len(paras)
            paras = [p for p in paras if any(k.upper() in p["text"].upper() for k in CIM_REQUIRED_KW)]
            print(f"  {code} {name}: CIM 预筛 {before} -> {len(paras)} 段")
        # 去重 (同标题+同段落)
        deduped: list[dict] = []
        for p in paras:
            key = hashlib.sha256((p["title"] + p["text"]).encode()).hexdigest()[:16]
            if key not in seen_para:
                seen_para.add(key)
                deduped.append(p)
        paras = deduped

        hit_count = excluded = skipped_budget = 0
        excluded_samples: list[str] = []
        for p in paras:
            if llm_calls >= MAX_LLM_CALLS:
                skipped_budget += 1
                continue
            llm_calls += 1
            result = extract_evidence(name, p["text"], business_desc)
            if is_confirmed_hit(result):
                hit_count += 1
                for m in maps:
                    ev = build_llm_event(m, p, result)
                    events.append(ev)
                    hits_by_mapping[m["mapping_id"]].append(ev)
                print(f"    ✓ 命中 [{p['source_type']}] {p['date']} {p['title'][:40]}")
                print(f"      business={result['business'][:60]} stage={result['stage']} reason={result['reason'][:40]}")
            else:
                excluded += 1
                summary = (f"{p['date']} {p['title'][:36]} :: "
                           + (f"relevant={result['relevant']} names={result['names_company']} "
                              f"strength={result['strength']} reason={result['reason'][:40]}"
                              if result else "LLM调用失败/解析失败"))
                excluded_samples.append(summary)
        print(f"  {code} {name}: 候选段落 {len(paras)} (正文 {len(fulltext)} / 问答 {len(qa)}), "
              f"命中 {hit_count}, 排除 {excluded}" + (f", 超预算跳过 {skipped_budget}" if skipped_budget else ""))
        for s in excluded_samples[:5]:
            print(f"    ✗ 排除 {s}")
        if len(excluded_samples) > 5:
            print(f"    … 其余 {len(excluded_samples) - 5} 条排除摘要略")

    print(f"\nLLM 调用合计 {llm_calls} 次 (预算 {MAX_LLM_CALLS})")
    print(f"新证据事件 {len(events)} 条, 可转正映射 {len(hits_by_mapping)} / {len(pendings)}")

    # ── 逐映射结论 ──
    verdicts: list[tuple[dict, list[dict], float]] = []
    for m in pendings:
        evs = hits_by_mapping.get(m["mapping_id"], [])
        if not evs:
            verdicts.append((m, [], 0.0))
            continue
        src_types = {ev["source_type"] for ev in evs}
        confidence = 0.85 if (len(evs) >= 3 or len(src_types) >= 2) else 0.80
        verdicts.append((m, evs, confidence))
    print("\n── 重评结论 ──")
    for m, evs, conf in verdicts:
        node = m["node_id"].replace("near_memory_computing_", "")
        if evs:
            print(f"  ✓ {m['code']} {m['company_name']} [{node}] -> verified, "
                  f"confidence={conf}, 证据 {len(evs)} 条")
        else:
            print(f"  · {m['code']} {m['company_name']} [{node}] 保持 pending_review (LLM 无 strong 命中)")

    if not args.apply:
        print("\ndry-run: 未写库, 加 --apply 落库")
        conn.close()
        return 0

    # ── 写库: GUC 'manual' 审核惯例 ──
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
        ev["reviewer"] = LLM_REVIEWER
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
            (conf, json.dumps(evidence_ids, ensure_ascii=False), m["mapping_id"], CHAIN_ID),
        )
    conn.commit()
    print(f"\n── 写库完成: 新事件 {inserted} 条, 转正 {len(hits_by_mapping)} 条映射 (reviewer='{LLM_REVIEWER}') ──")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="近存计算链证据采集 + 映射保守转正")
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--dry-run", action="store_true", help="只检索打印, 不写库")
    parser.add_argument("--llm-review", action="store_true", help="阶段二A: 对 pending_review 映射跑 LLM 重评")
    parser.add_argument("--apply", action="store_true", help="配合 --llm-review 写库 (默认 dry-run)")
    args = parser.parse_args()

    if args.llm_review:
        return llm_review(args)

    conn = psycopg2.connect(args.pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT m.mapping_id, m.code, m.node_id, m.tag_name, m.confidence, m.status,
               s.name AS company_name
        FROM business_tag_mapping m
        LEFT JOIN stocks s ON s.code = split_part(m.code, '.', 1)
        WHERE m.chain_id = %s
        ORDER BY m.code, m.node_id
        """,
        (CHAIN_ID,),
    )
    mappings = [dict(r) for r in cur.fetchall()]
    if not mappings:
        print("❌ 未找到 near_memory_computing 映射"); return 1
    companies: dict[str, str] = {}
    for m in mappings:
        companies[m["code"]] = m.get("company_name") or ""
    print(f"映射 {len(mappings)} 条, 公司 {len(companies)} 家, dry_run={args.dry_run}\n")

    # ── 采集 + 过滤 ──
    company_items: dict[str, list[dict]] = {}
    raw_counts: dict[str, dict[str, int]] = {}
    for code, name in sorted(companies.items()):
        raw = collect_company(cur, code, name)
        kept = [x for x in (classify(code, it) for it in raw) if x]
        company_items[code] = kept
        src_stat = defaultdict(lambda: [0, 0])
        for it in raw:
            src_stat[it["source_type"]][0] += 1
        for it in kept:
            src_stat[it["source_type"]][1] += 1
        raw_counts[code] = {k: tuple(v) for k, v in src_stat.items()}
        print(f"  {code} {name or '?'}: 命中 {len(kept)} 条 "
              f"(strong {sum(1 for i in kept if i['tier']=='strong')}, "
              f"approved {sum(1 for i in kept if i['review_status']=='approved')})")

    # ── 事件挂到该公司的每条 mapping, 每 (mapping, source) 限量, strong 优先 ──
    events: list[dict] = []
    per_mapping: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        items = company_items.get(m["code"], [])
        by_src: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            by_src[it["source_type"]].append(it)
        picked: list[dict] = []
        for src, arr in by_src.items():
            arr.sort(key=lambda x: (x["tier"] != "strong", -(int(x["date"].replace("-", "") or 0))))
            picked.extend(arr[:MAX_EVENTS_PER_MAPPING_SOURCE])
        for it in picked:
            ev = build_event(m, it)
            events.append(ev)
            per_mapping[m["mapping_id"]].append((ev, it))

    approved_by_mapping = {
        mid: [ev for ev, _ in pairs if ev["review_status"] == "approved"]
        for mid, pairs in per_mapping.items()
    }
    promotable = {mid: evs for mid, evs in approved_by_mapping.items() if evs}
    print(f"\n事件合计 {len(events)} 条 (approved {sum(len(v) for v in approved_by_mapping.values())})")
    print(f"可转正 mapping: {len(promotable)} / {len(mappings)}")

    if args.dry_run:
        print("\n── dry-run: 可转正明细 ──")
        for m in mappings:
            evs = promotable.get(m["mapping_id"])
            if not evs:
                continue
            top = evs[0]
            print(f"  {m['code']} {m['company_name']} [{m['node_id']}] approved={len(evs)}")
            print(f"     例: {top['event_date']} {top['source_type']} {top['title'][:70]}")
        conn.close()
        return 0

    # ── 写库 ──
    # migration 033 审核门: approved 行必须在显式 manual 审核事务中写入
    cur.execute("SET app.supply_chain_review_action = 'manual'")
    mapping_ids = [m["mapping_id"] for m in mappings]
    cur.execute("SELECT count(*) FROM business_tag_evidence_events WHERE event_id LIKE 'NMC-EV-%'")
    before_events = cur.fetchone()["count"]
    cur.execute("DELETE FROM business_tag_evidence_events WHERE event_id LIKE 'NMC-EV-%'")
    deleted_events = cur.rowcount

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
    for ev in events:
        if ev["review_status"] == "approved":
            ev["reviewer"] = REVIEWER
            ev["review_note"] = REVIEW_NOTE
            ev["reviewed_at"] = datetime.now()
        else:
            ev["reviewer"] = None
            ev["reviewed_at"] = None
        cur.execute(insert_sql, ev)

    # stage_tracking: 有证据的 mapping 各写一行
    cur.execute("DELETE FROM business_tag_stage_tracking WHERE stage_id LIKE 'NMC-ST-%'")
    deleted_stage = cur.rowcount
    cur.execute("SELECT max(trade_date) FROM daily_kline")
    trade_date = _to_date_str(cur.fetchone()["max"])
    stage_rows = 0
    for m in mappings:
        pairs = per_mapping.get(m["mapping_id"])
        if not pairs:
            continue
        texts = [it["title"] + " " + it["excerpt"] for _, it in pairs]
        c_stage = best_commercial_stage(texts)
        r_stage = best_research_stage(texts)
        approved = approved_by_mapping.get(m["mapping_id"], [])
        stage_id = "NMC-ST-" + hashlib.sha256(f"{m['mapping_id']}|{trade_date}".encode()).hexdigest()[:20]
        top_reason = (approved[0]["title"] if approved else pairs[0][0]["title"])[:150]
        cur.execute(
            """
            INSERT INTO business_tag_stage_tracking (
                stage_id, mapping_id, trade_date, research_stage,
                commercialization_stage, stage_reason, source_event_id,
                last_stage_change_date, review_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stage_id) DO NOTHING
            """,
            (stage_id, m["mapping_id"], trade_date, r_stage, c_stage,
             f"near_memory 证据关键词推断: {top_reason}",
             (approved[0]["event_id"] if approved else pairs[0][0]["event_id"]),
             trade_date, "approved" if approved else "pending_review"),
        )
        stage_rows += 1

    # 映射转正: 仅 approved >= 1 的 mapping; 其余不动
    promoted = []
    for m in mappings:
        evs = promotable.get(m["mapping_id"])
        if not evs:
            continue
        src_types = {ev["source_type"] for ev in evs}
        confidence = 0.85 if (len(evs) >= 3 or len(src_types) >= 2) else 0.80
        evidence_ids = [ev["event_id"] for ev in evs[:50]]
        cur.execute(
            """
            UPDATE business_tag_mapping
            SET status = 'verified', confidence = %s,
                evidence_ids = %s::jsonb, updated_at = CURRENT_TIMESTAMP
            WHERE mapping_id = %s AND chain_id = %s
            """,
            (confidence, json.dumps(evidence_ids, ensure_ascii=False), m["mapping_id"], CHAIN_ID),
        )
        promoted.append((m, len(evs), confidence))

    conn.commit()

    print(f"\n── 写库完成 ──")
    print(f"  事件: 删除旧 NMC-EV {deleted_events}, 新写入 {len(events)} (写前存量 {before_events})")
    print(f"  stage_tracking: 删除旧 NMC-ST {deleted_stage}, 新写入 {stage_rows}")
    print(f"  转正 mapping: {len(promoted)}")
    for m, n, conf in promoted:
        print(f"    ✓ {m['code']} {m['company_name']} [{m['node_id'].replace('near_memory_computing_', '')}] "
              f"approved={n} confidence={conf}")
    remain = [m for m in mappings if m["mapping_id"] not in promotable]
    print(f"  保持 pending_review: {len(remain)}")
    for m in remain:
        n = len(per_mapping.get(m["mapping_id"], []))
        print(f"    · {m['code']} {m['company_name']} [{m['node_id'].replace('near_memory_computing_', '')}] "
              f"(非approved证据 {n} 条)")

    # 导出证据 CSV 供人工抽查
    import csv
    out = PROJ / "outputs" / f"near_memory_chain_evidence_{date.today().strftime('%Y%m%d')}.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["mapping_id", "code", "node_id", "source_type", "date", "tier",
                    "review_status", "confidence", "stages", "chokepoint", "title", "excerpt"])
        for m in mappings:
            for ev, it in per_mapping.get(m["mapping_id"], []):
                w.writerow([m["mapping_id"], m["code"], m["node_id"], ev["source_type"], ev["event_date"],
                            it["tier"], ev["review_status"], ev["confidence"],
                            "|".join(it["stages"]), "|".join(it["chokepoint"][:3]),
                            ev["title"], ev["excerpt"][:200]])
    print(f"  证据 CSV: {out}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
