#!/usr/bin/env python3
"""agf-spec-archive.py — 把一个 change 的 delta merge 进活规格 + 归档（ADR-012 决策 3）。

UAT 业务签字后由 product-lead 跑。对 <changes-root>/<change>/specs/*.md 每个 delta，
按 **RENAMED → REMOVED → MODIFIED → ADDED** 顺序 apply 到 <specs-root>/<cap>/spec.md
（不存在则建），再把 <changes-root>/<change>/ 移到 <changes-root>/archive/<date>-<change>/。

确定性：日期由参数传入（不取 now），可单测。纯 Python 标准库，无第三方依赖。

**SSOT 护栏（v6.9.0 评审加固）**：先 **pre-flight**（解析 + 在副本上 apply、收集 warnings，零写盘）；
任何异常（名称失配 / 重名 Requirement / MODIFIED 退化为 ADDED 等）→ **非零退出、不写、不归档**，
提示先 `--dry-run` 检查；确认无误用 `--force` 放行。活规格是「永远反映现状」SSOT，
宁可拒绝归档也不静默污染。解析采用「段模型」正确处理 Requirement 与中间 `##` 小节交错。

用法:
  python3 agf-spec-archive.py <change> <YYYY-MM-DD>
          [--specs-root docs/specs] [--changes-root docs/changes] [--dry-run] [--force]

通常经薄包装调用: bash .claude/scripts/agf-spec-archive.sh <change> <YYYY-MM-DD>
"""
import argparse
import copy
import os
import re
import shutil
import sys

REQ_RE = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
SECTION_RE = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\s*$")
RENAME_RE = re.compile(r"^\s*-?\s*(FROM|TO):\s*`?(?:###\s+Requirement:\s*)?(.+?)`?\s*$")


def norm(name):
    return re.sub(r"\s+", " ", name.strip())


def _is_boundary(line):
    return line.startswith("### ") or line.startswith("## ") or line.startswith("# ")


def _rename_header(line, to):
    # 函数式替换：绝不把 to 当 re.sub 替换模板（防反斜杠崩溃 / \n 注入劈裂标题）。
    return re.sub(r"^(###\s+Requirement:\s*).+$", lambda m: m.group(1) + to, line)


def parse_spec(text):
    """活规格 → 有序段列表，正确处理 Requirement 与中间 `##` 小节交错（段模型）。

    每段: {'type':'req','name':..,'lines':[..]} 或 {'type':'other','lines':[..]}（逐字 passthrough）。
    """
    lines = text.split("\n")
    n = len(lines)
    i = 0
    segs = []
    other = []

    def flush_other():
        if other:
            segs.append({"type": "other", "lines": list(other)})
            other.clear()

    while i < n:
        m = REQ_RE.match(lines[i])
        if m:
            flush_other()
            name = norm(m.group(1))
            block = [lines[i]]
            i += 1
            while i < n and not _is_boundary(lines[i]):
                block.append(lines[i])
                i += 1
            while block and block[-1].strip() == "":
                block.pop()
            segs.append({"type": "req", "name": name, "lines": block})
        else:
            other.append(lines[i])
            i += 1
    flush_other()
    return segs


def parse_delta(text):
    """delta → {'ADDED':[[name,block]], 'MODIFIED':[[name,block]], 'REMOVED':[name], 'RENAMED':[(from,to)]}."""
    lines = text.split("\n")
    n = len(lines)
    out = {"ADDED": [], "MODIFIED": [], "REMOVED": [], "RENAMED": []}
    i = 0
    section = None
    pending_from = None
    while i < n:
        sm = SECTION_RE.match(lines[i])
        if sm:
            section = sm.group(1)
            pending_from = None
            i += 1
            continue
        if section in ("ADDED", "MODIFIED", "REMOVED") and REQ_RE.match(lines[i]):
            name = norm(REQ_RE.match(lines[i]).group(1))
            block = [lines[i]]
            i += 1
            while i < n and not _is_boundary(lines[i]):
                block.append(lines[i])
                i += 1
            while block and block[-1].strip() == "":
                block.pop()
            if section == "REMOVED":
                out["REMOVED"].append(name)
            else:
                out[section].append([name, block])
            continue
        if section == "RENAMED":
            rm = RENAME_RE.match(lines[i])
            if rm:
                if rm.group(1) == "FROM":
                    pending_from = norm(rm.group(2))
                elif rm.group(1) == "TO" and pending_from is not None:
                    out["RENAMED"].append((pending_from, norm(rm.group(2))))
                    pending_from = None
        i += 1
    return out


def _append_req(segs, nm, block):
    last = -1
    for k, s in enumerate(segs):
        if s["type"] == "req":
            last = k
    pos = last + 1 if last >= 0 else len(segs)
    segs.insert(pos, {"type": "req", "name": norm(nm), "lines": list(block)})


