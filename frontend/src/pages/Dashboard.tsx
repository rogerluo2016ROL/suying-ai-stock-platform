import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
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
import { MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, PrototypeTabs } from '../components/prototype'
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
  market_sentiment?: MarketSentimentData
  market_regime_v2?: MarketRegimeData
  signal_stocks?: SignalStock[]
  limit_stocks?: {
    up_count: number
    down_count: number
    data_source?: string
  }
  alert_signals?: AlertSignal[]
  auction_intent?: {
    total_analyzed: number
    bullish_count: number
    bearish_count: number
    top_bullish?: AuctionIntentItem[]
    top_bearish?: AuctionIntentItem[]
  }
  watchlist?: WatchlistItem[]
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

const fallbackSectors = [
  ['半导体', 85, 82, 3.2], ['新能源', 78, 72, 2.8], ['AI算力', 75, 75, 2.5], ['消费电子', 68, 60, 1.8],
  ['白酒', 65, 68, 1.5], ['汽车', 60, 55, 1.2], ['医药', 58, 50, 0.8], ['光伏', 52, 48, 0.5],
  ['金融', 50, 45, 0.2], ['军工', 45, 38, -0.3], ['传媒', 42, 35, -0.5], ['电力', 40, 40, -0.1],
  ['农业', 38, 36, -0.8], ['有色', 36, 32, -1.0], ['化工', 34, 30, -0.6], ['钢铁', 30, 22, -1.5],
]

const fallbackAuctionBullish: AuctionIntentItem[] = [
  { code: '688981', name: '中芯国际', industry: '半导体', chg_pct: 5.56, vol_ratio: 13.5, buy_sell_ratio: 42, score: 92, intent: '🔥强烈抢筹' },
  { code: '300750', name: '宁德时代', industry: '新能源', chg_pct: 4.58, vol_ratio: 11.1, buy_sell_ratio: 38, score: 88, intent: '🔥强烈抢筹' },
  { code: '000001', name: '平安银行', industry: '金融', chg_pct: 4.17, vol_ratio: 12.3, buy_sell_ratio: 35, score: 85, intent: '🔥强烈抢筹' },
  { code: '002415', name: '海康威视', industry: 'AI算力', chg_pct: 3.66, vol_ratio: 10.5, buy_sell_ratio: 30, score: 82, intent: '🔥强烈抢筹' },
  { code: '601012', name: '隆基绿能', industry: '光伏', chg_pct: 4.69, vol_ratio: 9.8, buy_sell_ratio: 28, score: 81, intent: '🔥强烈抢筹' },
  { code: '002230', name: '科大讯飞', industry: 'AI算力', chg_pct: 3.9, vol_ratio: 9.2, buy_sell_ratio: 27, score: 80, intent: '🔥强烈抢筹' },
]

const fallbackAuctionBearish: AuctionIntentItem[] = [
  { code: '600000', name: '浦发银行', industry: '银行', chg_pct: -5.27, vol_ratio: 15.2, score: 18, intent: '⚠️强烈出货' },
  { code: '000858', name: '五粮液', industry: '白酒', chg_pct: -2.82, vol_ratio: 10.2, score: 20, intent: '⚠️强烈出货' },
  { code: '000002', name: '万科A', industry: '地产', chg_pct: -4.23, vol_ratio: 9.8, score: 22, intent: '⚠️强烈出货' },
  { code: '601398', name: '工商银行', industry: '银行', chg_pct: -3.12, vol_ratio: 11.5, score: 24, intent: '⚠️强烈出货' },
  { code: '600031', name: '三一重工', industry: '机械', chg_pct: -2.41, vol_ratio: 7.8, score: 26, intent: '⚠️强烈出货' },
  { code: '600036', name: '招商银行', industry: '银行', chg_pct: -3.29, vol_ratio: 8.3, score: 28, intent: '📉偏空出货' },
]

