#!/usr/bin/env python3
"""agf-verdict.py — 结构化 verdict 数据契约的核心（解析 + 三套推导 + validate + matrix）。

frontmatter 是 verdict 数据的唯一机读 SSOT（见 ADR-010 / spec
docs/superpowers/specs/2026-06-15-structured-verdict-contract-design.md）。
本模块用健壮的 yaml 解析替代脆弱的 bash 文本抽取，并把「verdict 必从原子事实
推导 + 不符硬阻断」的保证集中在此处（单处推导 SSOT）。

CLI:
  agf-verdict.py validate <file> --kind=review|qa
      一致 → exit 0；声明≠推导 / QA 底线违规 → exit 2 + stderr。
      FAIL-OPEN（文件缺失 / yaml 解析异常 / 缺 PyYAML）→ exit 0 + stderr
      `[agf-verdict] WARN — ...`（沿用 ADR-003 保守姿态，绝不误杀）。
  agf-verdict.py matrix --type=review|qa --feature=<slug>
      扫 docs/reviews/ 或 docs/qa/（相对 CWD，可用 --docs-root 覆盖），
      输出 markdown 表。
"""
import sys

WARN_PREFIX = "[agf-verdict] WARN —"


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def _read_frontmatter_text(path):
    """读取 `---`-fenced frontmatter 原文（首个围栏块）。无 frontmatter → ""。"""
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    out = []
    for line in lines[1:]:
        if line.strip() == "---":
            return "\n".join(out)
        out.append(line)
    # 没有闭合围栏 → 视为无有效 frontmatter
    return ""


def parse_report(path):
    """解析报告 frontmatter → dict。

    robust：yaml.safe_load 整个 frontmatter 块。无围栏 / 空 → {}。
    PyYAML 不可用或 yaml 解析失败时抛异常（由 CLI fail-open 接住）。
    """
    import yaml  # 延迟 import：缺 PyYAML 时由 CLI fail-open 处理

    text = _read_frontmatter_text(path)
    if not text.strip():
        return {}
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return {}
    return data


