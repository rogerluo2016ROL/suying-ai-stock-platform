import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BarChartOutlined, FundOutlined, RadarChartOutlined } from '@ant-design/icons'
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
import type { ScreenerPick } from '../api/types'

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
    defaultModel: '秋神竞价超预期选股',
    modes: [
      { id: 'leader_auction', name: '秋神竞价超预期选股', tags: ['9:25', '竞价'] },
      { id: 'leader_afternoon', name: '秋神午后选股模型', tags: ['14:30', '午后'] },
      { id: 'leader_intraday', name: '秋神盘中龙头 V7.0', tags: ['盘中', '1-2天'] },
      { id: 'leader_closing', name: '秋神尾盘顺势 V2.0', tags: ['尾盘', '顺势'] },
      { id: 'leader_scalp', name: '秋神盘后龙头', tags: ['盘后', '1-5天'] },
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
    count: 3,
    note: '用于筛选债底保护、日内博弈和竞价概念选债。',
    defaultModel: '底价选债',
    modes: [
      { id: 'cb_floor', name: '底价选债', tags: ['可转债', '日频'] },
      { id: 'cb_intraday', name: '匪爷日内投机博弈', tags: ['日内', '激进'] },
      { id: 'cb_auction', name: '秋神竞价概念选债', tags: ['竞价', '1-2天'] },
    ],
  },
]

type DetailItem = [string, number, string, string]