const fallbackWatchlist: WatchlistItem[] = [
  { code: '300750', name: '宁德时代', industry: '新能源', market_cap: 9850, price: 218.5, change_pct: 8.21, signal: '强买', score: 82 },
  { code: '688981', name: '中芯国际', industry: '半导体', market_cap: 5420, price: 68.2, change_pct: 5.82, signal: '强买', score: 78 },
  { code: '600519', name: '贵州茅台', industry: '白酒', market_cap: 22400, price: 1785, change_pct: 3.15, signal: '买入', score: 68 },
  { code: '601012', name: '隆基绿能', industry: '光伏', market_cap: 2180, price: 32.8, change_pct: 4.53, signal: '买入', score: 65 },
  { code: '002594', name: '比亚迪', industry: '汽车', market_cap: 8320, price: 285.3, change_pct: 1.22, signal: '持有', score: 52 },
  { code: '603259', name: '药明康德', industry: '医药', market_cap: 2680, price: 68.5, change_pct: 0.85, signal: '持有', score: 48 },
  { code: '603019', name: '中科曙光', industry: 'AI算力', market_cap: 1150, price: 52.4, change_pct: 0.38, signal: '持有', score: 45 },
  { code: '000858', name: '五粮液', industry: '白酒', market_cap: 5760, price: 148.3, change_pct: -2.81, signal: '减仓', score: 32, stop_distance: 0.7 },
  { code: '600000', name: '浦发银行', industry: '金融', market_cap: 2180, price: 8.92, change_pct: 1.13, signal: '审计风险', score: 35, risk_note: '保留意见' },
  { code: '601899', name: '紫金矿业', industry: '有色', market_cap: 4120, price: 16.82, change_pct: 2.31, signal: '持有', score: 55 },
  { code: '601318', name: '中国平安', industry: '金融', market_cap: 9520, price: 52.4, change_pct: 0.58, signal: '持有', score: 50 },
  { code: '300274', name: '阳光电源', industry: '光伏', market_cap: 1850, price: 88.6, change_pct: 3.42, signal: '持有', score: 58 },
]

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

const fallbackSignalMatrix: SignalMatrixItem[] = [
  { code: '688981', name: '中芯国际', industry: '半导体', level: 'STRONG_BUY', score: 92, price: 68.2, changePct: 5.56, watchlist: true },
  { code: '002371', name: '北方华创', industry: '半导体', level: 'STRONG_BUY', score: 88, price: 312.4, changePct: 4.2 },
  { code: '603986', name: '兆易创新', industry: '半导体', level: 'BUY', score: 76, price: 153.0, changePct: 3.1 },
  { code: '002156', name: '通富微电', industry: '半导体', level: 'TIMING_ALERT', score: 71, price: 26.8, changePct: 2.8 },
  { code: '300750', name: '宁德时代', industry: '新能源', level: 'STRONG_BUY', score: 90, price: 218.5, changePct: 8.2, watchlist: true },
  { code: '002594', name: '比亚迪', industry: '新能源', level: 'BUY', score: 82, price: 98.5, changePct: 4.5, watchlist: true },
  { code: '601012', name: '隆基绿能', industry: '新能源', level: 'BUY', score: 78, price: 32.8, changePct: 4.7, watchlist: true },
  { code: '300274', name: '阳光电源', industry: '新能源', level: 'HOLD', score: 61, price: 77.2, changePct: 1.9, watchlist: true },
  { code: '688256', name: '寒武纪', industry: 'AI算力', level: 'STRONG_BUY', score: 87, price: 425.8, changePct: 6.3, watchlist: true },
  { code: '603019', name: '中科曙光', industry: 'AI算力', level: 'BUY', score: 79, price: 56.4, changePct: 3.5 },
  { code: '000977', name: '浪潮信息', industry: 'AI算力', level: 'TIMING_ALERT', score: 74, price: 43.6, changePct: 3.1 },
  { code: '002230', name: '科大讯飞', industry: 'AI算力', level: 'BUY', score: 80, price: 58.2, changePct: 3.9 },
  { code: '002475', name: '立讯精密', industry: '消费电子', level: 'BUY', score: 73, price: 31.9, changePct: 2.8 },
  { code: '002241', name: '歌尔股份', industry: '消费电子', level: 'HOLD', score: 58, price: 18.2, changePct: 1.3 },
  { code: '300433', name: '蓝思科技', industry: '消费电子', level: 'REDUCE', score: 41, price: 14.6, changePct: -0.8 },
  { code: '002938', name: '鹏鼎控股', industry: '消费电子', level: 'TIMING_ALERT', score: 67, price: 36.1, changePct: 1.6 },
  { code: '600519', name: '贵州茅台', industry: '白酒', level: 'BUY', score: 72, price: 1785.0, changePct: 3.2, watchlist: true },
  { code: '000858', name: '五粮液', industry: '白酒', level: 'REDUCE', score: 38, price: 152.0, changePct: -2.1, watchlist: true },
  { code: '000568', name: '泸州老窖', industry: '白酒', level: 'HOLD', score: 55, price: 168.7, changePct: 0.6 },
  { code: '600276', name: '恒瑞医药', industry: '医药', level: 'HOLD', score: 62, price: 45.3, changePct: 1.1, watchlist: true },
  { code: '603259', name: '药明康德', industry: '医药', level: 'SELL', score: 24, price: 69.4, changePct: -1.5, watchlist: true },
  { code: '300760', name: '迈瑞医疗', industry: '医药', level: 'BUY', score: 70, price: 285.6, changePct: 2.4 },
  { code: '601633', name: '长城汽车', industry: '汽车', level: 'HOLD', score: 53, price: 27.5, changePct: 0.9, watchlist: true },
  { code: '000625', name: '长安汽车', industry: '汽车', level: 'REDUCE', score: 36, price: 18.6, changePct: -0.9 },
  { code: '000002', name: '万科A', industry: '房地产', level: 'SELL', score: 18, price: 8.2, changePct: -4.2, watchlist: true },
  { code: '600048', name: '保利发展', industry: '房地产', level: 'REDUCE', score: 33, price: 9.4, changePct: -1.8 },
  { code: '601155', name: '新城控股', industry: '房地产', level: 'SELL', score: 20, price: 11.1, changePct: -3.2 },
]

