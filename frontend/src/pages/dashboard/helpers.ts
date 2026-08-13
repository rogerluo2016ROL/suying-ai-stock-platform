import type { EChartsOption } from 'echarts'
import { lightTokens, signalLevelTokens, alpha } from '../../styles/tokens'
import type {
  AuctionIntentItem,
  DashboardData,
  LimitStocksPayload,
  MarketSentimentData,
  SectorResonance,
  SectorStockDetail,
  SentimentPageKey,
  SentimentReason,
  SignalLevelKey,
  SignalMatrixItem,
  SignalStock,
  WatchlistItem,
} from './types'

export const fallbackSentiment: MarketSentimentData = {
  score: 0,
  label: '暂无数据',
  trade_date: '',
  avg_change_pct: 0,
  up_stocks: 0,
  down_stocks: 0,
  total_stocks: 0,
  model: 'market_regime_v2',
  formula: '',
}

const fallbackDimTone = `linear-gradient(90deg,${lightTokens.border2},${lightTokens.border2})`

export const fallbackDimensions = [
  { key: 'trend', label: '趋势', weight: 25, score: 0, tone: fallbackDimTone },
  { key: 'breadth', label: '广度', weight: 20, score: 0, tone: fallbackDimTone },
  { key: 'liquidity', label: '流动性', weight: 15, score: 0, tone: fallbackDimTone },
  { key: 'leverage', label: '杠杆', weight: 10, score: 0, tone: fallbackDimTone },
  { key: 'foreign', label: '外资', weight: 5, score: 0, tone: fallbackDimTone },
  { key: 'valuation', label: '估值', weight: 5, score: 0, tone: fallbackDimTone },
  { key: 'risk', label: '风险事件', weight: 15, score: 0, tone: fallbackDimTone },
  { key: 'sentiment', label: '情绪', weight: 5, score: 0, tone: fallbackDimTone },
]

export const sentimentPages: Array<{ key: SentimentPageKey; number: string; label: string; desc: string }> = [
  { key: 'today', number: '01', label: '今日市场', desc: '当天情绪、资金、涨跌快照' },
  { key: 'history', number: '02', label: '历史情绪', desc: '30/60/120 日情绪回溯' },
  { key: 'sector', number: '03', label: '板块共振', desc: '强势板块、分化和共振方向' },
]

export const signalLevelMeta: Record<SignalLevelKey, { label: string; color: string; className: string }> = {
  STRONG_BUY: { label: '强买', color: signalLevelTokens.STRONG_BUY, className: 'buy-strong' },
  BUY: { label: '买入', color: signalLevelTokens.BUY, className: 'buy' },
  HOLD: { label: '持有', color: signalLevelTokens.HOLD, className: 'hold' },
  REDUCE: { label: '减仓', color: signalLevelTokens.REDUCE, className: 'reduce' },
  SELL: { label: '卖出', color: signalLevelTokens.SELL, className: 'sell' },
  TIMING_ALERT: { label: '拐点', color: signalLevelTokens.TIMING_ALERT, className: 'alert' },
}

export const signalStatsMeta = [
  { key: 'STRONG_BUY' as SignalLevelKey, icon: '●' },
  { key: 'BUY' as SignalLevelKey, icon: '●' },
  { key: 'HOLD' as SignalLevelKey, icon: '●' },
  { key: 'REDUCE' as SignalLevelKey, icon: '●' },
  { key: 'SELL' as SignalLevelKey, icon: '●' },
  { key: 'TIMING_ALERT' as SignalLevelKey, icon: '●' },
]

/**
 * 从已返回的 market_sentiment / market_regime_v2 八维分数 + 市场快照派生 3 条 AI 解读支撑原因。
 * 后端尚未提供结构化 `reasons` 字段，这里用真实接口值推导文案，缺字段时标注 fallback_reason，
 * 不引入演示数据，不空白。
 */
