import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { Drawer } from 'antd'
import {
  ApartmentOutlined,
  AreaChartOutlined,
  BarChartOutlined,
  DollarOutlined,
  EyeOutlined,
  FireOutlined,
  FundOutlined,
  LineChartOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { DataFreshnessBar, MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, PrototypeTabs } from '../components/prototype'
import { signalApi } from '../api/client'

interface SignalStock {
  code: string
  name: string
  price: number
  change_pct: number
  signal: string
  desc?: string
  score?: number
  industry?: string
  market?: string
}

interface WatchlistItem {
  code: string
  name: string
  market_cap?: number
  industry?: string
  price?: number
  change_pct?: number
  signal?: string
  score?: number
  stop_distance?: number
  risk_note?: string
}

interface AlertSignal {
  code: string
  name: string
  level: string
  change_pct: number
  reason: string
}

interface AuctionIntentItem {
  code: string
  name: string
  chg_pct?: number
  gap_pct?: number
  price?: number
  score?: number
  industry?: string
  vol_ratio?: number
  buy_sell_ratio?: number
  intent?: string
  reasons?: string[]
}

interface LimitStockItem {
  code: string
  name?: string
  price?: number
  change_pct?: number
  chg_pct?: number
  score?: number
  industry?: string
  sector?: string
  board?: string
  concept?: string
  signal?: string
  desc?: string
}

type LimitStocksPayload = LimitStockItem[] | {
  up_count?: number
  down_count?: number
  data_source?: string
  up_list?: LimitStockItem[]
  down_list?: LimitStockItem[]
  list?: LimitStockItem[]
  stocks?: LimitStockItem[]
}

interface MarketSentimentData {
  score: number
  label: string
  trade_date?: string
  avg_change_pct?: number
  up_stocks?: number
  down_stocks?: number
  total_stocks?: number
  model?: string
  formula?: string
  sub_dimensions?: Record<string, string>
}

interface MarketRegimeData {
  regime: string
  score: number
  confidence: number
  label: string
  dimensions?: Record<string, { score: number; weight: number }>
}

interface DashboardData {
  refreshed_at?: string
  data_freshness?: {
    status?: string
    as_of?: string | null
    source?: string
    quality_score?: number
  }
  next_trading_day?: string | null
  market_sentiment?: MarketSentimentData
  market_regime_v2?: MarketRegimeData
  signal_stocks?: SignalStock[]
  limit_stocks?: LimitStocksPayload
  alert_signals?: AlertSignal[]
  auction_intent?: {
    trade_date?: string
    data_source?: string
    total_analyzed: number
    strong_bullish_count?: number
    moderate_bullish_count?: number
    bullish_count: number
    moderate_bearish_count?: number
    strong_bearish_count?: number
    bearish_count: number
    neutral_count?: number
    top_bullish?: AuctionIntentItem[]
    top_bearish?: AuctionIntentItem[]
  }
  watchlist?: WatchlistItem[]
  data_sources?: Record<string, string>
}

const dashboardTabs = [
  { key: 'sentiment', path: '/', label: '市场情绪', subLabel: '宽度 / 资金' },
  { key: 'auction', path: '/dashboard/auction', label: '竞价意图', subLabel: '9:25 抢筹' },
  { key: 'signals', path: '/dashboard/signals', label: '信号总览', subLabel: '今日触发' },
  { key: 'watchlist', path: '/dashboard/watchlist', label: '自选跟踪', subLabel: '持仓线索' },
]

const fallbackSentiment: MarketSentimentData = {
  score: 72,
  label: '偏牛',
  trade_date: '2026-06-28',
  avg_change_pct: 1.2,
  up_stocks: 1852,
  down_stocks: 1432,
  total_stocks: 3852,
  model: 'market_regime_v2',
  formula: 'trend×25% + breadth×20% + liquidity×15% + leverage×10% + foreign×5% + valuation×5% + risk×15% + sentiment×5%',
}

const fallbackDimensions = [
  { key: 'trend', label: '趋势', weight: 25, score: 75, tone: 'linear-gradient(90deg,#2ec27e,#1a7a4c)' },
  { key: 'breadth', label: '广度', weight: 20, score: 68, tone: 'linear-gradient(90deg,#3d8bff,#2ec27e)' },
  { key: 'liquidity', label: '流动性', weight: 15, score: 72, tone: 'linear-gradient(90deg,#fa8c16,#fa541c)' },
  { key: 'leverage', label: '杠杆', weight: 10, score: 65, tone: 'linear-gradient(90deg,#3d8bff,#1677ff)' },
  { key: 'foreign', label: '外资', weight: 5, score: 70, tone: 'linear-gradient(90deg,#fa8c16,#ff7a45)' },
  { key: 'valuation', label: '估值', weight: 5, score: 55, tone: 'linear-gradient(90deg,#3d8bff,#5b8def)' },
  { key: 'risk', label: '风险事件', weight: 15, score: 80, tone: 'linear-gradient(90deg,#2ec27e,#237804)' },
  { key: 'sentiment', label: '情绪', weight: 5, score: 62, tone: 'linear-gradient(90deg,#3d8bff,#1677ff)' },
]

type SentimentPageKey = 'today' | 'history' | 'sector'

const sentimentPages: Array<{ key: SentimentPageKey; number: string; label: string; desc: string }> = [
  { key: 'today', number: '01', label: '今日市场', desc: '当天情绪、资金、涨跌快照' },
  { key: 'history', number: '02', label: '历史情绪', desc: '30/60/120 日情绪回溯' },
  { key: 'sector', number: '03', label: '板块共振', desc: '强势板块、分化和共振方向' },
]

interface SectorResonance {
  name: string
  score: number
  upRatio: number
  change: number
  fund: number
}

interface SectorStockDetail {
  code: string
  name: string
  industry: string
  price: number
  changePct: number
  score: number
  signal: string
  source: string
}

const fallbackSectors = [
  { name: '半导体', score: 85, upRatio: 82, change: 3.2, fund: 32.6 },
  { name: '新能源', score: 78, upRatio: 72, change: 2.8, fund: 18.4 },
  { name: 'AI算力', score: 75, upRatio: 75, change: 2.5, fund: 15.9 },
  { name: '消费电子', score: 68, upRatio: 60, change: 1.8, fund: 8.1 },
  { name: '白酒', score: 65, upRatio: 68, change: 1.5, fund: 5.6 },
  { name: '汽车', score: 60, upRatio: 55, change: 1.2, fund: 4.8 },
  { name: '医药', score: 58, upRatio: 50, change: 0.8, fund: 3.2 },
  { name: '光伏', score: 52, upRatio: 48, change: 0.5, fund: 2.1 },
  { name: '金融', score: 50, upRatio: 45, change: 0.2, fund: 1.6 },
  { name: '军工', score: 45, upRatio: 38, change: -0.3, fund: -0.8 },
  { name: '传媒', score: 42, upRatio: 35, change: -0.5, fund: -1.2 },
  { name: '电力', score: 40, upRatio: 40, change: -0.1, fund: -0.5 },
  { name: '农业', score: 38, upRatio: 36, change: -0.8, fund: -1.8 },
  { name: '有色', score: 36, upRatio: 32, change: -1.0, fund: -2.4 },
  { name: '化工', score: 34, upRatio: 30, change: -0.6, fund: -1.5 },
  { name: '钢铁', score: 30, upRatio: 22, change: -1.5, fund: -3.2 },
] satisfies SectorResonance[]

type SignalLevelKey = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'REDUCE' | 'SELL' | 'TIMING_ALERT'

interface SignalMatrixItem {
  code: string
  name: string
  industry: string
  level: SignalLevelKey
  score: number
  price: number
  changePct: number
  watchlist?: boolean
}

const signalLevelMeta: Record<SignalLevelKey, { label: string; color: string; className: string }> = {
  STRONG_BUY: { label: '强买', color: '#ff4d4f', className: 'buy-strong' },
  BUY: { label: '买入', color: '#fa8c16', className: 'buy' },
  HOLD: { label: '持有', color: '#3d8bff', className: 'hold' },
  REDUCE: { label: '减仓', color: '#faad14', className: 'reduce' },
  SELL: { label: '卖出', color: '#8c8c8c', className: 'sell' },
  TIMING_ALERT: { label: '拐点', color: '#722ed1', className: 'alert' },
}

const signalStatsMeta = [
  { key: 'STRONG_BUY' as SignalLevelKey, icon: '●' },
  { key: 'BUY' as SignalLevelKey, icon: '●' },
  { key: 'HOLD' as SignalLevelKey, icon: '●' },
  { key: 'REDUCE' as SignalLevelKey, icon: '●' },
  { key: 'SELL' as SignalLevelKey, icon: '●' },
  { key: 'TIMING_ALERT' as SignalLevelKey, icon: '●' },
]

function activeTabFromPath(pathname: string) {
  if (pathname.endsWith('/auction')) return 'auction'
  if (pathname.endsWith('/signals')) return 'signals'
  if (pathname.endsWith('/watchlist')) return 'watchlist'
  return 'sentiment'
}

function normalizeSentiment(data: DashboardData | null): MarketSentimentData {
  if (data?.market_sentiment) return data.market_sentiment
  if (data?.market_regime_v2) {
    return {
      ...fallbackSentiment,
      score: Number(data.market_regime_v2.score ?? fallbackSentiment.score),
      label: data.market_regime_v2.label,
      model: `market_regime_v2 · 置信度 ${data.market_regime_v2.confidence ?? '--'}%`,
    }
  }
  return fallbackSentiment
}

function dimensionsFromData(data: DashboardData | null) {
  const dimensions = data?.market_regime_v2?.dimensions
  if (!dimensions) return fallbackDimensions
  const labelMap: Record<string, string> = {
    trend: '趋势',
    breadth: '广度',
    liquidity: '流动性',
    leverage: '杠杆',
    foreign: '外资',
    valuation: '估值',
    risk: '风险事件',
    sentiment: '情绪',
  }
  return fallbackDimensions.map(item => {
    const source = dimensions[item.key]
    return source ? {
      ...item,
      label: labelMap[item.key] ?? item.label,
      weight: Math.round((source.weight ?? item.weight / 100) * 100),
      score: Math.max(0, Math.min(100, Math.round(source.score ?? item.score))),
    } : item
  })
}

function buildGaugeOption(score: number): EChartsOption {
  return {
    series: [{
      type: 'gauge',
      center: ['50%', '55%'],
      radius: '88%',
      startAngle: 220,
      endAngle: -40,
      min: 0,
      max: 100,
      splitNumber: 10,
      axisLine: {
        lineStyle: {
          width: 18,
          color: [[0.2, '#237804'], [0.4, '#52c41a'], [0.6, '#3d8bff'], [0.8, '#fa8c16'], [1, '#ff4d4f']],
        },
      },
      pointer: { length: '72%', width: 6, itemStyle: { color: '#d8dee8' } },
      axisTick: { distance: -18, length: 6, lineStyle: { color: '#8a96a8', width: 1 } },
      splitLine: { distance: -22, length: 14, lineStyle: { color: '#8a96a8', width: 2 } },
      axisLabel: { color: '#8a96a8', fontSize: 9, fontFamily: 'var(--font-mono)', distance: 28 },
      detail: {
        valueAnimation: true,
        formatter: `{value|${score}}\n{unit| 分}\n{change|▲ +5}`,
        rich: {
          value: { fontSize: 38, fontWeight: 720, color: '#1a2230', fontFamily: 'var(--font-mono)' },
          unit: { fontSize: 13, color: '#52617a', padding: [0, 0, 0, 2] },
          change: { fontSize: 12, color: '#ff4d4f', padding: [6, 0, 0, 0] },
        },
        offsetCenter: [0, '18%'],
      },
      title: { offsetCenter: [0, '52%'], color: '#52617a', fontSize: 12 },
      data: [{ value: score, name: '综合情绪指数' }],
    }],
    backgroundColor: 'transparent',
  }
}

function buildTrendOption(score: number): EChartsOption {
  const dates = Array.from({ length: 30 }, (_, index) => {
    const day = index + 1
    return `06/${String(day).padStart(2, '0')}`
  })
  const scores = dates.map((_, index) => Math.round(Math.max(35, Math.min(88, score - 13 + Math.sin(index / 4) * 8 + index * 0.7))))
  const hs300 = scores.map(value => Math.round(3650 + (value - 50) * 15))

  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 70, top: 30, bottom: 42 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 9, color: '#8a96a8', interval: 4 } },
    yAxis: [
      { type: 'value', name: '情绪指数', min: 0, max: 100, axisLabel: { fontSize: 9, color: '#52617a' }, splitLine: { lineStyle: { color: '#e6eaf0' } } },
      { type: 'value', name: '沪深300', axisLabel: { fontSize: 9, color: '#8a96a8' }, splitLine: { show: false } },
    ],
    series: [
      {
        name: '情绪指数',
        type: 'line',
        yAxisIndex: 0,
        data: scores,
        lineStyle: { width: 2.5, color: '#3d8bff' },
        itemStyle: { color: '#3d8bff' },
        symbol: 'circle',
        symbolSize: 5,
        smooth: true,
        markLine: {
          silent: true,
          symbol: 'none',
          data: [
            { xAxis: '06/07', label: { formatter: '政策催化', fontSize: 9, color: '#f5a623' }, lineStyle: { color: '#f5a623', type: 'dashed', width: 1 } },
            { xAxis: '06/18', label: { formatter: '资金拐点', fontSize: 9, color: '#f5a623' }, lineStyle: { color: '#f5a623', type: 'dashed', width: 1 } },
          ],
        },
      },
      {
        name: '沪深300',
        type: 'line',
        yAxisIndex: 1,
        data: hs300,
        lineStyle: { width: 1.2, type: 'dashed', color: 'rgba(82,97,122,0.45)' },
        symbol: 'none',
        smooth: true,
      },
    ],
    legend: { bottom: 0, textStyle: { fontSize: 10, color: '#52617a' }, itemWidth: 14, itemHeight: 8 },
  }
}

