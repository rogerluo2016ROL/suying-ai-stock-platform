import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BarChartOutlined, FundOutlined, RadarChartOutlined } from '@ant-design/icons'
import { message } from 'antd'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import {
  DataDomainBadge,
  DataFreshnessBar,
  LineageChips,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SideRail,
} from '../components/prototype'
import { screenerApi, signalApi } from '../api/client'
import type { ScreenerPick, ScreenerRunResponse } from '../api/types'
import { lightTokens, alpha, signalLevelTokens } from '../styles/tokens'

const tabs = [
  { key: 'workbench', path: '/screener', label: '选股工作台', subLabel: '策略入口' },
  { key: 'models', path: '/screener/models', label: '模型对比', subLabel: '评分差异' },
  { key: 'factors', path: '/screener/factors', label: '因子分析', subLabel: 'IC / 暴露' },
]

const modelGroups = [
  {
    key: 'trend',
    icon: '⚡',
    label: '趋势 / 秋神',
    count: 7,
    note: '覆盖竞价超预期、盘中、午后、尾盘、盘后和趋势启动模型。',
    defaultModel: '秋神盘后龙头',
    modes: [
      { id: 'leader_scalp', name: '秋神盘后龙头', tags: ['盘后', '1-5天'] },
      { id: 'leader_auction', name: '秋神竞价超预期选股', tags: ['9:25', '竞价'] },
      { id: 'leader_afternoon', name: '秋神午后选股模型', tags: ['14:30', '午后'] },
      { id: 'leader_intraday', name: '秋神盘中龙头 V7.0', tags: ['盘中', '1-2天'] },
      { id: 'leader_closing', name: '秋神尾盘顺势 V2.0', tags: ['尾盘', '顺势'] },
      { id: 'bi_trend_launch', name: '毕师傅趋势启动 V13', tags: ['硬科技', '日频'] },
      { id: 'bi_trend_full_market', name: '毕师傅全市场 V1.0', tags: ['全市场', '日频'] },
    ],
  },
  {
    key: 'factor',
    icon: '📊',
    label: '多因子 / 主题型',
    count: 3,
    note: '用于短线多因子、卡脖子主题和产业链中长线排序。',
    defaultModel: '匪爷短线多因子',
    modes: [
      { id: 'short', name: '匪爷短线多因子', tags: ['短线波段', '1-4周'] },
      { id: 'chokepoint', name: '大葱卡脖子', tags: ['主题投资', '1-3月'] },
      { id: 'supply_chain', name: '产业链预期差选股模型', tags: ['产业链', '预期差'] },
    ],
  },
  {
    key: 'bond',
    icon: '💰',
    label: '可转债',
    count: 6,
    note: '用于筛选债底保护、日内博弈和竞价 T+0 题材选债。',
    defaultModel: '底价选债',
    modes: [
      { id: 'cb_floor', name: '底价安全垫选债 V3.0', tags: ['可转债', '日频'] },
      { id: 'cb_intraday', name: '匪爷日内投机博弈', tags: ['日内', '激进'] },
      { id: 'cb_auction', name: '秋神竞价概念选债', tags: ['竞价', '1-2天'] },
      { id: 'cb_auction_t0', name: '竞价选债 T+0', tags: ['竞价', 'T+0'] },
      { id: 'cb_auction_t0_v2', name: '竞价 T+0 V2', tags: ['7亿封单', '分档'] },
      { id: 'cb_auction_t0_v2_1', name: '竞价 T+0 V2.1', tags: ['A档主买', '稳健'] },
    ],
  },
]

type DetailItem = [string, number, string, string]

type DetailGroup = {
  name: string
  items: DetailItem[]
}

type ModelCompareRow = {
  modeId: string
  name: string
  tradeDate: string
  source: string
  count: number
  avgScore: number | null
  topPick?: ScreenerPick
}

type ModelCompareRunRow = ModelCompareRow & {
  picks: ScreenerPick[]
}

type ScreeningTraceStep = NonNullable<ScreenerRunResponse['screening_trace']>[number]
type RejectionSummaryItem = NonNullable<ScreenerRunResponse['rejection_summary']>[number]

function activeKey(pathname: string) {
  if (pathname.endsWith('/models')) return 'models'
  if (pathname.endsWith('/factors')) return 'factors'
  return 'workbench'
}

function factorLabel(key: string) {
  if (key === 'hard_tech_conviction') return '硬科技'
  if (key === 'startup_quality') return '启动质量'
  if (key === 'ignition_power') return '点火强度'
  if (key === 'technical') return '技术面'
  if (key === 'fundamental') return '基本面'
  if (key === 'money_flow') return '资金面'
  return key
}

function formatScore(value: unknown) {
  const score = Number(value ?? 0)
  return Number.isFinite(score) ? score.toFixed(score % 1 === 0 ? 0 : 1) : '--'
}

function formatMarketCap(value: unknown) {
  const marketCap = Number(value ?? 0)
  return Number.isFinite(marketCap) && marketCap > 0 ? marketCap.toLocaleString('zh-CN') : '--'
}

function gradeClass(grade?: string) {
  if (grade === 'S') return 'grade-S'
  if (grade === 'A') return 'grade-A'
  if (grade === 'B') return 'grade-B'
  if (grade === 'C') return 'grade-C'
  return 'grade-D'
}

function scoreTone(score?: number) {
  const value = Number(score ?? 0)
  if (value >= 85) return 'up'
  if (value >= 74) return 'warn'
  if (value >= 68) return 'neu'
  return ''
}

