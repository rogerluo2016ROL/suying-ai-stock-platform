#!/usr/bin/env python3
"""生成 v2 vs v3 6月复利曲线对比 HTML 图表"""
import json, numpy as np
from collections import defaultdict

def compound_curve(fn, label):
    with open(fn) as f:
        data = json.load(f)
    valid = [p for p in data['picks'] if p.get('next_day_return') is not None]
    daily = defaultdict(list)
    for p in valid:
        daily[p['trade_date']].append(p['next_day_return'])

    dates = sorted(daily.keys())
    cap = 1_000_000
    curve = []
    for td in dates:
        day_ret = np.mean(daily[td])
        cap *= (1 + day_ret / 100)
        curve.append({'date': td, 'capital': round(cap), 'day_ret': round(day_ret, 2), 'n': len(daily[td])})
    return curve, dates, valid

v2_curve, v2_dates, v2_picks = compound_curve('outputs/backtest_bi_trend_2026-06_v2.json', 'v2')
v3_curve, v3_dates, v3_picks = compound_curve('outputs/backtest_bi_trend_2026-06_v3.json', 'v3')

# Merge dates for x-axis
all_dates = sorted(set(v2_dates + v3_dates))

# Build ECharts data
v2_data = []
v3_data = []
v2_ret = []
v3_ret = []

for td in all_dates:
    v2p = next((p for p in v2_curve if p['date'] == td), None)
    v3p = next((p for p in v3_curve if p['date'] == td), None)
    v2_data.append(v2p['capital'] if v2p else None)
    v3_data.append(v3p['capital'] if v3p else None)
    v2_ret.append(v2p['day_ret'] if v2p else None)
    v3_ret.append(v3p['day_ret'] if v3p else None)

# Annotations for key events
# Find 06-08 (market circuit breaker) and 06-10 (big drop day)
markpoints = []
for i, td in enumerate(all_dates):
    if td == '2026-06-08':
        markpoints.append({'name': '熔断', 'coord': [td, 1018000], 'value': '🔒 熔断', 'itemStyle': {'color': '#ff9800'}})

