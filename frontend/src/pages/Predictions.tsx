import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { AreaChartOutlined, BarChartOutlined, LineChartOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { predictionApi } from '../api/client'
import { MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, PrototypeTabs, SegmentTabs } from '../components/prototype'

interface TrajectoryPoint {
  day: number
  open: number
  high: number
  low: number
  close: number
}

const tabs = [
  { key: 'overview', path: '/predictions', label: '预测总览', subLabel: '模型概览' },
  { key: 'single', path: '/predictions/single', label: '单股预测', subLabel: '30 日路径' },
  { key: 'compare', path: '/predictions/compare', label: '多股对比', subLabel: '组合比较' },
  { key: 'backtest', path: '/predictions/backtest', label: '准确率回测', subLabel: '命中复核' },
]

const watchStocks = [
  { code: '300750', name: '宁德时代', price: 218.5, target: 242.3, score: 90, ret: 12.5 },
  { code: '688981', name: '中芯国际', price: 68.2, target: 75.1, score: 88, ret: 10.1 },
  { code: '600519', name: '贵州茅台', price: 1785, target: 1858, score: 79, ret: 4.1 },
  { code: '002594', name: '比亚迪', price: 248, target: 242.8, score: 72, ret: -2.1 },
]

const fallbackTrajectory: TrajectoryPoint[] = Array.from({ length: 30 }, (_, index) => {
  const base = 218.5 + index * 0.82 + Math.sin(index / 3) * 2.4
  return {
    day: index + 1,
    open: Number((base - 1.2).toFixed(2)),
    high: Number((base + 2.8).toFixed(2)),
    low: Number((base - 3.1).toFixed(2)),
    close: Number((base + 0.9).toFixed(2)),
  }
})

function activeKey(pathname: string) {
  if (pathname.endsWith('/single')) return 'single'
  if (pathname.endsWith('/compare')) return 'compare'
  if (pathname.endsWith('/backtest')) return 'backtest'
  return 'overview'
}

function buildTrajectoryOption(traj: TrajectoryPoint[]): EChartsOption {
  return {
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: { left: 44, right: 18, top: 22, bottom: 36 },
    xAxis: { type: 'category', data: traj.map(item => `D${item.day}`), axisLabel: { fontSize: 10, color: '#8a96a8' } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 10, color: '#52617a' }, splitLine: { lineStyle: { color: '#e6eaf0' } } },
    dataZoom: [{ type: 'inside' }],
    series: [{
      type: 'candlestick',
      data: traj.map(item => [item.open, item.close, item.low, item.high]),
      itemStyle: { color: '#ff4d4f', color0: '#2ec27e', borderColor: '#ff4d4f', borderColor0: '#2ec27e' },
    }, {
      type: 'line',
      data: traj.map(item => item.close),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#3d8bff', width: 2 },
    }],
  }
}

function buildOverviewOption(): EChartsOption {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 34 },
    xAxis: { type: 'category', data: watchStocks.map(item => item.name), axisLabel: { color: '#52617a' } },
    yAxis: { type: 'value', axisLabel: { color: '#52617a' }, splitLine: { lineStyle: { color: '#e6eaf0' } } },
    series: [{
      type: 'bar',
      data: watchStocks.map(item => item.ret),
      itemStyle: { color: (params: any) => Number(params.value) >= 0 ? '#ff4d4f' : '#2ec27e' },
      barWidth: 26,
    }],
  }
}

