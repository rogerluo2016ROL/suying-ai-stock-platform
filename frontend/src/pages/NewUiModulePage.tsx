import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  ApiOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  FundOutlined,
  LineChartOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import api, { screenerApi, signalApi, tradeApi } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useLiveTrade, type OrderParams, type PreCheckResult } from '../hooks/useLiveTrade'
import { P0WorkflowNav } from '../components/layout'
import { MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, PrototypeTabs, SegmentTabs } from '../components/prototype'
import type { RiskVerdictRecord } from '../api/types'

type ModuleKey =
  | 'screener'
  | 'signals'
  | 'trade'
  | 'strategy'
  | 'autoTrade'
  | 'backtest'
  | 'diagnosis'
  | 'training'
  | 'modelRegistry'
  | 'dataUpdate'

type MetricTone = 'up' | 'down' | 'warn' | 'accent' | 'muted'
type P0Step = 'candidate' | 'plan' | 'order' | 'risk' | 'review'

interface ModuleTab {
  key: string
  path: string
  label: string
  subLabel: string
}

interface ModuleConfig {
  title: string
  subtitle: string
  tabs: ModuleTab[]
  icon: ReactNode
  metrics: Array<{ label: string; value: string; sub: string; tone: MetricTone }>
  tableTitle: string
  tableMeta: string
}

interface ScreenerMode {
  id: string
  name: string
  cycle?: string
}

interface ScreenerPick {
  code?: string
  name?: string
  price?: number
  score?: number
  grade?: string
  signal?: string
  hard_tech?: {
    track?: string
    tier?: string
    matched_keywords?: string[]
  }
  factor_breakdown?: Record<string, number>
  entry_reason?: string
  risk_flags?: string[]
}

interface AutoStrategy {
  id: string
  name: string
  status?: string
  trade_mode?: string
  capital?: number
  picks_count?: number
}

interface AutoLog {
  timestamp?: string
  level?: string
  message?: string
  details?: Record<string, string | number | undefined>
}

interface ReviewRow {
  orderId: string
  verdictId: string
  decisionContextId: string
  planId: string
  candidateId: string
  reason: string
}