def apply_delta(segs, delta):
    """原地 apply 到 segs（段模型），返回 warnings。顺序 RENAMED→REMOVED→MODIFIED→ADDED。"""
    warnings = []

    def find(nm):
        nm = norm(nm)
        hits = [k for k, s in enumerate(segs) if s["type"] == "req" and s["name"] == nm]
        if len(hits) > 1:
            warnings.append(f"活规格存在 {len(hits)} 个同名 Requirement '{nm}'，只改首个（活规格应去重）")
        return hits[0] if hits else -1

    for frm, to in delta["RENAMED"]:
        k = find(frm)
        if k < 0:
            warnings.append(f"RENAMED: 活规格找不到 '{frm}'，跳过")
            continue
        segs[k]["lines"][0] = _rename_header(segs[k]["lines"][0], to)
        segs[k]["name"] = norm(to)

    for nm in delta["REMOVED"]:
        k = find(nm)
        if k < 0:
            warnings.append(f"REMOVED: 活规格找不到 '{nm}'，跳过")
            continue
        segs.pop(k)

    for nm, block in delta["MODIFIED"]:
        k = find(nm)
        if k < 0:
            warnings.append(f"MODIFIED: 活规格找不到 '{nm}'，按 ADDED 追加（疑似 header 漂移）")
            _append_req(segs, nm, block)
            continue
        segs[k] = {"type": "req", "name": norm(nm), "lines": list(block)}

    for nm, block in delta["ADDED"]:
        k = find(nm)
        if k >= 0:
            warnings.append(f"ADDED: '{nm}' 活规格已存在，原地替换（疑似应为 MODIFIED）")
            segs[k] = {"type": "req", "name": norm(nm), "lines": list(block)}
            continue
        _append_req(segs, nm, block)

    return warnings


def serialize_spec(segs):
    out = []
    for s in segs:
        if s["type"] == "other":
            out.extend(s["lines"])
        else:
            if out and out[-1].strip() != "":
                out.append("")
            out.extend(s["lines"])
            out.append("")
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip() + "\n"


def _new_spec_segs(cap):
    return [{"type": "other", "lines": [
        f"# Spec: {cap}", "", "## Purpose", "",
        "（待补充——本能力由变更首次引入）", "", "## Requirements",
    ]}]


def plan_delta(delta_path, specs_root):
    """pre-flight：解析 delta + 活规格，在副本上 apply 收集 warnings，**不写盘**。
    返回 (cap, spec_path, merged_segs, warnings, counts)。"""
    cap = os.path.splitext(os.path.basename(delta_path))[0]
    spec_path = os.path.join(specs_root, cap, "spec.md")
    delta = parse_delta(open(delta_path, encoding="utf-8").read())
    if os.path.isfile(spec_path):
        segs = parse_spec(open(spec_path, encoding="utf-8").read())
    else:
        segs = _new_spec_segs(cap)
    segs = copy.deepcopy(segs)
    warnings = apply_delta(segs, delta)
    counts = {k: len(v) for k, v in delta.items()}
    return cap, spec_path, segs, warnings, counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="merge change delta 进活规格 + 归档")
    ap.add_argument("change")
    ap.add_argument("date", help="YYYY-MM-DD")
    ap.add_argument("--specs-root", default="docs/specs")
    ap.add_argument("--changes-root", default="docs/changes")
    ap.add_argument("--dry-run", action="store_true", help="预览 merge 结果，不写盘、不归档")
    ap.add_argument("--force", action="store_true", help="即使 pre-flight 有 warning 也强制归档")
    args = ap.parse_args(argv)

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
        print(f"✗ date 须为 YYYY-MM-DD: {args.date}", file=sys.stderr)
        return 1
    change_dir = os.path.join(args.changes_root, args.change)
    specs_dir = os.path.join(change_dir, "specs")
    if not os.path.isdir(change_dir):
        print(f"✗ 变更文件夹不存在: {change_dir}", file=sys.stderr)
        return 1
    if not os.path.isdir(specs_dir):
        print(f"✗ 缺 delta 目录: {specs_dir}", file=sys.stderr)
        return 1
    archive_dir = os.path.join(args.changes_root, "archive", f"{args.date}-{args.change}")
    if os.path.exists(archive_dir):
        print(f"✗ 归档目标已存在: {archive_dir}", file=sys.stderr)
        return 1

    deltas = sorted(f for f in os.listdir(specs_dir) if f.endswith(".md"))
    if not deltas:
        print(f"✗ {specs_dir} 内无 delta（*.md）", file=sys.stderr)
        return 1

    # === pre-flight：零写盘，收集全部 warnings ===
    plans = []
    all_warnings = []
    for d in deltas:
        cap, spec_path, segs, warnings, counts = plan_delta(os.path.join(specs_dir, d), args.specs_root)
        plans.append((cap, spec_path, segs))
        for w in warnings:
            all_warnings.append(f"{cap}: {w}")
        print(f"  • {cap}: ADDED={counts['ADDED']} MODIFIED={counts['MODIFIED']} "
              f"REMOVED={counts['REMOVED']} RENAMED={counts['RENAMED']} → {spec_path}")

    if all_warnings:
        print(f"\n⚠️  pre-flight 发现 {len(all_warnings)} 个异常：", file=sys.stderr)
        for w in all_warnings:
            print(f"    - {w}", file=sys.stderr)
        if not args.force:
            print("\n✗ 已中止（未写活规格、未归档）。活规格是 SSOT，拒绝静默污染。", file=sys.stderr)
            print("  先跑 `--dry-run` 检查 merge 结果，确认无误后加 `--force` 放行；或修正 delta 后重跑。", file=sys.stderr)
            return 2
        print("\n⚠️  --force：忽略上述异常继续归档。", file=sys.stderr)

    if args.dry_run:
        print(f"\n[dry-run] 将写 {len(plans)} 份活规格 + 移动 {change_dir} → {archive_dir}（未执行）")
        return 0

    # === commit：写活规格 + 原子前置的归档存在性已在上方校验 ===
    for cap, spec_path, segs in plans:
        os.makedirs(os.path.dirname(spec_path), exist_ok=True)
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(serialize_spec(segs))
    os.makedirs(os.path.dirname(archive_dir), exist_ok=True)
    shutil.move(change_dir, archive_dir)
    print(f"✅ 已 merge {len(plans)} 份 delta + 归档 → {archive_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
