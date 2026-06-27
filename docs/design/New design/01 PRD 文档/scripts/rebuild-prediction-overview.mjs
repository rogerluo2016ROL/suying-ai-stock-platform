import fs from 'node:fs';

const file = new URL('../5.0 prediction-preview.html', import.meta.url);
let html = fs.readFileSync(file, 'utf8');

const overviewCss = `

/* Prediction Overview */
.overview-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:18px 20px;background:linear-gradient(135deg,rgba(61,139,255,.12),rgba(46,194,126,.08));border:1px solid var(--border);border-radius:var(--radius);margin-bottom:12px}
.overview-hero h1{font-size:24px;line-height:1.2;margin-bottom:6px}
.overview-hero .desc{color:var(--fg-2);font-size:13px}
.hero-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.action-link{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 12px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--fg);text-decoration:none;font-weight:650;font-size:12px}
.action-link.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.action-link:hover{border-color:var(--accent);color:var(--accent)}
.action-link.primary:hover{color:#fff;filter:brightness(1.05)}
.overview-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:12px}
.kpi-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:13px 14px;min-height:94px}
.kpi-card .label{font-size:11px;color:var(--fg-2);font-weight:650;margin-bottom:8px}
.kpi-card .value{font-family:var(--font-mono);font-size:26px;line-height:1;font-weight:760;letter-spacing:0}
.kpi-card .hint{margin-top:8px;font-size:11px;color:var(--muted)}
.overview-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(340px,.65fr);gap:12px;margin-bottom:12px}
.overview-grid.equal{grid-template-columns:1fr 1fr}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.panel-h{height:42px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;border-bottom:1px solid var(--border);font-weight:700}
.panel-h .sub{font-size:11px;color:var(--muted);font-weight:500}
.panel-b{padding:14px}
.rank-table{width:100%;border-collapse:collapse;font-size:12px}
.rank-table th{height:32px;text-align:left;color:var(--muted);font-weight:650;border-bottom:1px solid var(--border)}
.rank-table td{height:46px;border-bottom:1px solid var(--border);vertical-align:middle}
.rank-table tr:last-child td{border-bottom:0}
.rank-table tr{cursor:pointer}
.rank-table tbody tr:hover{background:rgba(61,139,255,.06)}
.stock-name{font-weight:700;color:var(--fg)}
.stock-code{font-family:var(--font-mono);color:var(--fg-2);font-size:11px;margin-top:1px}
.score-pill{display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:14px;font-family:var(--font-mono);font-size:11px;font-weight:700;background:var(--accent-dim);color:var(--accent)}
.status-pill{display:inline-flex;align-items:center;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:700}
.status-pill.good{background:var(--down-bg);color:var(--down)}
.status-pill.warn{background:var(--warn-bg);color:var(--warn)}
.status-pill.risk{background:var(--up-bg);color:var(--up)}
.text-btn{border:0;background:transparent;color:var(--accent);font-weight:700;font-size:12px;cursor:pointer}
.health-list{display:grid;gap:10px}
.health-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 11px;background:var(--surface-2);border:1px solid var(--border);border-radius:7px}
.health-item strong{font-size:12px}
.health-item span{font-size:11px;color:var(--fg-2)}
.health-value{font-family:var(--font-mono);font-size:12px;font-weight:750;color:var(--fg)}
.mini-chart{height:260px}
.workflow-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.workflow-card{display:flex;flex-direction:column;gap:8px;min-height:128px;padding:14px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);text-decoration:none;color:var(--fg)}
.workflow-card:hover{border-color:var(--accent);background:rgba(61,139,255,.06)}
.workflow-card .eyebrow{font-size:11px;color:var(--muted);font-weight:700}
.workflow-card .title{font-size:16px;font-weight:760}
.workflow-card .copy{color:var(--fg-2);font-size:12px;line-height:1.55;flex:1}
.workflow-card .go{font-size:12px;color:var(--accent);font-weight:700}
.alert-list{display:grid;gap:8px}
.alert-item{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)}
.alert-item:last-child{border-bottom:0}
.alert-dot{width:8px;height:8px;border-radius:50%;background:var(--accent)}
.alert-dot.warn{background:var(--warn)}
.alert-dot.risk{background:var(--up)}
.alert-copy strong{display:block;font-size:12px}
.alert-copy span{display:block;font-size:11px;color:var(--fg-2);margin-top:1px}
.alert-time{font-size:11px;color:var(--muted);font-family:var(--font-mono)}
`;