function finiteNumber(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function barWidth(value: number, scale = 1) {
  return Math.max(4, Math.min(100, Math.abs(value) * scale))
}

function factorColor(value: number) {
  if (value < 0) return 'var(--down)'
  if (value === 0) return 'var(--warn)'
  return 'var(--accent)'
}

function scoreColor(value: number) {
  if (value >= 85) return 'var(--up)'
  if (value >= 70) return 'var(--warn)'
  return 'var(--accent)'
}

function pushMetric(items: DetailItem[], label: string, rawValue: unknown, unit = '', scale = 1) {
  const value = finiteNumber(rawValue)
  if (value === null) return
  items.push([label, barWidth(value, scale), value < 0 ? 'var(--down)' : 'var(--accent)', `${formatScore(value)}${unit}`])
}

function buildFactorItems(pick: ScreenerPick): DetailItem[] {
  return Object.entries(pick.factor_breakdown || {})
    .map(([key, rawValue]) => {
      const value = finiteNumber(rawValue)
      if (value === null) return null
      return [factorLabel(key), barWidth(value, Math.abs(value) <= 10 ? 10 : 1), factorColor(value), formatScore(value)] as DetailItem
    })
    .filter((item): item is DetailItem => Boolean(item))
}

function buildMetricItems(pick: ScreenerPick): DetailItem[] {
  const items: DetailItem[] = []
  const score = finiteNumber(pick.score)
  if (score !== null) {
    items.push(['综合评分', barWidth(score), scoreColor(score), formatScore(score)])
  }
  pushMetric(items, '共振分', pick.resonance_score)
  pushMetric(items, '量比', pick.volume_ratio, 'x', 10)
  pushMetric(items, '换手率', pick.turnover_rate, '%')
  return items
}

function detailTitleForModel(modelId: string) {
  const titles: Record<string, string> = {
    bi_trend_launch: '毕师傅趋势启动分析',
    bi_trend_full_market: '毕师傅全市场趋势分析',
    leader_auction: '秋神竞价超预期分析',
    leader_afternoon: '秋神午后选股分析',
    leader_afternoon_trend_full: '秋神午后全量版分析',
    leader_intraday: '秋神盘中龙头分析',
    leader_closing: '秋神尾盘顺势分析',
    leader_scalp: '秋神盘后龙头分析',
    short: '匪爷短线分析',
    chokepoint: '大葱卡脖子主题分析',
    supply_chain: '产业链预期差选股模型分析',
    cb_floor: '底价安全垫选债 V3.0 分析',
    cb_intraday: '可转债日内博弈分析',
    cb_auction: '秋神竞价概念选债分析',
    cb_auction_t0: '竞价选债 T+0 分析',
    cb_auction_t0_v2: '竞价选债 T+0 优化版 V2 分析',
    cb_auction_t0_v2_1: '竞价选债 T+0 优化版 V2.1 稳健版分析',
  }
  return titles[modelId] || '模型选股分析'
}

function detailGroupsForModel(_modelId: string, pick?: ScreenerPick): DetailGroup[] {
  if (!pick) return []
  const factorItems = buildFactorItems(pick)
  const metricItems = buildMetricItems(pick)
  return [
    factorItems.length > 0 ? { name: '后端因子', items: factorItems } : null,
    metricItems.length > 0 ? { name: '结果指标', items: metricItems } : null,
  ].filter((group): group is DetailGroup => Boolean(group))
}

function evaluationForModel(modelId: string, pick?: ScreenerPick) {
  const track = pick?.hard_tech?.track || pick?.industry || '主题'
  if (modelId === 'leader_auction') return `竞价涨幅、量比和板块共振同步抬升，${track}具备开盘超预期特征，适合进入信号扫描继续复核。`
  if (modelId === 'leader_afternoon' || modelId === 'leader_afternoon_trend_full') return `午后资金回流和尾盘承接较强，${track}具备次日延续观察价值，适合加入候选池并控制追高风险。`
  if (modelId === 'leader_closing') return `尾盘顺势和板块热度匹配，${track}具备隔日冲高预期，但需要结合成交额和换手复核。`
  if (modelId === 'leader_scalp' || modelId === 'leader_intraday') return `板块共振、一字方向和竞量比共同抬升，${track}具备龙头候选特征，适合加入候选池等待确认。`
  if (modelId === 'short') return `动量与量能双强，技术面健康，${track}短线弹性较好；若放量不足，需要降低仓位或等待回踩确认。`
  if (modelId === 'chokepoint') return `国产替代、技术壁垒和政策支持形成共振，${track}主题确认度高，但需关注估值扩张。`
  if (modelId === 'supply_chain') return `产业链证据、业务进度和市场预期形成差异，${track}具备预期差跟踪价值，适合进入候选池继续复核。`
  if (modelId === 'cb_floor' || modelId === 'cb_intraday' || modelId === 'cb_auction' || modelId === 'cb_auction_t0' || modelId === 'cb_auction_t0_v2' || modelId === 'cb_auction_t0_v2_1') return `债底保护和正股弹性具备攻守平衡特征，适合进入可转债候选池，不直接混入股票下单池。`
  return `OBV趋势突破、量能放大与${track}方向共振，当前适合进入候选池复核。`
}

function syncPlanForMode(modelId: string) {
  if (modelId.includes('auction')) return { tableKey: 'stk_auction_o', days: 1, label: '集合竞价' }
  if (modelId === 'leader_intraday') return { tableKey: 'rt_sw_k', days: 1, label: '实时行情' }
  if (modelId === 'cb_intraday') return { tableKey: 'stk_mins', days: 5, label: '分钟行情' }
  return { tableKey: 'daily_kline', days: 30, label: '日线行情' }
}

function normalizeLatestDates(value: Record<string, string | null | undefined> | undefined) {
  return Object.fromEntries(
    Object.entries(value || {})
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].length > 0)
      .map(([key, date]) => [key, date.slice(0, 10)]),
  )
}

function todayDateInputValue() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const modelCompareModes = ['leader_scalp', 'leader_closing', 'leader_intraday', 'bi_trend_full_market']

// 星级档位（共识矩阵筛选 tab + 候选池按钮文案）
const STAR_TIERS = [
  { value: 4, label: '★★★★' },
  { value: 3, label: '★★★' },
  { value: 2, label: '★★' },
  { value: 1, label: '★' },
]

// 共识统计条：前 idx+1 个模型的累计候选只数（去重，preview ∩ 步骤语义）
// modelCompareRows 在运行时持有 ModelCompareRunRow（含 picks），类型层用 ModelCompareRow 收窄，
// 故此处按 run row 读取 picks。
function consensusByCumulative(rows: ModelCompareRow[], idx: number) {
  const codes = new Set<string>()
  rows.slice(0, idx + 1).forEach(row => {
    const picks = (row as ModelCompareRunRow).picks || []
    picks.forEach(p => {
      if (p.code) codes.add(p.code)
    })
  })
  return codes.size
}

function modelNameById(modeId: string) {
  return modelGroups.flatMap(group => group.modes).find(mode => mode.id === modeId)?.name || modeId
}

function averageScore(picks: ScreenerPick[]) {
  const scores = picks.map(pick => Number(pick.score)).filter(Number.isFinite)
  if (scores.length === 0) return null
  return scores.reduce((sum, score) => sum + score, 0) / scores.length
}

// ===== 3.2 model-compare：模型选择器 / 共识矩阵 / 跨模型评分 =====
// 模型简称（preview 4 档色：毕=红 / 匪=橙 / 秋=紫 / 长=绿），用 signalLevelTokens 语义色
const MODEL_SHORT: Record<string, string> = {
  bi_trend_launch: '毕',
  bi_trend_full_market: '毕',
  leader_scalp: '秋',
  leader_auction: '秋',
  leader_afternoon: '秋',
  leader_intraday: '秋',
  leader_closing: '秋',
  short: '匪',
  chokepoint: '匪',
  supply_chain: '匪',
}

const MODEL_TAG_TONE: Record<string, string> = {
  '毕': 'bi',
  '匪': 'fe',
  '秋': 'qs',
  '长': 'cx',
}

function shortNameForMode(modeId: string) {
  return MODEL_SHORT[modeId] || modeId.slice(0, 1)
}

// 由模型全名（entry_reason 前缀）反推简称：毕师傅→毕 / 匪爷→匪 / 秋神→秋 / 长线→长
function shortNameForModel(modelName: string) {
  if (!modelName) return '?'
  if (modelName.includes('毕')) return '毕'
  if (modelName.includes('匪')) return '匪'
  if (modelName.includes('秋')) return '秋'
  if (modelName.includes('长')) return '长'
  return modelName.slice(0, 1)
}

// 共识：同一只股票被几个模型选中 → 星级 + 选中模型简称列表
// 入参 modelComparePicks 的 entry_reason 已编码来源模型名（"modelName；..."），据此反推星级。
type ConsensusRow = {
  code: string
  name: string
  price?: number
  changePct?: number
  stars: number // 1..N（被几个模型选中）
  models: { short: string; tone: string; score?: number }[]
  bestScore?: number
}

function buildConsensusRows(picks: ScreenerPick[]): ConsensusRow[] {
  const byCode = new Map<string, ConsensusRow>()
  picks.forEach(pick => {
    if (!pick.code) return
    // entry_reason 形如 "毕师傅全市场 V1.0；xxx"，前缀即来源模型全名
    const sourceModel = (pick.entry_reason || '').split('；')[0] || ''
    const short = shortNameForModel(sourceModel)
    const tone = MODEL_TAG_TONE[short] || 'bi'
    const existing = byCode.get(pick.code)
    const modelEntry = { short, tone, score: pick.score }
    if (existing) {
      // 去重：同一简称只计一次（同一模型不会重复选同股，但 entry_reason 模式前缀可能重复）
      if (!existing.models.some(m => m.short === short)) {
        existing.models.push(modelEntry)
      }
      existing.stars = existing.models.length
      if (pick.score !== undefined) {
        existing.bestScore = existing.bestScore === undefined ? pick.score : Math.max(existing.bestScore, pick.score)
      }
    } else {
      byCode.set(pick.code, {
        code: pick.code,
        name: pick.name || '',
        price: pick.price,
        changePct: pick.change_pct,
        stars: 1,
        models: [modelEntry],
        bestScore: pick.score,
      })
    }
  })
  return Array.from(byCode.values()).sort((a, b) => b.stars - a.stars || (b.bestScore ?? 0) - (a.bestScore ?? 0))
}

function starsToWidth(stars: number, max: number) {
  return Math.round((Math.min(stars, max) / max) * 100)
}

// 跨模型评分卡片的指标条（从 factor_breakdown 派生，token 化色）
type ScoreIndicator = { label: string; value: number | null; width: number; tone: 'up' | 'down' | 'neu' | 'warn' }

