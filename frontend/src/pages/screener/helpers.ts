import type { ScreenerPick } from '../../api/types'
import { lightTokens } from '../../styles/tokens'
import type {
  ConsensusRow,
  DetailGroup,
  DetailItem,
  IndustryRow,
  ModelCompareRow,
  ModelCompareRunRow,
  ModelGroup,
  ScoreIndicator,
} from './types'

export const tabs = [
  { key: 'workbench', path: '/screener', label: '选股工作台', subLabel: '策略入口' },
  { key: 'models', path: '/screener/models', label: '模型对比', subLabel: '评分差异' },
  { key: 'factors', path: '/screener/factors', label: '因子分析', subLabel: 'IC / 暴露' },
]

export const modelGroups: ModelGroup[] = [
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

export function activeKey(pathname: string) {
  if (pathname.endsWith('/models')) return 'models'
  if (pathname.endsWith('/factors')) return 'factors'
  return 'workbench'
}

export function factorLabel(key: string) {
  if (key === 'hard_tech_conviction') return '硬科技'
  if (key === 'startup_quality') return '启动质量'
  if (key === 'ignition_power') return '点火强度'
  if (key === 'technical') return '技术面'
  if (key === 'fundamental') return '基本面'
  if (key === 'money_flow') return '资金面'
  return key
}

export function formatScore(value: unknown) {
  const score = Number(value ?? 0)
  return Number.isFinite(score) ? score.toFixed(score % 1 === 0 ? 0 : 1) : '--'
}

export function formatMarketCap(value: unknown) {
  const marketCap = Number(value ?? 0)
  return Number.isFinite(marketCap) && marketCap > 0 ? marketCap.toLocaleString('zh-CN') : '--'
}

export function gradeClass(grade?: string) {
  if (grade === 'S') return 'grade-S'
  if (grade === 'A') return 'grade-A'
  if (grade === 'B') return 'grade-B'
  if (grade === 'C') return 'grade-C'
  return 'grade-D'
}

export function scoreTone(score?: number) {
  const value = Number(score ?? 0)
  if (value >= 85) return 'up'
  if (value >= 74) return 'warn'
  if (value >= 68) return 'neu'
  return ''
}

export function finiteNumber(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function barWidth(value: number, scale = 1) {
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

export function detailTitleForModel(modelId: string) {
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

export function detailGroupsForModel(_modelId: string, pick?: ScreenerPick): DetailGroup[] {
  if (!pick) return []
  const factorItems = buildFactorItems(pick)
  const metricItems = buildMetricItems(pick)
  return [
    factorItems.length > 0 ? { name: '后端因子', items: factorItems } : null,
    metricItems.length > 0 ? { name: '结果指标', items: metricItems } : null,
  ].filter((group): group is DetailGroup => Boolean(group))
}

export function evaluationForModel(modelId: string, pick?: ScreenerPick) {
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

export function syncPlanForMode(modelId: string) {
  if (modelId.includes('auction')) return { tableKey: 'stk_auction_o', days: 1, label: '集合竞价' }
  if (modelId === 'leader_intraday') return { tableKey: 'rt_sw_k', days: 1, label: '实时行情' }
  if (modelId === 'cb_intraday') return { tableKey: 'stk_mins', days: 5, label: '分钟行情' }
  return { tableKey: 'daily_kline', days: 30, label: '日线行情' }
}

export function normalizeLatestDates(value: Record<string, string | null | undefined> | undefined) {
  return Object.fromEntries(
    Object.entries(value || {})
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].length > 0)
      .map(([key, date]) => [key, date.slice(0, 10)]),
  )
}

export function todayDateInputValue() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function createTradeDateResolver(latestDates: Record<string, string>, fallbackDate: string) {
  return (modeId: string, requestedDate = fallbackDate) => {
    const syncPlan = syncPlanForMode(modeId)
    const latestForSource = latestDates[syncPlan.tableKey]
    if (latestForSource && (!requestedDate || latestForSource < requestedDate)) return latestForSource
    return requestedDate || latestForSource || latestDates.daily_kline || undefined
  }
}

export const modelCompareModes = ['leader_scalp', 'leader_closing', 'leader_intraday', 'bi_trend_full_market']

// 星级档位（共识矩阵筛选 tab + 候选池按钮文案）
export const STAR_TIERS = [
  { value: 4, label: '★★★★' },
  { value: 3, label: '★★★' },
  { value: 2, label: '★★' },
  { value: 1, label: '★' },
]

// 共识统计条：前 idx+1 个模型的累计候选只数（去重，preview ∩ 步骤语义）
// modelCompareRows 在运行时持有 ModelCompareRunRow（含 picks），类型层用 ModelCompareRow 收窄，
// 故此处按 run row 读取 picks。
export function consensusByCumulative(rows: ModelCompareRow[], idx: number) {
  const codes = new Set<string>()
  rows.slice(0, idx + 1).forEach(row => {
    const picks = (row as ModelCompareRunRow).picks || []
    picks.forEach(p => {
      if (p.code) codes.add(p.code)
    })
  })
  return codes.size
}

export function modelNameById(modeId: string) {
  return modelGroups.flatMap(group => group.modes).find(mode => mode.id === modeId)?.name || modeId
}

export function averageScore(picks: ScreenerPick[]) {
  const scores = picks.map(pick => Number(pick.score)).filter(Number.isFinite)
  if (scores.length === 0) return null
  return scores.reduce((sum, score) => sum + score, 0) / scores.length
}

// ===== 3.2 model-compare：模型选择器 / 共识矩阵 / 跨模型评分 =====
// 模型简称（preview 4 档色：毕=红 / 匪=橙 / 秋=紫 / 长=绿），用 signalLevelTokens 语义色
export const MODEL_TAG_TONE: Record<string, string> = {
  '毕': 'bi',
  '匪': 'fe',
  '秋': 'qs',
  '长': 'cx',
}

// 由模型全名（entry_reason 前缀）反推简称：毕师傅→毕 / 匪爷→匪 / 秋神→秋 / 长线→长
export function shortNameForModel(modelName: string) {
  if (!modelName) return '?'
  if (modelName.includes('毕')) return '毕'
  if (modelName.includes('匪')) return '匪'
  if (modelName.includes('秋')) return '秋'
  if (modelName.includes('长')) return '长'
  return modelName.slice(0, 1)
}

// 入参 modelComparePicks 的 entry_reason 已编码来源模型名（"modelName；..."），据此反推星级。
export function buildConsensusRows(picks: ScreenerPick[]): ConsensusRow[] {
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

// 选中股在各模型中的评分卡（从 modelComparePicks 中按 code 聚合，每模型取一条）
export function buildCrossModelScores(selectedConsensus: ConsensusRow | undefined, modelComparePicks: ScreenerPick[]) {
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
}

export function indicatorToneColor(tone: ScoreIndicator['tone']) {
  if (tone === 'up') return lightTokens.up
  if (tone === 'down') return lightTokens.down
  if (tone === 'warn') return lightTokens.warn
  return lightTokens.accent
}

export function buildIndustryRows(picks: ScreenerPick[]): IndustryRow[] {
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