export default function Predictions() {
  const location = useLocation()
  const navigate = useNavigate()
  const [code, setCode] = useState('300750')
  const [range, setRange] = useState('all')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const active = activeKey(location.pathname)
  const selected = result ?? {
    code: '300750',
    name: '宁德时代',
    current_price: 218.5,
    pred_last_close: 242.3,
    pred_return_pct: 12.5,
    confidence: 78,
    trend: '偏强上行',
    pred_low: 211.8,
    pred_high: 248.6,
    max_drawdown_pct: -4.2,
    pred_trajectory: fallbackTrajectory,
  }
  const trajectoryOption = useMemo(() => buildTrajectoryOption(selected.pred_trajectory || fallbackTrajectory), [selected.pred_trajectory])
  const overviewOption = useMemo(() => buildOverviewOption(), [])

  const runPredict = async () => {
    if (!code.trim()) return
    setLoading(true)
    try {
      const { data } = await predictionApi.predict(code.trim(), 30)
      setResult(data)
    } catch {
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="K线预测页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />

      {active === 'overview' && (
        <>
          <PrototypePageHeader title="预测总览" subtitle="Kronos V2.3 · 自选/候选池/最近预测的模型概览" />
          <div className="kpis">
            <MetricCard label="覆盖股票" value="30" sub="自选 + 候选池" tone="accent" />
            <MetricCard label="看涨路径" value="21" sub="未来 30 日" tone="up" />
            <MetricCard label="平均置信度" value="76%" sub="多因子共振" tone="down" />
            <MetricCard label="风险预警" value="4" sub="回撤 > 6%" tone="warn" />
          </div>
          <div className="row r-6-4">
            <PrototypeCard title="组合预测分布" icon={<BarChartOutlined />} meta="预期收益率">
              <ReactECharts option={overviewOption} style={{ height: 320, width: '100%' }} notMerge />
            </PrototypeCard>
            <PrototypeCard title="重点标的排行" icon={<ThunderboltOutlined />} meta="按置信度排序">
              <table className="tbl">
                <thead><tr><th>代码</th><th>名称</th><th className="r">预期收益</th><th className="r">置信度</th></tr></thead>
                <tbody>
                  {watchStocks.map(item => (
                    <tr key={item.code}>
                      <td className="code">{item.code}</td>
                      <td className="nm">{item.name}</td>
                      <td className={`r ${item.ret >= 0 ? 'up' : 'down'}`}>{item.ret >= 0 ? '+' : ''}{item.ret}%</td>
                      <td className="r mono">{item.score}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </PrototypeCard>
          </div>
        </>
      )}

      {active === 'single' && (
        <>
          <PrototypePageHeader title="单股预测" subtitle="单标的 30 日 OHLCV 路径 · 因子贡献 · 信号一致性" />
          <PrototypeCard title="预测标的" icon={<LineChartOutlined />} meta="30 日路径">
            <div className="filter-bar" style={{ marginBottom: 0 }}>
              <div className="search" style={{ maxWidth: 320 }}>
                <input className="inp" value={code} onChange={event => setCode(event.target.value)} placeholder="搜索代码/名称..." />
              </div>
              <button type="button" className={`btn primary ${loading ? 'is-loading' : ''}`} onClick={runPredict}>开始预测</button>
              <SegmentTabs
                ariaLabel="预测周期"
                activeKey={range}
                onChange={setRange}
                items={[{ key: 'all', label: '全部' }, { key: '30d', label: '近30日' }, { key: 'future30', label: '预测30日' }]}
              />
            </div>
          </PrototypeCard>
          <div className="row r-6-4">
            <PrototypeCard title={`${selected.name ?? '宁德时代'} 预测路径`} icon={<AreaChartOutlined />} meta={`${selected.code ?? code} · Kronos V2.3`}>
              <ReactECharts option={trajectoryOption} style={{ height: 520, width: '100%' }} notMerge />
            </PrototypeCard>
            <div className="grid">
              <PrototypeCard title="预测概览" icon={<BarChartOutlined />}>
                <div style={{ textAlign: 'center', padding: '12px 0 18px' }}>
                  <div className="prototype-panel-note">Kronos V2.3</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 32, fontWeight: 760 }}>
                    {selected.current_price} <span style={{ color: 'var(--muted)' }}>→</span> <span className={selected.pred_return_pct >= 0 ? 'up' : 'down'}>{selected.pred_last_close}</span>
                  </div>
                  <div className={selected.pred_return_pct >= 0 ? 'up' : 'down'} style={{ fontFamily: 'var(--font-mono)', fontWeight: 760, fontSize: 20 }}>
                    {selected.pred_return_pct >= 0 ? '+' : ''}{selected.pred_return_pct}%
                  </div>
                </div>
                <div className="dim-row">
                  <div className="dim-lbl">置信度</div>
                  <div className="dim-bar-wrap"><div className="dim-bar" style={{ width: `${selected.confidence ?? 78}%`, background: 'var(--accent)' }} /></div>
                  <div className="dim-val neu">{selected.confidence ?? 78}%</div>
                </div>
              </PrototypeCard>
              <PrototypeCard title="信号一致性" icon={<ThunderboltOutlined />}>
                <div className="prototype-fallback" style={{ background: 'var(--down-bg)', borderColor: 'rgba(46,194,126,.35)', color: 'var(--down)' }}>
                  信号方向一致
                </div>
                <div className="prototype-panel-note" style={{ marginTop: 10 }}>信号强度: 强买 82分 · 多因子共振</div>
              </PrototypeCard>
              <PrototypeCard title="因子贡献" icon={<BarChartOutlined />}>
                {[
                  ['技术面', 45, 'var(--accent)'],
                  ['资金面', 28, '#7c3aed'],
                  ['基本面', 15, 'var(--down)'],
                  ['情绪面', 12, 'var(--warn)'],
                ].map(([label, value, color]) => (
                  <div className="dim-row" key={String(label)}>
                    <div className="dim-lbl">{label}</div>
                    <div className="dim-bar-wrap"><div className="dim-bar" style={{ width: `${value}%`, background: String(color) }} /></div>
                    <div className="dim-val">{value}%</div>
                  </div>
                ))}
              </PrototypeCard>
            </div>
          </div>
        </>
      )}

      {active === 'compare' && (
        <>
          <PrototypePageHeader title="多股对比" subtitle="多标的预测路径、置信度和风险收益比较" />
          <PrototypeCard title="对比矩阵" icon={<BarChartOutlined />}>
            <table className="tbl">
              <thead><tr><th>股票</th><th className="r">当前价</th><th className="r">目标价</th><th className="r">预期收益</th><th className="r">置信度</th></tr></thead>
              <tbody>{watchStocks.map(item => (
                <tr key={item.code}><td><span className="nm">{item.name}</span> <span className="code">{item.code}</span></td><td className="r mono">{item.price}</td><td className="r mono">{item.target}</td><td className={`r ${item.ret >= 0 ? 'up' : 'down'}`}>{item.ret}%</td><td className="r mono">{item.score}%</td></tr>
              ))}</tbody>
            </table>
          </PrototypeCard>
        </>
      )}

      {active === 'backtest' && (
        <>
          <PrototypePageHeader title="准确率回测" subtitle="预测命中率 · 偏差分布 · 模型版本复核" />
          <div className="kpis">
            <MetricCard label="30日方向命中" value="72%" sub="近 120 个样本" tone="down" />
            <MetricCard label="平均绝对误差" value="4.8%" sub="收盘价偏差" tone="accent" />
            <MetricCard label="高置信样本" value="83%" sub="置信度 > 75" tone="up" />
            <MetricCard label="待复核" value="6" sub="异常波动样本" tone="warn" />
          </div>
          <PrototypeCard title="回测说明" icon={<LineChartOutlined />}>
            <div className="prototype-panel-note">按模型版本、样本区间和置信度分层复核预测命中率，异常波动样本进入人工复盘。</div>
          </PrototypeCard>
        </>
      )}
    </PrototypePage>
  )
}
