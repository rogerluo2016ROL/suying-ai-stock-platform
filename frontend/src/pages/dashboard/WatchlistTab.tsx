import { useMemo } from 'react'
import {
  ApartmentOutlined,
  AreaChartOutlined,
  DollarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { DataFreshnessBar, MetricCard, PrototypeCard, PrototypePageHeader } from '../../components/prototype'
import type { DashboardData } from './types'
import {
  marketCapYi,
  mergeWatchlistRows,
  normalizeSentiment,
  signalDisplay,
  signalTone,
  watchlistSectorRows,
} from './helpers'

interface WatchlistTabProps {
  data: DashboardData | null
  lastRefresh: string
}

export default function WatchlistTab({ data, lastRefresh }: WatchlistTabProps) {
  const sentiment = normalizeSentiment(data)
  const updatedAt = data?.refreshed_at || lastRefresh
  const watchlist = useMemo(() => mergeWatchlistRows(data?.watchlist), [data?.watchlist])
  const watchlistSectorStats = useMemo(() => watchlistSectorRows(watchlist), [watchlist])
  const watchlistWinners = watchlist.filter(item => Number(item.change_pct ?? 0) >= 0).length
  const watchlistLosers = Math.max(watchlist.length - watchlistWinners, 0)
  const strongestWatch = watchlist.reduce((best, item) => Number(item.change_pct ?? -Infinity) > Number(best.change_pct ?? -Infinity) ? item : best, watchlist[0])
  const weakestWatch = watchlist.reduce((worst, item) => Number(item.change_pct ?? Infinity) < Number(worst.change_pct ?? Infinity) ? item : worst, watchlist[0])
  const buySignalCount = watchlist.filter(item => ['强买', '买入'].some(label => item.signal?.includes(label))).length
  const warnSignalCount = watchlist.filter(item => ['减仓', '风险'].some(label => item.signal?.includes(label))).length
  const avgWatchReturn = watchlist.reduce((sum, item) => sum + Number(item.change_pct ?? 0), 0) / Math.max(watchlist.length, 1)

  return (
    <>
      <PrototypePageHeader
        title="自选跟踪"
        subtitle={`${watchlist.length} 只自选 · 实时行情 · 信号监控 · 盈亏分析`}
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={sentiment.trade_date}
            updatedAt={updatedAt}
            source={data?.data_sources?.watchlist || 'watchlist'}
          />
        )}
        actions={[
          { key: 'sort', label: '排序: 涨跌幅', active: true, tone: 'neutral' },
          { key: 'signal', label: '信号' },
          { key: 'market-cap', label: '市值' },
          { key: 'industry', label: '行业' },
        ]}
      />

      <div className="watchlist-kpis">
        <MetricCard label="自选等权盈亏" value={`${avgWatchReturn >= 0 ? '+' : ''}${avgWatchReturn.toFixed(2)}%`} sub={`${watchlistWinners}涨 · ${watchlistLosers}跌`} tone="down" />
        <MetricCard label="今日最强" value={`${strongestWatch?.code ?? '--'} ${strongestWatch?.name?.slice(0, 2) ?? '--'}`} sub={`${Number(strongestWatch?.change_pct ?? 0) >= 0 ? '+' : ''}${Number(strongestWatch?.change_pct ?? 0).toFixed(1)}% · 评分 ${strongestWatch?.score ?? '--'}`} tone="up" />
        <MetricCard label="今日最弱" value={`${weakestWatch?.code ?? '--'} ${weakestWatch?.name?.slice(0, 2) ?? '--'}`} sub={`${Number(weakestWatch?.change_pct ?? 0).toFixed(1)}% · 距止损 ${weakestWatch?.stop_distance ?? 0.7}%`} tone="down" />
        <MetricCard label="买入信号" value={`${buySignalCount} 只`} sub="来自 watchlist.signal" tone="up" />
        <MetricCard label="卖出/警报" value={`${warnSignalCount} 只`} sub="减仓 / 风险标签" tone="warn" />
        <MetricCard label="板块覆盖" value={`${watchlistSectorStats.length} 个`} sub={watchlistSectorStats[0] ? `${watchlistSectorStats[0][0]}最集中 (${watchlistSectorStats[0][1]}只)` : '暂无自选'} tone="accent" />
      </div>

      <div className="watchlist-layout">
        <PrototypeCard title="自选清单" icon={<AreaChartOutlined />} meta="实时行情 · 点击跳转诊断">
          <div className="watch-add-bar">
            <span>+ 添加</span>
            <input aria-label="添加自选代码" placeholder="输入代码 如 000001" />
            <button type="button" className="tag t-neu">添加</button>
            <small>从选股导入</small>
          </div>
          <div className="watch-table-head">
            <span>代码</span><span>名称</span><span>现价</span><span>涨跌幅</span><span>5日走势</span><span>信号</span><span>行业</span><span>市值</span><span>操作</span>
          </div>
          <div className="watch-table-body">
            {watchlist.map((item, index) => {
              const change = Number(item.change_pct ?? 0)
              const isRisk = item.signal?.includes('减仓') || item.signal?.includes('风险')
              return (
                <div className={`watch-stock-row ${isRisk ? 'risk' : ''}`} key={item.code}>
                  <span className={`code ${change >= 3 ? 'up' : isRisk ? 'warn' : ''}`}>{item.code}</span>
                  <span className="nm">{item.name}</span>
                  <span className="mono">{Number(item.price ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                  <span className={`mono ${change >= 0 ? 'up' : 'down'}`}>{change >= 0 ? '+' : ''}{change.toFixed(2)}%</span>
                  <span className="mini-trend" aria-label={`${item.name} 5日走势`}>
                    {[0, 1, 2, 3, 4].map(step => (
                      <i
                        key={step}
                        style={{ height: `${10 + Math.max(0, change) * 2 + ((index + step) % 3) * 4}px` }}
                      />
                    ))}
                  </span>
                  <span><span className={`tag ${signalTone(item.signal)}`}>{signalDisplay(item)}</span></span>
                  <span>{item.industry ?? '未知'}</span>
                  <span className="mono">{marketCapYi(item).toLocaleString()}亿</span>
                  <span className="watch-actions">诊断 · ×</span>
                </div>
              )
            })}
            {watchlist.length === 0 && <div className="prototype-panel-note">暂无自选股数据。</div>}
          </div>
        </PrototypeCard>

        <div className="grid">
          <PrototypeCard title="行业分布" icon={<ApartmentOutlined />} meta={`${watchlist.length}只 · ${watchlistSectorStats.length}板块`}>
            <div className="watch-sector-list">
              {watchlistSectorStats.map(([sector, count]) => (
                <div className="watch-sector-bar" key={sector}>
                  <span>{sector}</span>
                  <div><i style={{ width: `${Math.max(24, count / Math.max(watchlist.length, 1) * 100)}%` }} /></div>
                  <b>{count}只</b>
                </div>
              ))}
              {watchlistSectorStats.length === 0 && <div className="prototype-panel-note">暂无行业分布。</div>}
            </div>
            <div className="zit">{watchlistSectorStats[0] ? `${watchlistSectorStats[0][0]}集中度 ${Math.round(watchlistSectorStats[0][1] / Math.max(watchlist.length, 1) * 100)}% · 建议分散` : '等待自选股数据'}</div>
          </PrototypeCard>

          <PrototypeCard title="盈亏贡献" icon={<DollarOutlined />} meta="按涨跌排序">
            <div className="watch-perf-list">
              {[...watchlist].sort((a, b) => Number(b.change_pct ?? 0) - Number(a.change_pct ?? 0)).slice(0, 6).map(item => {
                const change = Number(item.change_pct ?? 0)
                return (
                  <div className="watch-perf-row" key={item.code}>
                    <span className={`mono ${change >= 0 ? 'up' : 'down'}`}>{change >= 0 ? '+' : ''}{change.toFixed(1)}%</span>
                    <div><i style={{ width: `${Math.min(100, Math.abs(change) / 8.2 * 100)}%` }} /></div>
                    <b className={change >= 0 ? 'up' : 'down'}>{item.name}</b>
                  </div>
                )
              })}
              {watchlist.length === 0 && <div className="prototype-panel-note">暂无盈亏贡献。</div>}
            </div>
            <div className="watch-avg-row"><span>等权平均</span><b className="up">{avgWatchReturn >= 0 ? '+' : ''}{avgWatchReturn.toFixed(2)}%</b></div>
          </PrototypeCard>

          <PrototypeCard title="信号联动" icon={<ThunderboltOutlined />} meta="自选股信号触发">
            <div className="watch-alert-list">
              {watchlist
                .filter(item => item.signal || item.risk_note || typeof item.stop_distance === 'number')
                .slice(0, 6)
                .map(item => {
                  const tone = item.signal?.includes('减仓') || item.signal?.includes('风险') || item.risk_note ? 'warn' : 'up'
                  const title = `${item.name} ${signalDisplay(item)}`
                  const detail = item.risk_note || `现价 ${item.price ?? '-'} · 评分 ${item.score ?? '-'} · 行业 ${item.industry ?? '未知'}`
                  return (
                    <div className="watch-alert-row" key={title}>
                      <span className={`led ${tone === 'up' ? 'on' : 'warn'}`} />
                      <div><b className={tone === 'up' ? 'up' : 'warn'}>{title}</b><small>{detail}</small></div>
                    </div>
                  )
                })}
              {watchlist.length === 0 && <div className="prototype-panel-note">暂无自选信号联动。</div>}
            </div>
          </PrototypeCard>
        </div>
      </div>

      <div className="footer-bar">
        <span>自选表: PG watchlist · 行情: daily_kline · 信号: signal-service</span>
        <span className="sep" />
        <span>覆盖: 实时行情 · 5日走势 · 六维信号 · 止损监控 · 审计风险 · 板块分布</span>
        <span className="sep" />
        <span>点击股票跳转诊断 · × 移出自选</span>
      </div>
    </>
  )
}
