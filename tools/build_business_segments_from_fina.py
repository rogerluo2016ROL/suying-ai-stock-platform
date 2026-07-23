#!/usr/bin/env python3
"""从 fina_mainbz 主营构成生成/更新 company_business_segments,并回填
business_tag_mapping 的 revenue_ratio / gross_profit_ratio。

默认 dry-run(只打印覆盖率前后对比与匹配样例),--apply 才写库。

口径说明(重要):
- fina_mainbz.biz_ratio 当前全量为 NULL(2026-07 核验 61232 行 count(biz_ratio)=0),
  收入占比改用 biz_income / sum(biz_income)(同 code+end_date+biz_type 组内)计算;
  已抽查验证组内合计等于公司当期总营收(如 000063 的 P/I/D 三组合计一致)。
- 分部行优先取 biz_type='P'(按产品);该公司最新报告期无 P 行时回退 'I'(按行业);
  'D'(按地区)不参与业务匹配(地区名与业务标签无语义对应)。
- gross_profit_ratio = financial_indicator 最新 gross_margin/100 * revenue_ratio,
  即"以公司整体毛利率近似该业务毛利贡献占总营收的比例"。fina_mainbz 无分部毛利
  字段,这不是分部毛利率,仅供评分相对比较,口径在此注明。
- 匹配规则保守:tag 核心词(取最后一个"："之后、去 业务/产品 等后缀)与 biz_item
  核心词双向包含,或共享 ≥2 字且非通用词的最长公共子串;匹配不到保持 NULL 不动。
- 幂等:company_business_segments 以 segment_id(内容 hash)upsert;
  business_tag_mapping 只更新仍为 NULL 的目标字段,不覆盖已有值。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get(
    "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"
)

# 无业务语义的 biz_item(其他/地区/合计类),不参与匹配
NOISE_ITEMS = {
    "其他", "其他业务", "其他主营业务", "其他主营", "其他收入", "其他业务收入",
    "合计", "总计", "销售收入", "中国大陆", "国内", "国外", "境外", "内销", "外销",
    "抵消", "内部抵消", "租赁收入", "服务费收入", "废料",
}
# 共享子串规则下的通用词:仅靠它们共现不算匹配(保守,宁缺毋滥)
GENERIC_TOKENS = {
    "业务", "产品", "收入", "服务", "其他", "主营", "销售", "制造", "技术",
    "科技", "电子", "公司", "股份", "有限", "集团", "设备", "材料", "工程",
    "建设", "信息", "智能", "能源", "实业", "发展", "控股", "贸易",
}
# tag/biz_item 尾部通用后缀,剥离后再比较
_SUFFIXES = ("业务", "产品", "板块", "收入", "服务", "分部")


def normalize_text(text: Any) -> str:
    """小写 + 去空白去标点(仅保留字母/数字/CJK)。"""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _strip_suffixes(text: str) -> str:
    changed = True
    while changed:
        changed = False
        for suffix in _SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                text = text[: -len(suffix)]
                changed = True
    return text


def tag_core(tag_name: Any) -> str:
    """tag_name 核心词:取最后一个'：'之后(剥离'候选：公司业务标签：'类前缀),再去通用后缀。"""
    text = str(tag_name or "").strip()
    for sep in ("：", ":"):
        if sep in text:
            text = text.rsplit(sep, 1)[-1]
    return _strip_suffixes(normalize_text(text))


def item_core(biz_item: Any) -> str:
    """biz_item 核心词:去括号附注与通用后缀。"""
    text = str(biz_item or "").strip()
    for ch in ("(", "（"):
        if ch in text:
            text = text.split(ch, 1)[0]
    return _strip_suffixes(normalize_text(text))


def longest_common_substring(a: str, b: str) -> str:
    """经典 DP,返回 a/b 的最长公共子串(短的在前优先)。"""
    if not a or not b:
        return ""
    best = ""
    prev = [0] * (len(b) + 1)
    for i, ca in enumerate(a, 1):
        curr = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                curr[j] = prev[j - 1] + 1
                if curr[j] > len(best):
                    best = a[i - curr[j]:i]
        prev = curr
    return best


def match_segment(tag_name: Any, segments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """在该公司分部列表中为 tag 找最佳分部;匹配不到返回 None(保守)。

    规则:核心词双向包含 > 共享 ≥2 字非通用词最长公共子串;
    同分按 biz_income 高者优先,结果确定性排序。
    """
    core_tag = tag_core(tag_name)
    if len(core_tag) < 2:
        return None
    best: tuple | None = None
    best_seg: dict[str, Any] | None = None
    for seg in segments:
        core_item = item_core(seg.get("biz_item"))
        if len(core_item) < 2 or core_item in NOISE_ITEMS:
            continue
        score = 0
        if core_item in core_tag or core_tag in core_item:
            score = 100 + min(len(core_item), len(core_tag))
        else:
            common = longest_common_substring(core_tag, core_item)
            if len(common) >= 2 and common not in GENERIC_TOKENS:
                score = len(common)
        if not score:
            continue
        cand = (score, float(seg.get("biz_income") or 0.0), str(seg.get("biz_item") or ""))
        if best is None or cand > best:
            best = cand
            best_seg = seg
    return best_seg


def build_segments_from_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """fina_mainbz 行 → {code: 最新报告期分部列表(含计算出的 revenue_ratio)}。

    每 code 取最新 end_date,优先 biz_type='P',无 P 回退 'I';
    revenue_ratio = biz_income / 同组 biz_income 合计。
    """
    by_code: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_code.setdefault(str(row["code"]), []).append(row)
    result: dict[str, list[dict[str, Any]]] = {}
    for code, items in by_code.items():
        latest = max(str(item["end_date"]) for item in items)
        period_rows = [item for item in items if str(item["end_date"]) == latest]
        picked = [item for item in period_rows if item.get("biz_type") == "P"]
        biz_type = "P"
        if not picked:
            picked = [item for item in period_rows if item.get("biz_type") == "I"]
            biz_type = "I"
        if not picked:
            continue
        total = sum(float(item.get("biz_income") or 0.0) for item in picked)
        segments = []
        for item in picked:
            income = float(item.get("biz_income") or 0.0)
            ratio = round(income / total, 6) if total > 0 else None
            segments.append({
                "code": code,
                "end_date": latest,
                "biz_item": str(item.get("biz_item") or ""),
                "biz_income": income,
                "biz_type": biz_type,
                "revenue_ratio": ratio,
                "segment_id": segment_id_for(code, latest, str(item.get("biz_item") or "")),
            })
        result[code] = segments
    return result


def segment_id_for(code: str, end_date: str, biz_item: str) -> str:
    payload = f"{code}|{end_date}|{biz_item}"
    return "FSEG-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def coverage_snapshot(cur) -> dict[str, int]:
    cur.execute(
        """
        SELECT count(*) AS total, count(revenue_ratio) AS rev,
               count(gross_profit_ratio) AS gross
        FROM business_tag_mapping
        """
    )
    row = cur.fetchone()
    cur.execute("SELECT count(*) AS n FROM company_business_segments")
    segments = cur.fetchone()["n"]
    return {"total": row["total"], "revenue_ratio": row["rev"], "gross_profit_ratio": row["gross"],
            "company_business_segments": segments}


def _print_coverage(label: str, snap: dict[str, int]) -> None:
    total = snap["total"] or 1
    print(
        f"[{label}] business_tag_mapping total={snap['total']} "
        f"revenue_ratio 非空={snap['revenue_ratio']} ({snap['revenue_ratio'] / total:.1%}) "
        f"gross_profit_ratio 非空={snap['gross_profit_ratio']} ({snap['gross_profit_ratio'] / total:.1%}) "
        f"company_business_segments={snap['company_business_segments']}"
    )


def run(pg_url: str, apply: bool = False) -> dict[str, Any]:
    import psycopg2
    import psycopg2.extras

    stats: dict[str, Any] = {"apply": apply}
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            before = coverage_snapshot(cur)
            _print_coverage("before", before)
            stats["before"] = before

            cur.execute(
                "SELECT code, end_date, biz_item, biz_income, biz_type FROM fina_mainbz"
            )
            fina_rows = [dict(row) for row in cur.fetchall()]
            segments_by_code = build_segments_from_rows(fina_rows)
            all_segments = [seg for segs in segments_by_code.values() for seg in segs]
            stats["segments_built"] = len(all_segments)
            stats["codes_with_segments"] = len(segments_by_code)

            cur.execute(
                """
                SELECT DISTINCT ON (code) code, gross_margin
                FROM financial_indicator
                WHERE gross_margin IS NOT NULL
                ORDER BY code, end_date DESC
                """
            )
            gross_margin = {
                str(row["code"]): float(row["gross_margin"]) for row in cur.fetchall()
            }

            cur.execute(
                """
                SELECT mapping_id, code, tag_name, revenue_ratio, gross_profit_ratio
                FROM business_tag_mapping
                """
            )
            mappings = [dict(row) for row in cur.fetchall()]

            updates: list[dict[str, Any]] = []
            matched = unmatched = gross_only = 0
            for mapping in mappings:
                code = str(mapping["code"])
                margin = gross_margin.get(code)
                rev_ratio = mapping.get("revenue_ratio")
                new_rev = None
                segment = None
                if rev_ratio is None:
                    segment = match_segment(mapping.get("tag_name"), segments_by_code.get(code, []))
                    if segment is None or segment.get("revenue_ratio") is None:
                        unmatched += 1
                    else:
                        matched += 1
                        new_rev = round(float(segment["revenue_ratio"]), 6)
                        rev_ratio = new_rev
                new_gross = None
                if mapping.get("gross_profit_ratio") is None and rev_ratio is not None and margin is not None:
                    # 口径:公司整体毛利率 × 业务收入占比 ≈ 该业务毛利贡献占总营收比例
                    new_gross = round(margin / 100.0 * float(rev_ratio), 6)
                    if new_rev is None:
                        gross_only += 1
                if new_rev is not None or new_gross is not None:
                    updates.append({
                        "mapping_id": mapping["mapping_id"],
                        "revenue_ratio": new_rev,
                        "gross_profit_ratio": new_gross,
                        "business_segment_id": segment["segment_id"] if segment else None,
                    })
            stats["matched"] = matched
            stats["unmatched"] = unmatched
            stats["gross_only_backfill"] = gross_only
            stats["mapping_updates"] = len(updates)

            if apply:
                cur.executemany(
                    """
                    INSERT INTO company_business_segments (
                        segment_id, code, segment_name, report_period, revenue,
                        revenue_ratio, source_table, source_row_id,
                        evidence_status, metadata
                    )
                    VALUES (
                        %(segment_id)s, %(code)s, %(biz_item)s, %(end_date)s,
                        %(biz_income)s, %(revenue_ratio)s, 'fina_mainbz',
                        %(source_row_id)s, 'pending_review', %(metadata)s::jsonb
                    )
                    ON CONFLICT (segment_id) DO UPDATE SET
                        report_period = EXCLUDED.report_period,
                        revenue = EXCLUDED.revenue,
                        revenue_ratio = EXCLUDED.revenue_ratio,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    [
                        {
                            **seg,
                            "source_row_id": f"{seg['code']}:{seg['end_date']}:{seg['biz_item']}",
                            "metadata": json.dumps(
                                {"biz_type": seg["biz_type"],
                                 "generator": "build_business_segments_from_fina"},
                                ensure_ascii=False,
                            ),
                        }
                        for seg in all_segments
                    ],
                )
                cur.executemany(
                    """
                    UPDATE business_tag_mapping
                    SET revenue_ratio = coalesce(revenue_ratio, %(revenue_ratio)s),
                        gross_profit_ratio = coalesce(gross_profit_ratio, %(gross_profit_ratio)s),
                        business_segment_id = coalesce(business_segment_id, %(business_segment_id)s),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE mapping_id = %(mapping_id)s
                    """,
                    updates,
                )
                conn.commit()

            after = dict(before)
            after["revenue_ratio"] = before["revenue_ratio"] + sum(
                1 for u in updates if u["revenue_ratio"] is not None
            )
            after["gross_profit_ratio"] = before["gross_profit_ratio"] + sum(
                1 for u in updates if u["gross_profit_ratio"] is not None
            )
            after["company_business_segments"] = (
                before["company_business_segments"] + len(all_segments)
                if apply else before["company_business_segments"]
            )
            _print_coverage("after(projected)" if not apply else "after", after)
            stats["after"] = after

            samples = [u["mapping_id"] for u in updates[:10]]
            if samples:
                cur.execute(
                    """
                    SELECT mapping_id, code, tag_name, revenue_ratio, gross_profit_ratio
                    FROM business_tag_mapping WHERE mapping_id = ANY(%s)
                    """,
                    (samples,),
                )
                if apply:
                    stats["samples"] = [dict(row) for row in cur.fetchall()]
            if not apply:
                stats["samples"] = [
                    {
                        "mapping_id": u["mapping_id"],
                        "revenue_ratio": u["revenue_ratio"],
                        "gross_profit_ratio": u["gross_profit_ratio"],
                    }
                    for u in updates[:10]
                ]
    print(json.dumps({k: v for k, v in stats.items() if k not in {"samples"}},
                     ensure_ascii=False, indent=1, default=str))
    for sample in stats.get("samples", []):
        print("sample:", json.dumps(sample, ensure_ascii=False, default=str))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--apply", action="store_true", help="实际写库(默认 dry-run)")
    args = parser.parse_args()
    run(args.pg_url, apply=args.apply)


if __name__ == "__main__":
    main()