export function buildSentimentReasons(
  sentiment: MarketSentimentData,
  dimensions: Array<{ key: string; label: string; score: number; weight: number }>,
  snapshot: { upStocks: number; downStocks: number; upCount: number; downCount: number; totalStocks: number },
): SentimentReason[] {
  const dimBy = (key: string) => dimensions.find(item => item.key === key)
  const hasSnapshot = snapshot.totalStocks > 0 || snapshot.upCount > 0 || snapshot.downCount > 0

  const trend = dimBy('trend')
  const liquidity = dimBy('liquidity')

  const reasons: SentimentReason[] = [
    {
      title: trend ? `支撑原因 1 · ${trend.label}` : '支撑原因 1 · 趋势',
      detail: trend
        ? `${trend.label}维度评分 ${trend.score}（权重 ${trend.weight}%），反映指数层面趋势环境${trend.score >= 60 ? '对做多更友好' : '仍需观察确认'}。`
        : '后端未返回趋势维度分数，暂无法量化指数趋势环境。',
      fallback: !trend,
    },
    {
      title: liquidity ? `支撑原因 2 · ${liquidity.label}` : '支撑原因 2 · 资金',
      detail: liquidity
        ? `${liquidity.label}维度评分 ${liquidity.score}（权重 ${liquidity.weight}%），近似资金面与成交活跃度${liquidity.score >= 60 ? '处于活跃区间' : '偏中性'}。`
        : '实时资金（北向/主力/融资）字段未接入，资金支撑原因待后端补齐。',
      fallback: !liquidity,
    },
    {
      title: '支撑原因 3 · 赚钱效应',
      detail: hasSnapshot
        ? `上涨 ${snapshot.upStocks.toLocaleString()} 只 / 下跌 ${snapshot.downStocks.toLocaleString()} 只，涨停 ${snapshot.upCount}、跌停 ${snapshot.downCount}，赚钱效应${snapshot.upStocks >= snapshot.downStocks ? '扩散较好' : '尚未扩散'}。`
        : '涨跌家数与涨停跌停未返回，赚钱效应扩散度待市场快照补齐。',
      fallback: !hasSnapshot,
    },
  ]

  return reasons
}

export function normalizeSentiment(data: DashboardData | null): MarketSentimentData {
  if (data?.market_sentiment) return data.market_sentiment
  if (data?.market_regime_v2) {
    return {
      ...fallbackSentiment,
      score: Number(data.market_regime_v2.score ?? 0),
      label: data.market_regime_v2.label,
      model: `market_regime_v2 · 置信度 ${data.market_regime_v2.confidence ?? '--'}%`,
    }
  }
  return fallbackSentiment
}

export function toneFromScore(score: number) {
  if (score >= 70) return `linear-gradient(90deg,${lightTokens.down},${lightTokens.downDeep})`
  if (score >= 55) return `linear-gradient(90deg,${lightTokens.accent},${lightTokens.down})`
  if (score >= 40) return `linear-gradient(90deg,${lightTokens.accent},${lightTokens.accent})`
  return `linear-gradient(90deg,${lightTokens.up},${lightTokens.warn})`
}

export function dimensionsFromData(data: DashboardData | null) {
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
    if (!source) return item
    const score = Math.max(0, Math.min(100, Math.round(source.score ?? item.score)))
    return {
      ...item,
      label: labelMap[item.key] ?? item.label,
      weight: Math.round((source.weight ?? item.weight / 100) * 100),
      score,
      tone: toneFromScore(score),
    }
  })
}

