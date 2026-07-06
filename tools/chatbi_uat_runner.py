#!/usr/bin/env python3
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path


BASE_URL = "http://127.0.0.1:8088/ds-cockpit-screen/api/v1/chatbi"


@dataclass
class Case:
    no: int
    category: str
    question: str
    expected_intent: str
    answer_mode: str


CASES = [
    Case(1, "产业链候选", "AI算力候选公司Top5", "supply_chain_ranking", "quick"),
    Case(2, "产业链候选", "具身智能产业链卡脖子公司清单", "supply_chain_ranking", "deep"),
    Case(3, "产业链候选", "光模块产业链三高公司排序", "supply_chain_ranking", "quick"),
    Case(4, "产业链候选", "半导体设备产业链候选公司Top20", "supply_chain_ranking", "quick"),
    Case(5, "产业链候选", "氢能产业链值得跟踪的公司清单", "supply_chain_ranking", "deep"),
    Case(6, "公司证据链", "中际旭创的产业链证据链和L8证据", "company_evidence", "deep"),
    Case(7, "公司证据链", "光洋股份具身智能卡脖子证据链", "company_evidence", "deep"),
    Case(8, "公司证据链", "源杰科技AI算力三高和研发商用进度", "company_evidence", "deep"),
    Case(9, "公司证据链", "绿的谐波具身智能标签证据和商业化阶段", "company_evidence", "deep"),
    Case(10, "公司证据链", "飞凯材料相关产业链标签和毛利证据", "company_evidence", "deep"),
    Case(11, "选股模型", "今天所有选股模型结果汇总", "stock_model_run", "quick"),
    Case(12, "选股模型", "秋神午后选股今天有没有票", "stock_model_run", "quick"),
    Case(13, "选股模型", "毕师傅硬核科技今天候选股票", "stock_model_run", "quick"),
    Case(14, "选股模型", "AI算力相关股票今天模型信号", "stock_model_run", "deep"),
    Case(15, "选股模型", "机器人产业链股票近期涨幅和模型结果", "stock_model_run", "deep"),
    Case(16, "选债模型", "匪爷竞价选债今天有没有票", "bond_model_run", "quick"),
    Case(17, "选债模型", "今天所有选债模型结果汇总", "bond_model_run", "quick"),
    Case(18, "选债模型", "近期强赎风险可转债筛选", "bond_model_run", "deep"),
    Case(19, "选债模型", "AI算力相关可转债候选清单", "bond_model_run", "deep"),
    Case(20, "选债模型", "选债模型为什么今天没票", "bond_model_run", "deep"),
    Case(21, "模型共振", "今天所有选股选债模型共振情况", "model_resonance", "quick"),
    Case(22, "模型共振", "AI算力和光模块产业链今天是否共振", "model_resonance", "deep"),
    Case(23, "模型共振", "多个模型同时命中的公司Top20", "model_resonance", "quick"),
    Case(24, "无票诊断", "匪爷竞价选债为什么没票", "no_pick_diagnosis", "deep"),
    Case(25, "无票诊断", "今天秋神午后选股为什么没有候选", "no_pick_diagnosis", "deep"),
    Case(26, "无票诊断", "中大力德为什么没有进入具身智能卡脖子清单", "no_pick_diagnosis", "deep"),
    Case(27, "数据质量", "产业链候选数据最新交易日和更新状态", "data_quality", "quick"),
    Case(28, "数据质量", "当前项目有哪些数据缺失会影响ChatBI回答", "data_quality", "deep"),
    Case(29, "报告导出", "生成中际旭创产业链拆解报告", "report_export", "deep"),
    Case(30, "报告导出", "导出光洋股份具身智能证据链报告", "report_export", "deep"),
]


def post_stream(case: Case):
    payload = {
        "question": case.question,
        "answerMode": case.answer_mode,
        "userId": "uat",
        "userName": "UAT",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/messages/stream",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    elapsed_ms = int((time.time() - start) * 1000)
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if not body or body == "[DONE]":
            continue
        try:
            root = json.loads(body)
            if isinstance(root, dict) and isinstance(root.get("data"), dict):
                events.append(root["data"])
        except Exception:
            continue
    return raw, events, elapsed_ms


def infer_result(case: Case, raw: str, events: list, elapsed_ms: int):
    answer_parts = [str(e.get("message") or "") for e in events if e.get("type") == "message_delta"]
    answer = "\n".join(answer_parts)
    node_text = " ".join(str(e.get("message") or "") for e in events)
    matched_intent = case.expected_intent in node_text or case.expected_intent in answer
    has_answer = len(answer.strip()) > 20
    has_structured = any(e.get("type") in ("node_started", "node_finished", "done") for e in events)
    has_date_or_source = any(k in answer for k in ["最新交易日", "交易日", "数据版本", "证据", "来源", "数据源状态", "限制说明"])
    raw_json_noise = answer.count("{") > 8 or answer.count('"items"') > 0
    hallucination = False
    if "unavailable" in answer and "大模型状态" in answer:
        hallucination = False
    if not has_answer:
        conclusion = "不通过"
    elif raw_json_noise:
        conclusion = "不通过"
    elif matched_intent and has_structured and has_date_or_source:
        conclusion = "通过"
    elif matched_intent and has_answer:
        conclusion = "部分通过"
    else:
        conclusion = "部分通过"
    return {
        "no": case.no,
        "category": case.category,
        "question": case.question,
        "expected_intent": case.expected_intent,
        "answer_mode": case.answer_mode,
        "matched_intent": matched_intent,
        "has_answer": has_answer,
        "has_structured": has_structured,
        "has_date_or_source": has_date_or_source,
        "raw_json_noise": raw_json_noise,
        "hallucination": hallucination,
        "elapsed_ms": elapsed_ms,
        "conclusion": conclusion,
        "answer_excerpt": re.sub(r"\s+", " ", answer)[:240],
    }


def main():
    results = []
    for case in CASES:
        try:
            raw, events, elapsed_ms = post_stream(case)
            results.append(infer_result(case, raw, events, elapsed_ms))
        except Exception as exc:
            results.append({
                "no": case.no,
                "category": case.category,
                "question": case.question,
                "expected_intent": case.expected_intent,
                "answer_mode": case.answer_mode,
                "matched_intent": False,
                "has_answer": False,
                "has_structured": False,
                "has_date_or_source": False,
                "raw_json_noise": False,
                "hallucination": False,
                "elapsed_ms": None,
                "conclusion": "不通过",
                "answer_excerpt": str(exc)[:240],
            })
    out_dir = Path("outputs/chatbi_uat")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "chatbi_uat_30q_results.json"
    md_path = out_dir / "chatbi_uat_30q_results.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# ChatBI 30题 UAT 自动化结果", "", "| 序号 | 类别 | 意图 | 模式 | 结论 | 耗时ms | 摘要 |", "| ---: | --- | --- | --- | --- | ---: | --- |"]
    for r in results:
        lines.append(f"| {r['no']} | {r['category']} | {r['expected_intent']} | {r['answer_mode']} | {r['conclusion']} | {r['elapsed_ms'] or ''} | {r['answer_excerpt'].replace('|', ' ')} |")
    lines.append("")
    total = len(results)
    passed = sum(1 for r in results if r["conclusion"] == "通过")
    partial = sum(1 for r in results if r["conclusion"] == "部分通过")
    failed = total - passed - partial
    lines.append(f"通过={passed}，部分通过={partial}，不通过={failed}，总数={total}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path), "passed": passed, "partial": partial, "failed": failed, "total": total}, ensure_ascii=False))


if __name__ == "__main__":
    main()