type DetailGroup = {
  name: string
  items: DetailItem[]
}

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
    cb_floor: '底价选债分析',
    cb_intraday: '可转债日内博弈分析',
    cb_auction: '秋神竞价概念选债分析',
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
  if (modelId === 'cb_floor' || modelId === 'cb_intraday' || modelId === 'cb_auction') return `债底保护和正股弹性具备攻守平衡特征，适合进入可转债候选池，不直接混入股票下单池。`
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
  const [tradeDate, setTradeDate] = useState('')
  const [topN, setTopN] = useState(20)
  const [runStage, setRunStage] = useState<'idle' | 'data' | 'model' | 'output' | 'done' | 'error'>('idle')
  const [runMessage, setRunMessage] = useState('正在读取最新可用交易日')
  const [lastRunAt, setLastRunAt] = useState('')
  const [freshnessSource, setFreshnessSource] = useState('screener-service')
  const [latestDates, setLatestDates] = useState<Record<string, string>>({})
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)

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
        const latestTradeDate = nextLatestDates[syncPlan.tableKey] || nextLatestDates.daily_kline || ''
        if (latestTradeDate) {
          const normalizedDate = String(latestTradeDate).slice(0, 10)
          setTradeDate(normalizedDate)
          setRunMessage(`已加载最新可用交易日：${normalizedDate}`)
        } else {
          setRunMessage('后端未返回最新交易日，请手动选择日期后运行')
        }
        setFreshnessSource(latestTradeDate ? syncPlan.tableKey : freshness?.source || 'screener/modes')
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
    setTradeDate(latestTradeDate)
    setFreshnessSource(syncPlan.tableKey)
  }, [latestDates, selectedMode])

  const runScreener = async () => {
    setLoading(true)
    setRunStage('data')
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
      const runTradeDate = tradeDate || undefined
      const response = await screenerApi.run(selectedMode, topN, runTradeDate)
      const nextPicks = response.data?.picks || []
      const actualTradeDate = response.data?.trade_date || response.data?.data_freshness?.as_of || tradeDate
      setRunStage('output')
      setRunMessage(`模型完成，正在整理 ${nextPicks.length} 只候选股票`)
      setHasRun(true)
      setPicks(nextPicks)
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
                    <b>暂无选股结果</b>
                    <span>{hasRun ? '请换一个交易日、Top 数量或模型后重新运行。' : '选择模型、日期和 Top 后点击运行选股。'}</span>
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
                <button type="button" className="action-btn primary" disabled title="候选池写入接口未接入">加入候选池 →</button>
                <button type="button" className="action-btn" disabled title="自选股写入接口未接入">加入自选</button>
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
                  {!selectedPick && (
                    <div className="prototype-fallback">
                      <div className="nm">等待模型输出</div>
                      <div className="mt6">当前没有可展示的股票明细，运行成功后这里会展示首只候选的指标、风险和模型评价。</div>
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
                    <button type="button" className="action-btn primary" disabled title="候选池写入接口未接入">加入候选池</button>
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
            <span>智能选股 · 选股工作台 | 盘后 16:18</span>
            <span className="sep" />
            <span>模型: {selectedModeConfig.name} | 结果: {visiblePicks.length}只</span>
            <span className="sep" />
            <span>数据来源: screener-service + Kronos 模型引擎</span>
          </div>
        </>
      )}

      {active === 'models' && (
        <div className="row r-6-4">
          <div className="grid">
            <PrototypeCard title="模型评分差异" icon={<BarChartOutlined />} meta="3.2 模型对比">
            <table className="tbl">
              <thead><tr><th>模型</th><th>偏好</th><th className="r">命中</th><th className="r">说明</th></tr></thead>
              <tbody>
                {[
                  ['趋势启动 V13', '动量/竞价', '72%', '短线启动更敏感'],
                  ['多因子价值 V7', '估值/质量', '65%', '回撤更低'],
                  ['产业链增强 V4', '链路/主题', '69%', '适合主题行情'],
                ].map(row => (
                  <tr key={row[0]}><td className="nm">{row[0]}</td><td>{row[1]}</td><td className="r mono">{row[2]}</td><td className="r">{row[3]}</td></tr>
                ))}
              </tbody>
            </table>
            </PrototypeCard>
            <PrototypeCard title="候选池排行" icon={<FundOutlined />} meta="Candidate">
              <table className="tbl">
                <thead><tr><th>代码</th><th>名称</th><th>来源模型</th><th className="r">评分</th></tr></thead>
                <tbody>
                  {visiblePicks.map(pick => (
                    <tr key={pick.code}>
                      <td className="code">{pick.code}</td>
                      <td className="nm">{pick.name}</td>
                      <td>{pick.entry_reason?.split('；')[0] || '模型共识'}</td>
                      <td className="r mono">{pick.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </PrototypeCard>
          </div>
          <SideRail title="模型结论" meta="公共模型">
            <DataDomainBadge domain="public" label="公共模型输出" />
            <RiskBanner status="review" title="趋势模型占优" detail="短线启动模型对竞价和动量更敏感；价值模型回撤更低，适合做组合约束。" />
          </SideRail>
        </div>
      )}

      {active === 'factors' && (
        <div className="row r-6-4">
          <PrototypeCard title="因子暴露" icon={<RadarChartOutlined />} meta="3.3 因子分析">
            {[
              ['启动质量', 78, 'var(--accent)'],
              ['点火强度', 65, 'var(--warn)'],
              ['硬科技确认', 82, 'var(--down)'],
              ['流动性风险', 31, 'var(--up)'],
            ].map(([label, value, color]) => (
              <div className="dim-row" key={String(label)}>
                <div className="dim-lbl">{label}</div>
                <div className="dim-bar-wrap"><div className="dim-bar" style={{ width: `${value}%`, background: String(color) }} /></div>
                <div className="dim-val">{value}</div>
              </div>
            ))}
          </PrototypeCard>
          <SideRail title="因子解释" meta="IC / 暴露">
            <DataDomainBadge domain="public" label="公共因子" />
            <LineageChips
              items={[
                { label: 'IC', value: '0.12', tone: 'accent' },
                { label: 'ICIR', value: '1.8', tone: 'safe' },
                { label: '风险暴露', value: '31', tone: 'warn' },
              ]}
            />
            <RiskBanner status="pass" title="因子组合可用" detail="启动质量和硬科技确认贡献最高，流动性风险保持在可控区间。" />
          </SideRail>
        </div>
      )}
    </PrototypePage>
  )
}