export function buildGaugeOption(score: number): EChartsOption {
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
          color: [[0.2, lightTokens.downDeep], [0.4, lightTokens.down], [0.6, lightTokens.accent], [0.8, lightTokens.warn], [1, lightTokens.up]],
        },
      },
      pointer: { length: '72%', width: 6, itemStyle: { color: lightTokens.border2 } },
      axisTick: { distance: -18, length: 6, lineStyle: { color: lightTokens.muted, width: 1 } },
      splitLine: { distance: -22, length: 14, lineStyle: { color: lightTokens.muted, width: 2 } },
      axisLabel: { color: lightTokens.muted, fontSize: 9, fontFamily: 'var(--font-mono)', distance: 28 },
      detail: {
        valueAnimation: true,
        formatter: `{value|${score}}\n{unit| 分}`,
        rich: {
          value: { fontSize: 38, fontWeight: 720, color: lightTokens.fg, fontFamily: 'var(--font-mono)' },
          unit: { fontSize: 13, color: lightTokens.fg2, padding: [0, 0, 0, 2] },
          change: { fontSize: 12, color: lightTokens.up, padding: [6, 0, 0, 0] },
        },
        offsetCenter: [0, '18%'],
      },
      title: { offsetCenter: [0, '52%'], color: lightTokens.fg2, fontSize: 12 },
      data: [{ value: score, name: '综合情绪指数' }],
    }],
    backgroundColor: 'transparent',
  }
}

export function buildTrendOption(): EChartsOption {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 70, top: 30, bottom: 42 },
    xAxis: { type: 'category', data: [], axisLabel: { fontSize: 9, color: lightTokens.muted, interval: 4 } },
    yAxis: [
      { type: 'value', name: '情绪指数', min: 0, max: 100, axisLabel: { fontSize: 9, color: lightTokens.fg2 }, splitLine: { lineStyle: { color: lightTokens.border } } },
      { type: 'value', name: '沪深300', axisLabel: { fontSize: 9, color: lightTokens.muted }, splitLine: { show: false } },
    ],
    series: [
      {
        name: '情绪指数',
        type: 'line',
        yAxisIndex: 0,
        data: [],
        lineStyle: { width: 2.5, color: lightTokens.accent },
        itemStyle: { color: lightTokens.accent },
        symbol: 'circle',
        symbolSize: 5,
        smooth: true,
      },
      {
        name: '沪深300',
        type: 'line',
        yAxisIndex: 1,
        data: [],
        lineStyle: { width: 1.2, type: 'dashed', color: alpha.fg2(0.45) },
        symbol: 'none',
        smooth: true,
      },
    ],
    legend: { bottom: 0, textStyle: { fontSize: 10, color: lightTokens.fg2 }, itemWidth: 14, itemHeight: 8 },
  }
}

export function sectorColor(score: number) {
  if (score >= 80) {
    return { bg: 'var(--up-bg)', border: 'var(--up)', text: 'var(--up)', level: '主线', className: 'hot' }
  }
  if (score >= 70) {
    return { bg: 'var(--warn-bg)', border: 'var(--warn)', text: lightTokens.warnDeep, level: '强势', className: 'strong' }
  }
  if (score >= 60) {
    return { bg: 'var(--down-bg)', border: 'var(--down)', text: lightTokens.downDeep, level: '跟随', className: 'follow' }
  }
  if (score >= 50) {
    return { bg: 'var(--accent-dim)', border: 'var(--accent)', text: 'var(--accent)', level: '中性', className: 'neutral' }
  }
  return {
    bg: alpha.muted(0.08),
    border: 'var(--border-2)',
    text: lightTokens.fg2,
    level: '偏弱',
    className: 'weak',
  }
}

export function normalizeSectorName(value?: string) {
  return (value || '').replace(/\s+/g, '').toLowerCase()
}

export function sectorMatches(industry: string, sectorName: string) {
  const normalizedIndustry = normalizeSectorName(industry)
  const normalizedSector = normalizeSectorName(sectorName)
  if (!normalizedIndustry || !normalizedSector) return false
  return normalizedIndustry.includes(normalizedSector) || normalizedSector.includes(normalizedIndustry)
}