function sectorColor(score: number) {
  if (score >= 80) {
    return { bg: 'var(--up-bg)', border: 'var(--up)', text: 'var(--up)', level: '主线', className: 'hot' }
  }
  if (score >= 70) {
    return { bg: 'var(--warn-bg)', border: 'var(--warn)', text: '#b75d00', level: '强势', className: 'strong' }
  }
  if (score >= 60) {
    return { bg: 'var(--down-bg)', border: 'var(--down)', text: '#237804', level: '跟随', className: 'follow' }
  }
  if (score >= 50) {
    return { bg: 'var(--accent-dim)', border: 'var(--accent)', text: 'var(--accent)', level: '中性', className: 'neutral' }
  }
  return {
    bg: 'rgba(138,150,168,.08)',
    border: 'var(--border-2)',
    text: '#5f6b7a',
    level: '偏弱',
    className: 'weak',
  }
}

function normalizeSectorName(value?: string) {
  return (value || '').replace(/\s+/g, '').toLowerCase()
}

function sectorMatches(industry: string, sectorName: string) {
  const normalizedIndustry = normalizeSectorName(industry)
  const normalizedSector = normalizeSectorName(sectorName)
  if (!normalizedIndustry || !normalizedSector) return false
  return normalizedIndustry.includes(normalizedSector) || normalizedSector.includes(normalizedIndustry)
}

