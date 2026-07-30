"""海外市场早报 — 美股/韩股板块共振 + 热门股清单 + 美韩日热点新闻 Top10.

数据源:
- 美股: PG us_stock_daily (Tushare VIP us_daily 主源, data-service 7:50 写入),
  缺失时东财 push2 实时快照兜底.
- 韩股: PG kr_stock_daily (Naver, data-service 9:02 写入), 缺失/过旧时直连 Naver 兜底.
- 新闻: PG global_news_flash (新浪7x24/金十).
- LLM (DeepSeek): 热门股板块归类 + 新闻 Top10 排序; 无 key 或调用失败时规则降级.

返回结构迁就统一研究流水线 (picks 装热门股清单):
{status, mode, trade_date, picks[], picks_down[], total_picks, sector_resonance[],
 sector_resonance_down[], news_top10[],
 market_strength{indices[], snapshot_time}, data_source, brief_type}
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger("screener.morning_brief")

PG_URL = os.environ.get("KRONOS_PG_URL",
                        "postgresql://kronos:kronos@localhost:6432/kronos")

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

INDEX_NAMES = {"IXIC": "纳斯达克", "DJI": "道琼斯", "SPX": "标普500",
               "N225": "日经225", "KS11": "韩国KOSPI"}

# 硬科技关键词 — 新闻 Top10 排序加权 & 板块归类提示
HARD_TECH_HINT = "半导体/芯片、AI算力/GPU/数据中心、机器人、商业航天、生物科技、新能源、量子、先进制造"


# ── PG 读取 ────────────────────────────────────────────────────────────────

def _pg_query(sql: str, params: tuple = ()) -> list[tuple]:
    import psycopg2
    with psycopg2.connect(PG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def _load_us_hot(top_n: int) -> tuple[str, list[dict], list[dict], str]:
    """返回 (trade_date, hot_stocks, loser_stocks, data_source).
    hot = 涨幅榜 ∪ 成交额榜; losers = 纯跌幅榜 (供板块共振跌幅)."""
    rows = _pg_query("""
        SELECT d.trade_date, d.ts_code,
               COALESCE(NULLIF(b.name,''), b.enname, d.ts_code) AS name,
               d.pct_chg, d.amount, d.source
        FROM us_stock_daily d
        LEFT JOIN us_stock_basic b ON b.ts_code = d.ts_code
        WHERE d.trade_date = (SELECT max(trade_date) FROM us_stock_daily)
          AND d.pct_chg IS NOT NULL
    """)
    if not rows:
        hot, losers = _fetch_us_spot_em(top_n)
        return (datetime.now().date().isoformat(), hot, losers, "eastmoney_realtime")

    trade_date = str(rows[0][0])
    source = rows[0][5] or "tushare"
    stocks = [{"code": r[1], "name": r[2], "pct_chg": float(r[3]),
               "amount": float(r[4] or 0)} for r in rows]
    return (trade_date, _pick_hot(stocks, top_n),
            _pick_losers(stocks, top_n), source)


def _pick_hot(stocks: list[dict], top_n: int,
              min_pct: float = 3.0, min_amount: float = 5e6) -> list[dict]:
    """热门股 = 涨幅榜 (涨幅≥min_pct 且成交额≥min_amount) ∪ 成交额榜, 去重后封顶 top_n."""
    liquid = [s for s in stocks if s["amount"] >= min_amount]
    gainers = sorted([s for s in liquid if s["pct_chg"] >= min_pct],
                     key=lambda x: -x["pct_chg"])[: top_n * 2]
    by_amount = sorted(liquid, key=lambda x: -x["amount"])[: top_n]
    seen, hot = set(), []
    for s in gainers + by_amount:
        if s["code"] in seen:
            continue
        seen.add(s["code"])
        hot.append(s)
        if len(hot) >= top_n:
            break
    return hot


def _pick_losers(stocks: list[dict], top_n: int,
                 min_pct: float = 3.0, min_amount: float = 5e6) -> list[dict]:
    """领跌股 = 跌幅榜 (跌幅≤-min_pct 且成交额≥min_amount), 跌最多在前, 封顶 top_n.

    与 _pick_hot 不同: 不混入成交额榜 — 跌幅共振需要纯领跌样本,
    避免与热门股清单大面积重叠造成阅读困惑.
    """
    liquid = [s for s in stocks if s["amount"] >= min_amount]
    return sorted([s for s in liquid if s["pct_chg"] <= -min_pct],
                  key=lambda x: x["pct_chg"])[:top_n]


def _load_kr_hot(top_n: int) -> tuple[str, list[dict], list[dict], str]:
    rows = _pg_query("""
        SELECT trade_date, code, name, pct_chg, amount, snapshot_ts
        FROM kr_stock_daily
        WHERE trade_date = (SELECT max(trade_date) FROM kr_stock_daily)
          AND pct_chg IS NOT NULL
    """)
    today = datetime.now().date().isoformat()
    # 快照非当日 或 快照早于今早 8 点 (韩股未开盘的旧数据) → 直连 Naver
    if not rows or str(rows[0][0]) != today:
        hot, losers = _fetch_kr_spot(top_n)
        return today, hot, losers, "naver_realtime"
    stocks = [{"code": r[1], "name": r[2], "pct_chg": float(r[3]),
               "amount": float(r[4] or 0) * 1e6} for r in rows]  # 百万韩元→韩元
    return (str(rows[0][0]), _pick_hot(stocks, top_n, min_pct=2.0, min_amount=1e10),
            _pick_losers(stocks, top_n, min_pct=2.0, min_amount=1e10), "naver")


def _load_indices(codes: list[str]) -> list[dict]:
    out = []
    for code in codes:
        rows = _pg_query("""
            SELECT trade_date, close, pct_chg FROM global_index_daily
            WHERE ts_code = %s ORDER BY trade_date DESC LIMIT 1
        """, (code,))
        if rows:
            out.append({"ts_code": code, "name": INDEX_NAMES.get(code, code),
                        "trade_date": str(rows[0][0]),
                        "close": float(rows[0][1]), "pct_chg": float(rows[0][2])})
    return out


def _load_news_window(hours: int = 16, limit: int = 200) -> list[dict]:
    since = datetime.now() - timedelta(hours=hours)
    rows = _pg_query("""
        SELECT pub_time, source, content FROM global_news_flash
        WHERE pub_time >= %s ORDER BY pub_time DESC LIMIT %s
    """, (since, limit))
    return [{"pub_time": str(r[0]), "source": r[1], "content": r[2] or ""}
            for r in rows]


# ── 实时兜底 (PG 无数据时直连源站) ─────────────────────────────────────────

def _fetch_us_spot_em(top_n: int = 30) -> tuple[list[dict], list[dict]]:
    """东财实时快照兜底. 返回 (hot, losers).
    fid=f3(涨跌幅): po=1 降序翻 2 页取涨幅侧, po=0 升序 1 页补跌幅侧样本."""
    stocks: list[dict] = []
    seen: set[str] = set()
    for pn, po in ((1, 1), (2, 1), (1, 0)):
        params = {
            "pn": pn, "pz": 100, "po": po, "np": 1, "fltt": 2, "invt": 2,
            "fid": "f3", "fs": "m:105,m:106,m:107",
            "fields": "f12,f14,f2,f3,f5,f6",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        }
        url = ("https://push2.eastmoney.com/api/qt/clist/get?"
               + urllib.parse.urlencode(params))
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _UA, "Referer": "https://quote.eastmoney.com/"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                diff = (json.loads(resp.read().decode("utf-8", "ignore"))
                        .get("data") or {}).get("diff") or []
        except Exception as e:
            logger.warning("us spot fallback failed: %s", e)
            break
        for it in diff:
            if it.get("f3") in (None, "-"):
                continue
            code = str(it.get("f12"))
            if code in seen:
                continue
            seen.add(code)
            stocks.append({"code": code, "name": str(it.get("f14") or ""),
                           "pct_chg": float(it["f3"]), "amount": float(it.get("f6") or 0)})
    return _pick_hot(stocks, top_n), _pick_losers(stocks, top_n)


def _fetch_kr_spot(top_n: int = 30) -> tuple[list[dict], list[dict]]:
    """Naver 实时快照兜底 (按市值取样本, 涨跌双向天然覆盖). 返回 (hot, losers)."""
    stocks: list[dict] = []
    for market in ("KOSPI", "KOSDAQ"):
        for page in range(1, 4):  # 兜底只取市值前 300/市场
            url = (f"https://m.stock.naver.com/api/stocks/marketValue/{market}"
                   f"?page={page}&pageSize=100")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _UA})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    items = (json.loads(resp.read().decode("utf-8", "ignore"))
                             .get("stocks") or [])
            except Exception as e:
                logger.warning("kr spot fallback failed: %s", e)
                break
            for s in items:
                try:
                    pct = float(str(s.get("fluctuationsRatio", "")).replace(",", ""))
                    amt = float(str(s.get("accumulatedTradingValue", "0")).replace(",", "")) * 1e6
                except ValueError:
                    continue
                stocks.append({"code": str(s.get("itemCode")), "name": str(s.get("stockName") or ""),
                               "pct_chg": pct, "amount": amt})
            if len(items) < 100:
                break
    return (_pick_hot(stocks, top_n, min_pct=2.0, min_amount=1e10),
            _pick_losers(stocks, top_n, min_pct=2.0, min_amount=1e10))


# ── LLM (DeepSeek) ─────────────────────────────────────────────────────────

def _llm_chat(system: str, user: str, max_tokens: int = 2000) -> Optional[str]:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.info("DEEPSEEK_API_KEY missing, LLM step skipped")
        return None
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            timeout=60,
        )
        resp = client.chat.completions.create(
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.2, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return None


def _extract_json(text: str) -> Any:
    m = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    body = m.group(1) if m else text
    start = min([i for i in (body.find("["), body.find("{")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no json found")
    return json.loads(body[start:] if body[start] == "{" else body[body.find("["):])


def _classify_sectors(hot: list[dict]) -> dict[str, str]:
    """热门股 → 板块/主题. LLM 批量归类, 失败降级'综合'."""
    if not hot:
        return {}
    lines = "\n".join(f"{s['code']} {s['name']}" for s in hot)
    text = _llm_chat(
        "你是股票市场行业分类助手。把给定股票归入简洁的板块/主题名(2-6字, 如: 半导体设备、"
        "AI算力、新能源车、生物医药、软件SaaS、金融、能源、消费电子、机器人、航空航天)。"
        "只输出 JSON 对象 {代码: 板块}, 不要其他内容。",
        lines, max_tokens=1500)
    if text:
        try:
            mapping = _extract_json(text)
            if isinstance(mapping, dict):
                return {str(k): str(v) for k, v in mapping.items()}
        except (ValueError, TypeError):
            pass
    return {s["code"]: "综合" for s in hot}


# ── 股票名称中文化 ─────────────────────────────────────────────────────────

def _needs_translation(name: str) -> bool:
    """名称不含任何 CJK 字符 → 需要翻译 (英文/韩文/纯代码)."""
    return bool(name) and not any("一" <= c <= "鿿" for c in name)


def _translate_names_to_chinese(hot: list[dict], market: str) -> None:
    """批量把英文/韩文股票名翻译为中文 (原地修改, 保留 name_origin 原名).

    知名公司用官方中文名 (NVIDIA→英伟达, 삼성전자→三星电子),
    不知名公司按含义翻译或音译. LLM 不可用时保持原名, 不阻断流程.
    Tushare us_basic 已带中文名的美股会被 _needs_translation 跳过.
    """
    targets = [s for s in hot if _needs_translation(str(s.get("name") or ""))]
    if not targets:
        return
    market_label = {"us": "美股", "kr": "韩国股市"}.get(market, market)
    lines = "\n".join(f"{s['code']} {s['name']}" for s in targets)
    text = _llm_chat(
        f"你是股票名称翻译助手。把给定{market_label}股票的名称翻译或查找为中文名。"
        "知名公司必须使用市场通用官方中文名 (如 NVIDIA→英伟达, Tesla→特斯拉, "
        "삼성전자→三星电子, SK하이닉스→SK海力士, 레인보우로보틱스→彩虹机器人); "
        "不知名公司按业务含义翻译, 实在无法判断再音译, 保持 2-8 个汉字, 不要带括号注释。"
        "只输出 JSON 对象 {代码: 中文名}, 不要其他内容。",
        lines, max_tokens=1200)
    if not text:
        return
    try:
        mapping = _extract_json(text)
    except (ValueError, TypeError):
        return
    if not isinstance(mapping, dict):
        return
    for s in targets:
        cn = str(mapping.get(s["code"]) or "").strip()
        if cn:
            s["name_origin"] = s["name"]
            s["name"] = cn


def _build_resonance(hot: list[dict], sectors: dict[str, str],
                     min_cluster: int = 2, direction: str = "up") -> list[dict]:
    """板块共振 = 同一板块热门股 ≥ min_cluster 只.
    direction="down" 时代表个股按跌幅排序 (跌最多在前), 供板块共振跌幅."""
    clusters: dict[str, list[dict]] = {}
    for s in hot:
        sector = sectors.get(s["code"], "综合")
        s["sector"] = sector
        clusters.setdefault(sector, []).append(s)
    out = []
    for sector, members in clusters.items():
        if len(members) < min_cluster:
            continue
        ranked = sorted(members,
                        key=lambda x: x["pct_chg"] if direction == "down" else -x["pct_chg"])
        out.append({
            "sector": sector,
            "hot_count": len(members),
            "avg_pct": round(sum(m["pct_chg"] for m in members) / len(members), 2),
            "total_amount": sum(m["amount"] for m in members),
            "stocks": [f"{m['name']}({m['pct_chg']:+.1f}%)" for m in ranked[:6]],
        })
    out.sort(key=lambda x: (-x["hot_count"], -x["total_amount"]))
    return out


def _select_news_top10(news: list[dict], market_focus: str) -> list[dict]:
    """LLM 排序选 Top10 (硬科技加权), 失败降级为最新 10 条."""
    if not news:
        return []
    if len(news) <= 10:
        candidates = news
    else:
        candidates = news[:120]
    lines = "\n".join(
        f"{i+1}. [{n['pub_time'][5:16]}] {n['content'][:120]}" for i, n in enumerate(candidates))
    text = _llm_chat(
        "你是全球财经新闻编辑。从给定快讯中选出最重要的 10 条, 侧重: "
        f"1) 硬核科技({HARD_TECH_HINT}); 2) 影响美/韩/日股市的宏观与产业事件; "
        "3) 剔除纯行情播报和重复内容。按重要性排序, 只输出 JSON 数组, 每项: "
        '{"idx": 原编号, "title": 15字内标题, "summary": 40字内摘要, '
        '"market": "美国|韩国|日本|全球", "tags": ["标签"]}。',
        f"编号列表:\n{lines}", max_tokens=2500)
    if text:
        try:
            items = _extract_json(text)
            out = []
            for rank, it in enumerate(items[:10], 1):
                idx = int(it.get("idx", 0))
                raw = candidates[idx - 1] if 1 <= idx <= len(candidates) else {}
                out.append({
                    "rank": rank,
                    "title": str(it.get("title") or raw.get("content", ""))[:60],
                    "summary": str(it.get("summary") or "")[:120],
                    "market": str(it.get("market") or "全球"),
                    "tags": [str(t) for t in (it.get("tags") or [])][:3],
                    "pub_time": raw.get("pub_time", ""),
                    "source": raw.get("source", ""),
                })
            if out:
                return out
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("news top10 parse failed: %s", e)
    # 降级: 最新 10 条
    return [{"rank": i + 1, "title": n["content"][:60], "summary": "",
             "market": "全球", "tags": [], "pub_time": n["pub_time"],
             "source": n["source"]}
            for i, n in enumerate(news[:10])]


# ── mode 入口 (统一流水线 _run_registered_mode 调用) ───────────────────────

def _run_us_morning_brief_mode(mode: str, top_n: int,
                               trade_date: Optional[str]) -> dict:
    """8:00 美股早报: 美股板块共振(涨/跌) + 热门股 + 美韩日新闻 Top10 (硬科技侧重)."""
    us_date, hot, losers, source = _load_us_hot(top_n)
    # 涨/跌两榜合并做一次翻译+归类 (hot 优先, losers 去重追加), 避免 LLM 调用翻倍
    seen = {s["code"] for s in hot}
    both = hot + [s for s in losers if s["code"] not in seen]
    _translate_names_to_chinese(both, "us")
    sectors = _classify_sectors(both)
    resonance = _build_resonance(hot, sectors)
    resonance_down = _build_resonance(losers, sectors, direction="down")
    news = _load_news_window(hours=16)
    news_top10 = _select_news_top10(news, market_focus="美国")
    indices = _load_indices(["IXIC", "DJI", "SPX"])

    return {
        "status": "success",
        "mode": mode,
        "brief_type": "us_morning",
        "trade_date": us_date,
        "picks": hot,
        "picks_down": losers,
        "total_picks": len(hot),
        "sector_resonance": resonance,
        "sector_resonance_down": resonance_down,
        "news_top10": news_top10,
        "market_strength": {
            "indices": indices,
            "snapshot_time": datetime.now().isoformat(timespec="seconds"),
        },
        "data_source": source,
    }


def _run_kr_morning_brief_mode(mode: str, top_n: int,
                               trade_date: Optional[str]) -> dict:
    """9:05 韩股早报: 韩股开盘首小时板块共振(涨/跌) + 热门股 + 韩国相关新闻."""
    kr_date, hot, losers, source = _load_kr_hot(top_n)
    seen = {s["code"] for s in hot}
    both = hot + [s for s in losers if s["code"] not in seen]
    _translate_names_to_chinese(both, "kr")
    sectors = _classify_sectors(both)
    resonance = _build_resonance(hot, sectors)
    resonance_down = _build_resonance(losers, sectors, direction="down")
    news = _load_news_window(hours=16)
    kr_related = [n for n in news if re.search(r"韩国|三星|SK|海力士|KOSPI|首尔", n["content"])]
    # 韩国相关新闻凑不齐 10 条时, 用全量窗口补足 (全球宏观同样影响韩股)
    news_top10 = _select_news_top10(kr_related if len(kr_related) >= 10 else news,
                                    market_focus="韩国")
    indices = _load_indices(["KS11", "N225"])

    return {
        "status": "success",
        "mode": mode,
        "brief_type": "kr_morning",
        "trade_date": kr_date,
        "picks": hot,
        "picks_down": losers,
        "total_picks": len(hot),
        "sector_resonance": resonance,
        "sector_resonance_down": resonance_down,
        "news_top10": news_top10,
        "market_strength": {
            "indices": indices,
            "snapshot_time": datetime.now().isoformat(timespec="seconds"),
            "note": "韩国股市开盘首小时数据 (非全日)",
        },
        "data_source": source,
    }