export function formatSignedPct(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

export function limitStockRows(payload?: LimitStocksPayload): SectorStockDetail[] {
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

export function limitStockCount(payload: LimitStocksPayload | undefined, key: 'up' | 'down') {
  if (!payload) return 0
  if (Array.isArray(payload)) return key === 'up' ? payload.length : 0
  const explicit = key === 'up' ? payload.up_count : payload.down_count
  if (typeof explicit === 'number' && Number.isFinite(explicit)) return explicit
  const list = key === 'up' ? payload.up_list : payload.down_list
  return Array.isArray(list) ? list.length : 0
}

export function limitStockSource(payload?: LimitStocksPayload) {
  return payload && !Array.isArray(payload) ? payload.data_source : undefined
}

export function sectorStockRows(
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

export function mergeAuctionRows(primary: AuctionIntentItem[], fallback: AuctionIntentItem[]) {
  const seen = new Set<string>()
  return [...primary, ...fallback]
    .filter(item => {
      if (!item.code || seen.has(item.code)) return false
      seen.add(item.code)
      return true
    })
    .slice(0, 10)
}

export function auctionChange(item: AuctionIntentItem) {
  return Number(item.chg_pct ?? item.gap_pct ?? 0)
}

export function auctionScore(item: AuctionIntentItem, fallback: number) {
  const score = Number(item.score)
  return Number.isFinite(score) ? score : fallback
}

export function auctionBucketPct(count: number, total: number) {
  if (!total) return '0%'
  return `${((count / total) * 100).toFixed(1)}%`
}

export function auctionIntentLabel(item: AuctionIntentItem, fallbackScore: number) {
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

// 1.2 竞价意图专属：四维评分 = 竞量比 / 委比 / 涨幅缺口 / 评分
export function auctionDimensionRows(item: AuctionIntentItem): Array<[string, number]> {
  const vr = Math.min(100, Math.abs(Number(item.vol_ratio ?? 0)) * 8)
  const wb = Math.min(100, Math.abs(Number(item.buy_sell_ratio ?? 0)) * 50)
  const gap = Math.min(100, Math.abs(auctionChange(item)) * 8)
  const score = auctionScore(item, 0)
  return [
    ['竞量比', vr],
    ['委比', wb],
    ['涨幅缺口', gap],
    ['综合评分', score],
  ]
}

// 1.2 撮合价走势：9:15-9:25 撮合价演变（缺数据退化为昨收→竞价价线性插值，不空白）
export function buildAuctionTimelineOption(item: AuctionIntentItem): EChartsOption {
  const prev = Number(item.price ?? 0) / (1 + auctionChange(item) / 100) || 0
  const aprice = Number(item.price ?? prev)
  const points = Array.from({ length: 11 }, (_, i) => {
    const t = i / 10
    return [`${9 + Math.floor((15 + i) / 60)}:${String((15 + i) % 60).padStart(2, '0')}`, +(prev + (aprice - prev) * t).toFixed(2)]
  })
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 16, top: 24, bottom: 36 },
    xAxis: { type: 'category', data: points.map(p => p[0]), axisLabel: { fontSize: 9, color: lightTokens.muted, interval: 1 }, axisLine: { lineStyle: { color: lightTokens.border } } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 9, color: lightTokens.fg2 }, splitLine: { lineStyle: { color: lightTokens.border } } },
    series: [{
      type: 'line',
      data: points.map(p => p[1]),
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2.5, color: signalLevelTokens.STRONG_BUY },
      itemStyle: { color: signalLevelTokens.STRONG_BUY },
      areaStyle: { color: alpha.up(0.12) },
    }],
  }
}

// 1.2 四维评分雷达
export function buildAuctionRadarOption(item: AuctionIntentItem): EChartsOption {
  const dims = auctionDimensionRows(item)
  return {
    tooltip: {},
    radar: {
      indicator: dims.map(([label]) => ({ name: label, max: 100 })),
      radius: '62%',
      axisName: { color: lightTokens.fg2, fontSize: 10 },
      splitLine: { lineStyle: { color: lightTokens.border } },
      splitArea: { areaStyle: { color: [alpha.accent(0.04), 'transparent'] } },
      axisLine: { lineStyle: { color: lightTokens.border } },
    },
    series: [{
      type: 'radar',
      data: [{ value: dims.map(([, v]) => Math.round(v)), name: item.name || item.code }],
      areaStyle: { color: alpha.up(0.18) },
      lineStyle: { color: signalLevelTokens.STRONG_BUY, width: 2 },
      itemStyle: { color: signalLevelTokens.STRONG_BUY },
    }],
  }
}