function formatSignedPct(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function limitStockRows(payload?: LimitStocksPayload): SectorStockDetail[] {
  if (!payload) return []
  const rows = Array.isArray(payload)
    ? payload
    : [
      ...(payload.up_list ?? []),
      ...(payload.down_list ?? []),
      ...(payload.list ?? []),
      ...(payload.stocks ?? []),
    ]
  return rows.map(item => ({
    code: item.code,
    name: item.name || item.code,
    industry: item.industry || item.sector || item.board || item.concept || '',
    price: Number(item.price ?? 0),
    changePct: Number(item.change_pct ?? item.chg_pct ?? 0),
    score: Number(item.score ?? 0),
    signal: item.signal || item.desc || '涨跌明细',
    source: '涨跌明细',
  }))
}

function limitStockCount(payload: LimitStocksPayload | undefined, key: 'up' | 'down', fallback: number) {
  if (!payload) return fallback
  if (Array.isArray(payload)) return key === 'up' ? payload.length : fallback
  const explicit = key === 'up' ? payload.up_count : payload.down_count
  if (typeof explicit === 'number' && Number.isFinite(explicit)) return explicit
  const list = key === 'up' ? payload.up_list : payload.down_list
  return Array.isArray(list) ? list.length : fallback
}

function limitStockSource(payload?: LimitStocksPayload) {
  return payload && !Array.isArray(payload) ? payload.data_source : undefined
}

function sectorStockRows(
  sector: SectorResonance,
  signalStocks: SignalStock[],
  auctionRows: AuctionIntentItem[],
  limitRows: SectorStockDetail[],
): SectorStockDetail[] {
  const rows: SectorStockDetail[] = [
    ...limitRows,
    ...signalStocks.map(stock => ({
      code: stock.code,
      name: stock.name,
      industry: stock.industry || stock.market || '',
      price: Number(stock.price ?? 0),
      changePct: Number(stock.change_pct ?? 0),
      score: Number(stock.score ?? 0),
      signal: stock.signal || stock.desc || '信号',
      source: '信号',
    })),
    ...auctionRows.map(item => ({
      code: item.code,
      name: item.name,
      industry: item.industry || '',
      price: Number(item.price ?? 0),
      changePct: auctionChange(item),
      score: auctionScore(item, 0),
      signal: auctionIntentLabel(item, auctionScore(item, 0)),
      source: '竞价',
    })),
  ]
  const seen = new Set<string>()
  return rows
    .filter(row => row.code && !seen.has(row.code) && sectorMatches(row.industry, sector.name))
    .filter(row => {
      seen.add(row.code)
      return true
    })
    .sort((a, b) => b.changePct - a.changePct || b.score - a.score)
    .slice(0, 12)
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

function mergeAuctionRows(primary: AuctionIntentItem[], fallback: AuctionIntentItem[]) {
  const seen = new Set<string>()
  return [...primary, ...fallback]
    .filter(item => {
      if (!item.code || seen.has(item.code)) return false
      seen.add(item.code)
      return true
    })
    .slice(0, 10)
}

function auctionChange(item: AuctionIntentItem) {
  return Number(item.chg_pct ?? item.gap_pct ?? 0)
}

function auctionScore(item: AuctionIntentItem, fallback: number) {
  const score = Number(item.score)
  return Number.isFinite(score) ? score : fallback
}

function auctionBucketPct(count: number, total: number) {
  if (!total) return '0%'
  return `${((count / total) * 100).toFixed(1)}%`
}

function auctionIntentLabel(item: AuctionIntentItem, fallbackScore: number) {
  const rawIntent = String(item.intent ?? '').toLowerCase()
  if (rawIntent) {
    if (rawIntent.includes('bear') || rawIntent.includes('sell') || rawIntent.includes('出货')) return '出货'
    if (rawIntent.includes('neutral') || rawIntent.includes('中性')) return '中性'
    if (rawIntent.includes('bull') || rawIntent.includes('buy') || rawIntent.includes('抢筹')) return '抢筹'
    return String(item.intent)
  }
  const score = auctionScore(item, fallbackScore)
  if (score >= 60) return '抢筹'
  if (score >= 40) return '中性'
  return '出货'
}

function mergeWatchlistRows(primary?: WatchlistItem[]) {
  const seen = new Set<string>()
  const normalizedPrimary = Array.isArray(primary) ? primary : []
  return normalizedPrimary.filter(item => {
    if (!item.code || seen.has(item.code)) return false
    seen.add(item.code)
    return true
  }).slice(0, 12)
}

function marketCapYi(item: WatchlistItem) {
  const raw = Number(item.market_cap ?? 0)
  if (!Number.isFinite(raw) || raw <= 0) return 0
  return raw > 1_000_000 ? Math.round(raw / 100000000) : Math.round(raw)
}

function signalTone(signal?: string) {
  if (signal?.includes('强买')) return 't-up'
  if (signal?.includes('买入')) return 't-warn'
  if (signal?.includes('减仓') || signal?.includes('风险')) return 't-down'
  return 't-neu'
}

function signalDisplay(item: WatchlistItem) {
  if (!item.signal) return '持有'
  if (typeof item.score === 'number' && !item.signal.includes('风险')) return `${item.signal} ${item.score}`
  return item.signal
}

function watchlistSectorRows(items: WatchlistItem[]) {
  const grouped = items.reduce<Record<string, number>>((acc, item) => {
    const key = item.industry || '其他'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
  return Object.entries(grouped).sort((a, b) => b[1] - a[1])
}

function levelFromStock(stock: SignalStock): SignalLevelKey {
  const raw = `${stock.signal ?? ''} ${stock.desc ?? ''}`.toLowerCase()
  if (raw.includes('strong') || raw.includes('强买') || raw.includes('强烈')) return 'STRONG_BUY'
  if (raw.includes('sell') || raw.includes('卖出')) return 'SELL'
  if (raw.includes('reduce') || raw.includes('减仓')) return 'REDUCE'
  if (raw.includes('alert') || raw.includes('拐点')) return 'TIMING_ALERT'
  if (raw.includes('buy') || raw.includes('多头') || raw.includes('买入')) return 'BUY'
  return 'HOLD'
}

function mergeSignalMatrix(signalStocks: SignalStock[]): SignalMatrixItem[] {
  const apiRows: SignalMatrixItem[] = signalStocks.map((stock, index) => {
    const level = levelFromStock(stock)
    return {
      code: stock.code,
      name: stock.name,
      industry: stock.industry || stock.market || '实时触发',
      level,
      score: Number(stock.score ?? (level === 'STRONG_BUY' ? 86 : level === 'BUY' ? 72 : level === 'SELL' ? 24 : 58)),
      price: Number(stock.price ?? 0),
      changePct: Number(stock.change_pct ?? 0),
      watchlist: index < 2,
    }
  })
  const seen = new Set<string>()
  return apiRows.filter(item => {
    if (!item.code || seen.has(item.code)) return false
    seen.add(item.code)
    return true
  })
}

function filterSignalMatrix(items: SignalMatrixItem[], filter: string) {
  return items.filter(item => {
    if (filter === 'buy') return ['STRONG_BUY', 'BUY', 'TIMING_ALERT'].includes(item.level)
    if (filter === 'sell') return ['REDUCE', 'SELL'].includes(item.level)
    if (filter === 'alert') return item.level === 'TIMING_ALERT'
    if (filter === 'watchlist') return item.watchlist
    return true
  })
}

function signalSectorRows(items: SignalMatrixItem[]) {
  const grouped = items.reduce<Record<string, SignalMatrixItem[]>>((acc, item) => {
    acc[item.industry] ||= []
    acc[item.industry].push(item)
    return acc
  }, {})
  return Object.entries(grouped)
    .map(([sector, cells]) => {
      const bullish = cells.filter(item => ['STRONG_BUY', 'BUY', 'TIMING_ALERT'].includes(item.level)).length
      const bearish = cells.filter(item => ['REDUCE', 'SELL'].includes(item.level)).length
      return { sector, cells, bullish, bearish, ratio: bullish / Math.max(bearish, 1) }
    })
    .sort((a, b) => b.ratio - a.ratio || b.bullish - a.bullish)
}

function buildSignalStats(items: SignalMatrixItem[]) {
  const total = Math.max(items.length, 1)
  return signalStatsMeta.map(meta => {
    const count = items.filter(item => item.level === meta.key).length
    return {
      ...meta,
      count,
      pct: `${Math.round((count / total) * 100)}%`,
    }
  })
}

function buildSignalTrendOption(): EChartsOption {
  const dates = Array.from({ length: 30 }, (_, index) => {
    const day = index + 1
    return `06-${String(day).padStart(2, '0')}`
  })
  const buyData = dates.map((_, index) => Math.round(230 + Math.sin(index * 0.3) * 38 + (index % 5) * 6))
  const sellData = dates.map((_, index) => Math.round(112 - Math.sin(index * 0.3) * 15 + (index % 4) * 4))
  const ratioData = buyData.map((buy, index) => Number((buy / Math.max(sellData[index], 1)).toFixed(2)))
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 50, top: 28, bottom: 42 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 9, color: '#8a96a8', interval: 4 } },
    yAxis: [
      { type: 'value', name: '信号数', axisLabel: { fontSize: 9, color: '#52617a' }, splitLine: { lineStyle: { color: '#e6eaf0' } } },
      { type: 'value', name: '多空比', axisLabel: { fontSize: 9, color: '#8a96a8' }, splitLine: { show: false } },
    ],
    series: [
      { name: '买入信号', type: 'line', data: buyData, smooth: true, showSymbol: false, lineStyle: { color: '#ff4d4f', width: 2 }, itemStyle: { color: '#ff4d4f' } },
      { name: '卖出信号', type: 'line', data: sellData, smooth: true, showSymbol: false, lineStyle: { color: '#2ec27e', width: 2 }, itemStyle: { color: '#2ec27e' } },
      { name: '多空比', type: 'bar', yAxisIndex: 1, data: ratioData, barWidth: '55%', itemStyle: { color: 'rgba(61,139,255,.18)' } },
    ],
    legend: { bottom: 0, textStyle: { fontSize: 10, color: '#52617a' } },
  }
}

function buildSignalBubbleOption(items: SignalMatrixItem[]): EChartsOption {
  const rows = signalSectorRows(items)
  return {
    tooltip: { trigger: 'item' },
    grid: { left: 60, right: 24, top: 28, bottom: 42 },
    xAxis: { type: 'value', name: '信号数', axisLabel: { fontSize: 9, color: '#52617a' }, splitLine: { lineStyle: { color: '#e6eaf0' } } },
    yAxis: { type: 'value', name: '平均评分', min: 20, max: 90, axisLabel: { fontSize: 9, color: '#52617a' }, splitLine: { lineStyle: { color: '#e6eaf0' } } },
    series: [{
      type: 'scatter',
      data: rows.map(row => {
        const avg = row.cells.reduce((sum, cell) => sum + cell.score, 0) / row.cells.length
        return {
          name: row.sector,
          value: [row.cells.length, Number(avg.toFixed(1)), row.bullish],
          itemStyle: { color: row.ratio >= 2 ? '#2ec27e' : row.ratio >= 1 ? '#3d8bff' : '#ff4d4f' },
        }
      }),
      symbolSize: (value: unknown) => {
        const arr = Array.isArray(value) ? value : [0, 0, 1]
        return Math.max(20, Math.min(58, Number(arr[2] || 1) * 9))
      },
      label: { show: true, formatter: '{b}', position: 'right', fontSize: 10, color: '#52617a' },
    }],
  }
}

export default function Dashboard() {
  const location = useLocation()
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [screeningPicks, setScreeningPicks] = useState<AuctionIntentItem[]>([])
  const [auctionPicks, setAuctionPicks] = useState<AuctionIntentItem[]>([])
  const [signalFilter, setSignalFilter] = useState('all')
  const [sentimentPage, setSentimentPage] = useState<SentimentPageKey>('today')
  const [selectedSectorIndex, setSelectedSectorIndex] = useState(0)
  const [sectorDetailOpen, setSectorDetailOpen] = useState(false)
  const [error, setError] = useState(false)
  const [lastRefresh, setLastRefresh] = useState('')
  const activeTab = activeTabFromPath(location.pathname)

  const fetchDashboard = useCallback(async () => {
    try {
      const response = await signalApi.getDashboardSummary()
      setData(response.data as DashboardData)
      setError(false)
      setLastRefresh(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
    } catch {
      setError(true)
    }
  }, [])

  useEffect(() => {
    fetchDashboard()
    const timer = setInterval(fetchDashboard, 60_000)
    return () => clearInterval(timer)
  }, [fetchDashboard])

  useEffect(() => {
    signalApi.getScreeningDashboardSummary()
      .then(({ data: payload }) => {
        const dual = Array.isArray(payload?.dual_consensus) ? payload.dual_consensus : []
        const merged = Array.isArray(payload?.merged) ? payload.merged : []
        setScreeningPicks((dual.length > 0 ? dual : merged).slice(0, 8))
      })
      .catch(() => setScreeningPicks([]))

    signalApi.getDashboardAuction()
      .then(({ data: payload }) => {
        setAuctionPicks(Array.isArray(payload?.picks) ? payload.picks.slice(0, 8) : [])
      })
      .catch(() => setAuctionPicks([]))
  }, [])

  const sentiment = normalizeSentiment(data)
  const dimensions = dimensionsFromData(data)
  const gaugeOption = useMemo(() => buildGaugeOption(Math.round(sentiment.score)), [sentiment.score])
  const trendOption = useMemo(() => buildTrendOption(Math.round(sentiment.score)), [sentiment.score])
  const sectorRows = useMemo(() => fallbackSectors, [])
  const topSectorRows = useMemo(() => sectorRows.slice(0, 5), [sectorRows])
  const selectedSector = sectorRows[selectedSectorIndex] ?? { name: '半导体', score: 85, upRatio: 82, change: 3.2, fund: 32.6 }
  const upCount = limitStockCount(data?.limit_stocks, 'up', 87)
  const downCount = limitStockCount(data?.limit_stocks, 'down', 14)
  const upStocks = sentiment.up_stocks ?? fallbackSentiment.up_stocks ?? 1852
  const downStocks = sentiment.down_stocks ?? fallbackSentiment.down_stocks ?? 1432
  const totalStocks = sentiment.total_stocks ?? 3852
  const alertSignals = data?.alert_signals ?? []
  const signalStocks = data?.signal_stocks ?? []
  const limitRows = useMemo(() => limitStockRows(data?.limit_stocks), [data?.limit_stocks])
  const watchlist = useMemo(() => mergeWatchlistRows(data?.watchlist), [data?.watchlist])
  const watchlistSectorStats = useMemo(() => watchlistSectorRows(watchlist), [watchlist])
  const watchlistWinners = watchlist.filter(item => Number(item.change_pct ?? 0) >= 0).length
  const watchlistLosers = Math.max(watchlist.length - watchlistWinners, 0)
  const strongestWatch = watchlist.reduce((best, item) => Number(item.change_pct ?? -Infinity) > Number(best.change_pct ?? -Infinity) ? item : best, watchlist[0])
  const weakestWatch = watchlist.reduce((worst, item) => Number(item.change_pct ?? Infinity) < Number(worst.change_pct ?? Infinity) ? item : worst, watchlist[0])
  const buySignalCount = watchlist.filter(item => ['强买', '买入'].some(label => item.signal?.includes(label))).length
  const warnSignalCount = watchlist.filter(item => ['减仓', '风险'].some(label => item.signal?.includes(label))).length
  const avgWatchReturn = watchlist.reduce((sum, item) => sum + Number(item.change_pct ?? 0), 0) / Math.max(watchlist.length, 1)
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
  const auctionCandidates = auctionPicks.length
    ? auctionPicks
    : (data?.auction_intent?.top_bullish?.length ? data.auction_intent.top_bullish : screeningPicks)
  const bullishAuctionRows = mergeAuctionRows(auctionCandidates, [])
  const bearishAuctionRows = mergeAuctionRows(data?.auction_intent?.top_bearish || [], [])
  const visibleAuctionRows = [...bullishAuctionRows, ...bearishAuctionRows]
  const selectedSectorStocks = useMemo(
    () => sectorStockRows(selectedSector, signalStocks, visibleAuctionRows, limitRows),
    [selectedSector, signalStocks, visibleAuctionRows, limitRows],
  )
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
  const updatedAt = data?.refreshed_at || lastRefresh
  const currentDataDate = data?.data_freshness?.as_of || data?.refreshed_at

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="智能看板页签"
        activeKey={activeTab}
        onChange={(key) => {
          const tab = dashboardTabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={dashboardTabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />

      {activeTab === 'sentiment' && (
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
                  <div className="zit">加权合成: {sentiment.formula ?? fallbackSentiment.formula}</div>
                  <div className="ai-sentiment-card">
                    <div className="ai-title"><span>AI 大模型情绪解读</span><em>由大模型生成</em></div>
                    <p>今日市场情绪判断为 <b>偏牛、但未进入过热。</b> 指数趋势和资金面形成主要支撑，赚钱效应扩散到多数股票，但炸板率仍提示短线追高风险。</p>
                    <div className="ai-reason-grid">
                      <div><strong>支撑原因 1 · 趋势</strong><span>上证、深成指同步走强，趋势分 75，说明指数环境对做多更友好。</span></div>
                      <div><strong>支撑原因 2 · 资金</strong><span>北向和主力资金均为净流入，两市成交额维持活跃，流动性分 72。</span></div>
                      <div><strong>支撑原因 3 · 赚钱效应</strong><span>上涨家数多于下跌家数，涨停 {upCount} 家，封板率 82.9%，情绪扩散较好。</span></div>
                    </div>
                    <div className="risk-banner warn"><strong>风险提醒</strong><span>若综合情绪继续接近 80 分，或炸板率明显抬升，应从积极进攻转为控制仓位。</span></div>
                  </div>
                </PrototypeCard>

                <div className="grid">
                  <PrototypeCard title="市场快照" icon={<EyeOutlined />} meta={`基于 ${totalStocks.toLocaleString()} 只股票`}>
                    <div className="snapshot-grid">
                      <div className="snap-stat"><div className="lbl">涨停</div><div className="val up">{upCount}</div><div className="sub">+12 vs 昨</div></div>
                      <div className="snap-stat"><div className="lbl">跌停</div><div className="val down">{downCount}</div><div className="sub">-3 vs 昨</div></div>
                      <div className="snap-stat"><div className="lbl">炸板</div><div className="val warn">18</div><div className="sub">炸板率 17.1%</div></div>
                      <div className="snap-stat"><div className="lbl">封板率</div><div className="val neu">82.9<span style={{ fontSize: 12 }}>%</span></div><div className="sub">连板 6 板</div></div>
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

                  <PrototypeCard title="资金全景" icon={<DollarOutlined />} meta="估算值">
                    <div className="fund-grid">
                      <div className="fund-item"><div className="lbl">北向资金</div><div className="val">+23.5 亿</div></div>
                      <div className="fund-item"><div className="lbl">主力资金</div><div className="val">+12.8 亿</div></div>
                      <div className="fund-item"><div className="lbl">融资余额变化</div><div className="val">+15.2 亿</div></div>
                      <div className="fund-item"><div className="lbl">两市成交额</div><div className="val">8,520 亿</div><div className="prototype-panel-note">换手率 3.2%</div></div>
                    </div>
                  </PrototypeCard>

                  <div className="op-hint">
                    <div className="pos warn">7-8<span style={{ fontSize: 16 }}>成</span></div>
                    <div className="op-body">
                      <div className="op-title warn">偏牛 · 适度积极</div>
                      <div className="op-desc">关注强势板块趋势延续机会。控制仓位在 7-8 成，警惕情绪接近过热区间。</div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          )}

          {sentimentPage === 'history' && (
            <section className="market-page" aria-label="历史情绪">
              <div className="insight-grid">
                <MetricCard label="当前分位" value="72%" sub="近 120 日偏高，但未极端" tone="warn" />
                <MetricCard label="情绪斜率" value="+5" sub="连续 3 日抬升" tone="down" />
                <MetricCard label="回撤风险" value="中" sub="高位追涨需降速" tone="accent" />
                <MetricCard label="历史相似" value="8 次" sub="5 次继续走强，3 次回落" tone="muted" />
              </div>
              <div className="history-layout">
                <PrototypeCard title="情绪历史趋势" icon={<LineChartOutlined />} meta="30日 · 60日 · 120日">
                  <ReactECharts option={trendOption} style={{ height: 420, width: '100%' }} notMerge />
                </PrototypeCard>
                <div className="history-side">
                  <PrototypeCard title="历史相似场景" icon={<EyeOutlined />} meta="按相似度排序">
                    <div className="similar-list">
                      {[
                        ['2026-05-22', '情绪 71，半导体主线启动，随后 3 日继续走强。'],
                        ['2026-04-18', '资金净流入但炸板率抬升，次日高开低走。'],
                        ['2026-03-29', '趋势与广度同步改善，强势板块轮动扩散。'],
                      ].map(([date, desc]) => (
                        <div className="similar-item" key={date}>
                          <b>{date}</b>
                          <span>{desc}</span>
                        </div>
                      ))}
                    </div>
                  </PrototypeCard>
                  <PrototypeCard title="周期状态表" icon={<BarChartOutlined />} meta="模型判断">
                    <table className="tbl compact">
                      <tbody>
                        <tr><td>短线</td><td className="warn">升温</td><td>追高风险增加</td></tr>
                        <tr><td>中线</td><td className="up">偏强</td><td>主线仍有延续</td></tr>
                        <tr><td>长线</td><td className="neu">修复</td><td>估值压力可控</td></tr>
                      </tbody>
                    </table>
                  </PrototypeCard>
                </div>
              </div>
            </section>
          )}

          {sentimentPage === 'sector' && (
            <section className="market-page" aria-label="板块共振">
              <div className="sector-top5">
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
                      <em>资金 {sector.fund >= 0 ? '+' : ''}{sector.fund} 亿，涨 {sector.upRatio}%，今日{index === 0 ? '最强' : '靠前'}。</em>
                    </button>
                  )
                })}
              </div>

              <div className="resonance-note">
                <div><b>结论：</b>今日不是普涨行情，主线集中在科技链。半导体、新能源、AI 算力同时具备资金净流入、上涨占比和情绪分抬升。</div>
                <div><b>用户最该看：</b>点击 Top5 或热力格子，查看该板块二级方向、龙头样本、补涨线和弱分支。</div>
                <div><b>下一步：</b>若明日科技链继续保持前三共振排名，优先跟踪强势龙头和低位补涨。</div>
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
                      <p>二级方向、成分股涨幅、资金共振和操作线索。</p>
                      <div className="detail-kpis">
                        <div><span>共振分</span><b>{selectedSector.score}</b></div>
                        <div><span>上涨占比</span><b>{selectedSector.upRatio}%</b></div>
                        <div><span>资金</span><b>{selectedSector.fund >= 0 ? '+' : ''}{selectedSector.fund}亿</b></div>
                      </div>
                      <div className="analysis-box"><b>看点：</b>下钻重点看二级方向是否集中、龙头是否继续封板、低位补涨是否扩散。</div>
                      <div className="sector-stock-section">
                        <h4>板块股票涨幅明细</h4>
                        <SectorStockTable rows={selectedSectorStocks} />
                      </div>
                      <table className="tbl compact">
                        <thead><tr><th>二级方向</th><th className="r">强度</th><th>动作</th></tr></thead>
                        <tbody>
                          <tr><td>设备 / 材料</td><td className="r up">强</td><td>主线跟踪</td></tr>
                          <tr><td>封测 / 模组</td><td className="r warn">中强</td><td>找补涨</td></tr>
                          <tr><td>低位分支</td><td className="r neu">观察</td><td>等放量</td></tr>
                        </tbody>
                      </table>
                    </div>
                  </PrototypeCard>
                  <PrototypeCard title="AI 共振结论" icon={<FundOutlined />} meta="由大模型生成">
                    <div className="ai-resonance">
                      <p><b>结论：</b>主线集中在科技链，强度最高的是 {topSectorRows[0]?.name}，其次是 {topSectorRows[1]?.name} 和 {topSectorRows[2]?.name}。</p>
                      <p><b>注意：</b>如果前排板块排名快速下滑，说明资金从进攻切换到防守，应降低追高仓位。</p>
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
      )}

      {activeTab === 'auction' && (
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
        </>
      )}

      {activeTab === 'signals' && (
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
                  <div><span>板块共振偏多</span><b className="up">14 板块</b></div>
                  <div><span>板块共振偏空</span><b className="down">3 板块</b></div>
                  <div><span>共振阈值</span><b>≥3 只同向</b></div>
                </div>
                <div className="watch-row">
                  <span>自选股信号</span>
                  <b>5 / 12 已触发</b>
                  <small>管理自选 →</small>
                </div>
              </PrototypeCard>

              <PrototypeCard title="实时信号流" icon={<ThunderboltOutlined />} meta="最近 20 条">
                <div className="signal-stream">
                  {topSignals.slice(0, 6).map((item, index) => {
                    const meta = signalLevelMeta[item.level]
                    return (
                      <div className="stream-row" key={`${item.code}-${index}`}>
                        <span className="stream-time mono">{['09:25', '09:31', '09:42', '10:08', '10:23', '10:41'][index]}</span>
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
            </PrototypeCard>
            <PrototypeCard title="板块信号气泡图" icon={<ApartmentOutlined />} meta="信号数量 × 平均评分 × 市值">
              <ReactECharts option={signalBubbleOption} style={{ height: 300, width: '100%' }} notMerge />
            </PrototypeCard>
          </div>

          <div className="footer-bar">
            <span>数据来源: signal-service (signal_snapshots 缓存)</span>
            <span className="sep" />
            <span>信号模型: Kronos(20) + 技术(20) + 资金(12) + 基本面(15) + 事件(13) + 市场(20) = 100分</span>
            <span className="sep" />
            <span>免责声明: 本页信号为量化模型输出，不构成投资建议。历史数据不代表未来表现</span>
          </div>
        </>
      )}

      {activeTab === 'watchlist' && (
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
                  {watchlistSectorStats.map(([sector, count], index) => (
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
      )}
    </PrototypePage>
  )
}
