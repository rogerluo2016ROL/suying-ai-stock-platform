import { useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import {
  ApartmentOutlined,
  BarChartOutlined,
  FundOutlined,
  LineChartOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { DataFreshnessBar, PrototypeCard, PrototypePageHeader } from '../../components/prototype'
import type { DashboardData } from './types'
import {
  buildSignalBubbleOption,
  buildSignalStats,
  buildSignalTrendOption,
  filterSignalMatrix,
  mergeSignalMatrix,
  normalizeSentiment,
  signalLevelMeta,
  signalSectorRows,
} from './helpers'

interface SignalsTabProps {
  data: DashboardData | null
  lastRefresh: string
}

export default function SignalsTab({ data, lastRefresh }: SignalsTabProps) {
  const [signalFilter, setSignalFilter] = useState('all')

  const sentiment = normalizeSentiment(data)
  const totalStocks = sentiment.total_stocks ?? 0
  const signalStocks = data?.signal_stocks ?? []
  const signalMatrix = useMemo(() => mergeSignalMatrix(signalStocks), [signalStocks])
  const signalStats = useMemo(() => buildSignalStats(signalMatrix), [signalMatrix])
  const visibleSignals = useMemo(() => filterSignalMatrix(signalMatrix, signalFilter), [signalMatrix, signalFilter])
  const signalRows = useMemo(() => signalSectorRows(visibleSignals), [visibleSignals])
  const topSignals = useMemo(
    () => filterSignalMatrix(signalMatrix, 'buy').sort((a, b) => b.score - a.score).slice(0, 8),
    [signalMatrix],
  )
  const signalTrendOption = useMemo(() => buildSignalTrendOption(), [])
  const signalBubbleOption = useMemo(() => buildSignalBubbleOption(signalMatrix), [signalMatrix])
  const updatedAt = data?.refreshed_at || lastRefresh
  const currentDataDate = data?.data_freshness?.as_of || data?.refreshed_at

  return (
    <>
      <PrototypePageHeader
        title="信号总览"
        subtitle="全市场六维信号扫描 · 板块共振 · 历史趋势"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={sentiment.trade_date}
            updatedAt={updatedAt}
            source={data?.data_sources?.signal_stocks || 'signal-service'}
            currentTradeDate={currentDataDate}
          />
        )}
        actions={[{ key: 'refresh', label: '刷新', active: true, tone: 'neutral' }]}
      />

      <div className="signal-overview-layout">
        <section className="signal-workbench">
          <div className="signal-filter-bar" aria-label="信号筛选">
            {[
              ['all', '全部信号'],
              ['buy', '仅买入'],
              ['sell', '仅卖出'],
              ['alert', '仅拐点'],
              ['watchlist', '仅自选'],
            ].map(([key, label]) => (
              <button
                className={`filter-btn ${signalFilter === key ? 'active' : ''}`}
                key={key}
                type="button"
                onClick={() => setSignalFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>

          <PrototypeCard title="行业信号矩阵" icon={<ThunderboltOutlined />} meta="按偏多程度降序">
            <div className="signal-matrix" aria-label="行业信号矩阵">
              {signalRows.map(row => (
                <div className="signal-sector-row" key={row.sector}>
                  <div className="signal-sector-name">
                    <strong>{row.sector}</strong>
                    <span>买{row.bullish} / 卖{row.bearish}</span>
                  </div>
                  <div className="signal-cell-strip">
                    {row.cells.map(cell => {
                      const meta = signalLevelMeta[cell.level]
                      const opacity = cell.score >= 75 ? 'hi' : cell.score >= 50 ? 'md' : 'lo'
                      return (
                        <button
                          type="button"
                          className={`signal-cell ${meta.className} ${opacity}`}
                          key={cell.code}
                          title={`${cell.name} ${meta.label} ${cell.score}分`}
                        >
                          <span className="signal-cell-code">{cell.code}</span>
                          <span className="signal-cell-score">{cell.score}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
              {signalRows.length === 0 && (
                <div className="prototype-panel-note">暂无实时信号数据。</div>
              )}
            </div>
            <div className="footer-bar signal-help">
              <span>每行 = 一个行业板块（按偏多程度降序） · 每格 = 一只股票 · 悬浮查看详情 · 点击跳转诊断</span>
            </div>
          </PrototypeCard>
        </section>

        <aside className="signal-side">
          <PrototypeCard title="今日信号概况" icon={<BarChartOutlined />} meta={`已覆盖 ${totalStocks.toLocaleString()} 只`}>
            <div className="signal-stat-list">
              {signalStats.map(stat => {
                const meta = signalLevelMeta[stat.key]
                return (
                  <div className="signal-stat-row" key={stat.key}>
                    <span className="sig-dot" style={{ color: meta.color }}>{stat.icon}</span>
                    <span className="sig-label">{meta.label}</span>
                    <span className="sig-count" style={{ color: meta.color }}>{stat.count}</span>
                    <span className="sig-bar"><i style={{ width: stat.pct, background: meta.color }} /></span>
                    <span className="sig-pct">{stat.pct}</span>
                  </div>
                )
              })}
            </div>
            <div className="signal-resonance">
              <div><span>板块共振偏多</span><b className="up">{signalRows.filter(row => row.bullish > row.bearish).length} 板块</b></div>
              <div><span>板块共振偏空</span><b className="down">{signalRows.filter(row => row.bearish > row.bullish).length} 板块</b></div>
              <div><span>共振阈值</span><b>≥3 只同向</b></div>
            </div>
            <div className="watch-row">
              <span>自选股信号</span>
              <b>{signalMatrix.filter(item => item.watchlist).length} / {signalMatrix.length} 已触发</b>
              <small>管理自选 →</small>
            </div>
          </PrototypeCard>

          <PrototypeCard title="实时信号流" icon={<ThunderboltOutlined />} meta="最近 20 条">
            <div className="signal-stream">
              {topSignals.slice(0, 6).map((item, index) => {
                const meta = signalLevelMeta[item.level]
                return (
                  <div className="stream-row" key={`${item.code}-${index}`}>
                    <span className="stream-time mono">实时</span>
                    <span className="code">{item.code}</span>
                    <span className="nm">{item.name}</span>
                    <span style={{ color: meta.color }}>{meta.label}</span>
                    <b style={{ color: meta.color }}>{item.score}</b>
                  </div>
                )
              })}
              {topSignals.length === 0 && <div className="prototype-panel-note">暂无买入或拐点信号。</div>}
            </div>
          </PrototypeCard>

          <PrototypeCard title="最强信号 TOP 8" icon={<FundOutlined />} meta="当日买入/拐点信号">
            <div className="signal-top-list">
              {topSignals.map((item, index) => {
                const meta = signalLevelMeta[item.level]
                const resonance = signalMatrix.filter(row => row.industry === item.industry && ['STRONG_BUY', 'BUY', 'TIMING_ALERT'].includes(row.level)).length
                return (
                  <div className="top-signal-row" key={item.code}>
                    <span className="top-rank">{index + 1}</span>
                    <span className="code">{item.code}</span>
                    <span className="nm">{item.name}</span>
                    <span className="tag" style={{ color: meta.color, background: `${meta.color}18` }}>{meta.label}</span>
                    <b style={{ color: meta.color }}>{item.score}</b>
                    <small>{item.industry}</small>
                    <small className="resonance-chip">共{resonance}只</small>
                  </div>
                )
              })}
              {topSignals.length === 0 && <div className="prototype-panel-note">暂无强信号。</div>}
            </div>
          </PrototypeCard>
        </aside>
      </div>

      <div className="row r-1-1">
        <PrototypeCard title="30 日信号趋势" icon={<LineChartOutlined />} meta="近 30 个交易日 · 买卖信号 + 多空比">
          <ReactECharts option={signalTrendOption} style={{ height: 300, width: '100%' }} notMerge />
          <div className="prototype-panel-note">暂无历史信号趋势接口；图表不展示模拟曲线。</div>
        </PrototypeCard>
        <PrototypeCard title="板块信号气泡图" icon={<ApartmentOutlined />} meta="信号数量 × 平均评分 × 市值">
          <ReactECharts option={signalBubbleOption} style={{ height: 300, width: '100%' }} notMerge />
        </PrototypeCard>
      </div>

      <div className="footer-bar">
        <span>数据来源: signal-service (signal_snapshots 缓存)</span>
        <span className="sep" />
        <span>信号模型权重以后端返回为准；前端不展示固定权重。</span>
        <span className="sep" />
        <span>免责声明: 本页信号为量化模型输出，不构成投资建议。历史数据不代表未来表现</span>
      </div>
    </>
  )
}