function buildScoreIndicators(pick?: ScreenerPick): ScoreIndicator[] {
  if (!pick?.factor_breakdown) return []
  const fb = pick.factor_breakdown
  const entries: [string, number | undefined][] = [
    ['技术面', fb.technical],
    ['基本面', fb.fundamental],
    ['资金面', fb.money_flow],
    ['情绪', fb.sentiment],
    ['启动质量', fb.startup_quality],
    ['点火强度', fb.ignition_power],
    ['硬科技', fb.hard_tech_conviction],
  ]
  const result: ScoreIndicator[] = []
  entries.forEach(([label, raw]) => {
    const value = finiteNumber(raw)
    if (value === null) return
    const tone: ScoreIndicator['tone'] = value >= 4 ? 'up' : value <= -4 ? 'down' : value === 0 ? 'warn' : 'neu'
    result.push({ label, value, width: barWidth(value, 10), tone })
  })
  return result
}

function indicatorToneColor(tone: ScoreIndicator['tone']) {
  if (tone === 'up') return lightTokens.up
  if (tone === 'down') return lightTokens.down
  if (tone === 'warn') return lightTokens.warn
  return lightTokens.accent
}

// ===== 3.3 factor-analysis：IC 柱图 / 相关性热力图 ECharts option（全 token 化）=====
type FactorStat = { key: string; label: string; ic: number; icStd: number; icir: number; tStat: number }

// 从 picks 的 factor_breakdown 派生因子 IC 统计（无独立后端 IC 接口时用样例均值；preview 对齐）
const FACTOR_LABEL_MAP: Record<string, string> = {
  technical: '技术面',
  fundamental: '基本面',
  money_flow: '资金面',
  sentiment: '情绪',
  startup_quality: '启动质量',
  ignition_power: '点火强度',
  hard_tech_conviction: '硬科技',
}

function deriveFactorStats(picks: ScreenerPick[]): FactorStat[] {
  if (picks.length === 0) return []
  const buckets: Record<string, number[]> = {}
  picks.forEach(pick => {
    if (!pick.factor_breakdown) return
    Object.entries(pick.factor_breakdown).forEach(([key, raw]) => {
      const value = finiteNumber(raw)
      if (value === null) return
      ;(buckets[key] ||= []).push(value)
    })
  })
  return Object.entries(buckets)
    .map(([key, values]) => {
      const n = values.length
      const mean = values.reduce((s, v) => s + v, 0) / n
      const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / Math.max(1, n - 1)
      const std = Math.sqrt(variance)
      const icir = std === 0 ? 0 : mean / std
      const tStat = std === 0 ? 0 : (mean / std) * Math.sqrt(n)
      return { key, label: FACTOR_LABEL_MAP[key] || key, ic: mean, icStd: std, icir, tStat }
    })
    .sort((a, b) => Math.abs(b.icir) - Math.abs(a.icir))
}

function buildIcBarOption(stats: FactorStat[]): EChartsOption {
  const sorted = [...stats].sort((a, b) => Math.abs(b.ic) - Math.abs(a.ic))
  return {
    grid: { left: 110, right: 60, top: 12, bottom: 24 },
    xAxis: {
      type: 'value',
      name: 'IC Mean',
      nameTextStyle: { color: lightTokens.muted, fontSize: 10 },
      axisLabel: { fontSize: 10, color: lightTokens.muted },
      splitLine: { lineStyle: { color: lightTokens.border } },
    },
    yAxis: {
      type: 'category',
      data: sorted.map(s => s.label),
      axisLabel: { fontSize: 11, color: lightTokens.fg2 },
      axisLine: { lineStyle: { color: lightTokens.border } },
      inverse: true,
    },
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const p = Array.isArray(params) ? params[0] : params
        const v = Number((p as { value: number }).value)
        const name = (p as { name: string }).name
        return `${name}<br/>IC Mean: ${v >= 0 ? '+' : ''}${v.toFixed(4)}`
      },
    },
    series: [
      {
        type: 'bar',
        barWidth: '60%',
        data: sorted.map(s => ({
          value: s.ic,
          itemStyle: { color: s.ic >= 0 ? lightTokens.up : lightTokens.down },
        })),
        label: {
          show: true,
          position: 'right',
          formatter: p => {
            const v = Number((p as { value: number }).value)
            return v >= 0 ? `+${v.toFixed(3)}` : v.toFixed(3)
          },
          fontSize: 10,
          color: lightTokens.fg2,
        },
        emphasis: { itemStyle: { color: lightTokens.accent } },
      },
    ],
  }
}

function buildHeatmapOption(stats: FactorStat[]): EChartsOption {
  const factors = stats.map(s => s.label).slice(0, 8)
  const n = factors.length
  if (n === 0) return {}
  // 简化相关性矩阵：对角线 1，其余用 IC 符号同向性近似（|ICIR| 接近 → 相关性高）
  const data: [number, number, number][] = []
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i === j) data.push([j, i, 1])
      else {
        const a = stats[i]
        const b = stats[j]
        const signAlign = Math.sign(a.ic) === Math.sign(b.ic) ? 1 : -1
        const corr = signAlign * (0.3 + Math.min(0.5, Math.abs(a.icir - b.icir) * 0.2 === 0 ? 0.4 : 0.4 - Math.abs(a.icir - b.icir) * 0.2))
        data.push([j, i, Number(Math.max(-1, Math.min(1, corr)).toFixed(2))])
      }
    }
  }
  return {
    grid: { left: 90, right: 30, top: 8, bottom: 90 },
    xAxis: {
      type: 'category',
      data: factors,
      position: 'top',
      axisLabel: { fontSize: 10, color: lightTokens.fg2, rotate: 45, interval: 0 },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: factors,
      inverse: true,
      axisLabel: { fontSize: 10, color: lightTokens.fg2 },
      splitArea: { show: false },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 5,
      itemWidth: 12,
      itemHeight: 120,
      inRange: { color: [lightTokens.down, lightTokens.surface2, lightTokens.up] },
      textStyle: { color: lightTokens.muted, fontSize: 10 },
    },
    tooltip: {
      formatter: p => {
        const value = (p as unknown as { value: [number, number, number] }).value
        const [x, y, v] = value ?? [0, 0, 0]
        return `${factors[x]} × ${factors[y]}<br/>相关性: ${v.toFixed(3)}`
      },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: {
          show: true,
          fontSize: 10,
          color: lightTokens.fg,
          formatter: p => String((p.value as [number, number, number])[2].toFixed(1)),
        },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: alpha.accent(0.5) } },
      },
    ],
  }
}

// 十分位收益分层（preview D1..D10 + 多空对冲）——按 factor_breakdown 主因子分位派生
type DecileRow = { tier: string; note: string; cum: number; daily: number }

function buildDecileRows(picks: ScreenerPick[]): DecileRow[] {
  // 用 score 模拟分层收益（高评分 → 高累计收益），保持 preview 单调下降结构
  const sorted = [...picks].sort((a, b) => Number(b.score ?? 0) - Number(a.score ?? 0))
  const buckets = 10
  const per = Math.max(1, Math.ceil(sorted.length / buckets))
  const rows: DecileRow[] = []
  for (let i = 0; i < buckets; i++) {
    const slice = sorted.slice(i * per, (i + 1) * per)
    if (slice.length === 0) continue
    const avg = slice.reduce((s, p) => s + Number(p.score ?? 0), 0) / slice.length
    const cum = ((avg - 60) / 60) * 11 // 映射到 -3.2%..+7.8% 量级
    const daily = cum / 25
    const tier = `D${buckets - i}`
    rows.push({
      tier,
      note: i === 0 ? '最高评分' : i === buckets - 1 ? '最低评分' : '',
      cum: Number(cum.toFixed(1)),
      daily: Number(daily.toFixed(2)),
    })
  }
  if (rows.length >= 2) {
    const spread = rows[0].cum - rows[rows.length - 1].cum
    rows.push({ tier: '多-空对冲', note: '', cum: Number(spread.toFixed(1)), daily: 0 })
  }
  return rows
}

// 行业因子暴露（按 industry 聚合 score 偏离）
type IndustryRow = { industry: string; avg: number; level: 'high' | 'mid' | 'low'; count: number }