def _as_int(value):
    """安全转 int，失败 → 0。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_str(value):
    """安全转 str（None → ""）。"""
    return "" if value is None else str(value)


def _count_problems(fm, keys):
    """frontmatter 计数字段中「present(非 None) 但 int() 不可解析」的 → 错误消息列表。

    W2：原 ``_as_int`` 把 ``critical_count: see-notes`` 这类静默转 0，使 ``derive_code``
    算出 "approve" 与声明的 "approve" 一致 → validate 放行，verdict 一致性门形同虚设。
    bool（YAML true/false 是 int 子类但语义不是计数）同样报；None / 缺省 → 不报（lenient，
    与 ``_as_int`` 默认 0 一致）。
    """
    msgs = []
    for k in keys:
        if k not in fm:
            continue
        v = fm[k]
        if v is None:
            continue
        if isinstance(v, bool):
            msgs.append(f'"{k}" 是布尔值不是整数计数（frontmatter 数据非法）')
            continue
        try:
            int(v)
        except (TypeError, ValueError):
            msgs.append(f'"{k}: {v!r}" 非整数计数（verdict 一致性门要求数据本身有效）')
    return msgs


def _warning_count(fm):
    """warning 计数（单处 SSOT，防 alias 规则漂移）：优先 `warning_count`，
    缺失（或显式 None）时认 miniapp/apple 的 `important_count` 别名。
    """
    if "warning_count" in fm and fm.get("warning_count") is not None:
        return _as_int(fm.get("warning_count"))
    return _as_int(fm.get("important_count"))


# --------------------------------------------------------------------------- #
# 推导规则 SSOT（spec §5）
# --------------------------------------------------------------------------- #
def derive_code(fm):
    """code verdict 推导：critical>0 → block；elif warning>0 → approve with changes；else approve。

    miniapp/apple 用 `important_count` 作 `warning_count` 别名（后者缺失时认前者）。
    """
    critical = _as_int(fm.get("critical_count"))
    warning = _warning_count(fm)
    if critical > 0:
        return "block"
    if warning > 0:
        return "approve with changes"
    return "approve"


def derive_sit(fm):
    """SIT Audit 推导：sit_checks 4 值任一 fail → Redo SIT；任一 concerns → Pass with concerns；else Pass。"""
    checks = fm.get("sit_checks")
    if not isinstance(checks, dict):
        checks = {}
    values = [_as_str(v).strip().lower() for v in checks.values()]
    if any(v == "fail" for v in values):
        return "Redo SIT"
    if any(v == "concerns" for v in values):
        return "Pass with concerns"
    return "Pass"


def qa_floor_violations(fm):
    """QA 客观底线违规（spec §5）→ list[str]（空 = OK）。

    - critical_defect_count>0 且 report_verdict != Block → 违规；
    - p0_pass2_ok < p0_pass2_total 且 report_verdict == Promote → 违规。
    不强定 Promote vs Conditional（定性选择不硬套）。
    """
    msgs = []
    verdict = _as_str(fm.get("report_verdict")).strip()
    crit = _as_int(fm.get("critical_defect_count"))
    if crit > 0 and verdict != "Block":
        msgs.append(
            f'critical_defect_count={crit}（>0）但 report_verdict="{verdict}" → 应为 "Block"'
        )
    total = _as_int(fm.get("p0_pass2_total"))
    ok = _as_int(fm.get("p0_pass2_ok"))
    if ok < total and verdict == "Promote":
        msgs.append(
            f"P0 pass²未全过（{ok}/{total}）但 report_verdict=\"Promote\" → P0 未全 pass² 不得 Promote"
        )
    return msgs


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def validate(path, kind):
    """(ok: bool, msg: str)。review → 校 code + SIT；qa → 校客观底线。

    异常（缺文件 / yaml 失败 / 缺 PyYAML）向上抛，由 CLI fail-open 接住。
    """
    fm = parse_report(path)
    if kind == "review":
        problems = list(_count_problems(fm, ("critical_count", "warning_count", "important_count")))
        declared_code = _as_str(fm.get("code_verdict")).strip()
        derived_code = derive_code(fm)
        if declared_code != derived_code:
            critical = _as_int(fm.get("critical_count"))
            warning = _warning_count(fm)
            problems.append(
                f'声明 code_verdict="{declared_code}"，但 critical={critical} '
                f'warning={warning} → 应为 "{derived_code}"'
            )
        declared_sit = _as_str(fm.get("sit_audit_verdict")).strip()
        derived_sit = derive_sit(fm)
        if declared_sit != derived_sit:
            problems.append(
                f'声明 sit_audit_verdict="{declared_sit}"，但 sit_checks={fm.get("sit_checks")} '
                f'→ 应为 "{derived_sit}"'
            )
        if problems:
            return False, "；".join(problems)
        return True, ""
    if kind == "qa":
        problems = list(_count_problems(fm, ("critical_defect_count", "p0_pass2_total", "p0_pass2_ok")))
        problems.extend(qa_floor_violations(fm))
        if problems:
            return False, "；".join(problems)
        return True, ""
    return True, ""


# --------------------------------------------------------------------------- #
# matrix
# --------------------------------------------------------------------------- #
def _md_escape(value):
    # 转义 `|`（列分隔符）并把内嵌换行压成空格，防 frontmatter 多行串破坏表格行对齐
    return _as_str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _collect_files(docs_root, subdir, feature, excludes):
    import glob
    import os

    pattern = os.path.join(docs_root, subdir, f"{feature}-*.md")
    files = sorted(glob.glob(pattern))
    kept = []
    for f in files:
        base = os.path.basename(f)
        if any(ex in base for ex in excludes):
            continue
        kept.append(f)
    return kept


def _safe_parse(path):
    """matrix 用：解析失败的单个文件不应炸整张表 → 返回 {}。"""
    try:
        return parse_report(path)
    except Exception:
        return {}


def matrix_review(docs_root, feature):
    files = _collect_files(docs_root, "docs/reviews", feature, ("_TEMPLATE", "retro-"))
    header = (
        "| Reviewer 实例 | 代码 Verdict | SIT Audit | Critical | Warning | 报告路径 |\n"
        "|---|---|---|---|---|---|"
    )
    if not files:
        return f"（feature `{feature}` 暂无 review 报告）"
    rows = [header]
    for f in files:
        fm = _safe_parse(f)
        reviewer = _as_str(fm.get("reviewer")).strip() or "code-reviewer"
        code_v = _as_str(fm.get("code_verdict")).strip() or "-"
        sit_v = _as_str(fm.get("sit_audit_verdict")).strip() or "-"
        critical = _as_int(fm.get("critical_count"))
        warning = _warning_count(fm)
        rows.append(
            f"| {_md_escape(reviewer)} | {_md_escape(code_v)} | {_md_escape(sit_v)} "
            f"| {critical} | {warning} | {_md_escape(f)} |"
        )
    return "\n".join(rows)


def matrix_qa(docs_root, feature):
    files = _collect_files(docs_root, "docs/qa", feature, ("_TEMPLATE", "process-log", "uat-cases"))
    header = (
        "| QA 实例 | 阶段 | 报告级 Verdict | UAT 业务签字 | pass^2 (P0) | 报告路径 |\n"
        "|---|---|---|---|---|---|"
    )
    if not files:
        return f"（feature `{feature}` 暂无 qa 报告）"
    rows = [header]
    for f in files:
        fm = _safe_parse(f)
        tester = _as_str(fm.get("tester")).strip() or "qa-engineer"
        stage = _as_str(fm.get("stage")).strip() or "-"
        report_v = _as_str(fm.get("report_verdict")).strip() or "-"
        signoff = _as_str(fm.get("uat_signoff_verdict")).strip() or "N/A"
        total = _as_int(fm.get("p0_pass2_total"))
        ok = _as_int(fm.get("p0_pass2_ok"))
        pass2 = f"{ok}/{total}" if total else "-"
        rows.append(
            f"| {_md_escape(tester)} | {_md_escape(stage)} | {_md_escape(report_v)} "
            f"| {_md_escape(signoff)} | {_md_escape(pass2)} | {_md_escape(f)} |"
        )
    return "\n".join(rows)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _get_opt(args, name):
    """从 args 取 --name=value 或 --name value，返回 value 或 None。"""
    prefix = f"--{name}="
    for i, a in enumerate(args):
        if a.startswith(prefix):
            return a[len(prefix):]
        if a == f"--{name}" and i + 1 < len(args):
            return args[i + 1]
    return None


def _cmd_validate(args):
    # 第一个非 -- 位置参数 = 文件
    positionals = [a for a in args if not a.startswith("--")]
    path = positionals[0] if positionals else None
    kind = _get_opt(args, "kind")
    if not path or kind not in ("review", "qa"):
        sys.stderr.write("用法: agf-verdict.py validate <file> --kind=review|qa\n")
        return 2
    import os

    if not os.path.isfile(path):
        sys.stderr.write(f"{WARN_PREFIX} 文件不存在: {path}（fail-open 放行）\n")
        return 0
    try:
        ok, msg = validate(path, kind)
    except ImportError:
        sys.stderr.write(f"{WARN_PREFIX} 缺 PyYAML，跳过 verdict 校验（fail-open 放行）\n")
        return 0
    except Exception as exc:  # yaml 解析异常等
        sys.stderr.write(f"{WARN_PREFIX} 解析 {path} 失败: {exc}（fail-open 放行）\n")
        return 0
    if ok:
        return 0
    sys.stderr.write(f"[agf-verdict] BLOCK — {path}: {msg}\n")
    return 2


def _cmd_matrix(args):
    mtype = _get_opt(args, "type")
    feature = _get_opt(args, "feature")
    docs_root = _get_opt(args, "docs-root") or "."
    if mtype not in ("review", "qa") or not feature:
        sys.stderr.write(
            "用法: agf-verdict.py matrix --type=review|qa --feature=<slug> [--docs-root=DIR]\n"
        )
        return 2
    try:
        if mtype == "review":
            print(matrix_review(docs_root, feature))
        else:
            print(matrix_qa(docs_root, feature))
    except ImportError:
        sys.stderr.write(f"{WARN_PREFIX} 缺 PyYAML，无法生成 matrix（fail-soft）\n")
        return 0
    return 0


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("用法: agf-verdict.py {validate|matrix} ...\n")
        return 2
    cmd, rest = argv[1], argv[2:]
    if cmd == "validate":
        return _cmd_validate(rest)
    if cmd == "matrix":
        return _cmd_matrix(rest)
    sys.stderr.write(f"未知子命令: {cmd}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