const main = `
                  <div class="overview-hero">
                    <div>
                      <h1>K线预测总览</h1>
                      <div class="desc">Kronos 模型状态 · 候选池预测排行 · 信号一致性 · 准确率复核</div>
                    </div>
                    <div class="hero-actions">
                      <a class="action-link primary" href="5.1 single-stock-preview.html">查看单股预测</a>
                      <a class="action-link" href="5.2 multi-compare-preview.html">进入多股对比</a>
                      <a class="action-link" href="5.3 backtest-preview.html">打开准确率回测</a>
                    </div>
                  </div>

                  <section class="overview-kpis">
                    <div class="kpi-card">
                      <div class="label">今日预测任务</div>
                      <div class="value neu">128</div>
                      <div class="hint">收盘后批量更新 96 只</div>
                    </div>
                    <div class="kpi-card">
                      <div class="label">高置信度标的</div>
                      <div class="value down">42</div>
                      <div class="hint">置信度 >= 75%</div>
                    </div>
                    <div class="kpi-card">
                      <div class="label">信号方向一致</div>
                      <div class="value down">31</div>
                      <div class="hint">预测方向与交易信号同向</div>
                    </div>
                    <div class="kpi-card">
                      <div class="label">待处理预警</div>
                      <div class="value warn">6</div>
                      <div class="hint">2 条支撑位，4 条阻力位</div>
                    </div>
                    <div class="kpi-card">
                      <div class="label">近30次方向正确率</div>
                      <div class="value neu">72%</div>
                      <div class="hint">较上周 +3.6 pct</div>
                    </div>
                  </section>

                  <section class="overview-grid">
                    <div class="panel">
                      <div class="panel-h">
                        <span>候选池预测排行</span>
                        <span class="sub">按“信号一致性 + 预测涨幅”排序</span>
                      </div>
                      <div class="panel-b">
                        <table class="rank-table">
                          <thead>
                            <tr>
                              <th>标的</th>
                              <th>当前价</th>
                              <th>目标价</th>
                              <th>预测涨幅</th>
                              <th>置信度</th>
                              <th>一致性</th>
                              <th>操作</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr onclick="openStock('300750')">
                              <td><div class="stock-name">宁德时代</div><div class="stock-code">300750</div></td>
                              <td class="mono">218.50</td>
                              <td class="mono up">242.30</td>
                              <td class="mono up">+12.5%</td>
                              <td><span class="score-pill">78</span></td>
                              <td><span class="status-pill good">方向一致</span></td>
                              <td><button class="text-btn" type="button">单股详情</button></td>
                            </tr>
                            <tr onclick="openStock('603986')">
                              <td><div class="stock-name">兆易创新</div><div class="stock-code">603986</div></td>
                              <td class="mono">152.00</td>
                              <td class="mono up">168.50</td>
                              <td class="mono up">+10.8%</td>
                              <td><span class="score-pill">75</span></td>
                              <td><span class="status-pill good">方向一致</span></td>
                              <td><button class="text-btn" type="button">单股详情</button></td>
                            </tr>
                            <tr onclick="openStock('688981')">
                              <td><div class="stock-name">中芯国际</div><div class="stock-code">688981</div></td>
                              <td class="mono">68.20</td>
                              <td class="mono up">73.80</td>
                              <td class="mono up">+8.2%</td>
                              <td><span class="score-pill">72</span></td>
                              <td><span class="status-pill good">方向一致</span></td>
                              <td><button class="text-btn" type="button">单股详情</button></td>
                            </tr>
                            <tr onclick="openStock('601012')">
                              <td><div class="stock-name">隆基绿能</div><div class="stock-code">601012</div></td>
                              <td class="mono">32.80</td>
                              <td class="mono up">35.20</td>
                              <td class="mono up">+7.3%</td>
                              <td><span class="score-pill">68</span></td>
                              <td><span class="status-pill warn">信号偏弱</span></td>
                              <td><button class="text-btn" type="button">单股详情</button></td>
                            </tr>
                            <tr onclick="openStock('002594')">
                              <td><div class="stock-name">比亚迪</div><div class="stock-code">002594</div></td>
                              <td class="mono">98.50</td>
                              <td class="mono down">96.40</td>
                              <td class="mono down">-2.1%</td>
                              <td><span class="score-pill">61</span></td>
                              <td><span class="status-pill risk">方向相悖</span></td>
                              <td><button class="text-btn" type="button">单股详情</button></td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div class="panel">
                      <div class="panel-h">
                        <span>模型运行状态</span>
                        <span class="sub">今日 09:32 更新</span>
                      </div>
                      <div class="panel-b">
                        <div class="health-list">
                          <div class="health-item"><div><strong>Kronos V2.3</strong><span>生产模型在线</span></div><div class="health-value down">正常</div></div>
                          <div class="health-item"><div><strong>Checkpoint</strong><span>2026-06-20 21:15</span></div><div class="health-value">ckpt-0620</div></div>
                          <div class="health-item"><div><strong>推理延迟</strong><span>候选池批处理 P95</span></div><div class="health-value">1.8s</div></div>
                          <div class="health-item"><div><strong>数据新鲜度</strong><span>Tushare + 实时行情</span></div><div class="health-value down">已同步</div></div>
                          <div class="health-item"><div><strong>回测基准</strong><span>最近 120 次样本</span></div><div class="health-value neu">68.4%</div></div>
                        </div>
                      </div>
                    </div>
                  </section>

                  <section class="overview-grid equal">
                    <div class="panel">
                      <div class="panel-h">
                        <span>预测任务趋势</span>
                        <span class="sub">近 7 个交易日</span>
                      </div>
                      <div class="panel-b">
                        <div id="chart-overview-trend" class="mini-chart"></div>
                      </div>
                    </div>
                    <div class="panel">
                      <div class="panel-h">
                        <span>信号一致性分布</span>
                        <span class="sub">128 个今日预测</span>
                      </div>
                      <div class="panel-b">
                        <div id="chart-overview-consistency" class="mini-chart"></div>
                      </div>
                    </div>
                  </section>

                  <section class="overview-grid">
                    <div class="panel">
                      <div class="panel-h">
                        <span>工作流入口</span>
                        <span class="sub">按 PRD 拆分的核心路径</span>
                      </div>
                      <div class="panel-b">
                        <div class="workflow-row">
                          <a class="workflow-card" href="5.1 single-stock-preview.html">
                            <span class="eyebrow">P0 · 个股择时</span>
                            <span class="title">单股预测</span>
                            <span class="copy">查看 60 日历史 K 线、30 日预测路径、置信区间、支撑阻力和信号标记。</span>
                            <span class="go">进入详情 →</span>
                          </a>
                          <a class="workflow-card" href="5.2 multi-compare-preview.html">
                            <span class="eyebrow">P0 · 候选筛选</span>
                            <span class="title">多股对比</span>
                            <span class="copy">横向比较候选池预测涨幅、置信度、信号一致性和历史准确率。</span>
                            <span class="go">进入对比 →</span>
                          </a>
                          <a class="workflow-card" href="5.3 backtest-preview.html">
                            <span class="eyebrow">P1 · 可信度复核</span>
                            <span class="title">准确率回测</span>
                            <span class="copy">复盘历史预测与实际走势偏差，评估模型在当前标的上的稳定性。</span>
                            <span class="go">进入回测 →</span>
                          </a>
                        </div>
                      </div>
                    </div>

                    <div class="panel">
                      <div class="panel-h">
                        <span>预测预警摘要</span>
                        <span class="sub">6 条待处理</span>
                      </div>
                      <div class="panel-b">
                        <div class="alert-list">
                          <div class="alert-item">
                            <span class="alert-dot warn"></span>
                            <div class="alert-copy"><strong>宁德时代接近阻力 251.00</strong><span>预测路径上沿已进入观察区</span></div>
                            <span class="alert-time">09:48</span>
                          </div>
                          <div class="alert-item">
                            <span class="alert-dot"></span>
                            <div class="alert-copy"><strong>中芯国际信号增强</strong><span>预测方向与强买信号保持一致</span></div>
                            <span class="alert-time">09:42</span>
                          </div>
                          <div class="alert-item">
                            <span class="alert-dot risk"></span>
                            <div class="alert-copy"><strong>比亚迪方向相悖</strong><span>预测回落但交易信号仍偏多</span></div>
                            <span class="alert-time">09:35</span>
                          </div>
                          <div class="alert-item">
                            <span class="alert-dot warn"></span>
                            <div class="alert-copy"><strong>隆基绿能置信度偏低</strong><span>建议进入回测页复核最近误差</span></div>
                            <span class="alert-time">09:31</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </section>
`;

