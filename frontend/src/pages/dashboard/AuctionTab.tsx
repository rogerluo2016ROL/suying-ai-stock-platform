import ReactECharts from 'echarts-for-react'
import {
  ApartmentOutlined,
  FireOutlined,
  LineChartOutlined,
  RadarChartOutlined,
  TableOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { DataFreshnessBar, EmptyState, MetricCard, PrototypeCard, PrototypePageHeader } from '../../components/prototype'
import { signalLevelTokens } from '../../styles/tokens'
import type { AuctionIntentItem, DashboardData } from './types'
import {
  auctionBucketPct,
  auctionChange,
  auctionDimensionRows,
  auctionIntentLabel,
  auctionScore,
  auctionSectorHeat,
  buildAuctionRadarOption,
  buildAuctionTimelineOption,
  mergeAuctionRows,
  normalizeSentiment,
} from './helpers'

interface AuctionTabProps {
  data: DashboardData | null
  lastRefresh: string
  screeningPicks: AuctionIntentItem[]
  auctionPicks: AuctionIntentItem[]
}

export default function AuctionTab({ data, lastRefresh, screeningPicks, auctionPicks }: AuctionTabProps) {
  const sentiment = normalizeSentiment(data)
  const updatedAt = data?.refreshed_at || lastRefresh
  const currentDataDate = data?.data_freshness?.as_of || data?.refreshed_at
  const auctionCandidates = auctionPicks.length
    ? auctionPicks
    : (data?.auction_intent?.top_bullish?.length ? data.auction_intent.top_bullish : screeningPicks)
  const bullishAuctionRows = mergeAuctionRows(auctionCandidates, [])
  const bearishAuctionRows = mergeAuctionRows(data?.auction_intent?.top_bearish || [], [])
  const visibleAuctionRows = [...bullishAuctionRows, ...bearishAuctionRows]
  const analyzedCount = data?.auction_intent?.total_analyzed ?? visibleAuctionRows.length
  const strongBullishCount = data?.auction_intent?.strong_bullish_count ?? visibleAuctionRows.filter(item => auctionScore(item, 0) >= 75).length
  const moderateBullishCount = data?.auction_intent?.moderate_bullish_count ?? visibleAuctionRows.filter(item => {
    const score = auctionScore(item, 0)
    return score >= 60 && score < 75
  }).length
  const neutralAuctionCount = data?.auction_intent?.neutral_count ?? visibleAuctionRows.filter(item => {
    const score = auctionScore(item, 0)
    return score >= 40 && score < 60
  }).length
  const moderateBearishCount = data?.auction_intent?.moderate_bearish_count ?? visibleAuctionRows.filter(item => {
    const score = auctionScore(item, 0)
    return score >= 25 && score < 40
  }).length
  const strongBearishCount = data?.auction_intent?.strong_bearish_count ?? visibleAuctionRows.filter(item => auctionScore(item, 0) < 25).length

  return (
    <>
      <PrototypePageHeader
        title="竞价意图"
        subtitle="四维评分模型 · 撮合价走势 · 一字定方向 · 全量明细"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={data?.auction_intent?.trade_date || sentiment.trade_date}
            updatedAt={updatedAt}
            source={data?.auction_intent?.data_source || 'dashboard/auction'}
            currentTradeDate={currentDataDate}
          />
        )}
        actions={[
          { key: 'refresh', label: '手动刷新', active: true, tone: 'neutral' },
        ]}
      />
      <div className="kpis">
        <MetricCard label="分析标的" value={analyzedCount} sub="覆盖沪深两市竞价" tone="muted" />
        <MetricCard label="强烈抢筹" value={strongBullishCount} sub={`评分 ≥ 75 · 占比 ${auctionBucketPct(strongBullishCount, analyzedCount)}`} tone="down" />
        <MetricCard label="偏多抢筹" value={moderateBullishCount} sub={`评分 60-74 · 占比 ${auctionBucketPct(moderateBullishCount, analyzedCount)}`} tone="warn" />
        <MetricCard label="中性" value={neutralAuctionCount} sub={`评分 40-59 · 占比 ${auctionBucketPct(neutralAuctionCount, analyzedCount)}`} tone="accent" />
        <MetricCard label="偏空出货" value={moderateBearishCount} sub={`评分 25-39 · 占比 ${auctionBucketPct(moderateBearishCount, analyzedCount)}`} tone="muted" />
        <MetricCard label="强烈出货" value={strongBearishCount} sub={`评分 < 25 · 占比 ${auctionBucketPct(strongBearishCount, analyzedCount)}`} tone="up" />
      </div>
      <div className="row r-1-1">
        <PrototypeCard title="抢筹 TOP 10" icon={<FireOutlined />} meta="评分从高到低 · 点击选中个股">
          <table className="tbl">
            <thead><tr><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
            <tbody>
              {bullishAuctionRows.map((item, index) => (
                <tr key={item.code} className={index === 2 ? 'sel' : ''}>
                  <td>{index + 1}</td>
                  <td className="code">{item.code}</td>
                  <td className="nm">{item.name}</td>
                  <td className="r up">+{Math.abs(auctionChange(item)).toFixed(2)}%</td>
                  <td className="r mono">{Number(item.vol_ratio ?? 9 + index / 2).toFixed(1)}x</td>
                  <td className="r mono up">{auctionScore(item, 90 - index)}</td>
                  <td><span className="tag t-warn">{auctionIntentLabel(item, 90 - index)}</span></td>
                </tr>
              ))}
              {bullishAuctionRows.length === 0 && (
                <tr><td colSpan={7} className="prototype-panel-note">暂无抢筹数据，等待 dashboard/auction 或 signal/dashboard-summary 返回。</td></tr>
              )}
            </tbody>
          </table>
        </PrototypeCard>

        <PrototypeCard title="出货预警 TOP 10" icon={<ThunderboltOutlined />} meta="评分从低到高 · 点击选中个股">
          <table className="tbl">
            <thead><tr><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
            <tbody>
              {bearishAuctionRows.map((item, index) => (
                <tr key={item.code}>
                  <td>{index + 1}</td>
                  <td className="code down">{item.code}</td>
                  <td className="nm">{item.name}</td>
                  <td className="r down">{auctionChange(item).toFixed(2)}%</td>
                  <td className="r mono">{Number(item.vol_ratio ?? 8 + index / 2).toFixed(1)}x</td>
                  <td className="r mono down">{auctionScore(item, 18 + index * 2)}</td>
                  <td><span className="tag t-neu">{auctionIntentLabel(item, 18 + index * 2)}</span></td>
                </tr>
              ))}
              {bearishAuctionRows.length === 0 && (
                <tr><td colSpan={7} className="prototype-panel-note">暂无出货预警。</td></tr>
              )}
            </tbody>
          </table>
        </PrototypeCard>
      </div>

      {/* 1.2 撮合价走势 + 四维评分：选中个股（默认首只抢筹） */}
      {(() => {
        const selectedAuction = bullishAuctionRows[0] || bearishAuctionRows[0]
        if (!selectedAuction) return null
        const timelineOption = buildAuctionTimelineOption(selectedAuction)
        const radarOption = buildAuctionRadarOption(selectedAuction)
        const score = auctionScore(selectedAuction, 0)
        const tone = score >= 60 ? 'up' : score >= 40 ? 'warn' : 'down'
        const scoreColor = score >= 60 ? signalLevelTokens.STRONG_BUY : score >= 40 ? signalLevelTokens.HOLD : signalLevelTokens.SELL
        return (
          <div className="row r-1-1">
            <PrototypeCard title="竞价撮合价走势" icon={<LineChartOutlined />} meta={`选中: ${selectedAuction.name || ''} ${selectedAuction.code} · 9:15-9:25`}>
              <ReactECharts option={timelineOption} style={{ height: 280, width: '100%' }} notMerge />
              <div className="prototype-panel-note">数据来源: Tushare stk_auction (实时) / stk_mins (降级) · 缺数据按昨收→竞价价插值不空白</div>
            </PrototypeCard>
            <PrototypeCard title="四维评分" icon={<RadarChartOutlined />} meta="竞价意图拆解">
              <ReactECharts option={radarOption} style={{ height: 200, width: '100%' }} notMerge />
              <div className="stock-info">
                <div className="si-code mono">{selectedAuction.code}</div>
                <div className="si-name">{selectedAuction.name}</div>
                <div className="si-row"><span className="si-lbl">竞价价</span><span className={`si-val ${tone}`}>{Number(selectedAuction.price ?? 0).toFixed(2)}</span></div>
                <div className="si-row"><span className="si-lbl">涨幅</span><span className={`si-val ${tone}`}>{auctionChange(selectedAuction).toFixed(2)}%</span></div>
                <div className="si-row"><span className="si-lbl">评分</span><span className="si-val" style={{ color: scoreColor }}>{score} 分</span></div>
                {selectedAuction.reasons && selectedAuction.reasons.length > 0 && (
                  <div className="chips mt6">
                    {selectedAuction.reasons.map(reason => <span className="chip" key={reason}>{reason}</span>)}
                  </div>
                )}
              </div>
            </PrototypeCard>
          </div>
        )
      })()}

      {/* 1.2 一字定方向：板块竞价热度 */}
      {(() => {
        const heat = auctionSectorHeat(visibleAuctionRows)
        if (heat.length === 0) {
          return (
            <PrototypeCard title="一字定方向" icon={<ApartmentOutlined />} meta="板块竞价热度 · 竞价共振题材">
              <EmptyState title="暂无板块竞价数据" detail="等待竞价快照写入后按行业聚合展示竞价热度与共振题材。" />
            </PrototypeCard>
          )
        }
        const maxCount = Math.max(...heat.map(item => item.count))
        return (
          <PrototypeCard title="一字定方向" icon={<ApartmentOutlined />} meta="板块竞价热度 · 竞价共振题材">
            <div className="sector-grid">
              {heat.map(item => {
                const intensity = Math.round((item.count / maxCount) * 100)
                const tone = item.avgScore >= 60 ? 'up' : item.avgScore >= 40 ? 'warn' : 'down'
                return (
                  <div className="sector-cell" key={item.sector}>
                    <div className="sector-cell-name">{item.sector}</div>
                    <div className={`sector-cell-score ${tone}`}>{item.avgScore}</div>
                    <div className="sector-cell-bar"><span style={{ width: `${intensity}%` }} /></div>
                    <div className="sector-cell-meta">{item.count} 只 · {item.change >= 0 ? '+' : ''}{item.change.toFixed(2)}%</div>
                  </div>
                )
              })}
            </div>
          </PrototypeCard>
        )
      })()}

      {/* 1.2 全量竞价明细 */}
      <PrototypeCard title="全量竞价明细" icon={<TableOutlined />} meta={`共 ${visibleAuctionRows.length} 只 · 评分排序`}>
        {visibleAuctionRows.length === 0 ? (
          <EmptyState title="暂无竞价明细" detail="等待 dashboard/auction 或 signal/dashboard-summary 返回全量竞价快照。" />
        ) : (
          <table className="tbl">
            <thead><tr><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅%</th><th className="r">竞价价</th><th className="r">竞量比</th><th className="r">委比</th><th className="r">评分</th><th>意图</th><th>板块</th></tr></thead>
            <tbody>
              {visibleAuctionRows.map((item, index) => {
                const score = auctionScore(item, 0)
                const tone = score >= 60 ? 'up' : score >= 40 ? 'warn' : 'down'
                return (
                  <tr key={item.code}>
                    <td>{index + 1}</td>
                    <td className="code">{item.code}</td>
                    <td className="nm">{item.name}</td>
                    <td className={`r ${auctionChange(item) >= 0 ? 'up' : 'down'}`}>{auctionChange(item).toFixed(2)}%</td>
                    <td className="r mono">{Number(item.price ?? 0).toFixed(2)}</td>
                    <td className="r mono">{Number(item.vol_ratio ?? 0).toFixed(1)}x</td>
                    <td className="r mono">{Number(item.buy_sell_ratio ?? 0).toFixed(2)}</td>
                    <td className={`r mono ${tone}`}>{score}</td>
                    <td><span className={`tag t-${tone === 'up' ? 'down' : tone === 'warn' ? 'warn' : 'neu'}`}>{auctionIntentLabel(item, score)}</span></td>
                    <td>{item.industry || '综合'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </PrototypeCard>
    </>
  )
}