// 1.2 一字定方向：按行业聚合竞价热度（行数/平均分）
export function auctionSectorHeat(rows: AuctionIntentItem[]): Array<{ sector: string; count: number; avgScore: number; change: number }> {
  const map = new Map<string, { count: number; score: number; change: number }>()
  for (const item of rows) {
    const sector = item.industry || '综合'
    const cur = map.get(sector) || { count: 0, score: 0, change: 0 }
    cur.count += 1
    cur.score += auctionScore(item, 0)
    cur.change += auctionChange(item)
    map.set(sector, cur)
  }
  return Array.from(map.entries())
    .map(([sector, agg]) => ({ sector, count: agg.count, avgScore: Math.round(agg.score / agg.count), change: agg.change / agg.count }))
    .sort((a, b) => b.count - a.count || b.avgScore - a.avgScore)
    .slice(0, 8)
}

export function mergeWatchlistRows(primary?: WatchlistItem[]) {
  const seen = new Set<string>()
  const normalizedPrimary = Array.isArray(primary) ? primary : []
  return normalizedPrimary.filter(item => {
    if (!item.code || seen.has(item.code)) return false
    seen.add(item.code)
    return true
  }).slice(0, 12)
}

export function marketCapYi(item: WatchlistItem) {
  const raw = Number(item.market_cap ?? 0)
  if (!Number.isFinite(raw) || raw <= 0) return 0
  return raw > 1_000_000 ? Math.round(raw / 100000000) : Math.round(raw)
}

export function signalTone(signal?: string) {
  if (signal?.includes('强买')) return 't-up'
  if (signal?.includes('买入')) return 't-warn'
  if (signal?.includes('减仓') || signal?.includes('风险')) return 't-down'
  return 't-neu'
}

export function signalDisplay(item: WatchlistItem) {
  if (!item.signal) return '持有'
  if (typeof item.score === 'number' && !item.signal.includes('风险')) return `${item.signal} ${item.score}`
  return item.signal
}