const overviewJs = `
const stockTargets = {
  '300750': '5.1 single-stock-preview.html?code=300750',
  '603986': '5.1 single-stock-preview.html?code=603986',
  '688981': '5.1 single-stock-preview.html?code=688981',
  '601012': '5.1 single-stock-preview.html?code=601012',
  '002594': '5.1 single-stock-preview.html?code=002594'
};

function openStock(code){
  location.href = stockTargets[code] || '5.1 single-stock-preview.html';
}

const trendEl = document.getElementById('chart-overview-trend');
const consistencyEl = document.getElementById('chart-overview-consistency');
const charts = [];

if (trendEl && window.echarts) {
  const trendChart = echarts.init(trendEl);
  charts.push(trendChart);
  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { color: '#9aa7b8', fontSize: 11 } },
    grid: { left: 34, right: 14, top: 42, bottom: 24 },
    xAxis: {
      type: 'category',
      data: ['06-19','06-20','06-21','06-22','06-23','06-24','06-25'],
      axisLine: { lineStyle: { color: '#2a3444' } },
      axisLabel: { color: '#9aa7b8', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#1f2733' } },
      axisLabel: { color: '#9aa7b8', fontSize: 11 }
    },
    series: [
      {
        name: '预测任务',
        type: 'bar',
        data: [86, 94, 102, 98, 116, 121, 128],
        barWidth: 16,
        itemStyle: { color: '#3d8bff', borderRadius: [4,4,0,0] }
      },
      {
        name: '高置信度',
        type: 'line',
        smooth: true,
        data: [24, 27, 31, 29, 36, 39, 42],
        symbolSize: 6,
        lineStyle: { color: '#2ec27e', width: 2 },
        itemStyle: { color: '#2ec27e' },
        areaStyle: { color: 'rgba(46,194,126,.08)' }
      }
    ]
  });
}

if (consistencyEl && window.echarts) {
  const consistencyChart = echarts.init(consistencyEl);
  charts.push(consistencyChart);
  consistencyChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: '#9aa7b8', fontSize: 11 } },
    series: [{
      name: '一致性',
      type: 'pie',
      radius: ['48%', '72%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      label: { color: '#e8edf4', formatter: '{b}\\n{c} 只' },
      labelLine: { lineStyle: { color: '#5e6a7d' } },
      data: [
        { value: 31, name: '方向一致', itemStyle: { color: '#2ec27e' } },
        { value: 19, name: '信号偏弱', itemStyle: { color: '#f5a623' } },
        { value: 8, name: '方向相悖', itemStyle: { color: '#ff4d4f' } },
        { value: 70, name: '待确认', itemStyle: { color: '#5e6a7d' } }
      ]
    }]
  });
}

window.addEventListener('resize', () => charts.forEach(chart => chart.resize()));
`;

