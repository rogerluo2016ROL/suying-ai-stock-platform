import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  BarChartOutlined,
  CheckCircleOutlined,
  DollarOutlined,
  FireOutlined,
  FundOutlined,
  LineChartOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { chainApi, signalApi, tradeApi } from '../api/client'
import type { ChainCandidate, DecisionContextRecord, Position, RiskVerdictRecord, StockSignal, TradeAccount, TradeOrder } from '../api/types'
import { DataFreshnessBar, MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, PrototypeTabs, SegmentTabs } from '../components/prototype'

const tabs = [
  { key: 'overview', path: '/open-decision', label: '决策总览', subLabel: '开盘闸门' },
  { key: 'auction', path: '/open-decision/auction', label: '竞价分析', subLabel: '集合竞价' },
  { key: 'signals', path: '/open-decision/signals', label: '信号扫描', subLabel: '触发队列' },
  { key: 'candidates', path: '/open-decision/candidates', label: '候选池', subLabel: 'AI 队列' },
  { key: 'execution', path: '/open-decision/execution', label: '执行监控', subLabel: '链路状态' },
]

const overnightNews = [
  { type: '公告', tone: 'danger', title: '中芯国际: 收到证监会立案调查通知书', impact: '影响: 高 · 竞价强度需复核', time: '昨 20:35' },
  { type: '公告', tone: 'danger', title: '贵州茅台: 半年度业绩预增 15%-20%', impact: '影响: 中 · 白酒高位分歧', time: '昨 19:00' },
  { type: '外盘', tone: 'accent', title: '美股三大指数收涨 · 道指 +0.32% · 纳指 +1.15%', impact: '影响: 正向 · AI算力风险偏好回暖', time: '今 05:00' },
  { type: '期货', tone: 'accent', title: 'A50 指数期货 +0.28% · 恒生期货 +0.45%', impact: '影响: 正向 · 开盘资金承接观察', time: '今 08:30' },
  { type: '舆情', tone: 'warn', title: '热词: #降息预期 #半导体出口管制 #新能源政策', impact: '影响: 主题催化 · 纳入情绪模型', time: '-' },
]

interface AuctionRow {
  code: string
  name: string
  industry?: string
  gap?: number
  drop?: number
  vol: number
  score: number
  intent: string
}

interface DashboardAuctionPick {
  code?: string
  name?: string
  industry?: string
  gap_pct?: number
  chg_pct?: number
  score?: number
  vol_ratio?: number
  volume_ratio?: number
  vol_z?: number
  intent?: string
}

interface SectorRow {
  name: string
  count: number
  change: number
  lead: string
  width: number
}

interface SignalRow {
  code: string
  name: string
  price: string
  signal: string
  score: number
  kronos: string
  target: string
  confidence: number
  consistency: string
  risk: string
  action: string
  watchlist: boolean
  dimensions: Array<{ label: string; value: number }>
}

interface CandidateRow {
  code: string
  name: string
  source: string
  score: number
  risk: string
  size: string
}

interface OrderRow {
  time: string
  code: string
  name: string
  dir: string
  price: string
  qty: string
  status: string
}

interface PositionRow {
  code: string
  name: string
  value: string
  pnl: string
  weight: string
}

interface OpenDecisionState {
  liveSignals: StockSignal[]
  liveTradeDate?: string
  candidates: ChainCandidate[]
  account?: TradeAccount
  positions: Position[]
  orders: TradeOrder[]
  verdicts: RiskVerdictRecord[]
  contexts: DecisionContextRecord[]
  auction: Record<string, unknown>
  loading: boolean
  error: string
}

const emptyState: OpenDecisionState = {
  liveSignals: [],
  liveTradeDate: undefined,
  candidates: [],
  positions: [],
  orders: [],
  verdicts: [],
  contexts: [],
  auction: {},
  loading: true,
  error: '',
}