html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>毕师傅 v2 vs v3 6月复利曲线</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f1923; color: #e0e0e0; margin: 0; padding: 20px; }}
  h2 {{ text-align: center; color: #4fc3f7; margin-bottom: 5px; }}
  .subtitle {{ text-align: center; color: #90a4ae; font-size: 14px; margin-bottom: 10px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .card {{ background: #1a2332; border-radius: 12px; padding: 20px; }}
  .card h3 {{ margin: 0 0 15px 0; color: #81c784; font-size: 16px; }}
  .stat {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #263238; }}
  .stat .label {{ color: #90a4ae; }}
  .stat .value {{ font-weight: bold; }}
  .up {{ color: #4caf50; }}
  .down {{ color: #ef5350; }}
  .container {{ width: 100%; height: 500px; }}
</style>
</head>
<body>
<h2>毕师傅硬核科技 — v2 vs v3 6月复利曲线对比</h2>
<div class="subtitle">2026-06-01 进场 → 06-18 离场 | 100万起投 | 等权每日调仓</div>

<div class="grid">
  <div class="card">
    <h3>📊 v2 (第一次回测)</h3>
    <div class="stat"><span class="label">最终市值</span><span class="value" style="color:#66bb6a">¥{v2_curve[-1]['capital']:,}</span></div>
    <div class="stat"><span class="label">总收益</span><span class="value up">+{(v2_curve[-1]['capital']-1000000)/10000:.1f}%</span></div>
    <div class="stat"><span class="label">交易笔数</span><span class="value">{len(v2_picks)}</span></div>
    <div class="stat"><span class="label">胜率</span><span class="value">{sum(1 for p in v2_picks if p['next_day_return']>0)/len(v2_picks)*100:.1f}%</span></div>
    <div class="stat"><span class="label">均值收益</span><span class="value">{np.mean([p['next_day_return'] for p in v2_picks]):+.2f}%</span></div>
    <div class="stat"><span class="label">最大回撤</span><span class="value down">{min(v2_data)-1000000:,.0f}</span></div>
  </div>
  <div class="card">
    <h3>📊 v3 (第二次回测)</h3>
    <div class="stat"><span class="label">最终市值</span><span class="value" style="color:#66bb6a">¥{v3_curve[-1]['capital']:,}</span></div>
    <div class="stat"><span class="label">总收益</span><span class="value up">+{(v3_curve[-1]['capital']-1000000)/10000:.1f}%</span></div>
    <div class="stat"><span class="label">交易笔数</span><span class="value">{len(v3_picks)}</span></div>
    <div class="stat"><span class="label">胜率</span><span class="value">{sum(1 for p in v3_picks if p['next_day_return']>0)/len(v3_picks)*100:.1f}%</span></div>
    <div class="stat"><span class="label">均值收益</span><span class="value">{np.mean([p['next_day_return'] for p in v3_picks]):+.2f}%</span></div>
    <div class="stat"><span class="label">最大回撤</span><span class="value down">{min(v3_data)-1000000:,.0f}</span></div>
  </div>
</div>

<div class="container" id="chart"></div>

<script>
var chart = echarts.init(document.getElementById('chart'));
var dates = {json.dumps(all_dates)};
var v2Data = {json.dumps(v2_data)};
var v3Data = {json.dumps(v3_data)};
var v2Ret = {json.dumps(v2_ret)};
var v3Ret = {json.dumps(v3_ret)};

var option = {{
  tooltip: {{
    trigger: 'axis',
    backgroundColor: 'rgba(20,30,40,0.95)',
    borderColor: '#37474f',
    textStyle: {{ color: '#e0e0e0' }},
    formatter: function(params) {{
      var s = '<b>' + params[0].axisValue + '</b><br/>';
      for (var i = 0; i < params.length; i++) {{
        var p = params[i];
        if (p.value === null || p.value === undefined || p.value === '-') continue;
        var prefix = p.seriesName === 'v2' ? '🟡' : '🟢';
        s += prefix + ' ' + p.seriesName + ': <b>¥' + p.value.toLocaleString() + '</b>';
        var ret = p.seriesName === 'v2' ? v2Ret[p.dataIndex] : v3Ret[p.dataIndex];
        if (ret != null) s += ' (' + (ret>0?'+':'') + ret.toFixed(2) + '%)';
        s += '<br/>';
      }}
      return s;
    }}
  }},
  legend: {{
    data: ['v2 (第一次)', 'v3 (第二次)'],
    textStyle: {{ color: '#90a4ae' }},
    top: 10
  }},
  grid: {{
    left: '8%',
    right: '5%',
    top: '15%',
    bottom: '8%'
  }},
  xAxis: {{
    type: 'category',
    data: dates,
    axisLine: {{ lineStyle: {{ color: '#37474f' }} }},
    axisLabel: {{
      color: '#90a4ae',
      formatter: function(v) {{ return v.substring(5); }}
    }},
    splitLine: {{ show: false }}
  }},
  yAxis: {{
    type: 'value',
    name: '市值 (元)',
    nameTextStyle: {{ color: '#90a4ae' }},
    axisLabel: {{
      color: '#90a4ae',
      formatter: function(v) {{ return '¥' + (v/10000).toFixed(0) + '万'; }}
    }},
    splitLine: {{ lineStyle: {{ color: '#263238', type: 'dashed' }} }},
    min: 880000,
    max: 1160000
  }},
  series: [
    {{
      name: 'v2 (第一次)',
      type: 'line',
      data: v2Data,
      connectNulls: false,
      lineStyle: {{ color: '#ffb74d', width: 2.5 }},
      itemStyle: {{ color: '#ffb74d' }},
      symbol: 'circle',
      symbolSize: 6,
      markLine: {{
        silent: true,
        symbol: 'none',
        lineStyle: {{ color: '#ffb74d', type: 'dashed', width: 1 }},
        data: [{{ yAxis: 1000000, label: {{ formatter: '本金线', color: '#ffb74d' }} }}]
      }},
      markPoint: {{
        data: [
          {{ name: '终点', coord: ['2026-06-17', {v2_data[-1]}], value: '¥' + ({v2_data[-1]}/10000).toFixed(1) + '万', symbol: 'pin', symbolSize: 40, itemStyle: {{ color: '#ffb74d' }} }}
        ]
      }}
    }},
    {{
      name: 'v3 (第二次)',
      type: 'line',
      data: v3Data,
      connectNulls: false,
      lineStyle: {{ color: '#66bb6a', width: 2.5 }},
      itemStyle: {{ color: '#66bb6a' }},
      symbol: 'diamond',
      symbolSize: 7,
      markPoint: {{
        data: [
          {{ name: '最大回撤', coord: ['2026-06-10', {min(v3_data)}], value: '-¥' + Math.abs({min(v3_data)}-1000000)/10000 + '万', symbol: 'triangle', symbolSize: 20, symbolRotate: 180, itemStyle: {{ color: '#ef5350' }} }},
          {{ name: '终点', coord: ['2026-06-17', {v3_data[-1]}], value: '¥' + ({v3_data[-1]}/10000).toFixed(1) + '万', symbol: 'pin', symbolSize: 40, itemStyle: {{ color: '#66bb6a' }} }}
        ]
      }}
    }}
  ]
}};

chart.setOption(option);
window.addEventListener('resize', function() {{ chart.resize(); }});
</script>
</body>
</html>
'''

with open('outputs/june_v2_v3_compare.html', 'w') as f:
    f.write(html)

print("✅ 图表已生成: outputs/june_v2_v3_compare.html")
print(f"   v2 终值: ¥{v2_curve[-1]['capital']:,} (+{(v2_curve[-1]['capital']-1000000)/10000:.1f}%)")
print(f"   v3 终值: ¥{v3_curve[-1]['capital']:,} (+{(v3_curve[-1]['capital']-1000000)/10000:.1f}%)")
