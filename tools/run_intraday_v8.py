#!/usr/bin/env python3
"""一键运行 秋神午后选股模型 V8.0 + 板块共振分析"""
import sys, os, sqlite3, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'packages/kronos-factors'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Kronos/src'))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Kronos/webui/stock_screening.db')

class RowDict:
    def __init__(self, row): self._row = row
    def get(self, key, default=None):
        try: return self._row[key]
        except (IndexError, KeyError): return default
    def __getitem__(self, key): return self._row[key]
    def keys(self): return self._row.keys()
    def __iter__(self): return iter(self._row.keys())

class CursorWrapper:
    def __init__(self, cur): self._cur = cur
    def fetchone(self):
        r = self._cur.fetchone()
        return RowDict(r) if r else None
    def fetchall(self):
        return [RowDict(r) for r in self._cur.fetchall()]

class SQLiteAdapter:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
    def execute(self, sql, params=None):
        cur = self.conn.cursor()
        if params: cur.execute(sql, params)
        else: cur.execute(sql)
        return CursorWrapper(cur)
    def _get_conn(self): return None
    def _put_conn(self, c): pass

from kronos_factors.scorer._db_stub import set_db_adapter
set_db_adapter(SQLiteAdapter(DB_PATH))

import kronos_factors.engine.leader_intraday as li
from datetime import datetime

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--date', default='2026-06-15')
    p.add_argument('--time', default='14:40')
    p.add_argument('--top-n', type=int, default=20)
    args = p.parse_args()

    trade_date = args.date
    time_slot = args.time
    top_n = args.top_n

    print('=' * 60)
    print(f'  秋神午后选股模型 V8.0')
    print(f'  数据日期: {trade_date}  {time_slot}')
    print('=' * 60)
    print()

    t0 = time.time()
    li._sector_climax_cache.clear()
    db = SQLiteAdapter(DB_PATH)

    # Step 1: Data loading
    snapshot = li.get_intraday_snapshot(db, trade_date, time_slot)
    print(f'  [1/7] 快照: {len(snapshot)} 只')
    pre_closes = li.get_pre_close_map(db, trade_date)
    print(f'  [2/7] pre_close: {len(pre_closes)} 只')
    limit_map = li.get_intraday_limit_status(db, trade_date)
    sealed_14 = sum(1 for v in limit_map.values() if v.get('is_sealed_by_14'))
    print(f'  [3/7] 已封板: {len(limit_map)} 只 (14:00前:{sealed_14})')

    stocks = db.execute(
        "SELECT code, name, industry FROM stocks WHERE is_st=0 "
        "AND name NOT LIKE '%ST%' AND (float_mv IS NULL OR float_mv >= 20)"
    ).fetchall()
    print(f'  [4/7] 股票池: {len(stocks)} 只')

    # Step 2: Pre-compute
    t_pre = time.time()
    concept_stats = li._precompute_concept_stats(db, trade_date, time_slot, snapshot=snapshot, pre_closes=pre_closes)
    industry_stats = li._precompute_industry_stats_fallback(db, trade_date, time_slot) if not concept_stats else {}
    kline_cache = li._prefetch_kline_batch(db, trade_date)
    mins_agg_cache = li._prefetch_mins_agg_batch(db, trade_date, time_slot)
    ths_covered = len(set(cs.get('concept_code', '') for cs in concept_stats.values()))
    print(f'  [5/7] 预计算: {ths_covered}THS概念/{len(concept_stats)}股 + '
          f'{len(industry_stats)}行业 + {len(kline_cache)}K线 + {len(mins_agg_cache)}分钟, {time.time()-t_pre:.1f}s')

    # Step 3: Score
    scores = []
    skipped = 0
    for r in stocks:
        c = r["code"]
        if c not in snapshot or c not in pre_closes:
            skipped += 1
            continue
        try:
            res = li.score_intraday_stock(
                c, r["name"], r["industry"] or "其他",
                snapshot[c], pre_closes[c], db,
                trade_date, time_slot, limit_map,
                industry_stats=industry_stats if industry_stats else None,
                concept_stats=concept_stats if concept_stats else None,
                kline_cache=kline_cache,
                mins_agg_cache=mins_agg_cache
            )
            if res: scores.append(res)
        except Exception:
            continue

    print(f'  [6/7] 评分完成: {len(scores)} 只通过 ({skipped} 缺失数据)')

    # Step 4: Market breadth & filters
    prev_date_row = db.execute(
        "SELECT MAX(trade_date) FROM daily_kline WHERE trade_date < ?", (trade_date,)
    ).fetchone()
    prev_date = prev_date_row.get("trade_date") if prev_date_row else None

    breadth = 50
    if prev_date:
        breadth_row = db.execute(
            "SELECT SUM(CASE WHEN m.close > d.close THEN 1 ELSE 0 END) as up, "
            "SUM(CASE WHEN m.close < d.close THEN 1 ELSE 0 END) as down "
            "FROM (SELECT DISTINCT ts_code, close FROM stk_mins "
            "      WHERE trade_time >= ? AND trade_time <= ? AND freq='5min') m "
            "JOIN daily_kline d ON d.code=SUBSTR(m.ts_code,1,6) AND d.trade_date=? "
            "WHERE d.close > 0",
            (f"{trade_date} 09:00:00", f"{trade_date} {time_slot}:59", prev_date)
        ).fetchone()
        if breadth_row:
            up = breadth_row["up"] or 0
            down = breadth_row["down"] or 0
            breadth = up / max(1, up + down) * 100

    print(f'  [7/7] 涨跌比: {breadth:.0f}%')

    # P20 假活跃熔断
    if 20 <= len(scores) < 40:
        print(f'\n  🛑 假活跃熔断: {len(scores)}只(20-40区间), 空仓!')
        return

    if len(scores) < 30:
        print(f'  ⚠️ 弱市预警: 仅{len(scores)}只, 建议谨慎')

    # Market breadth bonus
    if breadth < 30: market_breadth_bonus = 5
    elif breadth < 50: market_breadth_bonus = 3
    elif breadth < 65: market_breadth_bonus = 0
    else: market_breadth_bonus = -2

    # Effective N
    effective_n = top_n
    market_frenzy = len(scores) > 120
    if market_frenzy:
        print(f'  🔥 市场狂热: {len(scores)}只')

    if breadth < 40:
        effective_n = max(5, int(top_n * 0.5))
        print(f'  🌧️ 弱市: Top-N -> {effective_n}')
    elif breadth < 55:
        effective_n = max(8, int(top_n * 0.7))
        print(f'  ⛅ 中性: Top-N -> {effective_n}')

    if market_frenzy:
        effective_n = max(5, int(effective_n * 0.5))
        print(f'  🔥 狂热收紧: effective_n -> {effective_n}')

    # Resonance
    if scores:
        avg_res = sum(s.get('resonance_score', 0) for s in scores) / len(scores)
        print(f'  📡 共振均值: {avg_res:.1f}')
        if avg_res <= 5:
            effective_n = max(3, int(effective_n * 0.5))
            print(f'  🔻 共振弱: effective_n -> {effective_n}')
        if avg_res <= 4:
            effective_n = max(1, int(effective_n * 0.3))
            print(f'  🛑 共振极弱: effective_n -> {effective_n}')

    # Weekday
    dow = datetime.strptime(trade_date, "%Y-%m-%d").weekday()
    if dow == 0:
        effective_n = min(top_n, int(effective_n * 1.3))
        print(f'  📈 周一效应: effective_n -> {effective_n}')
    elif dow == 4:
        effective_n = max(3, int(effective_n * 0.7))
        print(f'  📉 周五减仓: effective_n -> {effective_n}')

    # Prev day protection
    if prev_date:
        prev_breadth = db.execute(
            "SELECT SUM(CASE WHEN a.close > b.close THEN 1 ELSE 0 END) as up, "
            "SUM(CASE WHEN a.close < b.close THEN 1 ELSE 0 END) as down "
            "FROM daily_kline a "
            "JOIN daily_kline b ON a.code=b.code AND b.trade_date IN "
            "(SELECT MAX(trade_date) FROM daily_kline WHERE trade_date < ?) "
            "WHERE a.trade_date=?",
            (prev_date, prev_date)
        ).fetchone()
        if prev_breadth:
            prev_up = prev_breadth["up"] or 0
            prev_down = prev_breadth["down"] or 0
            prev_br = prev_up / max(1, prev_up + prev_down) * 100
            if prev_br > 65 and breadth < 50:
                effective_n = max(3, int(effective_n * 0.5))
                print(f'  🛑 前日强({prev_br:.0f}%)->今日弱({breadth:.0f}%): effective_n -> {effective_n}')

    # Sort
    scores.sort(key=lambda x: -x["total_score"])

    # Normalize
    if len(scores) >= 5:
        raw_max = scores[0]["total_score"]
        raw_min = scores[-1]["total_score"]
        score_range = raw_max - raw_min if raw_max > raw_min else 1
        for s in scores:
            s["total_score_raw"] = s["total_score"]
            s["total_score"] = round((s["total_score"] - raw_min) / score_range * 100, 1)
            s["total_score"] += market_breadth_bonus
            ns = s["total_score"]
            s["grade"] = "S" if ns >= 75 else ("A" if ns >= 60 else ("B" if ns >= 45 else "C"))

    # Concept dedup
    deduped = []
    concept_counts = {}
    for s in scores:
        c = s.get("concept", "") or s.get("industry", "")
        if concept_counts.get(c, 0) < 2:
            deduped.append(s)
            concept_counts[c] = concept_counts.get(c, 0) + 1
    if len(deduped) < len(scores):
        print(f'  🔄 概念去重: {len(scores)} -> {len(deduped)}')

    top = deduped[:effective_n]
    elapsed = time.time() - t0

    if not top:
        print(f'\n  ⚠️ 无符合条件标的 (耗时 {elapsed:.1f}s)')
        return

    # ═══════════════════════════════════════════════════
    # OUTPUT: 选股结果
    # ═══════════════════════════════════════════════════
    print(f'\n{"=" * 120}')
    print(f'  秋神龙头战法-盘中 V8.0 — {trade_date} {time_slot}  Top {len(top)}')
    print(f'{"=" * 120}')
    ths_cnt = sum(1 for s in top if s.get("concept_code"))
    fresh_cnt = sum(1 for s in top if s.get("freshness_penalty", 0) > 0)
    climax_cnt = sum(1 for s in top if s.get("climax_penalty", 0) > 0)
    indep_cnt = sum(1 for s in top if s.get("independent_penalty", 0) > 0)
    print(f'  THS概念覆盖:{ths_cnt}/{len(top)} | 新鲜度惩罚:{fresh_cnt} | 高潮惩罚:{climax_cnt} | 独立惩罚:{indep_cnt}')
    print()
    print(f'  {"#":<3} {"代码":<8} {"名称":<8} {"总分":<6} {"级":<3} {"涨":<8} {"预估":<8} '
          f'{"同概念":<6} {"概念":<12} {"板块涨":<7} {"封板":<8} {"ATR":<5}')
    print(f'  {"-" * 105}')
    for i, s in enumerate(top, 1):
        concept_display = (s.get('concept', '') or s['industry'])[:12]
        seals = s.get('seal_status', '')[:8]
        atr = f'{s.get("atr_pct", 0):.1f}%' if s.get('atr_pct') else '-'
        print(f'  {i:<3} {s["code"]:<8} {s["name"]:<8} {s["total_score"]:<6.0f} {s["grade"]:<3} '
              f'{s["gain_14"]:>+6.1f}% {s["amount_yi_est"]:<6.0f}亿 {s.get("peer_count",0):<6} '
              f'{concept_display:<12} {s.get("sector_change",0):>+5.1f}% {seals:<8} {atr:<5}')

    sc = sum(1 for s in top if s['grade'] == 'S')
    ac = sum(1 for s in top if s['grade'] == 'A')
    bc = sum(1 for s in top if s['grade'] == 'B')
    print(f'\n  📊 S级={sc}  A级={ac}  B级={bc}')

    # ═══════════════════════════════════════════════════
    # OUTPUT: 交易计划
    # ═══════════════════════════════════════════════════
    plans = li.generate_intraday_plan(top)
    print(f'\n{"=" * 105}')
    print(f'  📋 盘中买入执行计划 V8.0 (ATR动态止损 + 分级止盈)')
    print(f'{"=" * 105}')
    print(f'  {"代码":<8} {"名称":<8} {"级":<3} {"动作":<22} {"入场":<8} {"止损":<8} {"止盈":<8} {"仓位":<6}')
    print(f'  {"-" * 85}')
    for p in plans:
        tp = f'{p.get("take_profit", 0):.2f}' if p.get('take_profit') else '-'
        print(f'  {p["code"]:<8} {p["name"]:<8} {p["grade"]:<3} {p["action"]:<22} '
              f'{p["entry_price"]:<8} {p["stop_loss"]:<8} {tp:<8} {p["position"]:<6}')
    for p in plans:
        tags = p.get('risk_tags', [])
        if tags:
            print(f'      {p["code"]} ⚠️ {" | ".join(tags)}')

    # ═══════════════════════════════════════════════════
    # OUTPUT: 板块共振详细分析
    # ═══════════════════════════════════════════════════
    print(f'\n{"=" * 100}')
    print(f'  📊 板块共振详细分析')
    print(f'{"=" * 100}')

    from collections import defaultdict
    sectors = defaultdict(list)
    for s in scores[:min(200, len(scores))]:
        concept = s.get('concept', '') or s.get('industry', '')
        if concept:
            sectors[concept].append(s)

    sorted_sec = sorted(sectors.items(), key=lambda x: len(x[1]), reverse=True)

    print(f'  {"板块":<20} {"股数":<5} {"均分":<6} {"均涨幅":<7} {"共振信号":<16} {"风险":<20} {"前排标的"}')
    print(f'  {"-" * 100}')
    for sector, stocks in sorted_sec[:25]:
        avg_score = sum(s['total_score'] for s in stocks) / len(stocks)
        avg_gain = sum(s['gain_14'] for s in stocks) / len(stocks)
        top_s = max(stocks, key=lambda x: x['total_score'])

        # 共振信号
        r = top_s.get('resonance_score', 0)
        sm = top_s.get('sector_momentum_score', 0)
        sp = top_s.get('sector_change', 0)
        if r >= 8 and sp < 0:
            res_tag = '🟢 板块抗跌最佳'
        elif r >= 8:
            res_tag = '🟢 板块超跌反弹'
        elif r >= 5 and sp < 0:
            res_tag = '🟡 板块逆市走强'
        elif r >= 5:
            res_tag = '🟡 温和共振'
        else:
            res_tag = '⚪ 双强/中性'

        # 风险
        risks = []
        cpen = top_s.get('climax_penalty', 0)
        if cpen >= 20: risks.append('🔴高潮次日')
        elif cpen >= 12: risks.append('🟡板块偏热')
        fpen = top_s.get('freshness_penalty', 0)
        if fpen >= 12: risks.append('🍂严重透支')
        elif fpen >= 6: risks.append('🍃轻度透支')
        ipen = top_s.get('independent_penalty', 0)
        if ipen >= 10: risks.append('⚠️独立标的')
        risk_str = ' '.join(risks) if risks else '✅ 正常'

        # 前排标的
        top_stocks = sorted(stocks, key=lambda x: x['total_score'], reverse=True)[:3]
        tops_str = ' | '.join(f'{s["code"]}({s["total_score"]:.0f})' for s in top_stocks)

        print(f'  {sector:<20} {len(stocks):<5} {avg_score:<6.0f} {avg_gain:>+5.1f}%  {res_tag:<16} {risk_str:<20} {tops_str}')

    # ═══════════════════════════════════════════════════
    # OUTPUT: 选股清单
    # ═══════════════════════════════════════════════════
    print(f'\n{"=" * 120}')
    print(f'  📋 选股清单 — {trade_date} {time_slot}  ({len(top)}只)')
    print(f'{"=" * 120}')
    for i, s in enumerate(top, 1):
        concept = s.get('concept', '') or s.get('industry', '')
        seals = s.get('seal_status', '')
        dist = s.get('dist_to_limit', 0)
        atr = s.get('atr_pct', 0)
        res = s.get('resonance_score', 0)
        peer = s.get('peer_count', 0)
        sm = s.get('sector_momentum_score', 0)
        vol_surge = s.get('vol_surge', 0)

        # 风险标签
        risk_info = ''
        cpen = s.get('climax_penalty', 0)
        if cpen >= 20: risk_info += ' 🔴高潮次日不买'
        elif cpen >= 12: risk_info += ' ⚡板块偏热'
        fpen = s.get('freshness_penalty', 0)
        if fpen >= 6: risk_info += ' 🍂' + str(fpen) + '分透支'

        print(f'  {i:>2}. {s["code"]} {s["name"]:<8} │ {s["grade"]}级 │ '
              f'总分:{s["total_score"]:.0f} │ '
              f'涨幅:{s["gain_14"]:>+5.1f}% │ '
              f'成交:{s["amount_yi_est"]:.0f}亿 │ '
              f'距涨停:{dist:.1f}% │ '
              f'共振:{res} │ '
              f'板块动量:{sm} │ '
              f'量比:{vol_surge:.1f}x │ '
              f'龙头排名:{s.get("intra_rank",0)}/{peer} │ '
              f'概念:{concept}{risk_info}')

    print(f'\n  ⏱️ 总耗时: {elapsed:.1f}s')

    # Determine overall market assessment
    print(f'\n  {"=" * 60}')
    print(f'  📊 市场环境评估')
    print(f'  {"=" * 60}')
    assessments = []
    if breadth >= 65:
        assessments.append('🟢 强市: 涨跌比 ' + f'{breadth:.0f}%')
    elif breadth >= 50:
        assessments.append('🟡 中性: 涨跌比 ' + f'{breadth:.0f}%')
    elif breadth >= 30:
        assessments.append('🟠 弱市: 涨跌比 ' + f'{breadth:.0f}%')
    else:
        assessments.append('🔴 极弱市: 涨跌比 ' + f'{breadth:.0f}%')

    if scores:
        avg_res = sum(s.get('resonance_score', 0) for s in scores) / len(scores)
        assessments.append(f'共振均值: {avg_res:.1f}')
        if avg_res >= 6:
            assessments.append('✅ 共振正常, 正常仓位')
        elif avg_res >= 5:
            assessments.append('⚠️ 共振偏弱, 减半仓')
        else:
            assessments.append('🔴 共振极弱, 建议空仓')

    climax_hit = sum(1 for s in scores if s.get('climax_penalty', 0) >= 12)
    if climax_hit > len(scores) * 0.3:
        assessments.append(f'🔴 板块高潮占比高 ({climax_hit}/{len(scores)})')

    if len(scores) < 30:
        assessments.append('⚠️ 弱市: 候选标的稀少')
    elif len(scores) > 120:
        assessments.append('🔥 狂热市: 候选标的过多')

    for a in assessments:
        print(f'  {a}')

if __name__ == '__main__':
    main()
