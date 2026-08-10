import { useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { Drawer } from 'antd'
import {
  ApartmentOutlined,
  BarChartOutlined,
  DollarOutlined,
  EyeOutlined,
  FundOutlined,
  LineChartOutlined,
} from '@ant-design/icons'
import { DataFreshnessBar, EmptyState, MetricCard, PrototypeCard, PrototypePageHeader } from '../../components/prototype'
import type { AuctionIntentItem, DashboardData, SectorStockDetail, SentimentPageKey } from './types'
import {
  buildGaugeOption,
  buildSectorResonanceRows,
  buildSentimentReasons,
  buildTrendOption,
  dimensionsFromData,
  formatSignedPct,
  limitStockCount,
  limitStockRows,
  limitStockSource,
  mergeAuctionRows,
  mergeSignalMatrix,
  normalizeSentiment,
  sectorColor,
  sectorStockRows,
  sentimentPages,
} from './helpers'

interface SentimentTabProps {
  data: DashboardData | null
  error: boolean
  lastRefresh: string
  screeningPicks: AuctionIntentItem[]
  auctionPicks: AuctionIntentItem[]
}

function SectorStockTable({ rows }: { rows: SectorStockDetail[] }) {
  if (rows.length === 0) {
    return (
      <div className="prototype-empty-state">
        <strong>暂无该板块股票明细</strong>
        <span>等待 signal_stocks 或 dashboard/auction 返回带 industry 的个股数据后自动联动。</span>
      </div>
    )
  }
  return (
    <table className="tbl compact sector-stock-table">
      <thead>
        <tr><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">价格</th><th className="r">评分</th><th>来源</th></tr>
      </thead>
      <tbody>
        {rows.map(row => (
          <tr key={row.code}>
            <td className="code">{row.code}</td>
            <td className="nm">{row.name}</td>
            <td className={`r ${row.changePct >= 0 ? 'up' : 'down'}`}>{formatSignedPct(row.changePct)}</td>
            <td className="r mono">{row.price > 0 ? row.price.toFixed(2) : '--'}</td>
            <td className="r mono">{row.score > 0 ? row.score : '--'}</td>
            <td><span className={`tag ${row.source === '竞价' ? 't-warn' : 't-neu'}`}>{row.source}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function SentimentTab({ data, error, lastRefresh, screeningPicks, auctionPicks }: SentimentTabProps) {
  const [sentimentPage, setSentimentPage] = useState<SentimentPageKey>('today')
  const [selectedSectorIndex, setSelectedSectorIndex] = useState(0)
  const [sectorDetailOpen, setSectorDetailOpen] = useState(false)

  const sentiment = normalizeSentiment(data)
  const dimensions = dimensionsFromData(data)
  const gaugeOption = useMemo(() => buildGaugeOption(Math.round(sentiment.score)), [sentiment.score])
  const trendOption = useMemo(() => buildTrendOption(), [])
  const upCount = limitStockCount(data?.limit_stocks, 'up')
  const downCount = limitStockCount(data?.limit_stocks, 'down')
  const upStocks = sentiment.up_stocks ?? 0
  const downStocks = sentiment.down_stocks ?? 0
  const totalStocks = sentiment.total_stocks ?? 0
  const sentimentReasons = useMemo(
    () => buildSentimentReasons(sentiment, dimensions, { upStocks, downStocks, upCount, downCount, totalStocks }),
    [sentiment, dimensions, upStocks, downStocks, upCount, downCount, totalStocks],
  )
  const signalStocks = data?.signal_stocks ?? []
  const limitRows = useMemo(() => limitStockRows(data?.limit_stocks), [data?.limit_stocks])
  const signalMatrix = useMemo(() => mergeSignalMatrix(signalStocks), [signalStocks])
  const auctionCandidates = auctionPicks.length
    ? auctionPicks
    : (data?.auction_intent?.top_bullish?.length ? data.auction_intent.top_bullish : screeningPicks)
  const bullishAuctionRows = mergeAuctionRows(auctionCandidates, [])
  const bearishAuctionRows = mergeAuctionRows(data?.auction_intent?.top_bearish || [], [])
  const visibleAuctionRows = [...bullishAuctionRows, ...bearishAuctionRows]
  const sectorRows = useMemo(
    () => buildSectorResonanceRows(limitRows, signalMatrix, visibleAuctionRows),
    [limitRows, signalMatrix, visibleAuctionRows],
  )
  const topSectorRows = useMemo(() => sectorRows.slice(0, 5), [sectorRows])
  const selectedSector = sectorRows[selectedSectorIndex] ?? { name: '暂无板块', score: 0, upRatio: 0, change: 0, fund: 0 }
  const selectedSectorStocks = useMemo(
    () => sectorStockRows(selectedSector, signalStocks, visibleAuctionRows, limitRows),
    [selectedSector, signalStocks, visibleAuctionRows, limitRows],
  )
  const updatedAt = data?.refreshed_at || lastRefresh
  const currentDataDate = data?.data_freshness?.as_of || data?.refreshed_at

  return (
    <>
      <PrototypePageHeader
        title="市场情绪"
        subtitle="八维风向感知模型 · 历史回溯 · 板块分化"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={sentiment.trade_date}
            updatedAt={updatedAt}
            source={limitStockSource(data?.limit_stocks) || data?.data_sources?.signal_stocks || 'signal-service'}
            currentTradeDate={currentDataDate}
          />
        )}
        actions={[
          { key: 'hot', label: '过热(80+)' },
          { key: 'ice', label: '冰点(20-)' },
          { key: 'turn', label: '急转预警', active: true, tone: 'warn' },
        ]}
      />

      {error && (
        <div className="prototype-fallback" role="status">
          数据服务连接异常，当前展示最近一次可用快照；恢复连接后会自动刷新。
        </div>
      )}

      <nav className="market-subnav" role="tablist" aria-label="市场情绪子页签">
        {sentimentPages.map(page => (
          <button
            key={page.key}
            type="button"
            role="tab"
            aria-selected={sentimentPage === page.key}
            className={`market-subtab ${sentimentPage === page.key ? 'active' : ''}`}
            onClick={() => setSentimentPage(page.key)}
          >
            <span className="market-subtab-no">{page.number}</span>
            <span className="market-subtab-text">
              <strong>{page.label}</strong>
              <small>{page.desc}</small>
            </span>
          </button>
        ))}
      </nav>

      {sentimentPage === 'today' && (
        <section className="market-page" aria-label="今日市场">
          <div className="row r-6-4">
            <PrototypeCard title="综合情绪指数 · 八维风向感知" icon={<FundOutlined />} meta={`模型: ${sentiment.model ?? 'market_regime_v2'}`}>
              <div className="gauge-panel">
                <div className="gauge-chart-wrap">
                  <ReactECharts option={gaugeOption} className="gauge-chart" notMerge />
                  <div className="gauge-readout" aria-label={`综合情绪指数 ${sentiment.score} 分`}>
                    <b>{sentiment.score}</b><span>分</span>
                    <small>{sentiment.label}</small>
                  </div>
                </div>
                <div className="breakdown-dims">
                  {dimensions.map(dim => (
                    <div className="dim-row" key={dim.key}>
                      <div className="dim-lbl">{dim.label}<span>{dim.weight}%</span></div>
                      <div className="dim-bar-wrap">
                        <div className="dim-bar" style={{ width: `${dim.score}%`, background: dim.tone }} />
                      </div>
                      <div className={`dim-val ${dim.score >= 70 ? 'up' : dim.score >= 55 ? 'neu' : 'down'}`}>{dim.score}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="zit">加权合成: {sentiment.formula || '后端未返回模型公式'}</div>
              <div className="ai-sentiment-card">
                <div className="ai-title"><span>实时指标解读</span><em>基于接口返回</em></div>
                <p>当前市场情绪为 <b>{sentiment.label}</b>，综合分 <b>{sentiment.score}</b>。上涨 {upStocks.toLocaleString()} 只，下跌 {downStocks.toLocaleString()} 只，涨停 {upCount} 只，跌停 {downCount} 只。</p>
                <div className="ai-reason-grid">
                  {sentimentReasons.map((reason, index) => (
                    <div key={index}>
                      <strong>{reason.title}{reason.fallback ? ' · 待补齐' : ''}</strong>
                      <span>{reason.detail}</span>
                    </div>
                  ))}
                </div>
                <div className="risk-banner warn"><strong>风险提醒</strong><span>本区只使用接口返回字段；缺失的资金、炸板率和历史归因不会用演示数据补齐。</span></div>
              </div>
            </PrototypeCard>

            <div className="grid">
              <PrototypeCard title="市场快照" icon={<EyeOutlined />} meta={`基于 ${totalStocks.toLocaleString()} 只股票`}>
                <div className="snapshot-grid">
                  <div className="snap-stat"><div className="lbl">涨停</div><div className="val up">{upCount}</div><div className="sub">limit_stocks</div></div>
                  <div className="snap-stat"><div className="lbl">跌停</div><div className="val down">{downCount}</div><div className="sub">limit_stocks</div></div>
                  <div className="snap-stat"><div className="lbl">炸板</div><div className="val warn">--</div><div className="sub">暂无实时字段</div></div>
                  <div className="snap-stat"><div className="lbl">封板率</div><div className="val neu">--</div><div className="sub">暂无实时字段</div></div>
                </div>
                <div className="advance-decline">
                  <span className="num adv up">涨 {upStocks.toLocaleString()}</span>
                  <div className="bar-wrap">
                    <div className="bar-up" style={{ flex: Math.max(upStocks, 1) }} />
                    <div className="bar-down" style={{ flex: Math.max(downStocks, 1) }} />
                  </div>
                  <span className="num down">跌 {downStocks.toLocaleString()}</span>
                </div>
                <div style={{ fontSize: 10.5, color: 'var(--muted)', textAlign: 'center' }}>
                  涨跌比 <b style={{ color: 'var(--fg)' }}>{(upStocks / Math.max(downStocks, 1)).toFixed(2)}:1</b> · 平盘 {Math.max(totalStocks - upStocks - downStocks, 0).toLocaleString()} 只
                </div>
              </PrototypeCard>

              <PrototypeCard title="资金全景" icon={<DollarOutlined />} meta="实时字段">
                <div className="snapshot-grid">
                  <div className="snap-stat"><div className="lbl">北向资金</div><div className="val neu">--</div><div className="sub">暂无实时字段</div></div>
                  <div className="snap-stat"><div className="lbl">主力资金</div><div className="val neu">--</div><div className="sub">暂无实时字段</div></div>
                  <div className="snap-stat"><div className="lbl">融资余额</div><div className="val neu">--</div><div className="sub">暂无实时字段</div></div>
                  <div className="snap-stat"><div className="lbl">两市成交</div><div className="val neu">--</div><div className="sub">暂无实时字段</div></div>
                </div>
                <div className="prototype-empty-state">
                  <strong>资金全景待接入实时字段</strong>
                  <span>fallback_reason：北向 / 主力净流入、融资余额变化、两市成交额均需后端新增实时接口；前端不展示估算演示值，避免误导仓位判断。</span>
                </div>
              </PrototypeCard>

              <div className="op-hint">
                <div className="pos warn">--</div>
                <div className="op-body">
                  <div className="op-title warn">{sentiment.label}</div>
                  <div className="op-desc">仓位建议需等待交易策略服务返回；本页不使用静态仓位建议。</div>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {sentimentPage === 'history' && (
        <section className="market-page" aria-label="历史情绪">
          <div className="insight-grid">
            <MetricCard label="当前分位" value="--" sub="fallback_reason：后端暂无历史分位接口，补齐后将显示近 60 日分位（如 72/偏高）。" tone="warn" />
            <MetricCard label="情绪斜率" value="--" sub="fallback_reason：后端暂无连续情绪序列，无法计算 3 日斜率变化。" tone="down" />
            <MetricCard label="回撤风险" value="--" sub="fallback_reason：后端暂无历史回撤接口，补齐后将显示低/中/高风险评级。" tone="accent" />
            <MetricCard label="历史相似" value="--" sub="fallback_reason：后端暂无相似样本匹配接口，补齐后将显示相似次数与胜率。" tone="muted" />
          </div>
          <div className="history-layout">
            <PrototypeCard title="情绪历史趋势" icon={<LineChartOutlined />} meta="30日 · 60日 · 120日">
              <ReactECharts option={trendOption} style={{ height: 420, width: '100%' }} notMerge />
            </PrototypeCard>
            <div className="history-side">
              <PrototypeCard title="历史相似场景" icon={<EyeOutlined />} meta="按相似度排序">
                <EmptyState
                  title="历史相似场景待接入"
                  detail="fallback_reason：后端暂无相似样本接口，不展示演示历史样本，避免误导周期判断。"
                />
              </PrototypeCard>
              <PrototypeCard title="周期状态表" icon={<BarChartOutlined />} meta="模型判断">
                <EmptyState
                  title="周期状态表待接入"
                  detail="fallback_reason：后端暂无周期判定接口，不展示固定的冰点/中性/偏牛/过热分档。"
                />
              </PrototypeCard>
            </div>
          </div>
        </section>
      )}

      {sentimentPage === 'sector' && (
        <section className="market-page" aria-label="板块共振">
          <div className="sector-top5">
            {topSectorRows.length === 0 && <div className="prototype-fallback">暂无板块共振数据；等待实时信号、涨停或竞价数据返回行业字段。</div>}
            {topSectorRows.map((sector, index) => {
              const color = sectorColor(sector.score)
              return (
                <button
                  key={sector.name}
                  type="button"
                  className={`top-sector-card ${color.className} ${selectedSector.name === sector.name ? 'active' : ''}`}
                  onClick={() => {
                    setSelectedSectorIndex(index)
                    setSectorDetailOpen(true)
                  }}
                >
                  <span>TOP {index + 1}</span>
                  <small>{color.level}</small>
                  <strong>{sector.name} {sector.score}</strong>
                  <em>上涨占比 {sector.upRatio}% · 均涨 {sector.change >= 0 ? '+' : ''}{sector.change}%</em>
                </button>
              )
            })}
          </div>

          <div className="resonance-note">
            <div><b>结论：</b>{topSectorRows.length ? `当前最强板块为 ${topSectorRows[0].name}，共振分 ${topSectorRows[0].score}。` : '暂无实时板块共振结论。'}</div>
            <div><b>数据来源：</b>涨跌明细、实时信号、竞价看多/看空列表。</div>
            <div><b>说明：</b>没有接口字段的二级方向、资金净流入和补涨判断不会用静态文案补齐。</div>
          </div>

          <div className="sector-layout">
            <PrototypeCard title="板块共振热力图" icon={<ApartmentOutlined />} meta="分数越高，共振越强">
              <div className="sector-grid resonance-grid">
                {sectorRows.map((sector, index) => {
                  const color = sectorColor(sector.score)
                  return (
                    <button
                      type="button"
                      className={`sector-cell ${color.className} ${selectedSector.name === sector.name ? 'active' : ''}`}
                      key={sector.name}
                      style={{ background: color.bg, borderLeftColor: color.border }}
                      onClick={() => {
                        setSelectedSectorIndex(index)
                      }}
                    >
                      <div className="sn">{sector.name}</div>
                      <div className="ss" style={{ color: color.text }}>{sector.score}</div>
                      <div className="sd">涨{sector.upRatio}% · 均涨{sector.change >= 0 ? '+' : ''}{sector.change}% · {sector.fund >= 0 ? '+' : ''}{sector.fund}亿</div>
                      <span className={`tag t-${sector.score >= 70 ? 'warn' : sector.score >= 60 ? 'up' : sector.score >= 50 ? 'accent' : 'neu'}`}>{color.level}</span>
                    </button>
                  )
                })}
              </div>
            </PrototypeCard>

            <div className="sector-side">
              <PrototypeCard title="选中板块详情" icon={<EyeOutlined />} meta="点击左侧格子切换">
              <div className="sector-detail-card">
                <h3>{selectedSector.name}</h3>
                  <p>基于接口返回的行业字段聚合。</p>
                  <div className="detail-kpis">
                    <div><span>共振分</span><b>{selectedSector.score}</b></div>
                    <div><span>上涨占比</span><b>{selectedSector.upRatio}%</b></div>
                    <div><span>资金</span><b>{selectedSector.fund >= 0 ? '+' : ''}{selectedSector.fund}亿</b></div>
                  </div>
                  <div className="analysis-box"><b>看点：</b>仅展示接口返回股票明细；二级方向和补涨线等待后端接口接入。</div>
                  <div className="sector-stock-section">
                    <h4>板块股票涨幅明细</h4>
                    <SectorStockTable rows={selectedSectorStocks} />
                  </div>
                  <div className="prototype-fallback mt14">暂无二级方向实时接口。</div>
                </div>
              </PrototypeCard>
              <PrototypeCard title="实时共振结论" icon={<FundOutlined />} meta="基于接口聚合">
                <div className="ai-resonance">
                  <p><b>结论：</b>{topSectorRows.length ? `强度最高的是 ${topSectorRows[0]?.name}。` : '暂无可聚合板块。'}</p>
                  <p><b>注意：</b>本结论只来自当前接口数据，不包含未接入的资金流或二级方向判断。</p>
                </div>
              </PrototypeCard>
            </div>
          </div>
        </section>
      )}

      <Drawer
        title={`${selectedSector.name} 股票涨幅明细`}
        open={sentimentPage === 'sector' && sectorDetailOpen}
        onClose={() => setSectorDetailOpen(false)}
        width={620}
      >
        <div className="sector-drawer-summary">
          <div><span>共振分</span><b>{selectedSector.score}</b></div>
          <div><span>上涨占比</span><b>{selectedSector.upRatio}%</b></div>
          <div><span>资金</span><b>{selectedSector.fund >= 0 ? '+' : ''}{selectedSector.fund}亿</b></div>
        </div>
        <SectorStockTable rows={selectedSectorStocks} />
      </Drawer>

      <div className="footer-bar">
        <span>数据来源: signal-service (market_regime_v2 + daily_kline)</span>
        <span className="sep" />
        <span>模型: 八维风向感知</span>
        <span className="sep" />
        <span>市场情绪指数为量化模型计算结果，不构成投资建议</span>
        {lastRefresh && <><span className="sep" /><span>最近刷新 {lastRefresh}</span></>}
      </div>
    </>
  )
}
