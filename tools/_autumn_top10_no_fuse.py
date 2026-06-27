#!/usr/bin/env python3
"""秋神午后选股 - 无熔断版 Top10"""

import sys
import os
import json

# 设置路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'packages', 'kronos-factors')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'packages', 'kronos-data')))

from kronos_factors.engine.leader_closing import run_intraday_screening

def main():
    trade_date = '2026-06-26'
    time_slot = '14:30'
    top_n = 50

    print('=' * 90)
    print(f'  秋神龙头战法-午后选股 V5.1 (无熔断版)')
    print(f'  {trade_date} {time_slot}')
    print('=' * 90)

    # 运行选股 - 获取全部评分结果
    top, all_scores = run_intraday_screening(trade_date, time_slot, top_n)

    # 直接从all_scores取Top10（绕过熔断）
    if all_scores:
        # 按总分排序
        sorted_scores = sorted(all_scores, key=lambda x: -x.get('total_score', 0))
        top10 = sorted_scores[:10]

        print(f'\n📊 市场状态:')
        up_cnt = len([s for s in all_scores if s.get('gain_14', 0) > 0])
        print(f'  涨跌比: {up_cnt / len(all_scores) * 100:.1f}%')
        print(f'  通过初筛: {len(all_scores)} 只')

        print(f'\n' + '=' * 90)
        print(f'  Top 10 (无熔断，按原始评分排序)')
        print('=' * 90)

        header = f"{'#':<3} {'代码':<8} {'名称':<10} {'总分':<6} {'级':<3} {'涨幅':<8} {'成交':<10} {'板块涨':<8} {'板块':<12}"
        print(header)
        print('-' * 90)

        for i, s in enumerate(top10, 1):
            code = s.get('code', '')
            name = s.get('name', '')
            score = s.get('total_score', 0)
            grade = s.get('grade', 'C')
            gain = s.get('gain_14', 0)
            amount = s.get('amount_yi_est', 0)
            sector_pct = s.get('sector_change', 0)
            industry = s.get('industry', '')

            # 独苗/高潮惩罚标记
            climax = s.get('climax_penalty', 0)
            indep = s.get('independent_penalty', 0)
            risk_tags = ''
            if indep > 0:
                risk_tags += '🔹独苗'
            if climax > 0:
                risk_tags += '⚡高潮'

            row = f"{i:<3} {code:<8} {name:<10} {score:<6.0f} {grade:<3} {gain:>+7.1f}% {amount:<9.0f}亿 {sector_pct:>+7.1f}% {industry:<12} {risk_tags}"
            print(row)

        # 统计
        s_cnt = sum(1 for s in top10 if s.get('grade') == 'S')
        a_cnt = sum(1 for s in top10 if s.get('grade') == 'A')
        b_cnt = sum(1 for s in top10 if s.get('grade') == 'B')

        print(f'\n  S级={s_cnt} A级={a_cnt} B级={b_cnt}')

        # 执行计划
        print(f'\n' + '=' * 90)
        print(f'  📋 买入执行计划 (14:30无熔断版)')
        print('=' * 90)

        for i, s in enumerate(top10, 1):
            code = s.get('code', '')
            name = s.get('name', '')
            grade = s.get('grade', 'S')
            close_14 = s.get('close_14', 0) or s.get('close', 0)

            # 止损3%
            stop_loss = round(close_14 * 0.97, 2)

            # 仓位：S级20%，A级15%，B级10%
            if grade == 'S':
                pos = '20%'
            elif grade == 'A':
                pos = '15%'
            else:
                pos = '10%'

            # 动作
            seal = s.get('seal_status', '')
            if seal in ('封死可排', '封板可排'):
                action = '🟢 排板买入'
            elif seal == '拉升中':
                action = '🟢 现价买入'
            elif seal == '炸板回封':
                action = '🟡 等回封'
            else:
                action = '🟢 现价买入'

            # 风险标签
            risks = []
            if s.get('climax_penalty', 0) >= 20:
                risks.append('🔴高潮次日不买')
            elif s.get('climax_penalty', 0) >= 12:
                risks.append('⚡板块偏热')
            if s.get('independent_penalty', 0) >= 12:
                risks.append('🔸独立标的')
            elif s.get('independent_penalty', 0) >= 4:
                risks.append('🔹独苗')

            risk_str = ' '.join(risks) if risks else ''

            plan_row = f"  {i:<2} {code:<8} {name:<10} {grade:<3} {action:<15} ¥{close_14:<7.2f} ¥{stop_loss:<7.2f} {pos:<5} {risk_str}"
            print(plan_row)

        # 导出JSON
        output = {
            'date': trade_date,
            'time_slot': time_slot,
            'no_fuse': True,
            'total_screened': len(all_scores),
            'top10': [{
                'rank': i,
                'code': s.get('code'),
                'name': s.get('name'),
                'grade': s.get('grade'),
                'total_score': s.get('total_score'),
                'gain_14': s.get('gain_14', 0),
                'amount_yi': s.get('amount_yi_est', 0),
                'sector_change': s.get('sector_change', 0),
                'industry': s.get('industry'),
                'close_14': s.get('close_14', 0),
                'stop_loss': round((s.get('close_14', 0) or s.get('close', 0)) * 0.97, 2),
                'climax_penalty': s.get('climax_penalty', 0),
                'independent_penalty': s.get('independent_penalty', 0),
            } for i, s in enumerate(top10, 1)]
        }

        output_file = f'outputs/autumn_top10_no_fuse_{trade_date}.json'
        with open(output_file, 'w') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f'\n📁 已导出: {output_file}')

        # 板块分布
        print(f'\n' + '=' * 90)
        print(f'  📊 Top10板块分布')
        print('=' * 90)

        from collections import Counter
        industries = [s.get('industry', '') for s in top10]
        ind_cnt = Counter(industries)
        for ind, cnt in ind_cnt.most_common():
            pct = cnt / 10 * 100
            stocks = [s.get('name') for s in top10 if s.get('industry') == ind]
            print(f'  {ind}: {cnt}只 ({pct:.0f}%) — {", ".join(stocks)}')

    else:
        print('\n⚠️ 无符合条件标的')


if __name__ == '__main__':
    main()