const signalStats = [
  { key: 'STRONG_BUY' as SignalLevelKey, icon: '●', count: 76, pct: '20%' },
  { key: 'BUY' as SignalLevelKey, icon: '●', count: 148, pct: '38%' },
  { key: 'HOLD' as SignalLevelKey, icon: '●', count: 412, pct: '54%' },
  { key: 'REDUCE' as SignalLevelKey, icon: '●', count: 89, pct: '12%' },
  { key: 'SELL' as SignalLevelKey, icon: '●', count: 35, pct: '5%' },
  { key: 'TIMING_ALERT' as SignalLevelKey, icon: '●', count: 12, pct: '2%' },
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
  const hue = 120 - (score / 100) * 120
  const light = 60 - (score / 100) * 25
  return {
    bg: `hsla(${hue},55%,${light}%,0.12)`,
    border: `hsl(${hue},55%,${light}%)`,
    text: `hsl(${hue},60%,35%)`,
  }
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

function mergeWatchlistRows(primary?: WatchlistItem[]) {
  const seen = new Set<string>()
  const normalizedPrimary = Array.isArray(primary) ? primary : []
  return [...normalizedPrimary, ...fallbackWatchlist].filter(item => {
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
  return [...apiRows, ...fallbackSignalMatrix].filter(item => {
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
  const upCount = data?.limit_stocks?.up_count ?? 87
  const downCount = data?.limit_stocks?.down_count ?? 14
  const upStocks = sentiment.up_stocks ?? fallbackSentiment.up_stocks ?? 1852
  const downStocks = sentiment.down_stocks ?? fallbackSentiment.down_stocks ?? 1432
  const totalStocks = sentiment.total_stocks ?? 3852
  const alertSignals = data?.alert_signals ?? []
  const signalStocks = data?.signal_stocks ?? []
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
  const bullishAuctionRows = mergeAuctionRows(auctionCandidates, fallbackAuctionBullish)
  const bearishAuctionRows = mergeAuctionRows(data?.auction_intent?.top_bearish || [], fallbackAuctionBearish)
  const analyzedCount = (data?.auction_intent?.total_analyzed || 0) >= 100 ? data?.auction_intent?.total_analyzed : 328
  const strongBullishCount = (data?.auction_intent?.bullish_count || 0) >= 10 ? data?.auction_intent?.bullish_count : 45
  const bearishCount = (data?.auction_intent?.bearish_count || 0) >= 10 ? data?.auction_intent?.bearish_count : 22

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

          <div className="row r-6-4 mt14">
            <PrototypeCard title="情绪历史趋势" icon={<LineChartOutlined />} meta="30日 · 60日 · 120日">
              <ReactECharts option={trendOption} style={{ height: 360, width: '100%' }} notMerge />
            </PrototypeCard>
            <PrototypeCard title="板块情绪分化" icon={<ApartmentOutlined />} meta="申万一级 · 28 板块">
              <div className="sector-grid">
                {fallbackSectors.map(([name, score, upRatio, change]) => {
                  const color = sectorColor(Number(score))
                  return (
                    <div className="sector-cell" key={String(name)} style={{ background: color.bg, borderLeftColor: color.border }}>
                      <div className="sn">{name}</div>
                      <div className="ss" style={{ color: color.text }}>{score}</div>
                      <div className="sd">涨{upRatio}% · 均涨{Number(change) >= 0 ? '+' : ''}{change}%</div>
                    </div>
                  )
                })}
              </div>
            </PrototypeCard>
          </div>

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
            actions={[
              { key: 'updated', label: '数据更新 09:25:42' },
              { key: 'refresh', label: '手动刷新', active: true, tone: 'neutral' },
            ]}
          />
          <div className="kpis">
            <MetricCard label="分析标的" value={analyzedCount} sub="覆盖沪深两市竞价" tone="muted" />
            <MetricCard label="强烈抢筹" value={strongBullishCount} sub="评分 ≥ 75 · 占比 13.7%" tone="down" />
            <MetricCard label="偏多抢筹" value="89" sub="评分 60-74 · 占比 27.1%" tone="warn" />
            <MetricCard label="中性" value="120" sub="评分 25-59 · 占比 36.6%" tone="accent" />
            <MetricCard label="偏空出货" value="52" sub="评分 15-24 · 占比 15.9%" tone="muted" />
            <MetricCard label="强烈出货" value={bearishCount} sub="评分 < 15 · 占比 6.7%" tone="up" />
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
                      <td><span className="tag t-warn">{item.intent || '🔥强烈抢筹'}</span></td>
                    </tr>
                  ))}
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
                      <td><span className="tag t-neu">{item.intent || '⚠️强烈出货'}</span></td>
                    </tr>
                  ))}
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
            subtitle="12 只自选 · 实时行情 · 信号监控 · 盈亏分析"
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
            <MetricCard label="买入信号" value={`${buySignalCount} 只`} sub="强买2 · 买入2 · 拐点0" tone="up" />
            <MetricCard label="卖出/警报" value={`${warnSignalCount} 只`} sub="减仓1 · 审计风险1" tone="warn" />
            <MetricCard label="板块覆盖" value={`${watchlistSectorStats.length} 个`} sub={`${watchlistSectorStats[0]?.[0] ?? '半导体'}最集中 (${watchlistSectorStats[0]?.[1] ?? 3}只)`} tone="accent" />
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
                </div>
                <div className="zit">半导体集中度 25% · 建议分散</div>
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
                </div>
                <div className="watch-avg-row"><span>等权平均</span><b className="up">{avgWatchReturn >= 0 ? '+' : ''}{avgWatchReturn.toFixed(2)}%</b></div>
              </PrototypeCard>

              <PrototypeCard title="信号联动" icon={<ThunderboltOutlined />} meta="自选股信号触发">
                <div className="watch-alert-list">
                  {[
                    ['宁德时代 强买 82分', 'Kronos78/技术82/板块共振9只 · 今日竞价高开3.2%', 'up'],
                    ['中芯国际 强买 78分', '技术80/资金68 · 北向连续3日净流入', 'up'],
                    ['五粮液 距止损仅0.7%', '现价148.30 · 止损147.25 · 建议关注', 'warn'],
                    ['浦发银行 审计:保留意见', '信号评分 -15分 · 基本面降级', 'warn'],
                  ].map(([title, detail, tone]) => (
                    <div className="watch-alert-row" key={title}>
                      <span className={`led ${tone === 'up' ? 'on' : 'warn'}`} />
                      <div><b className={tone === 'up' ? 'up' : 'warn'}>{title}</b><small>{detail}</small></div>
                    </div>
                  ))}
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
