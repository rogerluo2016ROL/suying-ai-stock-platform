"""政策法规同步 — Tushare npr (国家政策法规库) API.

独立权限接口: ¥1,000/年.
覆盖国务院及相关部委发布的政策文件, 主题分类 110+ 类.
行业政策突变是黑天鹅事件的重要信号源.
"""

import logging, sqlite3, time
from datetime import date, timedelta

logger = logging.getLogger("data-service.policy_law")

# 重点关注的行业政策分类
KEY_PTYPES = [
    "科技", "金融", "证券", "银行", "保险", "税务", "财政",
    "能源", "环保", "医药", "教育", "房地产", "农业", "交通",
    "知识产权", "海关", "外资", "中小企业", "国企改革",
]


def sync_policy_law(days_back: int = 7) -> dict:
    """同步国家政策法规 — 按发布机构 + 日期范围批量拉取.

    API: pro.npr(org, start_date, end_date, ptype, fields=...)
    输出: pubtime, title, url, content_html, pcode, puborg, ptype

    按重点行业分类逐类拉取, 确保覆盖所有对资本市场有影响的政策.

    Args:
        days_back: 回补天数, 默认 7 天

    Returns:
        {"table": "policy_law", "written": N, "pg_written": N, "elapsed": S}
    """
    from app.config import TUSHARE_TOKEN, DB_PATH
    from app.sync.rate_limiter import rate_limit

    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    t0 = time.time()
    today = date.today()
    end_date = today.strftime("%Y-%m-%d 23:59:59")
    start_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d 00:00:00")

    total_rows = 0
    pg_written = 0

    # 1. 按重点行业分类拉取
    for ptype in KEY_PTYPES:
        rate_limit()
        try:
            df = pro.npr(
                start_date=start_date, end_date=end_date,
                ptype=ptype,
                fields="pubtime,title,url,content_html,pcode,puborg,ptype",
            )
        except Exception as e:
            logger.debug("npr ptype=%s failed: %s", ptype, e)
            continue

        if df is None or len(df) == 0:
            continue

        rows = _parse_npr_rows(df)
        if rows:
            total_rows += len(rows)
            pg_written += _pg_write_batch(rows)
            _sqlite_write_batch(rows)

    # 2. 拉取国务院办公厅全部政策 (不分行业)
    for org in ("国务院办公厅", "国务院", "国家发展改革委", "中国证监会"):
        rate_limit()
        try:
            df = pro.npr(
                org=org, start_date=start_date, end_date=end_date,
                fields="pubtime,title,url,content_html,pcode,puborg,ptype",
            )
        except Exception as e:
            logger.debug("npr org=%s failed: %s", org, e)
            continue

        if df is None or len(df) == 0:
            continue

        rows = _parse_npr_rows(df)
        if rows:
            total_rows += len(rows)
            pg_written += _pg_write_batch(rows)
            _sqlite_write_batch(rows)

    elapsed = time.time() - t0
    logger.info("policy_law: %d rows over %d days, PG=%d, %.1fs",
                total_rows, days_back, pg_written, elapsed)
    return {
        "table": "policy_law",
        "written": total_rows,
        "pg_written": pg_written,
        "days_back": days_back,
        "elapsed": elapsed,
    }


def _parse_npr_rows(df) -> list:
    """解析 npr API 返回的 DataFrame → rows."""
    rows = []
    for _, r in df.iterrows():
        title = str(r.get("title", ""))
        pubtime = str(r.get("pubtime", ""))
        if not title:
            continue
        rows.append((
            pubtime,
            title,
            str(r.get("url", "")),
            str(r.get("content_html", ""))[:10000],
            str(r.get("pcode", "")),
            str(r.get("puborg", "")),
            str(r.get("ptype", "")),
        ))
    return rows


def _pg_write_batch(rows: list) -> int:
    """PG 直写."""
    try:
        from app.sync.pg_writer import _pg_write
        return _pg_write(
            "policy_law",
            ["pub_date", "title", "url", "content_html", "pcode", "puborg", "ptype"],
            ["pub_date", "title"],
            rows,
        )
    except Exception:
        return 0


def _sqlite_write_batch(rows: list):
    """SQLite fallback."""
    from app.config import DB_PATH
    try:
        db = sqlite3.connect(DB_PATH)
        db.executemany(
            "INSERT OR REPLACE INTO policy_law(pub_date, title, url, content_html, pcode, puborg, ptype) "
            "VALUES(?,?,?,?,?,?,?)", rows)
        db.commit(); db.close()
    except Exception:
        pass