const configs: Record<ModuleKey, ModuleConfig> = {
  screener: {
    title: '智能选股',
    subtitle: '选股工作台 · 模型对比 · 因子分析',
    icon: <FundOutlined />,
    tabs: [
      { key: 'workbench', path: '/screener', label: '选股工作台', subLabel: '策略入口' },
      { key: 'models', path: '/screener/models', label: '模型对比', subLabel: '评分差异' },
      { key: 'factors', path: '/screener/factors', label: '因子分析', subLabel: 'IC / 暴露' },
    ],
    metrics: [
      { label: '候选股票', value: '47', sub: '今日新增 12', tone: 'accent' },
      { label: '强信号', value: '9', sub: 'S/A 级', tone: 'up' },
      { label: '模型一致', value: '72%', sub: '双模型共识', tone: 'down' },
      { label: '待复核', value: '6', sub: '波动过高', tone: 'warn' },
    ],
    tableTitle: '候选池排行',
    tableMeta: 'Candidate 预览',
  },
  signals: {
    title: '交易信号',
    subtitle: '信号详情 · 信号总览 · 信号历史 · 风险扫描',
    icon: <ThunderboltOutlined />,
    tabs: [
      { key: 'detail', path: '/signals', label: '信号详情', subLabel: '当前触发' },
      { key: 'overview', path: '/signals/overview', label: '信号总览', subLabel: '多源聚合' },
      { key: 'history', path: '/signals/history', label: '信号历史', subLabel: '命中复核' },
      { key: 'risk', path: '/signals/risk', label: '风险扫描', subLabel: '拦截前置' },
    ],
    metrics: [
      { label: '今日信号', value: '38', sub: '强买 9', tone: 'accent' },
      { label: '一致信号', value: '21', sub: '方向一致', tone: 'down' },
      { label: '风险提示', value: '4', sub: '需复核', tone: 'warn' },
      { label: '命中率', value: '68%', sub: '近 30 日', tone: 'up' },
    ],
    tableTitle: '信号队列',
    tableMeta: 'Signal 对象',
  },
  trade: {
    title: '交易中心',
    subtitle: '交易总览 · 下单面板 · 持仓监控 · 订单管理 · 账户总览 · 券商管理',
    icon: <WalletOutlined />,
    tabs: [
      { key: 'overview', path: '/trade', label: '交易总览', subLabel: '资产/策略' },
      { key: 'order', path: '/trade/order', label: '下单面板', subLabel: '订单草稿' },
      { key: 'positions', path: '/trade/positions', label: '持仓监控', subLabel: '仓位风险' },
      { key: 'orders', path: '/trade/orders', label: '订单管理', subLabel: '委托/成交' },
      { key: 'account', path: '/trade/account', label: '账户总览', subLabel: '资金/盈亏' },
      { key: 'brokers', path: '/trade/brokers', label: '券商管理', subLabel: 'QMT 沙箱' },
    ],
    metrics: [
      { label: '总资产', value: '1,000,000', sub: 'Paper 账户', tone: 'accent' },
      { label: '可用资金', value: '738,200', sub: '模拟盘', tone: 'down' },
      { label: '持仓市值', value: '261,800', sub: '4 只持仓', tone: 'muted' },
      { label: '风控状态', value: 'PASS', sub: '实盘未启用', tone: 'warn' },
    ],
    tableTitle: '订单草稿',
    tableMeta: 'Order + RiskVerdict',
  },
  strategy: {
    title: '方案管理',
    subtitle: '方案列表 · 方案详情 · 方案对比 · 复盘报告',
    icon: <CheckCircleOutlined />,
    tabs: [
      { key: 'list', path: '/strategy', label: '方案列表', subLabel: 'Plan 池' },
      { key: 'detail', path: '/strategy/detail', label: '方案详情', subLabel: '执行策略' },
      { key: 'compare', path: '/strategy/compare', label: '方案对比', subLabel: '收益/风险' },
      { key: 'reports', path: '/strategy/reports', label: '复盘报告', subLabel: '结算归因' },
    ],
    metrics: [
      { label: '有效方案', value: '12', sub: '私有账户', tone: 'accent' },
      { label: '待执行', value: '3', sub: '风控预检', tone: 'warn' },
      { label: '平均收益', value: '+8.6%', sub: '近 30 日', tone: 'up' },
      { label: '最大回撤', value: '-3.2%', sub: '低风险', tone: 'down' },
    ],
    tableTitle: '方案列表',
    tableMeta: 'Plan 对象',
  },
  autoTrade: {
    title: '量化交易',
    subtitle: '策略市场 · 策略配置 · 策略监控 · 策略日志',
    icon: <RobotOutlined />,
    tabs: [
      { key: 'market', path: '/auto-trade', label: '策略市场', subLabel: '模板选择' },
      { key: 'config', path: '/auto-trade/config', label: '策略配置', subLabel: '参数执行' },
      { key: 'monitor', path: '/auto-trade/monitor', label: '策略监控', subLabel: '运行状态' },
      { key: 'logs', path: '/auto-trade/logs', label: '策略日志', subLabel: '审计链路' },
    ],
    metrics: [
      { label: '运行策略', value: '5', sub: 'Paper only', tone: 'accent' },
      { label: '今日触发', value: '18', sub: '自动任务', tone: 'up' },
      { label: '暂停策略', value: '1', sub: '风险复核', tone: 'warn' },
      { label: '审计记录', value: '128', sub: '近 7 日', tone: 'muted' },
    ],
    tableTitle: '自动执行日志',
    tableMeta: 'DecisionContext lineage',
  },
  backtest: {
    title: '回测分析',
    subtitle: '总览 · 运行回测 · 回测对比 · 交易复盘',
    icon: <LineChartOutlined />,
    tabs: [
      { key: 'overview', path: '/backtest', label: '回测总览', subLabel: '绩效摘要' },
      { key: 'run', path: '/backtest/run', label: '运行回测', subLabel: '参数提交' },
      { key: 'compare', path: '/backtest/compare', label: '回测对比', subLabel: '策略比较' },
      { key: 'trades', path: '/backtest/trades', label: '交易复盘', subLabel: '逐笔复核' },
    ],
    metrics: [
      { label: '年化收益', value: '+24.8%', sub: '样本 3 年', tone: 'up' },
      { label: '最大回撤', value: '-7.3%', sub: '可接受', tone: 'down' },
      { label: '胜率', value: '62%', sub: '逐笔交易', tone: 'accent' },
      { label: '待复盘', value: '9', sub: '异常成交', tone: 'warn' },
    ],
    tableTitle: '回测交易复盘',
    tableMeta: 'Order / RiskVerdict / DecisionContext',
  },
  diagnosis: {
    title: '个股诊断',
    subtitle: '诊断入口 · 诊断总览 · 模型视角 · 多股对比 · 风险扫描',
    icon: <BarChartOutlined />,
    tabs: [
      { key: 'entry', path: '/diagnosis', label: '诊断入口', subLabel: '搜索股票' },
      { key: 'overview', path: '/diagnosis/overview', label: '诊断总览', subLabel: '五维评分' },
      { key: 'model', path: '/diagnosis/model', label: '模型视角', subLabel: 'Kronos/因子' },
      { key: 'compare', path: '/diagnosis/compare', label: '多股对比', subLabel: '横向比较' },
      { key: 'risk', path: '/diagnosis/risk', label: '风险扫描', subLabel: '事件/波动' },
    ],
    metrics: [
      { label: '综合评分', value: '82', sub: '强买', tone: 'up' },
      { label: '技术面', value: '88', sub: '趋势强', tone: 'accent' },
      { label: '资金面', value: '76', sub: '主力流入', tone: 'down' },
      { label: '风险项', value: '2', sub: '公告/波动', tone: 'warn' },
    ],
    tableTitle: '诊断因子明细',
    tableMeta: 'Diagnosis evidence',
  },
  training: {
    title: '模型训练',
    subtitle: '训练总览 · 训练任务 · MLflow 实验',
    icon: <RobotOutlined />,
    tabs: [
      { key: 'overview', path: '/training', label: '训练总览', subLabel: '任务概览' },
      { key: 'tasks', path: '/training/tasks', label: '训练任务', subLabel: '队列/调度' },
      { key: 'mlflow', path: '/training/mlflow', label: 'MLflow 实验', subLabel: '指标追踪' },
    ],
    metrics: [
      { label: '训练任务', value: '7', sub: '1 个运行中', tone: 'accent' },
      { label: '最佳 IC', value: '0.083', sub: 'Kronos V2.3', tone: 'up' },
      { label: '模型版本', value: '14', sub: '已注册', tone: 'down' },
      { label: '失败任务', value: '0', sub: '近 24h', tone: 'muted' },
    ],
    tableTitle: '训练任务队列',
    tableMeta: 'Training jobs',
  },
  modelRegistry: {
    title: '模型注册',
    subtitle: '模型版本 · 上线审批 · A/B 对比',
    icon: <ApiOutlined />,
    tabs: [
      { key: 'registry', path: '/model-registry', label: '模型注册', subLabel: '版本管理' },
    ],
    metrics: [
      { label: '已注册模型', value: '14', sub: 'Kronos/LightGBM', tone: 'accent' },
      { label: '线上模型', value: '3', sub: '灰度启用', tone: 'down' },
      { label: '待审批', value: '2', sub: '上线门禁', tone: 'warn' },
      { label: 'A/B 实验', value: '4', sub: '运行中', tone: 'up' },
    ],
    tableTitle: '模型版本列表',
    tableMeta: 'Registry',
  },
  dataUpdate: {
    title: '数据更新',
    subtitle: '总览 · 数据概览 · 全表管理 · 同步计划',
    icon: <DatabaseOutlined />,
    tabs: [
      { key: 'dashboard', path: '/data-update', label: '数据总览', subLabel: '同步状态' },
      { key: 'overview', path: '/data-update/overview', label: '数据概览', subLabel: '覆盖率' },
      { key: 'tables', path: '/data-update/tables', label: '全表管理', subLabel: '表级状态' },
      { key: 'schedule', path: '/data-update/schedule', label: '同步计划', subLabel: '任务调度' },
    ],
    metrics: [
      { label: '在线数据源', value: '6', sub: 'Tushare/PG', tone: 'down' },
      { label: '今日同步', value: '128', sub: '任务完成', tone: 'accent' },
      { label: '异常表', value: '1', sub: '需重试', tone: 'warn' },
      { label: '覆盖股票', value: '5,286', sub: 'A 股全市场', tone: 'muted' },
    ],
    tableTitle: '同步任务列表',
    tableMeta: 'Data pipeline',
  },
}