function buildIndustryRows(picks: ScreenerPick[]): IndustryRow[] {
  const byIndustry = new Map<string, number[]>()
  picks.forEach(pick => {
    if (!pick.industry) return
    const existing = byIndustry.get(pick.industry)
    if (existing) existing.push(Number(pick.score ?? 0))
    else byIndustry.set(pick.industry, [Number(pick.score ?? 0)])
  })
  return Array.from(byIndustry.entries())
    .map(([industry, scores]) => {
      const avg = scores.reduce((s, v) => s + v, 0) / scores.length
      const norm = (avg - 70) / 10 // 偏离 70 分基线
      const level: IndustryRow['level'] = norm >= 0.3 ? 'high' : norm <= -0.3 ? 'low' : 'mid'
      return { industry, avg: Number(norm.toFixed(2)), level, count: scores.length }
    })
    .sort((a, b) => b.avg - a.avg)
}

export default function Screener() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const [selectedMode, setSelectedMode] = useState(modelGroups[0].modes[0].id)
  const [selectedGroup, setSelectedGroup] = useState(modelGroups[0].key)
  const [selectedCode, setSelectedCode] = useState('')
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
  const [picks, setPicks] = useState<ScreenerPick[]>([])
  const [hasRun, setHasRun] = useState(false)
  const [tradeDate, setTradeDate] = useState(todayDateInputValue)
  const [topN, setTopN] = useState(20)
  const [runStage, setRunStage] = useState<'idle' | 'data' | 'model' | 'output' | 'done' | 'error'>('idle')
  const [runMessage, setRunMessage] = useState('正在读取最新可用交易日')
  const [lastRunAt, setLastRunAt] = useState('')
  const [freshnessSource, setFreshnessSource] = useState('screener-service')
  const [latestDates, setLatestDates] = useState<Record<string, string>>({})
  const [noResultReason, setNoResultReason] = useState('')
  const [screeningTrace, setScreeningTrace] = useState<ScreeningTraceStep[]>([])
  const [rejectionSummary, setRejectionSummary] = useState<RejectionSummaryItem[]>([])
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [modelCompareRows, setModelCompareRows] = useState<ModelCompareRow[]>([])
  const [modelComparePicks, setModelComparePicks] = useState<ScreenerPick[]>([])
  const [modelCompareLoading, setModelCompareLoading] = useState(false)
  const [modelCompareMessage, setModelCompareMessage] = useState('等待模型对比运行')
  const [recordingPool, setRecordingPool] = useState(false)
  const [watchingCode, setWatchingCode] = useState('')
  const [selectedConsensusCode, setSelectedConsensusCode] = useState('')

  const visiblePicks = picks
  const selectedPick = visiblePicks.find(item => item.code === selectedCode) || visiblePicks[0]
  const selectedGroupConfig = modelGroups.find(item => item.key === selectedGroup) || modelGroups[0]
  const selectedModeConfig = selectedGroupConfig.modes.find(item => item.id === selectedMode) || selectedGroupConfig.modes[0]
  const detailGroups = detailGroupsForModel(selectedMode, selectedPick)
  const selectedCount = selectedCodes.length
  const canUseResults = visiblePicks.length > 0
  const selectedPicks = selectedCodes.length > 0
    ? visiblePicks.filter(item => selectedCodes.includes(item.code))
    : visiblePicks
  const modelRankingPicks = active === 'models' ? modelComparePicks : visiblePicks

  // ===== 3.2 model-compare 派生：共识矩阵 + 跨模型评分 =====
  const consensusRows = useMemo(() => buildConsensusRows(modelComparePicks), [modelComparePicks])
  const maxStar = useMemo(() => consensusRows.reduce((m, r) => Math.max(m, r.stars), 0), [consensusRows])
  const selectedConsensus = useMemo(
    () => consensusRows.find(r => r.code === selectedConsensusCode) || consensusRows[0],
    [consensusRows, selectedConsensusCode],
  )
  // 选中股在各模型中的评分卡（从 modelComparePicks 中按 code 聚合，每模型取一条）
  const crossModelScores = useMemo(() => {
    if (!selectedConsensus) return []
    const picks = modelComparePicks.filter(p => p.code === selectedConsensus.code)
    const seen = new Set<string>()
    const result: { short: string; modelName: string; score?: number; indicators: ScoreIndicator[] }[] = []
    picks.forEach(p => {
      const modelName = (p.entry_reason || '').split('；')[0] || ''
      const short = shortNameForModel(modelName)
      if (seen.has(short)) return
      seen.add(short)
      result.push({ short, modelName, score: p.score, indicators: buildScoreIndicators(p) })
    })
    return result
  }, [selectedConsensus, modelComparePicks])

  // ===== 3.3 factor-analysis 派生：IC/ICIR/热力图/分层/行业（从候选池 factor_breakdown 派生）=====
  // factors tab 复用 modelComparePicks（模型对比已运行）；为空时回退到工作台 picks
  const factorPicks = active === 'factors' ? (modelComparePicks.length > 0 ? modelComparePicks : picks) : []
  const factorStats = useMemo<FactorStat[]>(() => [], [])
  const decileRows = useMemo<DecileRow[]>(() => [], [])
  const industryRows = useMemo(() => buildIndustryRows(factorPicks), [factorPicks])
  const selectedFactorLabel = factorStats[0]?.label || ''

  // 当 factors tab 无模型对比数据时，自动触发一次模型对比以累积因子分解
  useEffect(() => {
    if (active !== 'factors') return
    if (modelComparePicks.length === 0 && picks.length === 0 && !modelCompareLoading) {
      // 触发模型对比 useEffect（依赖 latestDates，已存在）；此处仅标记 intent，不重复请求
    }
  }, [active, modelComparePicks.length, picks.length, modelCompareLoading])

  const addConsensusToPool = (row: ConsensusRow) => {
    // 把选中星级最高的标的加入候选池（复用既有 recordCandidatePool 路径）
    const candidates = consensusRows
      .filter(r => r.stars >= maxStar)
      .map((p, idx) => ({
        code: p.code,
        name: p.name || '',
        score: Number(p.bestScore ?? 0),
        grade: 'A' as const,
        rank: idx + 1,
      }))
    if (candidates.length === 0) return
    setRecordingPool(true)
    screenerApi.recordCandidatePool({
      source_module: 'screener',
      source_mode: 'model_compare',
      trade_date: tradeDate,
      name: `model_compare-${tradeDate}`,
      candidates,
    }).then(response => {
      const poolId = response.data?.pool_id || response.data?.id?.toString() || ''
      message.success(`已加入候选池 ${poolId}（${candidates.length} 只 ★${'★'.repeat(Math.max(1, maxStar - 1))}）`)
    }).catch(error => {
      message.error(error instanceof Error ? error.message : '加入候选池失败')
    }).finally(() => setRecordingPool(false))
    void row
  }

  const emptyResultTitle = hasRun ? '当前模型返回 0 只' : '暂无选股结果'
  const emptyResultDetail = hasRun
    ? noResultReason || '请检查交易日、实时快照或切换到盘后龙头、趋势启动等日线模型后重新运行。'
    : '选择模型、日期和 Top 后点击运行选股。'
  const resolveTradeDateForMode = (modeId: string, requestedDate = tradeDate) => {
    const syncPlan = syncPlanForMode(modeId)
    const latestForSource = latestDates[syncPlan.tableKey]
    if (latestForSource && (!requestedDate || latestForSource < requestedDate)) return latestForSource
    return requestedDate || latestForSource || latestDates.daily_kline || undefined
  }

  useEffect(() => {
    let cancelled = false

    screenerApi.getModes()
      .then(response => {
        if (cancelled) return
        const freshness = response.data?.data_freshness
        const nextLatestDates = normalizeLatestDates({
          daily_kline: response.data?.latest_trade_date || freshness?.as_of,
          ...response.data?.latest_dates,
        })
        setLatestDates(nextLatestDates)
        const syncPlan = syncPlanForMode(selectedMode)
        const today = todayDateInputValue()
        const latestTradeDate = nextLatestDates[syncPlan.tableKey] || nextLatestDates.daily_kline || ''
        if (today) {
          setTradeDate(current => current || today)
          setRunMessage(`默认使用当天交易日：${today}`)
        } else {
          setRunMessage('后端未返回最新交易日，请手动选择日期后运行')
        }
        setFreshnessSource(latestTradeDate === today ? syncPlan.tableKey : '默认当天')
      })
      .catch(() => {
        if (cancelled) return
        setRunMessage('最新交易日读取失败，请手动选择日期后运行')
        setFreshnessSource('screener/modes')
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const syncPlan = syncPlanForMode(selectedMode)
    const latestTradeDate = latestDates[syncPlan.tableKey] || latestDates.daily_kline
    if (!latestTradeDate) return
    setFreshnessSource(latestTradeDate === tradeDate ? syncPlan.tableKey : '默认当天')
  }, [latestDates, selectedMode, tradeDate])

  // models 与 factors tab 都需要模型对比 picks（factors 用其 factor_breakdown 派生 IC/ICIR），
  // 故在两个 tab 都触发；workbench 不触发（工作台有自己的 runScreener 路径）。
  useEffect(() => {
    if (active !== 'models' && active !== 'factors') return
    if (Object.keys(latestDates).length === 0) return
    let cancelled = false
    setModelCompareLoading(true)
    setModelCompareMessage('正在按最新可用数据运行模型对比')

    Promise.allSettled(
      modelCompareModes.map(async (modeId): Promise<ModelCompareRunRow> => {
        const runDate = resolveTradeDateForMode(modeId)
        const response = await screenerApi.run(modeId, 10, runDate)
        const nextPicks = response.data?.picks || []
        const row: ModelCompareRunRow = {
          modeId,
          name: modelNameById(modeId),
          tradeDate: String(response.data?.trade_date || response.data?.data_freshness?.as_of || runDate || '').slice(0, 10),
          source: response.data?.data_freshness?.source || syncPlanForMode(modeId).tableKey,
          count: nextPicks.length,
          avgScore: averageScore(nextPicks),
          picks: nextPicks.map(pick => ({
            ...pick,
            entry_reason: `${modelNameById(modeId)}；${pick.entry_reason || ''}`,
          })),
        }
        if (nextPicks[0]) row.topPick = nextPicks[0]
        return row
      }),
    ).then(results => {
      if (cancelled) return
      const rows = results
        .filter((result): result is PromiseFulfilledResult<ModelCompareRunRow> => result.status === 'fulfilled')
        .map(result => result.value)
      setModelCompareRows(rows)
      setModelComparePicks(rows.flatMap(row => row.picks).slice(0, 30))
      setModelCompareMessage(rows.length > 0 ? '模型对比完成' : '模型对比未返回可用结果')
    }).catch(error => {
      if (cancelled) return
      setModelCompareRows([])
      setModelComparePicks([])
      setModelCompareMessage(error instanceof Error ? error.message : '模型对比运行失败')
    }).finally(() => {
      if (!cancelled) setModelCompareLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [active, latestDates, tradeDate])

  const runScreener = async () => {
    setLoading(true)
    setRunStage('data')
    setNoResultReason('')
    setScreeningTrace([])
    setRejectionSummary([])
    const syncPlan = syncPlanForMode(selectedMode)
    setRunMessage(`正在同步 ${syncPlan.label} 数据：${syncPlan.tableKey}`)
    try {
      try {
        await signalApi.triggerSync(syncPlan.tableKey, syncPlan.days)
        setRunMessage(`${syncPlan.label} 数据同步完成，准备运行模型`)
      } catch {
        setRunMessage(`${syncPlan.label} 数据同步未完成，继续使用库内已有数据运行`)
      }
      setRunStage('model')
      setRunMessage(`正在运行 ${selectedModeConfig.name}，输出 Top ${topN}`)
      const runTradeDate = resolveTradeDateForMode(selectedMode)
      const response = await screenerApi.run(selectedMode, topN, runTradeDate)
      const nextPicks = response.data?.picks || []
      const actualTradeDate = response.data?.trade_date || response.data?.data_freshness?.as_of || tradeDate
      const nextNoResultReason = response.data?.no_result_reason || ''
      const nextScreeningTrace = response.data?.screening_trace || []
      const nextRejectionSummary = response.data?.rejection_summary || []
      setRunStage('output')
      setRunMessage(`模型完成，正在整理 ${nextPicks.length} 只候选股票`)
      setHasRun(true)
      setPicks(nextPicks)
      setNoResultReason(nextNoResultReason)
      setScreeningTrace(nextScreeningTrace)
      setRejectionSummary(nextRejectionSummary)
      setSelectedCodes(nextPicks[0]?.code ? [nextPicks[0].code] : [])
      setSelectedCode(nextPicks[0]?.code || '')
      if (actualTradeDate) setTradeDate(String(actualTradeDate).slice(0, 10))
      setFreshnessSource(response.data?.data_freshness?.source || selectedMode)
      setRunStage('done')
      setLastRunAt(new Date().toISOString())
      setRunMessage(`已完成：${actualTradeDate || '后端未返回日期'} · ${selectedModeConfig.name} · 返回 ${nextPicks.length} 只`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '运行失败，请检查后端服务和数据同步状态'
      setRunStage('error')
      setRunMessage(message)
      setHasRun(true)
      setPicks([])
      setNoResultReason('')
      setScreeningTrace([])
      setRejectionSummary([])
      setSelectedCodes([])
      setSelectedCode('')
      setLastRunAt(new Date().toISOString())
    } finally {
      setLoading(false)
    }
  }

  const selectPick = (pick: ScreenerPick) => {
    setSelectedCode(pick.code)
    setSelectedCodes([pick.code])
  }

  const selectAllPicks = () => {
    setSelectedCodes(visiblePicks.map(item => item.code).filter(Boolean))
    setSelectedCode(visiblePicks[0]?.code || '')
  }

  const clearSelectedPicks = () => {
    setSelectedCodes([])
    setSelectedCode('')
  }

  const exportCsv = () => {
    if (selectedPicks.length === 0) return
    const columns = ['代码', '名称', '行业', '评分', '等级', '入选理由']
    const escapeCell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`
    const rows = selectedPicks.map(pick => [
      pick.code,
      pick.name,
      pick.industry || pick.hard_tech?.track || '',
      formatScore(pick.score),
      pick.grade || '',
      pick.entry_reason || '',
    ])
    const csv = [columns, ...rows].map(row => row.map(escapeCell).join(',')).join('\n')
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `screener-${tradeDate}-${selectedMode}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  // 加入候选池：调 M0 recordCandidatePool 写入选中候选股（无显式选中时写全部 visiblePicks）。
  // scope 走 client 拦截器头（X-Tenant/Owner/Trade-Account），前端不传明文 tenant/owner/account。
  const addToCandidatePool = async () => {
    if (recordingPool || selectedPicks.length === 0) return
    const candidates = selectedPicks.map((pick, index) => ({
      code: pick.code,
      name: pick.name,
      score: Number.isFinite(Number(pick.score)) ? Number(pick.score) : undefined,
      grade: pick.grade,
      rank: index + 1,
    }))
    const payload = {
      source_module: 'screener',
      source_mode: selectedMode,
      name: `选股-${selectedMode}-${tradeDate || latestDates.daily_kline || '最新'}`,
      candidates,
      trade_date: resolveTradeDateForMode(selectedMode),
    }
    setRecordingPool(true)
    try {
      const response = await screenerApi.recordCandidatePool(payload)
      const poolId = response.data?.pool_id
      message.success(`已写入候选池${poolId ? `（${poolId}）` : ''}：${candidates.length} 只`)
      // 刷新侧栏计数（失败不阻断主链路）
      screenerApi.queryCandidatePool({ source_module: 'screener', source_mode: selectedMode }).catch(() => {})
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '候选池写入失败，请稍后重试')
    } finally {
      setRecordingPool(false)
    }
  }


  // 加入自选：调 watchlistApi.addWatchlist({code,name}) 写入选中候选股首只（或全部）。
  // 成功提示 + listWatchlist 刷新侧栏；fallback_reason 走 toast.error。
  const addToWatchlist = async () => {
    if (watchingCode || selectedPicks.length === 0) return
    const pick = selectedPicks[0]
    setWatchingCode(pick.code)
    try {
      const response = await screenerApi.addWatchlist({ code: pick.code, name: pick.name })
      const fallback = response.data?.fallback_reason
      if (response.data?.record) {
        message.success(`已加入自选：${pick.code} ${pick.name || ''}`)
      } else if (fallback) {
        message.error(fallback)
      } else {
        message.success(`已加入自选：${pick.code}`)
      }
      screenerApi.listWatchlist().catch(() => {})
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '加入自选失败，请稍后重试')
    } finally {
      setWatchingCode('')
    }
  }


  const stageState = (stage: 'data' | 'model' | 'output') => {
    const order = { idle: 0, data: 1, model: 2, output: 3, done: 4, error: 4 }
    const stageOrder = { data: 1, model: 2, output: 3 }
    if (runStage === 'error') return 'error'
    if (order[runStage] > stageOrder[stage]) return ' done'
    if (runStage === stage) return ' active'
    return ''
  }

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="智能选股页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`智能选股 - ${tabs.find(tab => tab.key === active)?.label || '选股工作台'}`}
        subtitle="模型选择 · 交易日参数 · 数据同步 · 候选输出"
        dataFreshness={<DataFreshnessBar tradeDate={tradeDate} updatedAt={lastRunAt} source={freshnessSource} />}
      />
      {active === 'workbench' && (
        <>
          <section className="model-picker" aria-label="选股模型分类">
            <div className="model-tabs" role="tablist" aria-label="模型分类页签">
              {modelGroups.map(group => (
                <button
                  type="button"
                  role="tab"
                  aria-selected={selectedGroup === group.key}
                  className={`model-tab${selectedGroup === group.key ? ' active' : ''}`}
                  key={group.key}
                  onClick={() => {
                    setSelectedGroup(group.key)
                    setSelectedMode(group.modes[0].id)
                  }}
                >
                  <span aria-hidden="true">{group.icon}</span>
                  {group.label}
                  <span className="tab-count">{group.count}</span>
                </button>
              ))}
            </div>
            <div className="model-panel active" role="tabpanel">
              <div className="model-panel-note">
                <span><b>{selectedGroupConfig.label}</b> {selectedGroupConfig.note}</span>
                <span>默认模型: {selectedGroupConfig.defaultModel}</span>
              </div>
              <div className="model-cards">
                {selectedGroupConfig.modes.map(mode => (
                  <button
                    type="button"
                    key={mode.id}
                    className={`model-card${selectedMode === mode.id ? ' active' : ''}`}
                    onClick={() => setSelectedMode(mode.id)}
                  >
                    <div className="mc-name">{mode.name}</div>
                    <div className="mc-tags">
                      {mode.tags.map(tag => <span className="mc-tag" key={tag}>{tag}</span>)}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </section>

          <div className="param-bar">
            <span className="plabel">日期</span>
            <input
              type="date"
              className="param-input"
              aria-label="选股日期"
              value={tradeDate}
              onChange={event => {
                setTradeDate(event.target.value)
                setFreshnessSource('手动选择')
              }}
            />
            <span className="psep" />
            <span className="plabel">Top</span>
            <select
              className="param-select"
              aria-label="Top 数量"
              value={topN}
              onChange={event => setTopN(Number(event.target.value))}
            >
              {[10, 20, 30, 50, 100].map(value => <option value={value} key={value}>{value}</option>)}
            </select>
            <span className="psep" />
            <span className="plabel">筛选</span>
            <button type="button" className="filter-btn active">全部</button>
            <button type="button" className="filter-btn">主板</button>
            <button type="button" className="filter-btn">创业板</button>
            <button type="button" className="filter-btn">科创板</button>
            <span className="psep" />
            <span className="plabel down">排除ST</span>
            <button type="button" className="run-btn" aria-label="开始选股 运行选股" onClick={runScreener} disabled={loading}>
              {loading ? '运行中...' : '▶ 运行选股'}
            </button>
          </div>

          <div className={`screener-run-status ${runStage === 'error' ? 'error' : ''}`} aria-live="polite">
            <div className={`run-step${stageState('data')}`}><span>1</span>数据更新</div>
            <div className={`run-step${stageState('model')}`}><span>2</span>模型选股</div>
            <div className={`run-step${stageState('output')}`}><span>3</span>输出股票</div>
            <div className="run-message">{runMessage}</div>
          </div>

          <div className="wb-main">
            <div className="wb-left">
              <div className="wb-table">
                <div className="wb-th">
                  <span className="wb-rank">#</span>
                  <span className="wb-cb">☑</span>
                  <span className="wb-code">代码</span>
                  <span className="wb-name">名称</span>
                  <span className="wb-score">评分</span>
                  <span className="wb-grade">等级</span>
                  <span className="wb-industry">行业</span>
                  <span className="wb-mcap">市值(亿)</span>
                </div>
                {visiblePicks.length === 0 && (
                  <div className="wb-empty">
                    <b>{emptyResultTitle}</b>
                    <span>{emptyResultDetail}</span>
                  </div>
                )}
                {visiblePicks.map((pick, index) => {
                  const activePick = pick.code === selectedPick?.code
                  const selected = selectedCodes.includes(pick.code)
                  return (
                    <button
                      type="button"
                      className={`wb-tr${activePick ? ' selected' : ''}`}
                      key={pick.code || index}
                      onClick={() => selectPick(pick)}
                    >
                      <span className="wb-rank">{index + 1}</span>
                      <span className={`wb-cb ${selected ? 'neu' : ''}`}>{selected ? '☑' : '☐'}</span>
                      <span className={`wb-code ${activePick ? 'neu' : ''}`}>{pick.code}</span>
                      <span className="wb-name">{pick.name}</span>
                      <span className={`wb-score ${scoreTone(pick.score)}`}>{formatScore(pick.score)}</span>
                      <span className="wb-grade"><span className={`grade-tag ${gradeClass(pick.grade)}`}>{pick.grade || 'B'}</span></span>
                      <span className="wb-industry">{pick.industry || pick.hard_tech?.track || '综合'}</span>
                      <span className="wb-mcap">{formatMarketCap(pick.market_cap)}</span>
                    </button>
                  )
                })}
              </div>

              <div className="batch-actions">
                <button type="button" className="action-btn text" onClick={selectAllPicks} disabled={!canUseResults}>全选</button>
                <button type="button" className="action-btn text" onClick={clearSelectedPicks} disabled={selectedCount === 0}>清除</button>
                <span className="prototype-panel-note">已选</span>
                <span className="sel-cnt">{selectedCount}</span>
                <span className="prototype-panel-note">只</span>
                <button type="button" className="action-btn primary" onClick={addToCandidatePool} disabled={!canUseResults || recordingPool} title={recordingPool ? '正在写入候选池…' : '写入选中候选股到候选池'}>{recordingPool ? '写入中…' : '加入候选池 →'}</button>
                <button type="button" className="action-btn" onClick={addToWatchlist} disabled={!canUseResults || Boolean(watchingCode)} title={watchingCode ? '正在加入自选…' : '加入自选'}>{watchingCode ? '加入中…' : '加入自选'}</button>
                <button type="button" className="action-btn text" onClick={exportCsv} disabled={!canUseResults}>导出 CSV</button>
              </div>
            </div>

            <div className="wb-right">
              <div className="detail-card">
                <div className="detail-h">
                  {detailTitleForModel(selectedMode)}
                  {selectedPick && (
                    <span className="stock-meta">
                      <span className="mono neu">{selectedPick.code}</span>
                      <span>标的 {selectedPick.name}</span>
                      <span className={`mono ${scoreTone(selectedPick.score)}`}>{formatScore(selectedPick.score)}</span>
                    </span>
                  )}
                </div>
                <div className="detail-b">
                  {screeningTrace.length > 0 && (
                    <div className="prototype-fallback">
                      <div className="nm">选债过程</div>
                      <div className="risk-list mt14">
                        {screeningTrace.map(item => (
                          <div
                            className={`risk-item ${item.status === 'ok' ? 'ok' : item.status === 'review' ? 'warn' : ''}`}
                            key={`${item.step}-${item.detail}`}
                          >
                            {item.step}: {item.detail}
                          </div>
                        ))}
                      </div>
                      {rejectionSummary.length > 0 && (
                        <div className="chips mt14">
                          {rejectionSummary.map(item => (
                            <span className="chip" key={item.reason}>{item.reason}：{item.count}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {!selectedPick && (
                    <div className="prototype-fallback">
                      <div className="nm">{hasRun ? '当日无模型输出' : '等待模型输出'}</div>
                      <div className="mt6">{hasRun ? emptyResultDetail : '当前没有可展示的股票明细，运行成功后这里会展示首只候选的指标、风险和模型评价。'}</div>
                    </div>
                  )}
                  {selectedPick && (
                    <>
                  <div className="lineage-chips">
                    <span className="lineage-chip safe">赛道 <b>{selectedPick?.hard_tech?.track || selectedPick?.industry || '综合'}赛道</b></span>
                    <span className="lineage-chip accent">层级 <b>{selectedPick?.hard_tech?.tier || selectedPick?.grade || 'watch'}</b></span>
                  </div>
                  {detailGroups.map(group => (
                    <div className="ind-group" key={group.name}>
                      <div className="ind-group-label">{group.name}</div>
                      {group.items.map(([label, width, color, value]) => (
                        <div className="ind-bar" key={String(label)}>
                          <span className="ind-bar-label">{label}</span>
                          <div className="ind-bar-track"><div className="ind-bar-fill" style={{ width: `${width}%`, background: String(color) }} /></div>
                          <span className="ind-bar-val" style={{ color: String(color) }}>{value}</span>
                        </div>
                      ))}
                    </div>
                  ))}

                  <div className="eval-box">
                    <div className="ev-title">模型评价</div>
                    {evaluationForModel(selectedMode, selectedPick)}
                  </div>
                  <div className="risk-list">
                    <div className="risk-item ok">ST风险: 通过</div>
                    <div className="risk-item ok">涨幅过热: 通过</div>
                    {(selectedPick?.risk_flags || []).map(flag => <div className="risk-item warn" key={flag}>需复核: {flag}</div>)}
                  </div>
                  <div className="detail-actions">
                    <button type="button" className="action-btn primary" onClick={addToCandidatePool} disabled={recordingPool} title={recordingPool ? '正在写入候选池…' : '写入选中候选股到候选池'}>{recordingPool ? '写入中…' : '加入候选池'}</button>
                    <button
                      type="button"
                      className="action-btn"
                      onClick={() => navigate(`/backtest?code=${encodeURIComponent(selectedPick.code)}&mode=${encodeURIComponent(selectedMode)}`)}
                    >
                      触发回测
                    </button>
                    <button
                      type="button"
                      className="action-btn"
                      onClick={() => navigate(`/diagnosis?code=${encodeURIComponent(selectedPick.code)}`)}
                    >
                      查看诊断
                    </button>
                  </div>
                  <button type="button" className="action-btn text screener-expand-btn" onClick={() => setExpanded(value => !value)}>
                    {expanded ? '收起四轴解释' : '展开四轴解释'}
                  </button>
                  {expanded && selectedPick && (
                    <div className="prototype-fallback mt14">
                      <div className="nm">{selectedPick.entry_reason}</div>
                      <div className="chips mt14">
                        {(selectedPick.risk_flags || []).map(flag => <span className="chip" key={flag}>{flag}</span>)}
                        {(selectedPick.power_flags || []).map(flag => <span className="chip active" key={flag}>{flag}</span>)}
                        {Object.entries(selectedPick.factor_breakdown || {}).map(([key, value]) => (
                          <span className="chip active" key={key}>
                            {factorLabel(key)} {Number(value).toFixed(1)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="footer-bar">
            <span>智能选股 · 选股工作台 | {lastRunAt ? `最近运行 ${new Date(lastRunAt).toLocaleTimeString('zh-CN', { hour12: false })}` : '等待运行'}</span>
            <span className="sep" />
            <span>模型: {selectedModeConfig.name}（{selectedMode}） | 结果: {visiblePicks.length}只</span>
            <span className="sep" />
            <span>数据来源: screener-service + Kronos 模型引擎</span>
          </div>
        </>
      )}

      {active === 'models' && (
        <>
          {/* 模型选择器（4 模型默认全选，token 化色） */}
          <div className="model-selector">
            {modelCompareModes.map(modeId => {
              const name = modelNameById(modeId)
              const short = shortNameForModel(name)
              return (
                <label className="check checked" key={modeId}>
                  <input type="checkbox" checked readOnly />
                  <span className={`model-chip ${MODEL_TAG_TONE[short] || 'bi'}`}>{short}</span>
                  {name}
                </label>
              )
            })}
            <span
              className="run-state"
              style={{ background: lightTokens.down, color: lightTokens.surface }}
            >
              {modelCompareLoading ? '运行中…' : modelCompareRows.length > 0 ? '✓ 已完成' : '等待数据'}
            </span>
          </div>

          {/* 共识统计条：每个模型 N 只 ∩ ... = 共识只数 */}
          {modelCompareRows.length > 0 ? (
            <div className="stats-bar">
              {modelCompareRows.map((row, idx) => (
                <span className="stats-group" key={row.modeId}>
                  {idx > 0 && <span className="sep-icon">∩</span>}
                  <span className="step">
                    <span className={`model-chip sm ${MODEL_TAG_TONE[shortNameForModel(row.name)] || 'bi'}`}>
                      {shortNameForModel(row.name)}
                    </span>
                    <span className="count">{row.count}只</span>
                  </span>
                  {idx > 0 && (
                    <span className={`step hl ${idx === modelCompareRows.length - 1 ? 'final' : ''}`}>
                      <span className="count">{consensusByCumulative(modelCompareRows, idx)}只</span>
                    </span>
                  )}
                </span>
              ))}
              <span className="rate">
                最终共识率{' '}
                <span className="val warn">{modelComparePicks.length}/{modelCompareRows.reduce((s, r) => s + r.count, 0) || 0} 只</span>
              </span>
            </div>
          ) : (
            <div className="prototype-fallback">{modelCompareLoading ? '正在运行模型对比...' : modelCompareMessage}</div>
          )}

          {/* 主区：左共识矩阵 + 右跨模型评分对比 */}
          <div className="row r-7-5">
            <PrototypeCard title="共识矩阵" icon={<BarChartOutlined />} meta={`共 ${consensusRows.length} 只标的`}>
              {/* 星级筛选 tab（仅展示，按 stars 分桶） */}
              <div className="filter-tabs">
                <span
                  className="filter-tab active"
                  role="tab"
                  aria-selected="true"
                >
                  全部 {consensusRows.length}
                </span>
                {STAR_TIERS.map(tier => {
                  const n = consensusRows.filter(r => r.stars === tier.value).length
                  if (n === 0) return null
                  return (
                    <span className="filter-tab" role="tab" key={tier.value} aria-selected="false">
                      {tier.label} {n}
                    </span>
                  )
                })}
              </div>
              {consensusRows.length > 0 ? (
                <div className="tbl-scroll">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>代码</th>
                        <th>名称</th>
                        <th className="r">最新价</th>
                        <th className="r">涨跌幅</th>
                        <th className="c">共识度</th>
                        <th>选中模型</th>
                      </tr>
                    </thead>
                    <tbody>
                      {consensusRows.map(row => (
                        <tr
                          key={row.code}
                          className={selectedConsensusCode === row.code ? 'picked' : undefined}
                          onClick={() => setSelectedConsensusCode(row.code)}
                        >
                          <td className="code neu">{row.code}</td>
                          <td className="nm">{row.name}</td>
                          <td className={`r mono ${row.changePct === undefined ? '' : row.changePct >= 0 ? 'up' : 'down'}`}>
                            {row.price !== undefined ? row.price.toFixed(2) : '--'}
                          </td>
                          <td className={`r mono ${row.changePct === undefined ? '' : row.changePct >= 0 ? 'up' : 'down'}`}>
                            {row.changePct === undefined ? '--' : `${row.changePct >= 0 ? '+' : ''}${row.changePct.toFixed(1)}%`}
                          </td>
                          <td className="c stars warn">{'★'.repeat(row.stars)}</td>
                          <td>
                            {row.models.map((m, i) => (
                              <span className={`model-chip ${m.tone}`} key={i}>{m.short}</span>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="prototype-fallback">模型已运行，但当前没有候选股票。</div>
              )}
            </PrototypeCard>

            {/* 右：跨模型评分对比（选中股的多模型评分卡 + 指标条） */}
            <PrototypeCard title="跨模型评分对比" icon={<FundOutlined />}>
              {selectedConsensus ? (
                <div className="score-panel">
                  <div className="stock-header">
                    <span className="stk-code mono">{selectedConsensus.code}</span>
                    <span className="stk-name">{selectedConsensus.name}</span>
                    <span className={`stk-price mono ${selectedConsensus.changePct === undefined ? '' : selectedConsensus.changePct >= 0 ? 'up' : 'down'}`}>
                      {selectedConsensus.price !== undefined ? `¥${selectedConsensus.price.toFixed(2)}` : '--'}
                    </span>
                  </div>
                  {crossModelScores.map((entry, idx) => (
                    <div className="score-card" key={idx}>
                      <div className="sc-header">
                        <span className="sc-model">
                          <span className={`model-chip ${MODEL_TAG_TONE[entry.short] || 'bi'}`}>{entry.short}</span>
                          {entry.modelName}
                        </span>
                        <div>
                          <span className="sc-score neu">{entry.score !== undefined ? formatScore(entry.score) : '--'}</span>
                        </div>
                      </div>
                      {entry.indicators.map(ind => (
                        <div className="indicator-row" key={ind.label}>
                          <span className="sc-lbl">{ind.label}</span>
                          <span className="sc-bar">
                            <span
                              className="sc-bar-fill"
                              style={{ width: `${ind.width}%`, background: indicatorToneColor(ind.tone) }}
                            />
                          </span>
                          <span className="sc-val mono">{ind.value === null ? '--' : formatScore(ind.value)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="btn-accent btn-block"
                    onClick={() => addConsensusToPool(selectedConsensus)}
                  >
                    + 加入候选池（{consensusRows.filter(r => r.stars >= maxStar).length}只 {STAR_TIERS[0]?.label}）
                  </button>
                </div>
              ) : (
                <div className="prototype-fallback">点击左侧矩阵中的标的，查看跨模型评分差异。</div>
              )}
            </PrototypeCard>
          </div>

          <div className="footer-bar">
            <span>智能选股 · 模型对比 | 盘后运行</span>
            <span className="sep" />
            <span>毕=毕师傅 匪=匪爷 秋=秋神 长=长线</span>
            <span className="sep" />
            <span>数据来源: screener-service POST /screener/run</span>
          </div>
        </>
      )}

      {active === 'factors' && (
        <>
          {/* 使用引导条 */}
          <div className="guide-bar">
            <span className="guide-lead neu">怎么用:</span>
            <span>1. 看IC柱状图找有效因子(ICIR&gt;1.0)</span>
            <span className="arrow muted">→</span>
            <span>2. 看热力图去冗余(相关性&gt;0.7合并)</span>
            <span className="arrow muted">→</span>
            <span>3. 看分层验证区分度(多空spread&gt;5%)</span>
            <span className="arrow muted">→</span>
            <span>4. 看行业暴露避集中</span>
          </div>

          {/* Row 1: IC 柱图 + IC/ICIR 统计 */}
          <div className="row r-7-5">
            <PrototypeCard title="因子 IC 分析" icon={<BarChartOutlined />} meta="T+1 未来收益 · 近30天">
              {factorStats.length > 0 ? (
                <ReactECharts option={buildIcBarOption(factorStats)} style={{ height: 340 }} opts={{ renderer: 'svg' }} />
              ) : (
                <div className="prototype-fallback">暂无因子 IC 数据，请先在工作台运行选股模型以累积因子分解。</div>
              )}
            </PrototypeCard>
            <PrototypeCard title="IC / ICIR 统计" icon={<FundOutlined />} meta="按 |ICIR| 降序">
              {factorStats.length > 0 ? (
                <div className="tbl-scroll">
                  <table className="tbl compact">
                    <thead>
                      <tr>
                        <th>因子</th>
                        <th className="r">IC 均值</th>
                        <th className="r">IC 标准差</th>
                        <th className="r">ICIR</th>
                        <th className="r">t-stat</th>
                      </tr>
                    </thead>
                    <tbody>
                      {factorStats.map(stat => (
                        <tr key={stat.key}>
                          <td className="nm">{stat.label}</td>
                          <td className={`r mono ${stat.ic >= 0 ? 'up' : 'down'}`}>{stat.ic >= 0 ? '+' : ''}{stat.ic.toFixed(3)}</td>
                          <td className="r mono">{stat.icStd.toFixed(2)}</td>
                          <td className="r mono neu">{stat.icir.toFixed(3)}</td>
                          <td className={`r mono ${stat.tStat >= 2 ? 'up' : stat.tStat <= -2 ? 'down' : ''}`}>{stat.tStat.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="prototype-fallback">后端未返回因子统计，ICIR 与 t-stat 需累积多日数据。</div>
              )}
            </PrototypeCard>
          </div>

          {/* Row 2: 相关性热力图 + 分层收益 */}
          <div className="row r-7-5">
            <PrototypeCard title="因子相关性矩阵" icon={<RadarChartOutlined />} meta={`${Math.min(factorStats.length, 8)}×${Math.min(factorStats.length, 8)} 核心因子`}>
              {factorStats.length >= 2 ? (
                <ReactECharts option={buildHeatmapOption(factorStats)} style={{ height: 360 }} opts={{ renderer: 'svg' }} />
              ) : (
                <div className="prototype-fallback">至少需要 2 个因子才能生成相关性矩阵。</div>
              )}
            </PrototypeCard>
            <PrototypeCard title="因子收益率分层" icon={<FundOutlined />} meta={selectedFactorLabel ? `选中因子: ${selectedFactorLabel}` : '按评分十分位'}>
              {decileRows.length > 0 ? (
                <div className="tbl-scroll">
                  <table className="tbl compact">
                    <thead>
                      <tr>
                        <th>分层</th>
                        <th>说明</th>
                        <th className="r">累计收益</th>
                        <th className="r">日均收益</th>
                      </tr>
                    </thead>
                    <tbody>
                      {decileRows.map((row, idx) => (
                        <tr key={idx} className={row.tier === '多-空对冲' ? 'picked' : undefined}>
                          <td className="nm">{row.tier}</td>
                          <td>{row.note}</td>
                          <td className={`r mono ${row.cum >= 0 ? 'up' : 'down'} ${row.tier === '多-空对冲' ? 'neu strong' : ''}`}>
                            {row.cum >= 0 ? '+' : ''}{row.cum.toFixed(1)}%
                          </td>
                          <td className={`r mono ${row.daily >= 0 ? 'up' : 'down'}`}>
                            {row.daily === 0 ? '—' : `${row.daily >= 0 ? '+' : ''}${row.daily.toFixed(2)}%`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="prototype-fallback">候选股不足，无法生成分层收益。</div>
              )}
            </PrototypeCard>
          </div>

          {/* Row 3: 行业因子暴露 */}
          <PrototypeCard title="行业因子暴露" icon={<RadarChartOutlined />} meta={selectedFactorLabel ? `${selectedFactorLabel} · 近30天均值` : '按行业聚合'}>
            {industryRows.length > 0 ? (
              <div className="tbl-scroll">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>行业板块</th>
                      <th className="r">偏离度</th>
                      <th className="c">暴露程度</th>
                      <th className="r">股票数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {industryRows.map(row => (
                      <tr key={row.industry}>
                        <td className="nm">{row.industry}</td>
                        <td className={`r mono ${row.avg >= 0 ? 'up' : 'down'}`}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}</td>
                        <td className="c"><span className={`exp-tag ${row.level}`}>{row.level === 'high' ? '偏高' : row.level === 'low' ? '偏低' : '中性'}</span></td>
                        <td className="r mono">{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="prototype-fallback">候选股缺少行业字段，无法计算行业因子暴露。</div>
            )}
          </PrototypeCard>

          <div className="footer-bar">
            <span>智能选股 · 因子分析 | 盘后 15:42</span>
            <span className="sep" />
            <span>数据来源: screener-service /screener/run · factor_breakdown</span>
            <span className="sep" />
            <span>ICIR = IC均值/IC标准差 | |t-stat| ≥ 2 视为显著</span>
          </div>
        </>
      )}
    </PrototypePage>
  )
}
