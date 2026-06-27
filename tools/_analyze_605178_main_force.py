#!/usr/bin/env python3
"""分析新洁能 (605111) — 主力资金流向 + 五维诊断"""

import sys
import os

# Add packages path
_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages"))
for pkg in ["kronos-factors", "kronos-core", "kronos-data"]:
    path = os.path.join(_PACKAGES, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import asyncio
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

# ═══════════════════════════════════════════════════════════════════════════
# 主力资金分析核心逻辑 (来自 diagnosis_engine.py)
# ═══════════════════════════════════════════════════════════════════════════

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

def analyze_main_force_flow(code: str, days: int = 5):
    """分析主力资金流向 (来自 diagnosis_engine._score_capital_flow 逻辑)

    判断是否主力拉升出货的关键信号：
    1. 主力资金连续净流入但股价滞涨 → 拉升出货嫌疑
    2. 主力资金大额流入后突然流出 → 出货完成信号
    3. 超大单/大单净流入 vs 中小单净流入 → 主力真实意图
    """
    engine = create_engine(PG_URL)

    print(f"\n{'=' * 90}")
    print(f"  📊 新洁能 (605111) — 主力资金流向分析 (近{days}日)")
    print(f"{'=' * 90}\n")

    with engine.connect() as conn:
        # 1. 基础信息
        stock_info = conn.execute(text(
            "SELECT code, name, industry FROM stocks WHERE code = :code"
        ), {"code": code}).fetchone()

        if not stock_info:
            print(f"❌ 股票 {code} 不存在数据库中")
            return

        info_dict = dict(stock_info._mapping)
        print(f"股票: {info_dict['name']} ({info_dict['code']}) | 行业: {info_dict['industry']}")

        # 2. 最新行情
        latest = conn.execute(text(
            "SELECT trade_date, close, change_pct, volume, amount "
            "FROM daily_kline WHERE code = :code "
            "ORDER BY trade_date DESC LIMIT 1"
        ), {"code": code}).fetchone()

        if latest:
            latest_dict = dict(latest._mapping)
            print(f"\n📅 最新交易日: {latest_dict['trade_date']}")
            close = latest_dict.get('close') or 0
            change_pct = latest_dict.get('change_pct') or 0
            volume = latest_dict.get('volume') or 0
            amount = latest_dict.get('amount') or 0
            print(f"   收盘价: ¥{close:.2f} | 涨跌: {change_pct:+.2f}%")
            print(f"   成交量: {volume/10000:.1f}万手 | 成交额: {amount/100000000:.2f}亿")

        # 3. 主力资金流向 (近N日)
        mf_sql = f"""
            SELECT trade_date, net_mf_amount, buy_elg_amount, buy_lg_amount,
                   buy_md_amount, buy_sm_amount, sell_elg_amount, sell_lg_amount
            FROM moneyflow WHERE code = :code
            AND trade_date >= CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY trade_date DESC
        """
        mf_rows = conn.execute(text(mf_sql), {"code": code}).fetchall()

        if not mf_rows:
            print(f"\n⚠️ 无主力资金数据")
            return

        print(f"\n{'─' * 90}")
        print(f"{'日期':<12} {'主力净流':<12} {'超大单':<12} {'大单':<12} {'中单':<12} {'小单':<12} {'股价涨跌':<10}")
        print(f"{'─' * 90}")

        total_main_flow = 0
        super_large_total = 0
        large_total = 0

        for row in mf_rows:
            row_dict = dict(row._mapping)
            date = row_dict['trade_date']
            net_mf = row_dict['net_mf_amount'] or 0  # 主力净流入
            super_large = row_dict['buy_elg_amount'] or 0  # 超大单买入净额
            large = row_dict['buy_lg_amount'] or 0  # 大单买入净额
            mid = row_dict['buy_md_amount'] or 0
            small = row_dict['buy_sm_amount'] or 0

            total_main_flow += net_mf
            super_large_total += super_large
            large_total += large

            # 获取当日涨跌
            kline = conn.execute(text(
                "SELECT change_pct FROM daily_kline WHERE code = :code AND trade_date = :date"
            ), {"code": code, "date": date}).fetchone()

            pct = dict(kline._mapping).get('change_pct') or 0 if kline else 0

            net_str = f"{net_mf/10000:+.1f}万" if abs(net_mf) > 10000 else f"{net_mf:+.0f}"
            sl_str = f"{super_large/10000:+.1f}万" if abs(super_large) > 10000 else f"{super_large:+.0f}"
            lg_str = f"{large/10000:+.1f}万" if abs(large) > 10000 else f"{large:+.0f}"

            print(f"{date:<12} {net_str:<12} {sl_str:<12} {lg_str:<12} "
                  f"{mid/10000:+.1f}万{'':<4} {small/10000:+.1f}万{'':<4} {pct:+.2f}%")

        print(f"{'─' * 90}")

        # 4. 主力资金汇总判断
        avg_main_flow = total_main_flow / len(mf_rows) if mf_rows else 0

        print(f"\n📊 主力资金汇总:")
        print(f"   近{days}日主力净流入: {total_main_flow/10000:+.1f}万元 (日均 {avg_main_flow/10000:+.1f}万)")
        print(f"   超大单累计: {super_large_total/10000:+.1f}万 | 大单累计: {large_total/10000:+.1f}万")

        # 5. 判断是否拉升出货
        print(f"\n{'=' * 90}")
        print(f"  🔍 主力拉升出货判断")
        print(f"{'=' * 90}\n")

        signals = []
        verdict = "不明"

        # 信号1: 主力大幅流入但股价滞涨
        if total_main_flow > 50000:  # diagnosis_engine阈值
            signals.append("✓ 主力资金大幅流入 (近5日净流入>5亿)")
            # 检查股价涨幅
            price_change = conn.execute(text(
                "SELECT close FROM daily_kline WHERE code = :code "
                "ORDER BY trade_date DESC LIMIT 6"
            ), {"code": code}).fetchall()

            if len(price_change) >= 2:
                recent_close = dict(price_change[0]._mapping)['close']
                prev_close = dict(price_change[-1]._mapping)['close']
                price_pct = (recent_close - prev_close) / prev_close * 100

                if price_pct < 3:
                    signals.append("⚠️ 主力流入但股价涨幅不大 (<3%)")
                    signals.append("⚠️ 嫌疑：主力可能在拉升出货")
                    verdict = "拉升出货嫌疑"
                else:
                    signals.append(f"✓ 股价同步上涨 {price_pct:+.2f}%")
                    verdict = "正常上涨"

        # 信号2: 主力流入后突然流出
        if len(mf_rows) >= 2:
            today_dict = dict(mf_rows[0]._mapping)
            prev_dict = dict(mf_rows[1]._mapping)
            today_mf = today_dict['net_mf_amount'] or 0
            prev_mf = prev_dict['net_mf_amount'] or 0

            if prev_mf > 0 and today_mf < 0:
                signals.append("⚠️ 主力前日流入今日流出")
                if today_mf < -10000:
                    signals.append("⚠️ 流出量较大 (>1亿)")
                    verdict = "出货信号"

        # 信号3: 超大单 vs 小单对比
        small_total = sum(dict(r._mapping)['buy_sm_amount'] or 0 for r in mf_rows)

        if super_large_total > 0 and small_total < 0:
            signals.append("✓ 超大单流入 + 小单流出")
            signals.append("⚠️ 嫌疑：主力买入诱多，散户卖出")

        # 信号4: 北向资金
        nb_rows = conn.execute(text(
            "SELECT trade_date, net_mf_amount FROM moneyflow WHERE code = :code "
            "AND trade_date >= CURRENT_DATE - INTERVAL '30 days' "
            "ORDER BY trade_date DESC LIMIT 30"
        ), {"code": code}).fetchall()

        nb_total = sum(dict(r._mapping)['net_mf_amount'] or 0 for r in nb_rows)
        if nb_total > 10000:
            signals.append(f"✓ 北向30日净流入: {nb_total/10000:+.1f}万")
        elif nb_total < -10000:
            signals.append(f"⚠️ 北向30日净流出: {nb_total/10000:+.1f}万")

        # 输出判断
        for sig in signals:
            print(f"   {sig}")

        print(f"\n   📌 结论: {verdict}")

        # 6. 龙虎榜分析
        lb_rows = conn.execute(text(
            "SELECT trade_date, net_amount, reason "
            "FROM top_list WHERE code = :code "
            "AND trade_date >= CURRENT_DATE - INTERVAL '10 days' "
            "ORDER BY trade_date DESC"
        ), {"code": code}).fetchall()

        if lb_rows:
            print(f"\n{'─' * 90}")
            print(f"  📋 龙虎榜动向 (近10日)")
            print(f"{'─' * 90}")
            lb_total = sum(dict(r._mapping).get('net_amount') or 0 for r in lb_rows)

            for row in lb_rows:
                lb_dict = dict(row._mapping)
                net_amt = lb_dict.get('net_amount') or 0
                reason = lb_dict.get('reason') or '日常交易'
                print(f"   {lb_dict['trade_date']}: 净买入 {net_amt/10000:+.1f}万 | "
                      f"原因: {reason}")

            if lb_total > 5000:
                print(f"\n   ✓ 龙虎榜累计净买入: {lb_total/10000:+.1f}万 (机构看好)")

        # 7. 融资融券
        mg_row = conn.execute(text(
            "SELECT trade_date, rzye, rzmre FROM margin_detail "
            "WHERE code = :code ORDER BY trade_date DESC LIMIT 5"
        ), {"code": code}).fetchone()

        if mg_row:
            print(f"\n{'─' * 90}")
            print(f"  💰 融资融券")
            print(f"{'─' * 90}")
            mg_dict = dict(mg_row._mapping)
            rzye = mg_dict.get('rzye') or 0
            rzmre = mg_dict.get('rzmre') or 0
            print(f"   {mg_dict['trade_date']}: 融资余额 {rzye/100000000:.2f}亿")
            if rzmre:
                print(f"   融资买入额: {rzmre/10000:.1f}万")

        print(f"\n{'=' * 90}\n")


if __name__ == "__main__":
    # 新洁能股票代码: 605111 (半导体行业)
    analyze_main_force_flow("605111", days=10)