const rows = [
  ['300750', '宁德时代', '新能源', '+8.2%', '90'],
  ['688981', '中芯国际', '半导体', '+5.8%', '88'],
  ['600519', '贵州茅台', '白酒', '+3.1%', '79'],
  ['002594', '比亚迪', '汽车', '-2.1%', '72'],
]

const p0StepByModule: Partial<Record<ModuleKey, P0Step>> = {
  screener: 'candidate',
  strategy: 'plan',
  trade: 'order',
  autoTrade: 'order',
  backtest: 'review',
}

function activeKeyFromPath(config: ModuleConfig, pathname: string) {
  const exact = config.tabs.find(tab => tab.path === pathname)
  if (exact) return exact.key
  return config.tabs[0].key
}

function useOptionalAuthUser() {
  try {
    return useAuth().user
  } catch {
    return null
  }
}

function getRiskChecks(record: unknown): Array<{ rule?: string; level?: string; message?: string }> {
  const value = record as any
  return value?.risk_check?.checks
    || value?.details?.risk_check?.checks
    || value?.details?.details?.risk_check?.checks
    || []
}

function textValue(value: unknown, fallback = '---') {
  if (value == null || value === '') return fallback
  return String(value)
}

function GenericModuleContent({ moduleKey, config, activeTab }: { moduleKey: ModuleKey; config: ModuleConfig; activeTab: ModuleTab }) {
  return (
    <div className="row r-6-4">
      <PrototypeCard title={config.tableTitle} icon={config.icon} meta={config.tableMeta}>
        <table className="tbl">
          <thead>
            <tr>
              <th>代码/对象</th>
              <th>名称</th>
              <th>分类</th>
              <th className="r">变化</th>
              <th className="r">评分</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={`${moduleKey}-${row[0]}`}>
                <td className="code">{row[0]}</td>
                <td className="nm">{row[1]}</td>
                <td>{row[2]}</td>
                <td className={`r ${row[3].startsWith('-') ? 'down' : 'up'}`}>{row[3]}</td>
                <td className="r mono">{row[4]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PrototypeCard>
      <ModuleSideRail moduleKey={moduleKey} activeTab={activeTab} />
    </div>
  )
}

function ModuleSideRail({ moduleKey, activeTab }: { moduleKey: ModuleKey; activeTab: ModuleTab }) {
  return (
    <div className="grid">
      <PrototypeCard title="当前页工作台" icon={<ThunderboltOutlined />} meta={activeTab.subLabel}>
        <div className="op-hint">
          <div className="pos neu">{activeTab.key.toUpperCase().slice(0, 3)}</div>
          <div>
            <div className="op-title">{activeTab.label}</div>
            <div className="op-desc">
              公共行情数据共享；方案、订单、风控和复盘记录按租户、用户、账户隔离。
            </div>
          </div>
        </div>
      </PrototypeCard>
      <PrototypeCard title="链路对象" icon={<SafetyCertificateOutlined />}>
        <div className="chips">
          <span className="chip active">DecisionContext</span>
          <span className="chip active">Candidate</span>
          <span className="chip active">Plan</span>
          <span className="chip active">Order</span>
          <span className="chip active">RiskVerdict</span>
        </div>
      </PrototypeCard>
      {moduleKey === 'trade' && (
        <PrototypeCard title="下单安全门" icon={<WalletOutlined />} meta="默认仅模拟盘">
          <SegmentTabs
            ariaLabel="交易模式"
            activeKey="paper"
            onChange={() => undefined}
            items={[{ key: 'paper', label: '模拟盘' }, { key: 'live', label: '实盘锁定' }]}
          />
          <div className="prototype-panel-note" style={{ marginTop: 12 }}>
            实盘/QMT 提交保持关闭；只有明确配置券商、账户和风控结论后才开放。
          </div>
        </PrototypeCard>
      )}
    </div>
  )
}

function ScreenerContent() {
  const [modes, setModes] = useState<ScreenerMode[]>([
    { id: 'bi_trend_launch', name: '毕师傅趋势启动', cycle: '短线' },
    { id: 'multi_factor_value', name: '多因子价值型', cycle: '日频' },
  ])
  const [selectedMode, setSelectedMode] = useState('bi_trend_launch')
  const [picks, setPicks] = useState<ScreenerPick[]>([])
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    screenerApi.getModes()
      .then(response => {
        const nextModes = (response.data as any)?.modes || []
        if (nextModes.length) {
          setModes(nextModes)
          setSelectedMode(nextModes[0].id)
        }
      })
      .catch(() => undefined)
  }, [])

  const runScreener = async () => {
    setLoading(true)
    try {
      const response = await screenerApi.run(selectedMode, 47)
      setPicks((response.data as any)?.picks || [])
    } finally {
      setLoading(false)
    }
  }

  const fallbackPicks: ScreenerPick[] = rows.map(row => ({
    code: row[0],
    name: row[1],
    score: Number(row[4]),
    hard_tech: { track: row[2], tier: 'watch' },
    entry_reason: '模型共振结果已进入候选池复核',
    risk_flags: [],
    factor_breakdown: {},
  }))
  const visiblePicks: ScreenerPick[] = picks.length ? picks : fallbackPicks

  return (
    <div className="row r-6-4">
      <PrototypeCard title="候选池排行" icon={<FundOutlined />} meta="Candidate">
        <div className="mode-grid">
          {modes.map(mode => (
            <button
              type="button"
              key={mode.id}
              className={`mode-card${selectedMode === mode.id ? ' on' : ''}`}
              onClick={() => setSelectedMode(mode.id)}
            >
              <div className="mc-name">{mode.name}</div>
              <div className="mc-meta">{mode.cycle || '日频'} · 账户私有候选</div>
            </button>
          ))}
        </div>
        <div className="filter-bar">
          <button type="button" className="btn primary" onClick={runScreener}>
            {loading ? '运行中...' : '开始选股'}
          </button>
          <button type="button" className="btn ghost" onClick={() => setExpanded(value => !value)}>
            展开四轴解释
          </button>
        </div>
        <table className="tbl">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>硬科技赛道</th>
              <th>层级</th>
              <th className="r">评分</th>
            </tr>
          </thead>
          <tbody>
            {visiblePicks.map((pick, index) => (
              <tr key={pick.code || index}>
                <td className="code">{pick.code}</td>
                <td className="nm">{pick.name}</td>
                <td>{pick.hard_tech?.track || '综合'}</td>
                <td>{pick.hard_tech?.tier || pick.grade || 'watch'}</td>
                <td className="r mono">{pick.score ?? '--'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {expanded && visiblePicks[0] && (
          <div className="prototype-fallback mt14">
            <div className="nm">{visiblePicks[0].entry_reason}</div>
            <div className="chips mt14">
              {(visiblePicks[0].risk_flags || []).map(flag => <span className="chip" key={flag}>{flag}</span>)}
              {Object.entries(visiblePicks[0].factor_breakdown || {}).map(([key, value]) => (
                <span className="chip active" key={key}>
                  {key === 'hard_tech_conviction' ? '硬科技' : key === 'startup_quality' ? '启动质量' : key} {Number(value).toFixed(1)}
                </span>
              ))}
            </div>
          </div>
        )}
      </PrototypeCard>
      <ModuleSideRail moduleKey="screener" activeTab={{ key: 'candidate', path: '/screener', label: '候选池', subLabel: '模型选股' }} />
    </div>
  )
}

function TradeContent() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useOptionalAuthUser()
  const liveTrade = useLiveTrade()
  const query = useMemo(() => new URLSearchParams(location.search), [location.search])
  const [code, setCode] = useState(query.get('code') || '')
  const [price, setPrice] = useState(query.get('price') ? Number(query.get('price')).toFixed(2) : '10.00')
  const [volume, setVolume] = useState('')
  const [decisionContextId, setDecisionContextId] = useState(query.get('decision_context_id') || '')
  const [candidateId, setCandidateId] = useState(query.get('candidate_id') || '')
  const [planId, setPlanId] = useState(query.get('plan_id') || '')
  const [error, setError] = useState('')
  const [riskVerdict, setRiskVerdict] = useState<any>(null)
  const accountId = user?.defaultTradeAccountId || 'paper-u-default'

  useEffect(() => {
    if (liveTrade.mode !== 'paper') {
      liveTrade.setMode('paper')
    }
  }, [liveTrade.mode, liveTrade.setMode])

  const submitOrder = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    const numericVolume = Number(volume)
    if (!/^\d{6}$/.test(code)) {
      setError('股票代码为 6 位数字')
      return
    }
    if (!Number.isFinite(numericVolume) || numericVolume <= 0 || numericVolume % 100 !== 0) {
      setError('数量须为 100 的整数倍')
      return
    }

    const params: OrderParams = {
      code,
      direction: 'BUY',
      price: Number(price) || 0,
      volume: numericVolume,
      trade_mode: 'paper',
      decision_context_id: decisionContextId || undefined,
      candidate_id: candidateId || undefined,
      plan_id: planId || undefined,
    }
    const result = await liveTrade.placeOrder(params, {
      onPreCheckFailed: (preCheck: PreCheckResult) => setRiskVerdict({ result: 'reject', risk_check: preCheck }),
      onLargeOrderConfirm: async () => false,
    })
    if (result.success) {
      setRiskVerdict(result.data?.risk_verdict || result.data)
    } else if (result.error) {
      setError(result.error)
    }
  }

  const riskChecks = getRiskChecks(riskVerdict)
  const riskQuery = new URLSearchParams()
  if (decisionContextId || riskVerdict?.decision_context_id) riskQuery.set('decision_context_id', decisionContextId || riskVerdict.decision_context_id)
  if (riskVerdict?.order_id) riskQuery.set('order_id', riskVerdict.order_id)
  if (planId || riskVerdict?.plan_id) riskQuery.set('plan_id', planId || riskVerdict.plan_id)
  if (candidateId || riskVerdict?.candidate_id) riskQuery.set('candidate_id', candidateId || riskVerdict.candidate_id)
  if (code || riskVerdict?.symbol) riskQuery.set('code', code || riskVerdict.symbol)

  return (
    <div className="row r-6-4">
      <PrototypeCard title="下单面板" icon={<WalletOutlined />} meta="Order draft">
        <form onSubmit={submitOrder}>
          <div className="row r-1-1">
            <div className="field">
              <label>券商账户</label>
              <input className="inp mono" value={accountId} readOnly />
            </div>
            <div className="field">
              <label>交易模式</label>
              <input className="inp" value={liveTrade.mode === 'live' ? '实盘锁定' : '模拟盘'} readOnly />
            </div>
          </div>
          <div className="row r-1-1">
            <div className="field">
              <label>股票代码</label>
              <input className="inp mono" placeholder="000001" value={code} onChange={event => setCode(event.target.value)} />
            </div>
            <div className="field">
              <label>价格</label>
              <input role="spinbutton" aria-label="价格" className="inp mono" value={price} onChange={event => setPrice(event.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>数量</label>
            <input type="number" aria-label="数量" className="inp mono" value={volume} onChange={event => setVolume(event.target.value)} />
          </div>
          <div className="row r-1-1">
            <div className="field">
              <label>DecisionContext</label>
              <input className="inp mono" placeholder="CTX-" value={decisionContextId} onChange={event => setDecisionContextId(event.target.value)} />
            </div>
            <div className="field">
              <label>Candidate</label>
              <input className="inp mono" placeholder="CAND-" value={candidateId} onChange={event => setCandidateId(event.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>Plan</label>
            <input className="inp mono" placeholder="PLAN-" value={planId} onChange={event => setPlanId(event.target.value)} />
          </div>
          {error && <div className="tag t-warn" style={{ marginBottom: 12 }}>{error}</div>}
          <div className="chips">
            <button type="submit" className="btn primary">下单</button>
          </div>
        </form>
      </PrototypeCard>
      <div className="grid">
        <PrototypeCard title="下单安全门" icon={<SafetyCertificateOutlined />} meta="默认仅模拟盘">
          <SegmentTabs
            ariaLabel="交易模式"
            activeKey="paper"
            onChange={() => undefined}
            items={[{ key: 'paper', label: '模拟盘' }, { key: 'live', label: '实盘锁定' }]}
          />
          <div className="prototype-panel-note" style={{ marginTop: 12 }}>
            实盘/QMT 提交保持关闭；当前只提交模拟盘订单，实盘必须经过券商配置与风控判定。
          </div>
        </PrototypeCard>
        {riskVerdict && (
          <PrototypeCard title="风控判定" icon={<SafetyCertificateOutlined />} meta={textValue(riskVerdict.verdict_id)}>
            <div className="chips">
              <span className="chip active">{textValue(riskVerdict.verdict_id)}</span>
              <span className="chip">{textValue(riskVerdict.result)}</span>
              <span className="chip">{riskChecks.length} 条规则</span>
              <span className="chip">{textValue(riskVerdict.candidate_id || candidateId)}</span>
            </div>
            <table className="tbl mt14">
              <tbody>
                <tr><td>来源</td><td>{textValue(riskVerdict.plan_id || planId)}</td></tr>
                <tr><td>Candidate</td><td>{textValue(riskVerdict.candidate_id || candidateId)}</td></tr>
                <tr><td>Plan</td><td>{textValue(riskVerdict.plan_id || planId)}</td></tr>
              </tbody>
            </table>
            <button type="button" className="btn sm mt14" onClick={() => navigate(`/trade/risk-verdicts?${riskQuery.toString()}`)}>
              查看风控
            </button>
          </PrototypeCard>
        )}
      </div>
    </div>
  )
}

function AutoTradeContent() {
  const navigate = useNavigate()
  const [strategies, setStrategies] = useState<AutoStrategy[]>([])
  const [logs, setLogs] = useState<AutoLog[]>([])

  useEffect(() => {
    api.get('/strategy/list')
      .then(response => setStrategies((response.data as any)?.strategies || []))
      .catch(() => setStrategies([]))
  }, [])

  const openDetail = async (strategy: AutoStrategy) => {
    await api.get(`/strategy/${strategy.id}`).catch(() => undefined)
    const logResponse = await api.get(`/strategy/${strategy.id}/log`)
    setLogs((logResponse.data as any)?.logs || [])
  }

  const navigateRisk = (details: Record<string, string | number | undefined> = {}) => {
    const params = new URLSearchParams()
    if (details.decision_context_id) params.set('decision_context_id', String(details.decision_context_id))
    if (details.order_id) params.set('order_id', String(details.order_id))
    if (details.plan_id) params.set('plan_id', String(details.plan_id))
    if (details.candidate_id) params.set('candidate_id', String(details.candidate_id))
    if (details.code) params.set('code', String(details.code))
    navigate(`/trade/risk-verdicts?${params.toString()}`)
  }

  return (
    <div className="row r-6-4">
        <PrototypeCard title="自动交易策略" icon={<RobotOutlined />} meta="模拟盘执行">
        <table className="tbl">
          <thead>
            <tr>
              <th>策略</th>
              <th>模式</th>
              <th>状态</th>
              <th className="r">候选</th>
              <th className="r">操作</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map(strategy => (
              <tr key={strategy.id}>
                <td className="nm">{strategy.name}</td>
                <td>{strategy.trade_mode || 'paper'}</td>
                <td>{strategy.status || 'active'}</td>
                <td className="r mono">{strategy.picks_count ?? 0}</td>
                <td className="r"><button type="button" className="btn sm" onClick={() => openDetail(strategy)}>详情</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </PrototypeCard>
      <PrototypeCard title="执行日志" icon={<SafetyCertificateOutlined />} meta="Lineage">
        {logs.length === 0 && <div className="prototype-panel-note">选择策略后展示自动执行日志。</div>}
        {logs.map((log, index) => (
          <div className="prototype-fallback" key={`${log.timestamp}-${index}`} style={{ marginBottom: 10 }}>
            <div className="nm">{log.message}</div>
            <div className="chips mt14">
              {log.details?.decision_context_id && <span className="chip active">{log.details.decision_context_id}</span>}
              {log.details?.plan_id && <span className="chip">{log.details.plan_id}</span>}
              {log.details?.candidate_id && <span className="chip">{log.details.candidate_id}</span>}
            </div>
            <button type="button" className="btn sm mt14" onClick={() => navigateRisk(log.details)}>风控</button>
          </div>
        ))}
      </PrototypeCard>
    </div>
  )
}

function BacktestContent({ activeKey }: { activeKey: string }) {
  const [reviewRows, setReviewRows] = useState<ReviewRow[]>([])

  useEffect(() => {
    if (activeKey !== 'trades') return
    Promise.all([
      tradeApi.getOrders(),
      tradeApi.getRiskVerdicts({ page: 1, page_size: 50 }),
      tradeApi.getDecisionContexts({ page: 1, page_size: 50 }),
    ])
      .then(([ordersResponse, verdictsResponse, contextsResponse]) => {
        const orders = (ordersResponse.data as any)?.orders || []
        const verdicts = (verdictsResponse.data as any)?.records || []
        const contexts = (contextsResponse.data as any)?.records || []
        const nextRows = orders.map((order: any) => {
          const verdict = verdicts.find((item: RiskVerdictRecord) => item.order_id === (order.order_id || order.id))
            || verdicts.find((item: RiskVerdictRecord) => item.decision_context_id === order.decision_context_id)
            || {}
          const context = contexts.find((item: any) => item.decision_context_id === (order.decision_context_id || verdict.decision_context_id))
            || {}
          return {
            orderId: order.order_id || order.id || '---',
            verdictId: verdict.verdict_id || '---',
            decisionContextId: order.decision_context_id || verdict.decision_context_id || context.decision_context_id || '---',
            planId: order.plan_id || verdict.plan_id || context.plan_id || '---',
            candidateId: order.candidate_id || verdict.candidate_id || context.candidate_id || '---',
            reason: context.payload?.reason || '等待复盘归因',
          }
        })
        setReviewRows(nextRows)
      })
      .catch(() => setReviewRows([]))
  }, [activeKey])

  if (activeKey !== 'trades') {
    return <GenericModuleContent moduleKey="backtest" config={configs.backtest} activeTab={configs.backtest.tabs.find(tab => tab.key === activeKey) || configs.backtest.tabs[0]} />
  }

  return (
    <div className="row r-6-4">
      <PrototypeCard title="交易复盘链路" icon={<LineChartOutlined />} meta="Order / RiskVerdict / DecisionContext">
        <table className="tbl">
          <thead>
            <tr>
              <th>Order</th>
              <th>RiskVerdict</th>
              <th>DecisionContext</th>
              <th>Plan</th>
              <th>Candidate</th>
            </tr>
          </thead>
          <tbody>
            {reviewRows.map(row => (
              <tr key={row.orderId}>
                <td className="code">{row.orderId}</td>
                <td className="code">{row.verdictId}</td>
                <td className="code">{row.decisionContextId}</td>
                <td className="code">{row.planId}</td>
                <td className="code">{row.candidateId}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PrototypeCard>
      <PrototypeCard title="复盘归因" icon={<SafetyCertificateOutlined />} meta="Lineage reason">
        {reviewRows.map(row => (
          <div className="prototype-fallback" key={`${row.orderId}-reason`} style={{ marginBottom: 10 }}>
            {row.reason}
          </div>
        ))}
      </PrototypeCard>
    </div>
  )
}

function DataUpdateContent() {
  const [status, setStatus] = useState<any>(null)

  useEffect(() => {
    signalApi.getDataStatus().then(response => setStatus(response.data)).catch(() => undefined)
    signalApi.getSyncSchedules().catch(() => undefined)
  }, [])

  const sources = status?.sources || []
  const okText = status ? `${status.active_tables}/${status.total_tables} 表正常` : '等待数据服务'

  return (
    <div className="row r-6-4">
      <PrototypeCard title="数据源状态" icon={<DatabaseOutlined />} meta={okText}>
        <table className="tbl">
          <thead>
            <tr>
              <th>数据表</th>
              <th>来源</th>
              <th>更新</th>
              <th className="r">行数</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source: any) => (
              <tr key={source.key}>
                <td className="nm">{source.name}</td>
                <td>{source.source}</td>
                <td>{source.update}</td>
                <td className="r mono">{source.rows}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PrototypeCard>
      <ModuleSideRail moduleKey="dataUpdate" activeTab={configs.dataUpdate.tabs[0]} />
    </div>
  )
}

function renderModuleContent(moduleKey: ModuleKey, config: ModuleConfig, activeKey: string, activeTab: ModuleTab) {
  if (moduleKey === 'screener') return <ScreenerContent />
  if (moduleKey === 'trade') return <TradeContent />
  if (moduleKey === 'autoTrade') return <AutoTradeContent />
  if (moduleKey === 'backtest') return <BacktestContent activeKey={activeKey} />
  if (moduleKey === 'dataUpdate') return <DataUpdateContent />
  return <GenericModuleContent moduleKey={moduleKey} config={config} activeTab={activeTab} />
}

export default function NewUiModulePage({ moduleKey }: { moduleKey: ModuleKey }) {
  const config = configs[moduleKey]
  const location = useLocation()
  const navigate = useNavigate()
  const [localActiveKey, setLocalActiveKey] = useState<string | null>(null)
  const routeActiveKey = activeKeyFromPath(config, location.pathname)
  const activeKey = localActiveKey || routeActiveKey
  const activeTab = config.tabs.find(tab => tab.key === activeKey) ?? config.tabs[0]
  const p0Step = p0StepByModule[moduleKey]

  useEffect(() => {
    setLocalActiveKey(null)
  }, [location.pathname, moduleKey])

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel={`${config.title}页签`}
        activeKey={activeKey}
        onChange={(key) => {
          const tab = config.tabs.find(item => item.key === key)
          if (!tab) return
          setLocalActiveKey(key)
          if (!(moduleKey === 'backtest' && key === 'trades')) {
            navigate(tab.path)
          }
        }}
        items={config.tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`${config.title} - ${activeTab.label}`}
        subtitle={config.subtitle}
        actions={[
          { key: 'shared', label: '公共数据' },
          { key: 'private', label: '账户私有', active: true, tone: 'neutral' },
          { key: 'paper', label: moduleKey === 'trade' ? '模拟盘安全' : '真实数据接入', tone: 'warn' },
        ]}
      />
      {p0Step && <P0WorkflowNav currentStep={p0Step} />}
      <div className="kpis">
        {config.metrics.map(item => (
          <MetricCard key={item.label} label={item.label} value={item.value} sub={item.sub} tone={item.tone} />
        ))}
      </div>
      {renderModuleContent(moduleKey, config, activeKey, activeTab)}
    </PrototypePage>
  )
}