if (!html.includes('.overview-hero')) {
  html = html.replace(/\n@media\(max-width:1100px\)/, `${overviewCss}\n@media(max-width:1100px)`);
}

html = html.replace(
  /@media\(max-width:1100px\)\{\.pm\{flex-direction:column\}\.ch\{height:340px\}\.ast\{grid-template-columns:repeat\(2,1fr\)\}\}/,
  '@media(max-width:1200px){.overview-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.overview-grid,.overview-grid.equal{grid-template-columns:1fr}.workflow-row{grid-template-columns:1fr}}\\n@media(max-width:760px){.overview-hero{flex-direction:column}.hero-actions{justify-content:flex-start}.overview-kpis{grid-template-columns:1fr}.panel-b{overflow-x:auto}.rank-table{min-width:760px}.mini-chart{height:220px}.pm{flex-direction:column}.ch{height:340px}.ast{grid-template-columns:repeat(2,1fr)}}'
);

html = html.replace(
  /<main class="content">[\s\S]*?<\/main>/,
  `<main class="content">\n${main}\n                </main>`
);

html = html.replace(
  /<script src="assets\/shell\.js"><\/script>\s*<script>[\s\S]*?<\/script>\s*<script src="assets\/preview-interactions\.js"><\/script>/,
  `<script src="assets/shell.js"></script>\n<script>${overviewJs}\n</script>\n<script src="assets/preview-interactions.js"></script>`
);

fs.writeFileSync(file, html);