export function watchlistSectorRows(items: WatchlistItem[]) {
  const grouped = items.reduce<Record<string, number>>((acc, item) => {
    const key = item.industry || '其他'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
  return Object.entries(grouped).sort((a, b) => b[1] - a[1])
}

export function levelFromStock(stock: SignalStock): SignalLevelKey {
  const raw = `${stock.signal ?? ''} ${stock.desc ?? ''}`.toLowerCase()
  if (raw.includes('strong') || raw.includes('强买') || raw.includes('强烈')) return 'STRONG_BUY'
  if (raw.includes('sell') || raw.includes('卖出')) return 'SELL'
  if (raw.includes('reduce') || raw.includes('减仓')) return 'REDUCE'
  if (raw.includes('alert') || raw.includes('拐点')) return 'TIMING_ALERT'
  if (raw.includes('buy') || raw.includes('多头') || raw.includes('买入')) return 'BUY'
  return 'HOLD'
}

export function mergeSignalMatrix(signalStocks: SignalStock[]): SignalMatrixItem[] {
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

export function filterSignalMatrix(items: SignalMatrixItem[], filter: string) {
  return items.filter(item => {
    if (filter === 'buy') return ['STRONG_BUY', 'BUY', 'TIMING_ALERT'].includes(item.level)
    if (filter === 'sell') return ['REDUCE', 'SELL'].includes(item.level)
    if (filter === 'alert') return item.level === 'TIMING_ALERT'
    if (filter === 'watchlist') return item.watchlist
    return true
  })
}

export function signalSectorRows(items: SignalMatrixItem[]) {
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

export function buildSectorResonanceRows(
  limitRows: SectorStockDetail[],
  signalItems: SignalMatrixItem[],
  auctionRows: AuctionIntentItem[],
): SectorResonance[] {
  const details: SectorStockDetail[] = [
    ...limitRows,
    ...signalItems.map(item => ({
      code: item.code,
      name: item.name,
      industry: item.industry,
      price: item.price,
      changePct: item.changePct,
      score: item.score,
      signal: item.level,
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
  ].filter(item => item.industry)

  const grouped = details.reduce<Record<string, SectorStockDetail[]>>((acc, item) => {
    acc[item.industry] ||= []
    acc[item.industry].push(item)
    return acc
  }, {})

  return Object.entries(grouped)
    .map(([name, rows]) => {
      const upCount = rows.filter(row => row.changePct > 0).length
      const avgChange = rows.reduce((sum, row) => sum + row.changePct, 0) / Math.max(rows.length, 1)
      const avgScore = rows.reduce((sum, row) => sum + row.score, 0) / Math.max(rows.length, 1)
      return {
        name,
        score: Math.round(Math.max(0, Math.min(100, avgScore || upCount * 10))),
        upRatio: Math.round((upCount / Math.max(rows.length, 1)) * 100),
        change: Number(avgChange.toFixed(2)),
        fund: 0,
      }
    })
    .sort((a, b) => b.score - a.score || b.upRatio - a.upRatio || b.change - a.change)
    .slice(0, 16)
}

export function buildSignalStats(items: SignalMatrixItem[]) {
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

export function buildSignalTrendOption(): EChartsOption {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 50, top: 28, bottom: 42 },
    xAxis: { type: 'category', data: [], axisLabel: { fontSize: 9, color: lightTokens.muted, interval: 4 } },
    yAxis: [
      { type: 'value', name: '信号数', axisLabel: { fontSize: 9, color: lightTokens.fg2 }, splitLine: { lineStyle: { color: lightTokens.border } } },
      { type: 'value', name: '多空比', axisLabel: { fontSize: 9, color: lightTokens.muted }, splitLine: { show: false } },
    ],
    series: [
      { name: '买入信号', type: 'line', data: [], smooth: true, showSymbol: false, lineStyle: { color: lightTokens.up, width: 2 }, itemStyle: { color: lightTokens.up } },
      { name: '卖出信号', type: 'line', data: [], smooth: true, showSymbol: false, lineStyle: { color: lightTokens.down, width: 2 }, itemStyle: { color: lightTokens.down } },
      { name: '多空比', type: 'bar', yAxisIndex: 1, data: [], barWidth: '55%', itemStyle: { color: alpha.accent(0.18) } },
    ],
    legend: { bottom: 0, textStyle: { fontSize: 10, color: lightTokens.fg2 } },
  }
}

export function buildSignalBubbleOption(items: SignalMatrixItem[]): EChartsOption {
  const rows = signalSectorRows(items)
  return {
    tooltip: { trigger: 'item' },
    grid: { left: 60, right: 24, top: 28, bottom: 42 },
    xAxis: { type: 'value', name: '信号数', axisLabel: { fontSize: 9, color: lightTokens.fg2 }, splitLine: { lineStyle: { color: lightTokens.border } } },
    yAxis: { type: 'value', name: '平均评分', min: 20, max: 90, axisLabel: { fontSize: 9, color: lightTokens.fg2 }, splitLine: { lineStyle: { color: lightTokens.border } } },
    series: [{
      type: 'scatter',
      data: rows.map(row => {
        const avg = row.cells.reduce((sum, cell) => sum + cell.score, 0) / row.cells.length
        return {
          name: row.sector,
          value: [row.cells.length, Number(avg.toFixed(1)), row.bullish],
          itemStyle: { color: row.ratio >= 2 ? lightTokens.down : row.ratio >= 1 ? lightTokens.accent : lightTokens.up },
        }
      }),
      symbolSize: (value: unknown) => {
        const arr = Array.isArray(value) ? value : [0, 0, 1]
        return Math.max(20, Math.min(58, Number(arr[2] || 1) * 9))
      },
      label: { show: true, formatter: '{b}', position: 'right', fontSize: 10, color: lightTokens.fg2 },
    }],
  }
}