function num(value: unknown, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function formatMoney(value?: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-'
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(1)}万`
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

function formatPct(value?: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-'
  const normalized = Math.abs(value) <= 1 ? value * 100 : value
  return `${normalized >= 0 ? '+' : ''}${normalized.toFixed(1)}%`
}

function signalLabel(level: StockSignal['level']) {
  const labels: Record<StockSignal['level'], string> = {
    strong_buy: '强买',
    buy: '买入',
    hold: '观察',
    sell: '减仓',
    strong_sell: '强卖',
  }
  return labels[level] || level
}

function signalLabelFromApi(signal: StockSignal) {
  if (signal.level) return signalLabel(signal.level)
  const raw = String((signal as StockSignal & { signal?: string }).signal || '').toLowerCase()
  if (raw.includes('bear') || raw.includes('sell') || raw.includes('空')) return '减仓'
  if (raw.includes('bull') || raw.includes('buy') || raw.includes('多')) return '买入'
  return '观察'
}

function orderStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    pending: '待成交',
    filled: '已成交',
    partial: '部分成交',
    cancelled: '已撤单',
    rejected: '已拒绝',
  }
  return labels[String(status || '')] || String(status || '-')
}

function candidateRisk(candidate: ChainCandidate, verdicts: RiskVerdictRecord[]) {
  const verdict = verdicts.find(item => item.symbol === candidate.code || item.candidate_id === candidate.candidate_id)
  if (!verdict) return '待风控'
  if (verdict.result === 'pass') return '通过'
  if (verdict.result === 'warn' || verdict.result === 'manual_review') return '仓位复核'
  return '止损'
}

function sectorRowsFromCandidates(candidates: ChainCandidate[]): SectorRow[] {
  const buckets = new Map<string, ChainCandidate[]>()
  candidates.forEach(candidate => {
    const sector = candidate.industry || candidate.resonance_level || '未分组'
    buckets.set(sector, [...(buckets.get(sector) || []), candidate])
  })
  return Array.from(buckets.entries())
    .map(([name, rows]) => {
      const avg = rows.reduce((sum, row) => sum + num(row.last_change_pct ?? row.change_pct), 0) / Math.max(rows.length, 1)
      const lead = rows
        .slice(0, 2)
        .map(row => `${row.name || row.code} ${formatPct(row.last_change_pct ?? row.change_pct)}`)
        .join(' / ')
      return { name, count: rows.length, change: Number(avg.toFixed(1)), lead: lead || '-', width: Math.min(96, Math.max(16, Math.round(avg * 12 + 48))) }
    })
    .sort((a, b) => b.count - a.count || b.change - a.change)
}

function signalRowsFromApi(signals: StockSignal[], verdicts: RiskVerdictRecord[]): SignalRow[] {
  return signals.map(signal => {
    const score = Math.round(num(signal.score ?? signal.confidence, 0))
    const fallbackReason = (signal as StockSignal & { fallback_reason?: string }).fallback_reason
    const dimensions = [
      { label: '技术面', value: Math.round(num(signal.dimensions?.technical, score)) },
      { label: '资金面', value: Math.round(num(signal.dimensions?.money_flow, score)) },
      { label: '基本面', value: Math.round(num(signal.dimensions?.fundamental, score)) },
      { label: '情绪', value: Math.round(num(signal.dimensions?.sentiment, score)) },
      { label: '置信度', value: Math.round(num(signal.confidence, score)) },
      { label: '风控', value: verdicts.some(item => item.symbol === signal.code && item.result !== 'pass') ? 45 : 78 },
    ]
    const risk = verdicts.some(item => item.symbol === signal.code && item.result === 'reject')
      ? '止损'
      : verdicts.some(item => item.symbol === signal.code && (item.result === 'warn' || item.result === 'manual_review'))
        ? '仓位复核'
        : '通过'
    return {
      code: signal.code,
      name: signal.name || signal.code,
      price: typeof (signal as StockSignal & { price?: number }).price === 'number'
        ? String((signal as StockSignal & { price?: number }).price)
        : '-',
      signal: signalLabelFromApi(signal),
      score,
      kronos: fallbackReason ? '模型不可用' : '-',
      target: '-',
      confidence: Math.round(num(signal.confidence, score)),
      consistency: fallbackReason ? '待确认' : '双确认',
      risk,
      action: risk === '止损' ? '排除' : risk === '仓位复核' ? '降低优先级' : '确认买入',
      watchlist: false,
      dimensions,
    }
  })
}

function candidateRowsFromApi(candidates: ChainCandidate[], verdicts: RiskVerdictRecord[]): CandidateRow[] {
  return candidates.map(candidate => ({
    code: candidate.code,
    name: candidate.name || candidate.code,
    source: candidate.trade_signal || candidate.resonance_level || '产业链候选',
    score: Math.round(num(candidate.score ?? candidate.resonance_score ?? candidate.chokepoint_score, 0)),
    risk: candidateRisk(candidate, verdicts),
    size: `${Math.max(5, Math.min(30, Math.round(num(candidate.score ?? 50, 50) / 4)))}%`,
  }))
}

function auctionRowsFromSignals(signals: SignalRow[], candidates: CandidateRow[]): AuctionRow[] {
  const source = signals.length
    ? signals.map(row => ({ code: row.code, name: row.name, score: row.score, gap: Math.max(0, Math.round((row.score - 50) / 8)), vol: Math.max(1, Number((row.confidence / 12).toFixed(1))), intent: row.score >= 75 ? '强烈抢筹' : '偏多抢筹' }))
    : candidates.map(row => ({ code: row.code, name: row.name, score: row.score, gap: Math.max(0, Math.round((row.score - 50) / 8)), vol: Math.max(1, Number((row.score / 12).toFixed(1))), intent: row.score >= 75 ? '强烈抢筹' : '偏多抢筹' }))
  return source.sort((a, b) => b.score - a.score)
}

function auctionIntentFromScore(score: number) {
  if (score >= 75) return '强烈抢筹'
  if (score >= 60) return '偏多抢筹'
  if (score >= 40) return '中性观察'
  if (score >= 25) return '偏空出货'
  return '强烈出货'
}

function auctionRowsFromDashboard(auction: Record<string, unknown>) {
  const picks = Array.isArray(auction.picks) ? auction.picks as DashboardAuctionPick[] : []
  const rows = picks
    .filter(pick => pick.code)
    .map(pick => {
      const score = Math.round(num(pick.score, 0))
      const gap = num(pick.gap_pct ?? pick.chg_pct, 0)
      const vol = Math.max(0.1, Number(num(pick.vol_ratio ?? pick.volume_ratio ?? pick.vol_z, 1).toFixed(1)))
      return {
        code: String(pick.code),
        name: pick.name || String(pick.code),
        industry: pick.industry,
        gap,
        vol,
        score,
        intent: pick.intent || auctionIntentFromScore(score),
      }
    })
    .sort((a, b) => b.score - a.score)

  return {
    bullish: rows.filter(row => row.score >= 40 || num(row.gap, 0) >= 0).slice(0, 10),
    bearish: rows.filter(row => row.score < 40 && num(row.gap, 0) < 0).slice(0, 10),
  }
}

function bearishRowsFromSignals(signals: SignalRow[]): AuctionRow[] {
  return signals
    .filter(row => (row.signal || '').includes('减') || (row.signal || '').includes('卖') || row.risk !== '通过')
    .map(row => ({ code: row.code, name: row.name, score: row.score, drop: -Math.max(1, Math.round((60 - row.score) / 8)), vol: Math.max(1, Number((row.confidence / 15).toFixed(1))), intent: row.risk === '止损' ? '强烈出货' : '偏空出货' }))
}

function orderRowsFromApi(rows: TradeOrder[]): OrderRow[] {
  return rows.map(row => ({
    time: (row.created_at || row.filled_at || '-').slice(11, 19) || '-',
    code: row.code,
    name: row.name || row.code,
    dir: String(row.direction).toLowerCase() === 'sell' ? '卖出' : '买入',
    price: String(row.filled_price ?? row.price ?? '-'),
    qty: Number(row.filled_volume ?? row.volume ?? 0).toLocaleString('zh-CN'),
    status: orderStatusLabel(row.status),
  }))
}

function positionRowsFromApi(rows: Position[], totalMarketValue?: number): PositionRow[] {
  const total = totalMarketValue || rows.reduce((sum, row) => sum + num(row.market_value), 0)
  return rows.map(row => ({
    code: row.code,
    name: row.name || row.code,
    value: formatMoney(row.market_value),
    pnl: formatPct(row.pnl_pct),
    weight: total ? `${Math.round((num(row.market_value) / total) * 100)}%` : '-',
  }))
}

function activeKey(pathname: string) {
  if (pathname.endsWith('/auction')) return 'auction'
  if (pathname.endsWith('/signals')) return 'signals'
  if (pathname.endsWith('/candidates')) return 'candidates'
  if (pathname.endsWith('/execution')) return 'execution'
  return 'overview'
}

function toneForRisk(risk: string) {
  if (risk === '通过') return 't-down'
  if (risk.includes('复核')) return 't-warn'
  return 't-mute'
}

function decisionHeader(activeLabel: string) {
  if (activeLabel === '信号扫描') return '验证工作台 · 逐条确认信号 · Kronos 交叉验证 · 一键推送候选池'
  if (activeLabel === '候选池') return '候选池: 竞价 + 信号 + 选股 + 自选 -> 多源融合去重'
  if (activeLabel === '执行监控') return '订单: trade-service (orders) | 持仓: trade-service (positions)'
  return '竞价分析 · 信号扫描 · 候选池 · 执行监控'
}

export default function OpenDecision() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const [state, setState] = useState<OpenDecisionState>(emptyState)

  useEffect(() => {
    let mounted = true
    Promise.allSettled([
      signalApi.getDashboardAuction(),
      signalApi.getLive('intra'),
      chainApi.getCandidates({ filter: 'all', top_n: 20 }),
      tradeApi.getAccount(),
      tradeApi.getPositions(),
      tradeApi.getOrders(),
      tradeApi.getRiskVerdicts({ page: 1, page_size: 20 }),
      tradeApi.getDecisionContexts({ page: 1, page_size: 20 }),
    ]).then(results => {
      if (!mounted) return
      const [auction, live, candidates, account, positions, orders, verdicts, contexts] = results
      const rejected = results.filter(result => result.status === 'rejected').length
      setState({
        auction: auction.status === 'fulfilled' ? auction.value.data || {} : {},
        liveSignals: live.status === 'fulfilled' ? live.value.data?.signals || [] : [],
        liveTradeDate: live.status === 'fulfilled'
          ? (live.value.data as typeof live.value.data & { trade_date?: string })?.trade_date || live.value.data?.data_freshness?.as_of || undefined
          : undefined,
        candidates: candidates.status === 'fulfilled' ? candidates.value.data?.candidates || [] : [],
        account: account.status === 'fulfilled' ? account.value.data?.account : undefined,
        positions: positions.status === 'fulfilled' ? positions.value.data?.positions || [] : [],
        orders: orders.status === 'fulfilled' ? orders.value.data?.orders || [] : [],
        verdicts: verdicts.status === 'fulfilled' ? verdicts.value.data?.records || [] : [],
        contexts: contexts.status === 'fulfilled' ? contexts.value.data?.records || [] : [],
        loading: false,
        error: rejected ? `${rejected} 个接口连接异常，页面已保留可用数据。` : '',
      })
    })
    return () => {
      mounted = false
    }
  }, [])

  const signalRows = useMemo(() => signalRowsFromApi(state.liveSignals, state.verdicts), [state.liveSignals, state.verdicts])
  const candidateRows = useMemo(() => candidateRowsFromApi(state.candidates, state.verdicts), [state.candidates, state.verdicts])
  const sectors = useMemo(() => sectorRowsFromCandidates(state.candidates), [state.candidates])
  const dashboardAuctionRows = useMemo(() => auctionRowsFromDashboard(state.auction), [state.auction])
  const bullishRows = useMemo(
    () => dashboardAuctionRows.bullish.length ? dashboardAuctionRows.bullish : auctionRowsFromSignals(signalRows, candidateRows),
    [dashboardAuctionRows.bullish, signalRows, candidateRows],
  )
  const bearishRows = useMemo(
    () => dashboardAuctionRows.bearish.length ? dashboardAuctionRows.bearish : bearishRowsFromSignals(signalRows),
    [dashboardAuctionRows.bearish, signalRows],
  )
  const orderRows = useMemo(() => orderRowsFromApi(state.orders), [state.orders])
  const positionRows = useMemo(() => positionRowsFromApi(state.positions, state.account?.market_value), [state.positions, state.account?.market_value])
  const auctionTradeDate = typeof state.auction.trade_date === 'string'
    ? state.auction.trade_date
    : (typeof state.auction.date === 'string' ? state.auction.date : undefined)
  const candidateTradeDates = state.candidates
    .map(candidate => candidate.last_trade_date)
    .filter((value): value is string => typeof value === 'string' && value.length > 0)
    .sort()
  const candidatesTradeDate = candidateTradeDates[candidateTradeDates.length - 1]
  const freshnessTradeDate = active === 'signals'
    ? state.liveTradeDate || auctionTradeDate
    : active === 'candidates'
      ? candidatesTradeDate || auctionTradeDate
      : auctionTradeDate
  const freshnessSource = active === 'execution'
    ? 'trade-service'
    : active === 'signals'
      ? 'signal/live'
      : active === 'candidates'
        ? 'supply-chain/workbench'
        : 'dashboard/auction'
  const auctionUpdatedAt = typeof state.auction.updated_at === 'string'
    ? state.auction.updated_at
    : (typeof state.auction.refreshed_at === 'string' ? state.auction.refreshed_at : undefined)
  const firstOrder = state.orders[0] as (TradeOrder & { updated_at?: string; created_at?: string }) | undefined
  const latestRuntimeUpdate = auctionUpdatedAt
    || firstOrder?.updated_at
    || firstOrder?.created_at
    || state.contexts[0]?.created_at
    || state.verdicts[0]?.created_at

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="开盘决策页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ key: tab.key, label: tab.label, subLabel: tab.subLabel, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`开盘决策 - ${activeTab.label}`}
        subtitle={decisionHeader(activeTab.label)}
        dataFreshness={<DataFreshnessBar tradeDate={freshnessTradeDate} updatedAt={latestRuntimeUpdate} source={freshnessSource} />}
      />

      {active === 'overview' && <DecisionOverview loading={state.loading} error={state.error} signalRows={signalRows} candidateRows={candidateRows} sectorRows={sectors} />}
      {active === 'auction' && <AuctionAnalysis loading={state.loading} error={state.error} bullishRows={bullishRows} bearishRows={bearishRows} candidateRows={candidateRows} sectorRows={sectors} auction={state.auction} />}
      {active === 'signals' && <SignalScan loading={state.loading} error={state.error} signalRows={signalRows} />}
      {active === 'candidates' && <CandidatePool loading={state.loading} error={state.error} candidateRows={candidateRows} verdicts={state.verdicts} />}
      {active === 'execution' && <ExecutionMonitor loading={state.loading} error={state.error} account={state.account} orderRows={orderRows} positionRows={positionRows} contexts={state.contexts} />}
    </PrototypePage>
  )
}

function DecisionOverview({
  loading,
  error,
  signalRows,
  candidateRows,
  sectorRows,
}: {
  loading: boolean
  error: string
  signalRows: SignalRow[]
  candidateRows: CandidateRow[]
  sectorRows: SectorRow[]
}) {
  const avgScore = signalRows.length ? Math.round(signalRows.reduce((sum, row) => sum + row.score, 0) / signalRows.length) : 0
  const strongSignals = signalRows.filter(row => row.score >= 70 && row.risk === '通过').length
  return (
    <>
      <section className="od-countdown card">
        <div>
          <div className="od-time mono">12:45</div>
          <strong>距竞价数据采集</strong>
          <span>09:25 竞价撮合 · 数据源 Tushare stk_auction</span>
        </div>
        <div className="prototype-panel-note">竞价开始后自动切换到竞价分析</div>
      </section>

      <div className="kpis od-kpis-5">
        <MetricCard label="情绪指数" value={avgScore ? String(avgScore) : '-'} sub="signal/live" tone="warn" />
        <MetricCard label="熔断器" value={error ? '复核' : '正常'} sub={error || '接口在线'} tone={error ? 'warn' : 'down'} />
        <MetricCard label="隔夜公告" value="2条" sub="1条需关注" tone="up" />
        <MetricCard label="候选池" value={`${candidateRows.length}只`} sub={`强信号 ${strongSignals} 只`} tone="accent" />
        <MetricCard label="数据状态" value={loading ? '加载中' : '已刷新'} sub="signal + trade + chain" tone="down" />
      </div>

      <div className="row r-6-4">
        <div className="grid">
          <PrototypeCard title="隔夜新闻" icon={<LineChartOutlined />} meta="最近 12 小时">
            <div className="od-news-list">
              {overnightNews.map(item => (
                <div className="od-news-row" key={item.title}>
                  <span className={`od-news-tag ${item.tone}`}>{item.type}</span>
                  <div className="od-news-main">
                    <strong>{item.title}</strong>
                    <span>{item.impact}</span>
                  </div>
                  <time className="mono">{item.time}</time>
                </div>
              ))}
            </div>
            <div className="od-news-summary">
              <div>
                <span>摘要</span>
                <strong>半导体与AI算力偏正向，白酒高位分歧需降权</strong>
              </div>
              <button type="button" className="btn sm ghost">全部还原 LLM原始结果</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="昨日复盘" icon={<LineChartOutlined />} meta="回看强势线索">
            <div className="od-review-grid">
              <div><b className="up mono">+2.8%</b><span>半导体延续</span></div>
              <div><b className="up mono">+1.9%</b><span>新能源反弹</span></div>
              <div><b className="warn mono">72</b><span>情绪偏牛</span></div>
              <div><b className="down mono">83.6%</b><span>风控余量</span></div>
            </div>
          </PrototypeCard>

          <PrototypeCard title="候选池预加载" icon={<ThunderboltOutlined />} meta="开盘前预热">
            <div className="chips">
              {candidateRows.map(row => <span className="chip active" key={row.code}>{row.name} {row.score}</span>)}
              {candidateRows.length === 0 && <span className="prototype-panel-note">暂无候选池数据，等待 chain/candidates 返回。</span>}
            </div>
            <div className="prototype-panel-note mt14">来自产业链候选、实时信号和风控判定，开盘后进入去重与风控。</div>
          </PrototypeCard>
        </div>

        <div className="grid">
          <PrototypeCard title="今日情绪 + 风控" icon={<SafetyCertificateOutlined />} meta="开盘前">
            <div className="op-hint">
              <div className="pos warn">{avgScore ? `${Math.min(9, Math.max(1, Math.round(avgScore / 10)))}成` : '-'}</div>
              <div>
                <div className="op-title warn">{strongSignals ? '信号已触发，需逐条确认' : '等待实时信号'}</div>
                <div className="op-desc">优先选择信号强、风控通过、候选来源清晰的标的。</div>
              </div>
            </div>
          </PrototypeCard>

          <PrototypeCard title="昨日强势板块 (可能延续)" icon={<BarChartOutlined />} meta="按共振强度">
            {sectorRows.slice(0, 4).map(row => (
              <div className="watch-sector-bar" key={row.name}>
                <span>{row.name}</span>
                <div><i style={{ width: `${row.width}%` }} /></div>
                <b className="up">+{row.change}%</b>
              </div>
            ))}
            {sectorRows.length === 0 && <div className="prototype-panel-note">暂无板块共振数据。</div>}
          </PrototypeCard>
        </div>
      </div>

      <div className="footer-bar">
        <span>开盘决策 · 决策总览 | 盘前 09:12</span>
        <span className="sep" />
        <span>隔夜新闻: stock_news + announcements + cctv_news</span>
        <span className="sep" />
        <span>候选池: CandidatePoolManager (screening_snapshots + watchlist)</span>
      </div>
    </>
  )
}

function AuctionAnalysis({
  loading,
  error,
  bullishRows,
  bearishRows,
  candidateRows,
  sectorRows,
  auction,
}: {
  loading: boolean
  error: string
  bullishRows: AuctionRow[]
  bearishRows: AuctionRow[]
  candidateRows: CandidateRow[]
  sectorRows: SectorRow[]
  auction: Record<string, unknown>
}) {
  const totalCount = num(auction.total_count ?? auction.total ?? auction.count, bullishRows.length + bearishRows.length)
  const firstBullish = bullishRows[0]
  return (
    <div className="od-auction-layout">
      <div className="od-auction-main">
        <section className="od-engine card">
          <div>
            <span className="led on" />
            <strong>竞价分析引擎</strong>
            <span className="mono">dashboard/auction</span>
            <span className="tag t-down">{loading ? '加载中' : '已刷新'}</span>
            <span className="tag t-neu">{totalCount} 只标的</span>
          </div>
          <div>
            <span className="prototype-panel-note">{error || '最近刷新来自 dashboard/auction 与 signal/live'}</span>
            <button type="button" className="btn sm ghost">刷新</button>
          </div>
        </section>

        <section className="od-risk-callout">
          <div className="od-risk-icon">!</div>
          <div>
            <div className="od-risk-title">竞价风险提示 · 高开过热板块需二次确认</div>
            <div className="prototype-panel-note">半导体、新能源板块竞价共振较强；若开盘 5 分钟量价不能延续，候选池标的进入信号扫描复核，不直接下单。</div>
          </div>
          <div className="od-risk-actions">
            <button type="button" className="btn sm ghost">查看意图全景</button>
            <button type="button" className="btn sm primary">进入竞价选股</button>
          </div>
        </section>

        <div className="od-subtabs">
          <SegmentTabs
            ariaLabel="竞价分析子页签"
            activeKey="overview"
            onChange={() => undefined}
            items={[
              { key: 'overview', label: '竞价意图全景' },
              { key: 'stock', label: '竞价选股' },
              { key: 'bond', label: '可转债竞价' },
              { key: 'detail', label: '全量明细' },
            ]}
          />
        </div>

        <div className="kpis od-auction-kpis">
          <MetricCard label="分析标的" value={String(totalCount)} sub="dashboard/auction" tone="muted" />
          <MetricCard label="强烈抢筹" value={String(bullishRows.filter(row => row.score >= 75).length)} sub="评分 >= 75" tone="up" />
          <MetricCard label="偏多抢筹" value={String(bullishRows.filter(row => row.score < 75).length)} sub="评分 60-74" tone="warn" />
          <MetricCard label="中性观察" value={String(Math.max(0, totalCount - bullishRows.length - bearishRows.length))} sub="等待开盘确认" tone="accent" />
          <MetricCard label="出货预警" value={String(bearishRows.length)} sub="偏空/强出货" tone="down" />
          <MetricCard label="候选池" value={String(candidateRows.length)} sub="已入池待复核" tone="accent" />
        </div>

        <div className="row r-1-1">
          <PrototypeCard title="抢筹 TOP 10" icon={<FireOutlined />} meta="勾选后加入候选池" className="od-card-up">
            <table className="tbl">
              <thead><tr><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
              <tbody>
                {bullishRows.map((row, index) => (
                  <tr key={row.code}>
                    <td>{index + 1}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r up">+{row.gap ?? 0}%</td>
                    <td className="r mono">{row.vol}x</td>
                    <td className="r up">{row.score}</td>
                    <td><span className="tag t-up">{row.intent}</span></td>
                  </tr>
                ))}
                {bullishRows.length === 0 && <tr><td colSpan={7} className="prototype-panel-note">暂无抢筹数据，等待 signal/live 或 chain/candidates。</td></tr>}
              </tbody>
            </table>
            <div className="od-selection-bar">
              <span>已选 <b>0</b></span>
              <button type="button" className="btn sm ghost">全选可用</button>
              <button type="button" className="btn sm primary">加入候选池</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="出货预警 TOP 10" icon={<SafetyCertificateOutlined />} meta="规避或反向观察" className="od-card-down">
            <table className="tbl">
              <thead><tr><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
              <tbody>
                {bearishRows.map((row, index) => (
                  <tr key={row.code}>
                    <td>{index + 1}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r down">{row.drop}%</td>
                    <td className="r mono">{row.vol}x</td>
                    <td className="r down">{row.score}</td>
                    <td><span className="tag t-down">{row.intent}</span></td>
                  </tr>
                ))}
                {bearishRows.length === 0 && <tr><td colSpan={7} className="prototype-panel-note">暂无出货预警。</td></tr>}
              </tbody>
            </table>
            <div className="od-selection-bar">
              <span>预警样本</span>
              <button type="button" className="btn sm ghost">全选可用</button>
              <button type="button" className="btn sm down">加入观察</button>
            </div>
          </PrototypeCard>
        </div>

        <div className="row r-16-8 mt14">
          <PrototypeCard title="竞价撮合价走势" icon={<LineChartOutlined />} meta="09:15-09:25 撮合价/匹配量">
            <div className="od-trend-bars">
              {[35, 46, 42, 58, 64, 79, 74, 88, 83, 96].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
            </div>
            <div className="prototype-panel-note mt14">撮合价持续上移且匹配量放大时，优先进入信号扫描复核。</div>
          </PrototypeCard>

          <PrototypeCard title="四维评分" icon={<BarChartOutlined />} meta="价格方向 / 买卖压力 / 竞价强度 / 开盘延续">
            <div className="od-score-bars">
              {[
                ['价格方向', 92],
                ['买卖压力', 86],
                ['竞价强度', 88],
                ['开盘延续', 74],
              ].map(([label, value]) => (
                <div className="watch-sector-bar" key={label}>
                  <span>{label}</span>
                  <div><i style={{ width: `${value}%` }} /></div>
                  <b className="up">{value}</b>
                </div>
              ))}
            </div>
            <div className="od-stock-info">
              <span className="code">{firstBullish?.code || '-'}</span>
              <b>{firstBullish?.name || '暂无标的'}</b>
              <span className="tag t-up">{firstBullish?.intent || '等待信号'}</span>
            </div>
          </PrototypeCard>
        </div>

        <PrototypeCard title="一字定方向" icon={<BarChartOutlined />} meta="板块竞价热度 · 点击板块查看强势股与转债" className="mt14">
          <div className="od-sector-grid">
            {sectorRows.map(row => (
              <button type="button" className="od-sector-tile" key={row.name}>
                <span>{row.name}</span>
                <b className="up">+{row.change}%</b>
                <small>{row.count} 只 · {row.lead}</small>
              </button>
            ))}
            {sectorRows.length === 0 && <div className="prototype-panel-note">暂无板块热度。</div>}
          </div>
        </PrototypeCard>

        <PrototypeCard title="全量竞价明细" icon={<BarChartOutlined />} meta="共 328 只 · 第 1-12 条" className="mt14">
          <table className="tbl">
            <thead><tr><th>代码</th><th>名称</th><th>板块</th><th className="r">竞价涨跌</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
            <tbody>
              {[...bullishRows.slice(0, 5), ...bearishRows.slice(0, 2)].map(row => (
                <tr key={row.code}>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}</td>
                  <td>{row.industry || '风险观察'}</td>
                  <td className={`r ${'gap' in row ? 'up' : 'down'}`}>{'gap' in row ? `+${row.gap}%` : `${row.drop}%`}</td>
                  <td className="r mono">{row.vol}x</td>
                  <td className="r mono">{row.score}</td>
                  <td><span className={`tag ${'gap' in row ? 't-up' : 't-down'}`}>{row.intent}</span></td>
                </tr>
              ))}
              {bullishRows.length + bearishRows.length === 0 && <tr><td colSpan={7} className="prototype-panel-note">暂无竞价明细。</td></tr>}
            </tbody>
          </table>
        </PrototypeCard>
      </div>

      <aside className="od-auction-rail">
        <PrototypeCard title="板块共振详情" icon={<BarChartOutlined />}>
          {sectorRows.map(row => (
            <div className="od-resonance-row" key={row.name}>
              <div>
                <strong>{row.name}</strong>
                <span>{row.count}只 · 领涨: {row.lead}</span>
              </div>
              <b className="up">+{row.change}%</b>
              <button type="button" className="btn sm primary">选股-&gt;</button>
            </div>
          ))}
          {sectorRows.length === 0 && <div className="prototype-panel-note">暂无板块共振详情。</div>}
        </PrototypeCard>

        <PrototypeCard title="板块强势标的" icon={<FireOutlined />}>
          {bullishRows.slice(0, 4).map(row => (
            <div className="li-row" key={row.code}>
              <span className="li-badge up">{row.score}</span>
              <div className="li-main"><div className="n">{row.name}</div><div className="s">{row.industry || '信号候选'} · +{row.gap ?? 0}% · {row.intent}</div></div>
            </div>
          ))}
          {bullishRows.length === 0 && <div className="prototype-panel-note">暂无强势标的。</div>}
        </PrototypeCard>

        <PrototypeCard title="候选池预览" icon={<FundOutlined />}>
          <div className="pool-count">{candidateRows.length}<span className="unit"> 只</span></div>
          <div className="chips mt14">
            {candidateRows.slice(0, 5).map((row, index) => <span className={index < 2 ? 'chip active' : 'chip'} key={row.code}>{row.code} {row.name}</span>)}
            {candidateRows.length === 0 && <span className="prototype-panel-note">暂无候选。</span>}
          </div>
          <button type="button" className="btn sm ghost mt14">查看全部候选池 -&gt;</button>
        </PrototypeCard>

        <PrototypeCard title="已锁定板块" icon={<CheckCircleOutlined />}>
          <div className="chips">
            {sectorRows.slice(0, 2).map(row => <span className="chip active" key={row.name}>{row.name} ({row.count})</span>)}
            {sectorRows.length === 0 && <span className="prototype-panel-note">暂无锁定板块。</span>}
          </div>
          <button type="button" className="btn primary mt14" style={{ width: '100%', justifyContent: 'center' }}>锁定板块 -&gt; 信号扫描</button>
        </PrototypeCard>

        <PrototypeCard title="工作流引导" icon={<CheckCircleOutlined />}>
          {[
            ['done', '竞价意图全景 -> 判断抢筹/出货方向'],
            ['active', '锁定强势板块 -> 切换到竞价选股引擎'],
            ['todo', '勾选标的 -> 加入候选池 -> 信号扫描验证'],
          ].map(([state, text], index) => (
            <div className={`od-workflow-row ${state}`} key={text}>
              <span>{state === 'done' ? '✓' : index + 1}</span>
              <b>{text}</b>
            </div>
          ))}
        </PrototypeCard>
      </aside>
    </div>
  )
}

function SignalScan({
  loading,
  error,
  signalRows,
}: {
  loading: boolean
  error: string
  signalRows: SignalRow[]
}) {
  const selected = signalRows[0]
  const dimensions = selected?.dimensions || [
    { label: '技术面', value: 0 },
    { label: '资金面', value: 0 },
    { label: '基本面', value: 0 },
    { label: '情绪', value: 0 },
    { label: '置信度', value: 0 },
    { label: '风控', value: 0 },
  ]
  const buyCount = signalRows.filter(row => row.signal.includes('买')).length
  const watchCount = signalRows.filter(row => row.watchlist).length

  return (
    <>
      <section className="od-locked-banner">
        <strong>锁定板块:</strong>
        <span className="chip active">实时信号 <b>{signalRows.length}</b></span>
        <span className="chip active">买入候选 <b>{buyCount}</b></span>
        <button type="button" className="btn sm ghost">清除锁定</button>
      </section>

      <section className="od-signal-filter-row">
        <div className="signal-filter-bar">
          <button type="button" className="filter-btn active">全部 <span className="mono">{signalRows.length}</span></button>
          <button type="button" className="filter-btn">仅买入 <span className="mono">{buyCount}</span></button>
          <button type="button" className="filter-btn">仅自选 <span className="mono">{watchCount}</span></button>
        </div>
        <div className="signal-filter-bar">
          <span className="sort-label">排序:</span>
          <button type="button" className="filter-btn active">信号评分 ▼</button>
          <button type="button" className="filter-btn">一致性</button>
          <button type="button" className="filter-btn">风险</button>
        </div>
      </section>

      <div className="od-signal-layout">
        <div className="od-signal-left">
        <PrototypeCard title="信号扫描" icon={<ThunderboltOutlined />} meta="验证工作台 · 逐条确认信号 · Kronos 交叉验证 · 一键推送候选池">
          <table className="tbl od-verify-table">
            <thead><tr><th>代码</th><th>名称</th><th>信号</th><th className="r">评分</th><th>Kronos预测</th><th>一致性</th><th>风险</th><th className="r">操作</th></tr></thead>
            <tbody>
              {signalRows.map(row => (
                <tr className={row.code === selected?.code ? 'picked' : ''} key={row.code}>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}{row.watchlist && <span className="in-pool-tag">自选</span>}</td>
                  <td><span className={row.score >= 70 ? 'tag t-up' : row.score >= 60 ? 'tag t-warn' : 'tag t-mute'}>{row.signal}</span></td>
                  <td className="r mono">{row.score}</td>
                  <td className={row.kronos.startsWith('+') ? 'up' : 'down'}>{row.kronos} -&gt; {row.target}</td>
                  <td><span className={row.consistency === '双确认' ? 'tag t-down' : row.consistency === '相悖' ? 'tag t-warn' : 'tag t-mute'}>{row.consistency}</span></td>
                  <td><span className={`tag ${toneForRisk(row.risk)}`}>{row.risk}</span></td>
                  <td className="r"><button type="button" className="btn sm ghost">{row.action}</button></td>
                </tr>
              ))}
              {signalRows.length === 0 && <tr><td colSpan={8} className="prototype-panel-note">{loading ? '实时信号加载中。' : error || '暂无实时信号。'}</td></tr>}
            </tbody>
          </table>
          <div className="od-batch-bar">
            <button type="button" className="btn sm primary">批量确认买入信号</button>
            <button type="button" className="btn sm ghost">一键排除风险标的</button>
            <span>点击行查看详情</span>
            <b>逐条确认决策</b>
          </div>
          <div className="od-summary-bar">
            已处理 <b>0</b>/<span>{signalRows.length}</span> · 已确认 <b className="down">0</b> · 已降级 <b className="warn">0</b> · 已排除 <b className="up">0</b>
          </div>
        </PrototypeCard>

        <PrototypeCard title="信号拆解" icon={<BarChartOutlined />} meta="信号 + 预测 + 风控">
          <div className="od-signal-stack">
            {dimensions.map(item => (
              <div className="watch-sector-bar" key={item.label}>
                <span>{item.label}</span>
                <div><i style={{ width: `${item.value}%` }} /></div>
                <b>{item.value}</b>
              </div>
            ))}
          </div>
        </PrototypeCard>
      </div>

      <aside className="od-signal-rail">
        <PrototypeCard title="选中股票" icon={<FundOutlined />} meta={selected?.code || '-'}>
          <div className="od-selected-stock">
            <span className="code">{selected?.code || '-'}</span>
            <b>{selected?.name || '暂无信号'}</b>
            <span className="mono">¥{selected?.price || '-'}</span>
          </div>
          <div className="od-signal-big-tag">{selected?.signal || '等待'} <span>{selected?.score || 0}分</span></div>
          <div className="od-detail-title">六维评分</div>
          {dimensions.map(item => (
            <div className="watch-sector-bar" key={item.label}>
              <span>{item.label}</span>
              <div><i style={{ width: `${item.value}%` }} /></div>
              <b>{item.value}</b>
            </div>
          ))}
        </PrototypeCard>

        <PrototypeCard title="Kronos 30日预测" icon={<LineChartOutlined />} meta={selected ? `${selected.code} ${selected.name}` : '暂无信号'}>
          <div className="od-kronos-dir">
            <span>↗</span>
            <div>
              <b className="mono">{selected?.price || '-'} -&gt; <span className="up">{selected?.target || '-'}</span></b>
              <strong>{selected?.kronos || '模型预测需等待 prediction 服务返回'}</strong>
            </div>
          </div>
          <div className="bar mt14"><i style={{ width: `${selected?.confidence || 0}%` }} /></div>
          <div className="prototype-panel-note mt14">置信度 {selected?.confidence || 0}% · {selected?.consistency || '等待信号'}</div>
        </PrototypeCard>

        <PrototypeCard title="信号+预测 方向一致" icon={<CheckCircleOutlined />}>
          <div className="od-verdict">
            <span>✓</span>
            <div>
              <strong>方向一致</strong>
              <p>信号强度: {selected?.signal || '-'} {selected?.score || 0}分 · 多因子共振 · {selected?.risk || '待风控'}</p>
            </div>
          </div>
        </PrototypeCard>

        <PrototypeCard title="风险检查" icon={<SafetyCertificateOutlined />} meta="RiskVerdict">
          {[
            `信号风险: ${selected?.risk || '待风控'}`,
            `置信度: ${selected?.confidence || 0}%`,
            `操作建议: ${selected?.action || '-'}`,
            `一致性: ${selected?.consistency || '-'}`,
          ].map((item, index) => (
            <div className="od-risk-row" key={item}>
              <span>{index + 1}. {item}</span>
              <b>{selected?.risk === '通过' && index === 0 ? '自动通过' : '执行前复核'}</b>
            </div>
          ))}
        </PrototypeCard>

        <PrototypeCard title="决策分类" icon={<FundOutlined />} meta="候选池推送">
          <div className="od-decision-group"><strong>已确认</strong><span>强买 + 预测一致 + 风控通过</span></div>
          <div className="od-decision-group"><strong>降级</strong><span>Kronos 相悖或置信度不足</span></div>
          <div className="od-decision-group"><strong>排除</strong><span>风险不通过或高价股限制</span></div>
          <button type="button" className="btn primary od-push-btn mt14">一键推送已确认 -&gt; 候选池</button>
          <button type="button" className="btn ghost od-push-btn mt14">查看候选池 -&gt;</button>
        </PrototypeCard>
      </aside>
    </div>
    </>
  )
}

function CandidatePool({
  loading,
  error,
  candidateRows,
  verdicts,
}: {
  loading: boolean
  error: string
  candidateRows: CandidateRow[]
  verdicts: RiskVerdictRecord[]
}) {
  const passed = candidateRows.filter(row => row.risk === '通过').length
  const planPosition = candidateRows.reduce((sum, row) => sum + Number(row.size.replace('%', '')), 0)
  return (
    <>
      <section className="workflow-nav">
        <div className="workflow-track" aria-label="P0 主链路">
          <span className="workflow-step active"><span className="workflow-index">01</span><span className="workflow-copy"><span className="workflow-label">P0 主链路</span><span className="workflow-desc">候选池</span></span></span>
          <span className="workflow-arrow">-&gt;</span>
          <span className="workflow-step"><span className="workflow-index">02</span><span className="workflow-copy"><span className="workflow-label">方案管理</span><span className="workflow-desc">生成方案</span></span></span>
          <span className="workflow-arrow">-&gt;</span>
          <span className="workflow-step"><span className="workflow-index">03</span><span className="workflow-copy"><span className="workflow-label">风控闸门</span><span className="workflow-desc">RiskVerdict</span></span></span>
        </div>
      </section>

      <div className="row r-6-4">
        <PrototypeCard title="多源候选池" icon={<FundOutlined />} meta="Candidate 对象预览 · 多源融合去重">
          <table className="tbl">
              <thead><tr><th>#</th><th>代码</th><th>名称</th><th>来源</th><th className="r">综合评分</th><th>风控</th><th className="r">建议仓位</th></tr></thead>
              <tbody>
                {candidateRows.map((row, index) => (
                <tr key={row.code}>
                  <td>{index + 1}</td>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}</td>
                  <td>{row.source}</td>
                  <td className="r up">{row.score}</td>
                  <td><span className={`tag ${toneForRisk(row.risk)}`}>{row.risk}</span></td>
                  <td className="r mono">{row.size}</td>
                </tr>
              ))}
              {candidateRows.length === 0 && <tr><td colSpan={7} className="prototype-panel-note">{loading ? '候选池加载中。' : error || '暂无候选池数据。'}</td></tr>}
            </tbody>
          </table>
        </PrototypeCard>

        <div className="grid">
          <PrototypeCard title="风控排查" icon={<SafetyCertificateOutlined />} meta="RiskVerdict">
            {(verdicts.length ? verdicts.slice(0, 4).map(item => `${item.symbol || item.candidate_id || item.scope}: ${item.result}`) : ['暂无风控判定']).map((item, index) => (
              <div className="li-row" key={item}>
                <span className="li-badge down">{index + 1}</span>
                <div className="li-main"><div className="n">{item}</div><div className="s">已写入候选对象风险字段</div></div>
              </div>
            ))}
          </PrototypeCard>

          <PrototypeCard title="交易方案预览" icon={<DollarOutlined />} meta="Plan 草稿">
            <div className="risk-banner safe">
              <strong>风控预检: {candidateRows.length ? `${passed}/${candidateRows.length} 通过` : '等待候选'}</strong>
              <span>{candidateRows.length}只候选 · 计划仓位 {planPosition}% · 最大单票 30% · 禁止追高价差 &gt; 2%</span>
            </div>
            <div className="od-actions mt14">
              <button type="button" className="btn primary">生成方案</button>
              <button type="button" className="btn ghost">保存为手动方案</button>
            </div>
          </PrototypeCard>
        </div>
      </div>
    </>
  )
}

function ExecutionMonitor({
  loading,
  error,
  account,
  orderRows,
  positionRows,
  contexts,
}: {
  loading: boolean
  error: string
  account?: TradeAccount
  orderRows: OrderRow[]
  positionRows: PositionRow[]
  contexts: DecisionContextRecord[]
}) {
  const filledOrders = orderRows.filter(row => row.status === '已成交').length
  const pendingOrders = orderRows.length - filledOrders
  return (
    <>
      <section className="od-account-bar card">
        {[
          ['总资产', formatMoney(account?.total_assets), '账户 account.paper'],
          ['可用', formatMoney(account?.available), '可下单资金'],
          ['今日盈亏', formatMoney(account?.total_pnl), 'trade/account'],
          ['总仓位', account?.market_value && account?.total_assets ? `${Math.round((account.market_value / account.total_assets) * 100)}%` : '-', '风险阈值 75%'],
        ].map(([label, value, sub]) => (
          <div key={label}>
            <span>{label}</span>
            <b className={`mono ${label === '今日盈亏' ? 'up' : ''}`}>{value}</b>
            <small>{sub}</small>
          </div>
        ))}
      </section>

      <div className="row r-6-4">
        <div className="grid">
          <PrototypeCard title="今日订单" icon={<DollarOutlined />} meta={`${orderRows.length}单 · 成交${filledOrders} · 待成交${pendingOrders}`}>
            <table className="tbl">
              <thead><tr><th>时间</th><th>代码</th><th>名称</th><th>方向</th><th className="r">价格</th><th className="r">数量</th><th>状态</th></tr></thead>
              <tbody>
                {orderRows.map(row => (
                  <tr key={`${row.time}-${row.code}`}>
                    <td className="mono">{row.time}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td><span className="tag t-up">{row.dir}</span></td>
                    <td className="r mono">{row.price}</td>
                    <td className="r mono">{row.qty}</td>
                    <td><span className={`tag ${row.status === '已成交' ? 't-down' : row.status === '待成交' ? 't-warn' : 't-neu'}`}>{row.status}</span></td>
                  </tr>
                ))}
                {orderRows.length === 0 && <tr><td colSpan={7} className="prototype-panel-note">{loading ? '订单加载中。' : error || '暂无订单。'}</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>

          <PrototypeCard title="持仓" icon={<FundOutlined />} meta="实时同步 trade-service">
            <table className="tbl">
              <thead><tr><th>代码</th><th>名称</th><th className="r">市值</th><th className="r">盈亏</th><th className="r">权重</th></tr></thead>
              <tbody>
                {positionRows.map(row => (
                  <tr key={row.code}>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r mono">{row.value}</td>
                    <td className="r up">{row.pnl}</td>
                    <td className="r mono">{row.weight}</td>
                  </tr>
                ))}
                {positionRows.length === 0 && <tr><td colSpan={5} className="prototype-panel-note">{loading ? '持仓加载中。' : '暂无持仓。'}</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>
        </div>

        <div className="grid">
          <PrototypeCard title="自动交易策略" icon={<ThunderboltOutlined />} meta="paper">
            {(contexts.length ? contexts.slice(0, 4).map(item => `${item.source_type}: ${item.intent}`) : ['暂无执行上下文']).map((item, index) => (
              <div className="li-row" key={item}>
                <span className={`li-badge ${index === 0 ? 'down' : 'neu'}`}>{index + 1}</span>
                <div className="li-main"><div className="n">{item}</div><div className="s">StrategyExecutionContext 已记录</div></div>
              </div>
            ))}
          </PrototypeCard>

          <PrototypeCard title="今日方案" icon={<CheckCircleOutlined />} meta={contexts[0]?.plan_id || '暂无方案'}>
            <div className="risk-banner accent">
              <strong>{contexts.length ? '开盘决策上下文已记录' : '等待方案生成'}</strong>
              <span>上下文 {contexts.length} 条 · 已下单 {orderRows.length} 只 · 待确认 {pendingOrders} 只</span>
            </div>
            <div className="od-actions mt14">
              <button type="button" className="btn primary">一键启动自动交易</button>
              <button type="button" className="btn ghost">去交易中心手动下单</button>
              <button type="button" className="btn ghost">删除</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="需关注" icon={<SafetyCertificateOutlined />}>
            {['北方华创未完全成交，10:00 前复核', '白酒高位分歧，不进入追涨队列', '若仓位超过 70%，暂停新增订单'].map((item, index) => (
              <div className="li-row" key={item}>
                <span className="li-badge warn">{index + 1}</span>
                <div className="li-main"><div className="n">{item}</div><div className="s">执行前提醒</div></div>
              </div>
            ))}
          </PrototypeCard>
        </div>
      </div>
    </>
  )
}
