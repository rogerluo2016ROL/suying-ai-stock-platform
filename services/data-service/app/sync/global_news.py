"""全球财经快讯同步 — 新浪财经 7x24 + 金十数据.

用途: 海外市场早报 (morning_brief) 的「美/韩/日热点财经新闻 Top10」原料.
akshare 的 stock_info_global_* 接口在本环境被远端断连 (Step 0 实测), 故直连源站 JSON API.
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

logger = logging.getLogger("data-service.global_news")

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_TIMEOUT = 20


def _http_json(url: str, params: dict | None = None,
               extra_headers: dict | None = None) -> dict | None:
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers={"User-Agent": _UA, **(extra_headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as e:
        logger.warning("global_news fetch failed %s: %s", url.split("/")[2], e)
        return None


def _fetch_sina(max_pages: int = 6) -> list[tuple]:
    """新浪 7x24 全球直播快讯. zhibo_id=152 为环球市场频道.

    默认 6 页 (300 条) 以覆盖隔夜窗口 (昨晚 17:00 ~ 今晨 8:00 的 8:00 早报场景)."""
    rows = []
    for page in range(1, max_pages + 1):
        data = _http_json("https://zhibo.sina.com.cn/api/zhibo/feed", {
            "page": page, "page_size": 50, "zhibo_id": 152,
            "tag_id": 0, "dire": "f", "dpc": 1, "type": 0,
        })
        items = (((data or {}).get("result") or {}).get("data") or {}).get("feed", {}).get("list") or []
        if not items:
            break
        for it in items:
            ext_id = str(it.get("id") or "")
            ts = it.get("create_time") or it.get("update_time") or ""
            content = str(it.get("rich_text") or it.get("text") or "").strip()
            if not ext_id or not ts or not content:
                continue
            try:
                pub_time = datetime.fromtimestamp(int(ts)) if ts.isdigit() else datetime.fromisoformat(ts)
            except (ValueError, OSError):
                continue
            rows.append((ext_id, pub_time, "", content[:2000], "sina", ""))
        if len(items) < 50:
            break
    return rows


def _fetch_jin10(max_pages: int = 1) -> list[tuple]:
    """金十数据快讯 (最近一页, 约 50 条)."""
    data = _http_json(
        "https://flash-api.jin10.com/get_flash_list",
        {"channel": "-8200", "vip": 1, "max_time": ""},
        {"x-app-id": "bVBF4FyRTn5NJF5n", "x-version": "1.0.0"},
    )
    items = (data or {}).get("data") or []
    rows = []
    for it in items:
        d = it.get("data") or {}
        ext_id = str(it.get("id") or "")
        pub_str = str(it.get("time") or "")
        content = str(d.get("content") or "").strip()
        # 金十内容常带 HTML 标签, 粗剥离
        for tag in ("<br />", "<br/>", "<br>"):
            content = content.replace(tag, " ")
        import re
        content = re.sub(r"<[^>]+>", "", content).strip()
        pic = str(d.get("pic") or "")
        if not ext_id or not pub_str or not content:
            continue
        try:
            pub_time = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        rows.append((ext_id, pub_time, "", content[:2000], "jin10", pic))
    return rows


def sync_global_news(days_back: int = 1) -> dict:
    """同步全球财经快讯 (新浪 + 金十), ON CONFLICT 去重.

    Args:
        days_back: 仅用于裁剪过早的新闻 (默认保留近 1 天窗口内的条目)

    Returns:
        {"table": "global_news_flash", "written": N, "pg_written": N, "elapsed": S}
    """
    from app.sync.pg_writer import _pg_write

    t0 = time.time()
    rows = _fetch_sina() + _fetch_jin10()
    cutoff = datetime.now() - timedelta(days=max(days_back, 1))
    rows = [r for r in rows if r[1] >= cutoff]

    pg_written = 0
    if rows:
        try:
            pg_written = _pg_write(
                "global_news_flash",
                ["ext_id", "pub_time", "title", "content", "source", "url"],
                ["source", "ext_id"],
                rows,
            )
        except Exception as e:
            logger.warning("PG write global_news_flash failed: %s", e)

    elapsed = time.time() - t0
    logger.info("global_news: fetched=%d pg_written=%d %.1fs", len(rows), pg_written, elapsed)
    return {
        "table": "global_news_flash",
        "written": len(rows),
        "pg_written": pg_written,
        "elapsed": elapsed,
    }
