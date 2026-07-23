"""codemap CLI 入口（build / update / diff / explain / onboard / understand / context）。"""

from __future__ import annotations
import argparse
import json
import sqlite3
import subprocess
from pathlib import Path

from codemap.analyze.impact import impact_report
from codemap.analyze.reachability import orphans_report
from codemap.analyze.incremental import update as do_update
from codemap.builder import build
from codemap.consume.context_builder import build_context
from codemap.consume.explain import explain as do_explain
from codemap.consume.onboard import onboard as do_onboard
from codemap.consume.understand import understand as do_understand
from codemap.graph.store import get_meta, init_db


def main() -> None:
    p = argparse.ArgumentParser(
        prog="codemap", description="Deeply Understand — AGF code understanding engine (ADR-021)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _common(sp):
        sp.add_argument("--db", default=".agf/code-map.db")

    pb = sub.add_parser("build"); _common(pb); pb.add_argument("path", nargs="?", default=".")
    pu = sub.add_parser("update"); _common(pu); pu.add_argument("path", nargs="?", default=".")
    pd = sub.add_parser("diff"); _common(pd); pd.add_argument("--base"); pd.add_argument("--hop", type=int, default=2); pd.add_argument("--out", default=None)
    po = sub.add_parser("orphans"); _common(po); po.add_argument("--changed", action="store_true"); po.add_argument("--base"); po.add_argument("--entrypoints", default=""); po.add_argument("--root", default="."); po.add_argument("--out", default=None)
    pe = sub.add_parser("explain"); _common(pe); pe.add_argument("target"); pe.add_argument("--root", default=".")
    po = sub.add_parser("onboard"); _common(po); po.add_argument("--out", default=None)
    pun = sub.add_parser("understand"); _common(pun); pun.add_argument("topic", nargs="?", default=None); pun.add_argument("--out", default=None)
    pc = sub.add_parser("context"); _common(pc); pc.add_argument("query")
    ps = sub.add_parser("search"); _common(ps); ps.add_argument("query"); ps.add_argument("--semantic", action="store_true")
    pdash = sub.add_parser("dashboard"); _common(pdash); pdash.add_argument("--out", default=".agf/dashboard.html"); pdash.add_argument("--max-nodes", type=int, default=2000); pdash.add_argument("--only-files", action="store_true"); pdash.add_argument("--label-threshold", type=int, default=8, help="入度 ≥ N 的节点默认显示文件名 label（默认 8）")
    pem = sub.add_parser("embed"); _common(pem)
    pmm = sub.add_parser("mermaid"); _common(pmm); pmm.add_argument("--only-files", action="store_true"); pmm.add_argument("--out", default=None); pmm.add_argument("--max-nodes", type=int, default=200)
    pdot = sub.add_parser("dot"); _common(pdot); pdot.add_argument("--only-files", action="store_true"); pdot.add_argument("--out", default=None); pdot.add_argument("--max-nodes", type=int, default=500)

    args = p.parse_args()
    if args.cmd == "build":
        print(json.dumps(build(args.path, args.db), indent=2, ensure_ascii=False))
    elif args.cmd == "update":
        print(json.dumps(do_update(args.path, args.db), indent=2, ensure_ascii=False))
    elif args.cmd == "diff":
        _emit(json.dumps(impact_report(_changed(args), sqlite3.connect(args.db), hop=args.hop),
                         indent=2, ensure_ascii=False), args.out)
    elif args.cmd == "orphans":
        changed = _changed(args) if args.changed else None
        eps = [e for e in args.entrypoints.split(",") if e.strip()] or None
        _emit(json.dumps(orphans_report(sqlite3.connect(args.db), changed_files=changed,
                                        extra_entrypoints=eps),
                         indent=2, ensure_ascii=False), args.out)
    elif args.cmd == "explain":
        print(do_explain(args.target, sqlite3.connect(args.db), args.root))
    elif args.cmd == "onboard":
        _emit(do_onboard(sqlite3.connect(args.db)), args.out)
    elif args.cmd == "understand":
        _emit(do_understand(args.topic, sqlite3.connect(args.db)), args.out)
    elif args.cmd == "context":
        print(build_context(args.query, sqlite3.connect(args.db)))
    elif args.cmd == "search":
        from codemap.search.semantic import search as sem_search
        results, source = sem_search(args.query, sqlite3.connect(args.db))
        print(f"[来源: {source}]")
        for r in results:
            print(f"- {r['name']} ({r['type']}) `{r['file_path']}`")
    elif args.cmd == "dashboard":
        from codemap.dashboard.render import render
        print(json.dumps(render(args.db, args.out, args.max_nodes, only_files=args.only_files, label_threshold=args.label_threshold), indent=2, ensure_ascii=False))
    elif args.cmd == "embed":
        from codemap.search.embedder import embed_nodes
        print(json.dumps(embed_nodes(sqlite3.connect(args.db)), indent=2, ensure_ascii=False))
    elif args.cmd == "mermaid":
        from codemap.dashboard.export import mermaid
        _emit(mermaid(sqlite3.connect(args.db), only_files=args.only_files, max_nodes=args.max_nodes), args.out)
    elif args.cmd == "dot":
        from codemap.dashboard.export import dot
        _emit(dot(sqlite3.connect(args.db), only_files=args.only_files, max_nodes=args.max_nodes), args.out)


def _emit(text: str, out: str | None) -> None:
    """输出到 stdout；--out 指定时写文件（自动建父目录），供 understand/onboard/diff
    原生落盘 docs/reviews/<slug>-{understand,onboard,diff}-<date>.md（消 command 声明
    vs stdout-only 的 gap；diff 落 JSON 结构化报告）。"""
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out} ({len(text)} chars)")
    else:
        print(text)


def _changed(args) -> list[str]:
    root = Path(getattr(args, "root", ".")).resolve()
    db = init_db(args.db)
    last = args.base or get_meta(db, "git_commit")
    if not last:
        return []
    out = subprocess.run(["git", "-C", str(root), "diff", "--name-only", f"{last}..HEAD"],
                         capture_output=True, text=True, check=False)
    return [l for l in out.stdout.splitlines() if l.strip()]


if __name__ == "__main__":
    main()
