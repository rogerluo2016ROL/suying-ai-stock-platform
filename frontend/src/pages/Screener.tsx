import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BarChartOutlined, FundOutlined, RadarChartOutlined } from '@ant-design/icons'
import { message } from 'antd'
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
      { id: 'supply_chain', name: '大葱产业链解构', tags: ['产业链', '中长线'] },
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
    supply_chain: '大葱产业链解构分析',
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
  if (modelId === 'supply_chain') return `产业链位置和政策主题形成匹配，${track}具备中长期链路价值，适合进入方案管理做更长周期跟踪。`
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

function modelNameById(modeId: string) {
  return modelGroups.flatMap(group => group.modes).find(mode => mode.id === modeId)?.name || modeId
}

function averageScore(picks: ScreenerPick[]) {
  const scores = picks.map(pick => Number(pick.score)).filter(Number.isFinite)
  if (scores.length === 0) return null
  return scores.reduce((sum, score) => sum + score, 0) / scores.length
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

  useEffect(() => {
    if (active !== 'models') return
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
                <button type="button" className="action-btn" disabled title="watchlist 待 Batch B">加入自选</button>
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
        <div className="row r-6-4">
          <div className="grid">
            <PrototypeCard title="模型评分差异" icon={<BarChartOutlined />} meta="3.2 模型对比">
              {modelCompareRows.length > 0 ? (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>模型</th>
                      <th>数据日</th>
                      <th>数据源</th>
                      <th className="r">候选</th>
                      <th className="r">均分</th>
                      <th>第一名</th>
                    </tr>
                  </thead>
                  <tbody>
                    {modelCompareRows.map(row => (
                      <tr key={row.modeId}>
                        <td>{row.name}</td>
                        <td className="mono">{row.tradeDate || '--'}</td>
                        <td>{row.source}</td>
                        <td className="r mono">{row.count}</td>
                        <td className="r mono">{row.avgScore === null ? '--' : formatScore(row.avgScore)}</td>
                        <td>{row.topPick ? `${row.topPick.code} ${row.topPick.name || ''}` : '无候选'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="prototype-fallback">{modelCompareLoading ? '正在运行模型对比...' : modelCompareMessage}</div>
              )}
            </PrototypeCard>
            <PrototypeCard title="候选池排行" icon={<FundOutlined />} meta="Candidate">
              <table className="tbl">
                <thead><tr><th>代码</th><th>名称</th><th>来源模型</th><th className="r">评分</th></tr></thead>
                <tbody>
                  {modelRankingPicks.map((pick, index) => (
                    <tr key={`${pick.code}-${index}`}>
                      <td className="code">{pick.code}</td>
                      <td className="nm">{pick.name}</td>
                      <td>{pick.entry_reason?.split('；')[0] || '模型共识'}</td>
                      <td className="r mono">{pick.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {modelRankingPicks.length === 0 && <div className="prototype-fallback">模型已运行，但当前没有候选股票。</div>}
            </PrototypeCard>
          </div>
          <SideRail title="模型结论" meta="公共模型">
            <DataDomainBadge domain="public" label="公共模型输出" />
            <RiskBanner
              status={modelCompareRows.some(row => row.count > 0) ? 'pass' : 'review'}
              title={modelCompareRows.some(row => row.count > 0) ? '模型对比已完成' : '等待可用候选'}
              detail={modelCompareRows.some(row => row.count > 0)
                ? `共运行 ${modelCompareRows.length} 个模型，候选池合计 ${modelComparePicks.length} 只。`
                : modelCompareMessage}
            />
          </SideRail>
        </div>
      )}

      {active === 'factors' && (
        <div className="row r-6-4">
          <PrototypeCard title="因子暴露" icon={<RadarChartOutlined />} meta="3.3 因子分析">
            {selectedPick ? buildFactorItems(selectedPick).map(([label, width, color, value]) => (
              <div className="dim-row" key={String(label)}>
                <div className="dim-lbl">{label}</div>
                <div className="dim-bar-wrap"><div className="dim-bar" style={{ width: `${width}%`, background: String(color) }} /></div>
                <div className="dim-val">{value}</div>
              </div>
            )) : <div className="prototype-fallback">暂无模型因子暴露。</div>}
            {selectedPick && buildFactorItems(selectedPick).length === 0 && <div className="prototype-fallback">后端未返回因子明细。</div>}
          </PrototypeCard>
          <SideRail title="因子解释" meta="IC / 暴露">
            <DataDomainBadge domain="public" label="公共因子" />
            <RiskBanner status="review" title="等待因子统计" detail="IC、ICIR 和风险暴露需由后端统计接口返回。" />
          </SideRail>
        </div>
      )}
    </PrototypePage>
  )
}
