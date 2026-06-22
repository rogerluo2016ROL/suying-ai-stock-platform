"""ST 历史同步 — Tushare namechange 解析戴帽/摘帽区间写 st_history.

阶段 1 AC-2（幸存者偏差修复）：回测选股池按 trade_date JOIN st_history 剔除
T 日已戴帽股。本模块拉 Tushare namechange，按 code 分组解析 name 字段：
  - name 含 "ST" / "*ST" → 戴帽事件（记 start_date + st_type）
  - name 去掉 ST 前缀 → 摘帽事件（回填上一区间的 end_date）
成对区间写 st_history（ON CONFLICT DO UPDATE，幂等）。

积分不足时 fallback：从 stocks.is_st 导当前快照（end_date=NULL）+ 降级标注，
ml-engineer-p1 回测读 source 字段判断可信度。
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict

from app.config import TUSHARE_TOKEN
from app.sync.rate_limiter import rate_limit

logger = logging.getLogger("data-service.namechange")

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

DEFAULT_START = "20180101"  # PL 指定：namechange 从 2018-01-01 起拉


def _get_pro():
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    return ts.pro_api()


def _code_from_ts(ts_code: str) -> str:
    return str(ts_code).split(".")[0][:6]


def _to_dash(d: str | None) -> str | None:
    """20180101 → '2018-01-01'; None/NaN → None."""
    if d is None:
        return None
    s = str(d).replace("-", "").strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def _classify_st(name: str) -> str | None:
    """Return st_type if name indicates ST, else None.

    '*ST' (退市风险) takes priority over plain 'ST'. 退市 marked separately.
    """
    if not name:
        return None
    n = str(name)
    if "*ST" in n:
        return "*ST"
    if "ST" in n:
        return "ST"
    return None


def _parse_st_intervals(records: list[dict]) -> list[tuple]:
    """Parse namechange rows into (code, start_date, end_date, st_type) intervals.

    records: list of {ts_code, name, start_date, end_date} dicts.
    For each code, walk the name-change timeline in start_date order:
      - transition non-ST → ST  = donning (open a new interval)
      - transition ST → non-ST  = lifting (close the open interval with end_date)
    An interval still open at the end of the timeline gets end_date=None.
    """
    by_code: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_code[_code_from_ts(r.get("ts_code", ""))].append(r)

    intervals: list[tuple] = []
    for code, rows in by_code.items():
        # sort by start_date ascending
        rows.sort(key=lambda r: str(r.get("start_date") or ""))
        open_start: str | None = None
        open_type: str | None = None
        for r in rows:
            st_type = _classify_st(r.get("name", ""))
            sd = _to_dash(r.get("start_date"))
            if sd is None:
                continue
            if st_type is not None and open_start is None:
                # donning ST
                open_start, open_type = sd, st_type
            elif st_type is None and open_start is not None:
                # lifting ST — close the open interval
                intervals.append((code, open_start, sd, open_type))
                open_start, open_type = None, None
            elif st_type is not None and open_start is not None and st_type != open_type:
                # ST type changed (e.g. ST → *ST): close + reopen as a new interval
                intervals.append((code, open_start, sd, open_type))
                open_start, open_type = sd, st_type
        # still open at end of timeline → currently ST
        if open_start is not None:
            intervals.append((code, open_start, None, open_type))
    return intervals


def _upsert_st_history(intervals: list[tuple]) -> int:
    """Upsert ST intervals into st_history (ON CONFLICT DO UPDATE end_date).

    intervals: list of (code, start_date, end_date, st_type).
    ADR-015.5: inline executemany → _pg_write(update). source 列由调用方
    拼入 rows (_pg_write 是 values-based, 不支持 SQL 字面量列). 表无
    updated_at 列, 不传 now_cols.
    """
    if not intervals:
        return 0
    # intervals 4 元组 → 拼 source 列成 5 元组
    rows = [(c, sd, ed, st, "tushare_namechange") for (c, sd, ed, st) in intervals]
    from app.sync.pg_writer import _pg_write
    return _pg_write(
        "st_history",
        columns=["code", "start_date", "end_date", "st_type", "source"],
        conflict_cols=["code", "start_date"],
        rows=rows,
        conflict_action="update",
        update_cols=["end_date", "st_type", "source"],
    )


def _fallback_snapshot() -> dict:
    """积分不足 fallback：从 stocks.is_st 导当前快照写 st_history.

    source='stocks_is_st_snapshot'，end_date=NULL（仅当前时点，无历史区间）。
    """
    import psycopg2
    conn = psycopg2.connect(PG_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO st_history(code, start_date, end_date, st_type, source) "
        "SELECT code, CURRENT_DATE, NULL, 'ST', 'stocks_is_st_snapshot' "
        "FROM stocks WHERE is_st = 1 "
        "ON CONFLICT(code, start_date) DO UPDATE SET "
        "  end_date = EXCLUDED.end_date, source = EXCLUDED.source"
    )
    written = cur.rowcount
    cur.execute("SELECT count(*) FROM stocks WHERE is_st = 1")
    st_count = cur.fetchone()[0]
    conn.close()
    logger.warning(
        "ST 过滤降级，仅当前快照 — namechange 积分不足，已从 stocks.is_st 导入 %d 只当前 ST 股 (end_date=NULL)",
        st_count,
    )
    return {"source": "stocks_is_st_snapshot", "snapshot_st_count": st_count, "written": written}


def sync_st_history(
    start_date: str = DEFAULT_START,
    end_date: str | None = None,
    dry_run: bool = False,
) -> dict:
    """拉 Tushare namechange → 解析戴帽/摘帽区间 → 写 st_history.

    Args:
        start_date: namechange 拉取起始日（YYYYMMDD），默认 20180101。
        end_date: 可选结束日；None = 拉到最新。
        dry_run: True = 只解析+打印统计，不写库（铁律 #2 批量脚本）。

    Returns:
        统计 dict（synced 区间数 / source / 是否降级）。
    """
    if not TUSHARE_TOKEN:
        logger.error("TUSHARE_TOKEN 未设置，无法同步 ST 历史")
        return {"error": "no token", "synced": 0}

    pro = _get_pro()
    t0 = time.time()

    # ── 1. 拉全市场 namechange（分页）──
    all_records: list[dict] = []
    try:
        for page in range(20):
            rate_limit()
            kwargs = {"start_date": start_date, "limit": 5000, "offset": page * 5000}
            if end_date:
                kwargs["end_date"] = end_date
            df = pro.namechange(**kwargs)
            if df is None or len(df) == 0:
                break
            all_records.extend(df.to_dict("records"))
            if len(df) < 5000:
                break  # last page
        logger.info("namechange 拉取完成：%d 条改名记录（%.1fs）", len(all_records), time.time() - t0)
    except Exception as e:
        msg = str(e)
        logger.warning("namechange API 失败（可能积分不足）：%s", msg[:200])
        if dry_run:
            return {"error": msg[:140], "synced": 0, "dry_run": True}
        # 积分/权限不足 → fallback snapshot
        if "积分" in msg or "permission" in msg.lower() or "权限" in msg:
            logger.warning("触发 fallback：stocks.is_st 静态快照")
            return {**_fallback_snapshot(), "synced": 0, "degraded": True}
        return {"error": msg[:140], "synced": 0}

    # ── 2. 解析戴帽/摘帽区间 ──
    intervals = _parse_st_intervals(all_records)
    st_count = len(intervals)
    logger.info("解析 ST 区间：%d 个（戴帽/摘帽成对，当前仍戴帽 end_date=NULL）", st_count)

    if dry_run:
        sample = intervals[:5]
        logger.info("[dry-run] 抽样区间：%s", sample)
        return {
            "dry_run": True,
            "namechange_records": len(all_records),
            "st_intervals": st_count,
            "sample": sample,
        }

    # ── 3. 写库（幂等 ON CONFLICT DO UPDATE）──
    written = _upsert_st_history(intervals)
    logger.info("st_history 写入完成：%d 区间（%.1fs）", written, time.time() - t0)
    return {
        "source": "tushare_namechange",
        "namechange_records": len(all_records),
        "st_intervals": st_count,
        "written": written,
    }
