#!/usr/bin/env python3
"""BOM 路径2 — 数据缓存: 拉候选宇宙全期财务/预告/问答/研报, 落本地 CSV.

cutoff-aware 评分需要逐 cutoff 切片 (ann_date<=cutoff), 逐 cutoff 实时拉 Tushare 太慢.
本脚本一次拉全期 (2024-01~2026-06), 落本地, 路径2 评分脚本读本地切片.

拉取: fina_indicator (财务) + forecast (预告) + irm_qa (问答) + research_report (研报)
      + fina_mainbz_vip type=P (主营产品)

Usage:
    TUSHARE_TOKEN=xxx python tools/bom_oos_cache.py
    TUSHARE_TOKEN=xxx python tools/bom_oos_cache.py --universe all_a --limit 5 --sleep-seconds 0 --out-dir outputs/bom_oos_cache_smoke
    TUSHARE_TOKEN=xxx python tools/bom_oos_cache.py --universe all_a --out-dir outputs/bom_oos_cache_all_a --resume
"""
import os
import sys
import time
from pathlib import Path

import tushare as ts

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")
for p in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    sys.path.insert(0, str(PROJ / p))

from kronos_factors.backtest.bom_oos_cache import (  # noqa: E402
    MANIFEST_NAME,
    CacheConfig,
    append_cache_frames,
    fetch_all_a_codes,
    fetch_company_payload,
    load_processed_codes,
    mark_code_processed,
    parse_code_list,
    parse_cache_args,
    prepare_cache_output_dir,
    to_ts_code,
)


def load_bom36_codes():
    import psycopg2
    conn = psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    cur = conn.cursor()
    cur.execute("SELECT code FROM company_bom_mapping ORDER BY code")
    codes = [r[0] for r in cur.fetchall()]
    conn.close()
    return [(c, to_ts_code(c)) for c in codes]


def resolve_codes(pro, universe, codes_arg=""):
    explicit_codes = parse_code_list(codes_arg)
    if explicit_codes:
        return explicit_codes
    if universe == "bom36":
        return load_bom36_codes()
    if universe == "all_a":
        return fetch_all_a_codes(pro)
    raise ValueError(f"unsupported universe={universe}")


def resolve_out_dir(out_dir):
    path = Path(out_dir)
    return path if path.is_absolute() else PROJ / path


def main(argv=None):
    args = parse_cache_args(argv)
    out_dir = resolve_out_dir(args.out_dir)
    try:
        output_paths = prepare_cache_output_dir(out_dir, overwrite=args.overwrite, resume=args.resume)
    except FileExistsError as exc:
        print(f"❌ {exc}")
        sys.exit(2)
    manifest_path = out_dir / MANIFEST_NAME
    if args.overwrite:
        for path in [*output_paths.values(), manifest_path]:
            if path.exists():
                path.unlink()

    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ TUSHARE_TOKEN 未设置"); sys.exit(1)
    ts.set_token(token)
    pro = ts.pro_api()
    config = CacheConfig(start=args.start, end=args.end)

    codes = resolve_codes(pro, args.universe, args.codes)
    if args.limit and args.limit > 0:
        codes = codes[:args.limit]
    print(f"拉取 {len(codes)} 只公司全期数据 ({config.start}~{config.end}) universe={args.universe} → {out_dir}")
    processed = load_processed_codes(manifest_path) if args.resume else set()
    if processed:
        print(f"  resume: 已完成 {len(processed)} 只, 将跳过")

    fetched = skipped = 0
    for i, (code6, ts_code) in enumerate(codes):
        if str(code6).zfill(6)[-6:] in processed:
            skipped += 1
            continue
        print(f"  [{i+1}/{len(codes)}] {ts_code}", end=" ", flush=True)
        payload = fetch_company_payload(pro, code6, ts_code, config)
        frames = payload["frames"]
        errors = payload["errors"]
        append_cache_frames(output_paths, frames)
        frame_counts = {name: len(frame) for name, frame in frames.items()}
        total_rows = sum(frame_counts.values())
        if total_rows > 0:
            status = "ok"
        elif errors:
            status = "error"
        else:
            status = "no_data"
        mark_code_processed(
            manifest_path,
            code6=code6,
            ts_code=ts_code,
            frame_counts=frame_counts,
            status=status,
            errors=errors,
        )
        fetched += 1
        error_hint = f" errors={len(errors)}" if errors else ""
        print(f"rows={total_rows} status={status}{error_hint}")
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    print(f"\n✅ 缓存完成: fetched={fetched}, skipped={skipped}, manifest={manifest_path}")
    print("   路径2 评分脚本可用 --cache-dir 指向该目录读取本地切片")


if __name__ == "__main__":
    main()
