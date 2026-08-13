import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AlertOutlined, AuditOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Modal } from 'antd'
import { signalApi, strategyApi, tradeApi } from '../api/client'
import type { DecisionContextRecord, Position, RiskVerdictRecord, SignalLiveResponse, CircuitBreakerStatus, AuditLogRecord } from '../api/types'
import { P0WorkflowNav } from '../components/layout'
import {
  DataDomainBadge,
  DataFreshnessBar,
  EmptyState,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SideRail,
} from '../components/prototype'

const tabs = [
  { key: 'dashboard', path: '/risk', label: '风控总览', subLabel: '风险闸门' },
  { key: 'overview', path: '/risk/overview', label: '风险总览', subLabel: '组合暴露' },
  { key: 'positions', path: '/risk/positions', label: '持仓风险', subLabel: '集中度' },
  { key: 'strategies', path: '/risk/strategies', label: '策略风险', subLabel: '回撤' },
  { key: 'market', path: '/risk/market', label: '市场风险', subLabel: '事件/波动' },
  { key: 'audit', path: '/risk/audit', label: '事件审计', subLabel: '留痕' },
]

function activeKey(pathname: string) {
  const last = pathname.split('/').filter(Boolean).pop()
  if (last && tabs.some(tab => tab.key === last)) return last
  return 'dashboard'
}

interface RiskConfig {
  max_position_pct?: number
  max_single_amount?: number
  price_limit_pct?: number
  large_order_threshold?: number
}

interface StrategyInstance {
  id: string
  name?: string
  status?: string
  daily_loss_limit_pct?: number
  stop_loss_pct?: number
  risk_rules?: {
    daily_max_loss_pct?: number
    stop_loss_pct?: number
  }
}

function resultClass(result: string) {
  if (result === 'pass') return 'up'
  if (result === 'warn' || result === 'manual_review') return 'warn'
  return 'down'
}

function percent(value?: number) {
  if (typeof value !== 'number') return '-'
  const normalized = value <= 1 ? value * 100 : value
  return `${Math.round(normalized)}%`
}

/** 熔断器返回的是 0-100 刻度百分比（如 5.0 表示 5%），直接格式化不再归一化。 */
function pct100(value?: number) {
  if (typeof value !== 'number') return '-'
  return `${Number(value.toFixed(1))}%`
}

function ruleText(record: RiskVerdictRecord) {
  const details = record.details as any
  const checks = details?.risk_check?.checks || details?.checks || []
  const first = Array.isArray(checks) ? checks[0] : undefined
  return first?.rule || first?.name || details?.message || record.scope
}

function stopDistancePct(position: Position) {
  if (typeof position.stop_loss !== 'number' || position.stop_loss <= 0) return undefined
  if (typeof position.current_price !== 'number') return undefined
  return ((position.current_price - position.stop_loss) / position.stop_loss) * 100
}

function strategyStatusClass(status?: string) {
  if (status === 'active' || status === 'running') return 'up'
  if (status === 'paused') return 'warn'
  return 'down'
}

function strategyRiskPct(row: StrategyInstance, key: 'daily' | 'stop') {
  const value = key === 'daily'
    ? row.daily_loss_limit_pct ?? row.risk_rules?.daily_max_loss_pct
    : row.stop_loss_pct ?? row.risk_rules?.stop_loss_pct
  return percent(value)
}

function breakerBannerStatus(status?: string): 'pass' | 'warn' | 'reject' | 'review' {
  if (status === 'TRIGGERED') return 'reject'
  if (status === 'HALF_OPEN') return 'review'
  return 'pass'
}

function auditTime(value?: string) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

export default function RiskControl() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const [verdicts, setVerdicts] = useState<RiskVerdictRecord[]>([])
  const [contexts, setContexts] = useState<DecisionContextRecord[]>([])
  const [riskConfig, setRiskConfig] = useState<RiskConfig>({})
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([])
  const [breaker, setBreaker] = useState<CircuitBreakerStatus | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [strategies, setStrategies] = useState<StrategyInstance[]>([])
  const [marketSummary, setMarketSummary] = useState<SignalLiveResponse['summary'] | null>(null)
  const [strategyMessage, setStrategyMessage] = useState('')
  const [strategyMessageOk, setStrategyMessageOk] = useState(true)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let mounted = true
    Promise.allSettled([
      tradeApi.getRiskVerdicts({ page: 1, page_size: 20 }),
      tradeApi.getDecisionContexts({ page: 1, page_size: 20 }),
      tradeApi.getAuditLogs({ page: 1, page_size: 20 }),
      tradeApi.getRiskConfig(),
      tradeApi.getCircuitBreakerStatus(),
      tradeApi.getPositions(),
      strategyApi.listInstances(),
      signalApi.getLive(),
    ]).then(([verdictResponse, contextResponse, auditResponse, configResponse, breakerResponse, positionResponse, strategyResponse, marketResponse]) => {
        if (!mounted) return
        if (verdictResponse.status === 'fulfilled') setVerdicts(verdictResponse.value.data?.records || [])
        if (contextResponse.status === 'fulfilled') setContexts(contextResponse.value.data?.records || [])
        if (auditResponse.status === 'fulfilled') {
          setAuditTotal(auditResponse.value.data?.total || auditResponse.value.data?.records?.length || 0)
          setAuditLogs(auditResponse.value.data?.records || [])
        }
        if (configResponse.status === 'fulfilled') setRiskConfig((configResponse.value.data as RiskConfig) || {})
        if (breakerResponse.status === 'fulfilled') {
          const breakers = breakerResponse.value.data?.breakers || []
          setBreaker(breakers[0] || null)
        }
        if (positionResponse.status === 'fulfilled') setPositions(positionResponse.value.data?.positions || [])
        if (strategyResponse.status === 'fulfilled') setStrategies(strategyResponse.value.data?.strategies || [])
        if (marketResponse.status === 'fulfilled') setMarketSummary(marketResponse.value.data?.summary || null)
        const failed = [verdictResponse, contextResponse, auditResponse, configResponse, breakerResponse, positionResponse, strategyResponse, marketResponse].filter(result => result.status === 'rejected').length
        setLoadError(failed > 0 ? `${failed} 个风控数据接口连接异常` : '')
      })
    return () => {
      mounted = false
    }
  }, [])

  const toggleStrategy = (row: StrategyInstance) => {
    const paused = row.status === 'paused'
    const label = paused ? '恢复' : '暂停'
    Modal.confirm({
      title: `${label}策略「${row.name || row.id}」？`,
      content: paused ? '恢复后策略重新参与自动交易执行，风控规则保持生效。' : '暂停后策略停止新开仓，已有持仓与止损规则保持不变。',
      okText: label,
      cancelText: '取消',
      onOk: async () => {
        const call = paused ? strategyApi.resumeInstance(row.id) : strategyApi.pauseInstance(row.id)
        const response = await call.catch(() => null)
        if (!response?.data) {
          setStrategyMessageOk(false)
          setStrategyMessage(`${label}接口连接异常`)
          return
        }
        const status = response.data.status
        setStrategyMessageOk(true)
        setStrategyMessage(response.data.message || `${label}已提交`)
        setStrategies(current => current.map(item => item.id === row.id ? { ...item, status: status || (paused ? 'active' : 'paused') } : item))
      },
    })
  }

  const blocked = verdicts.filter(row => row.result === 'reject' || row.result === 'manual_review').length
  const passed = verdicts.filter(row => row.result === 'pass').length
  const passRate = verdicts.length ? Math.round((passed / verdicts.length) * 100) : 0
  const warningCount = verdicts.filter(row => row.result === 'warn').length
  const firstVerdict = verdicts[0]
  const firstContext = contexts[0] as (DecisionContextRecord & { updated_at?: string; created_at?: string }) | undefined
  const firstRiskVerdict = firstVerdict as (RiskVerdictRecord & { updated_at?: string; created_at?: string; trade_date?: string }) | undefined

  const pausedCount = strategies.filter(row => row.status === 'paused').length
  const budgetRemainingPct = breaker && typeof breaker.daily_loss_pct === 'number' && typeof breaker.threshold_pct === 'number' && breaker.threshold_pct > 0
    ? Math.max(0, Math.round((1 - breaker.daily_loss_pct / breaker.threshold_pct) * 100))
    : undefined
  const nearStopPositions = positions.filter(position => {
    const distance = stopDistancePct(position)
    return typeof distance === 'number' && distance < 3
  })
  const bullCount = (marketSummary?.strong_buy_count || 0) + (marketSummary?.buy_count || 0)
  const bearCount = (marketSummary?.sell_count || 0) + (marketSummary?.strong_sell_count || 0)
  const defenseLayers: Array<{ layer: string; name: string; status: string; tone: string; metric: string }> = [
    {
      layer: 'L1',
      name: '交易前置',
      status: blocked > 0 ? '拦截生效' : '放行正常',
      tone: blocked > 0 ? 'warn' : 'up',
      metric: `近 ${verdicts.length || 20} 单拦截 ${blocked} 笔`,
    },
    {
      layer: 'L2',
      name: '策略执行',
      status: pausedCount > 0 ? `${pausedCount} 个策略暂停` : '全部运行',
      tone: pausedCount > 0 ? 'warn' : 'up',
      metric: `运行策略 ${strategies.length} 个`,
    },
    {
      layer: 'L3',
      name: '全局熔断',
      status: breaker ? (breaker.status || '未知') : '状态未知',
      tone: breaker ? (breaker.status === 'NORMAL' ? 'up' : breaker.status === 'HALF_OPEN' ? 'warn' : 'down') : 'warn',
      metric: `今日亏损 ${pct100(breaker?.daily_loss_pct)} / 阈值 ${pct100(breaker?.threshold_pct)}`,
    },
    {
      layer: 'L4',
      name: '市场环境',
      status: marketSummary ? (bearCount > bullCount ? '偏空' : '偏多/中性') : '状态未知',
      tone: !marketSummary ? 'warn' : bearCount > bullCount ? 'warn' : 'up',
      metric: `多头 ${bullCount} / 空头 ${bearCount}`,
    },
  ]

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="风控中心页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ key: tab.key, label: tab.label, subLabel: tab.subLabel, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`风控中心 - ${activeTab.label}`}
        subtitle="订单前置拦截 · 持仓暴露 · 策略回撤 · 事件审计"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={firstRiskVerdict?.trade_date}
            updatedAt={firstRiskVerdict?.updated_at || firstRiskVerdict?.created_at || firstContext?.updated_at || firstContext?.created_at}
            source="trade/risk"
          />
        )}
        actions={[
          { key: 'paper', label: '模拟盘风控', active: true },
          { key: 'live', label: '实盘强制预检', tone: 'warn' },
          { key: 'audit', label: '全链路留痕', tone: 'neutral' },
        ]}
      />
      <P0WorkflowNav currentStep="risk" />

      <div className="kpis">
        <MetricCard label="今日拦截" value={String(blocked)} sub={`预警 ${warningCount} 笔`} tone="warn" />
        <MetricCard label="风险通过率" value={`${passRate}%`} sub="RiskVerdict" tone="up" />
        <MetricCard label="单票上限" value={percent(riskConfig.max_position_pct)} sub="risk-config" tone="accent" />
        <MetricCard label="审计留痕" value={String(auditTotal)} sub="audit-logs" tone="muted" />
      </div>
      {loadError && <RiskBanner status="warn" title="风控服务异常" detail={loadError} />}

      {active === 'dashboard' && (
        <>
          {breaker ? (
            <RiskBanner
              status={breakerBannerStatus(breaker.status)}
              title={`熔断状态 ${breaker.status || '未知'}`}
              detail={`今日亏损 ${pct100(breaker.daily_loss_pct)} / 阈值 ${pct100(breaker.threshold_pct)} · 亏损预算剩余 ${typeof budgetRemainingPct === 'number' ? `${budgetRemainingPct}%` : '-'} · ${breaker.can_trade ? '允许交易' : '禁止开仓'}`}
            />
          ) : (
            <RiskBanner status="warn" title="熔断状态未获取" detail="trade/circuit-breaker/status 未返回熔断器状态，L3 全局熔断层状态未知。" />
          )}
          <div className="row r-6-4">
            <PrototypeCard title="风控闸门概览" icon={<SafetyCertificateOutlined />} meta="Risk Gate">
              <table className="tbl">
                <thead><tr><th>规则</th><th>作用域</th><th>结果</th><th className="r">说明</th></tr></thead>
                <tbody>
                  <tr><td className="nm">单票仓位</td><td>Account</td><td className="up">{percent(riskConfig.max_position_pct)}</td><td className="r">来自 trade/risk-config</td></tr>
                  <tr><td className="nm">大单阈值</td><td>Order</td><td className="warn">{riskConfig.large_order_threshold ?? '-'}</td><td className="r">超过阈值需复核</td></tr>
                  <tr><td className="nm">RiskVerdict</td><td>Order</td><td className={blocked ? 'down' : 'up'}>{blocked ? 'blocked' : 'pass'}</td><td className="r">近 20 条判定</td></tr>
                </tbody>
              </table>
            </PrototypeCard>
            <SideRail title="闸门结论" meta="Order Gate">
              <DataDomainBadge domain="account" label="账户级风控" />
              <RiskBanner status="warn" title="实盘保持锁定" detail="所有实盘订单必须经过券商连接、风控判定和人工确认。" />
            </SideRail>
          </div>
          <PrototypeCard title="四层防御状态" icon={<SafetyCertificateOutlined />} meta="Defense Layers">
            <table className="tbl">
              <thead><tr><th>层级</th><th>防线</th><th>状态</th><th className="r">指标</th></tr></thead>
              <tbody>
                {defenseLayers.map(layer => (
                  <tr key={layer.layer}>
                    <td className="nm">{layer.layer}</td>
                    <td>{layer.name}</td>
                    <td className={layer.tone}>{layer.status}</td>
                    <td className="r">{layer.metric}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrototypeCard>
        </>
      )}

      {active === 'overview' && (
        <>
          <PrototypeCard title="组合风险暴露" icon={<AlertOutlined />} meta="Portfolio">
            {[
              ['单票仓位上限', parseFloat(percent(riskConfig.max_position_pct)) || 0, 'var(--warn)'],
              ['涨跌价差限制', parseFloat(percent(riskConfig.price_limit_pct)) || 0, 'var(--accent)'],
              ['风险通过率', passRate, 'var(--up)'],
              ['人工复核占比', verdicts.length ? Math.round(((warningCount + blocked) / verdicts.length) * 100) : 0, 'var(--down)'],
            ].map(([label, value, color]) => (
              <div className="dim-row" key={String(label)}>
                <div className="dim-lbl">{label}</div>
                <div className="dim-bar-wrap"><div className="dim-bar" style={{ width: `${Number(value) * 3}%`, background: String(color) }} /></div>
                <div className="dim-val">{value}%</div>
              </div>
            ))}
          </PrototypeCard>
          <PrototypeCard title="策略风控状态" icon={<SafetyCertificateOutlined />} meta="Strategy Risk">
            <table className="tbl">
              <thead><tr><th>策略</th><th>状态</th><th className="r">日亏损上限</th><th className="r">单票止损</th></tr></thead>
              <tbody>
                {strategies.map(row => (
                  <tr key={row.id}>
                    <td className="nm">{row.name || row.id}</td>
                    <td className={strategyStatusClass(row.status)}>{row.status || 'active'}</td>
                    <td className="r mono">{strategyRiskPct(row, 'daily')}</td>
                    <td className="r mono">{strategyRiskPct(row, 'stop')}</td>
                  </tr>
                ))}
                {strategies.length === 0 && <tr><td colSpan={4} className="prototype-panel-note">暂无策略实例。</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>
        </>
      )}

      {active === 'positions' && (
        <>
          <PrototypeCard title="持仓风险" icon={<SafetyCertificateOutlined />} meta="Position">
            <table className="tbl">
              <thead><tr><th>标的</th><th>风险</th><th className="r">仓位</th><th className="r">动作</th></tr></thead>
              <tbody>
                {verdicts.map(row => (
                  <tr key={row.verdict_id}>
                    <td className="nm">{row.symbol || row.candidate_id || '-'}</td>
                    <td>{ruleText(row)}</td>
                    <td className="r mono">{percent(riskConfig.max_position_pct)}</td>
                    <td className={`r ${resultClass(row.result)}`}>{row.result}</td>
                  </tr>
                ))}
                {verdicts.length === 0 && <tr><td colSpan={4} className="prototype-panel-note">暂无风控判定记录。</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>
          <PrototypeCard title="止损逼近告警" icon={<AlertOutlined />} meta="Stop Loss">
            {nearStopPositions.length > 0 && (
              <RiskBanner status="warn" title={`${nearStopPositions.length} 个持仓逼近止损线`} detail="距离止损位不足 3%，已标红高亮，请优先处理。" />
            )}
            <table className="tbl">
              <thead><tr><th>标的</th><th className="r">现价</th><th className="r">止损价</th><th className="r">距止损</th><th className="r">浮动盈亏</th></tr></thead>
              <tbody>
                {positions.map(position => {
                  const distance = stopDistancePct(position)
                  const near = typeof distance === 'number' && distance < 3
                  return (
                    <tr key={position.code}>
                      <td className="nm">{position.name ? `${position.name} ${position.code}` : position.code}</td>
                      <td className="r mono">{typeof position.current_price === 'number' ? position.current_price.toFixed(2) : '-'}</td>
                      <td className="r mono">{typeof position.stop_loss === 'number' ? position.stop_loss.toFixed(2) : '-'}</td>
                      <td className={`r mono ${near ? 'down' : 'up'}`}>{typeof distance === 'number' ? `${distance.toFixed(1)}%` : '-'}</td>
                      <td className={`r mono ${position.pnl_pct < 0 ? 'down' : 'up'}`}>{percent(position.pnl_pct)}</td>
                    </tr>
                  )
                })}
                {positions.length === 0 && <tr><td colSpan={5} className="prototype-panel-note">暂无持仓数据。</td></tr>}
                {positions.length > 0 && nearStopPositions.length === 0 && (
                  <tr><td colSpan={5} className="prototype-panel-note">当前持仓距离止损位均在 3% 以上。</td></tr>
                )}
              </tbody>
            </table>
          </PrototypeCard>
        </>
      )}

      {active === 'strategies' && (
        <>
          <PrototypeCard title="策略风险" icon={<SafetyCertificateOutlined />} meta="Strategy">
            <table className="tbl">
              <thead><tr><th>方案</th><th>风险项</th><th className="r">回撤</th><th className="r">状态</th></tr></thead>
              <tbody>
                {contexts.map(row => (
                  <tr key={row.decision_context_id}>
                    <td className="nm">{row.plan_id || row.decision_context_id}</td>
                    <td>{row.intent}</td>
                    <td className="r down">-</td>
                    <td className="r warn">{row.source_type}</td>
                  </tr>
                ))}
                {contexts.length === 0 && <tr><td colSpan={4} className="prototype-panel-note">暂无 DecisionContext 记录。</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>
          <PrototypeCard title="策略运行控制" icon={<SafetyCertificateOutlined />} meta="Pause / Resume">
            {strategyMessage && <RiskBanner status={strategyMessageOk ? 'pass' : 'warn'} title="策略操作" detail={strategyMessage} />}
            <table className="tbl">
              <thead><tr><th>策略</th><th>状态</th><th className="r">日亏损上限</th><th className="r">单票止损</th><th className="r">操作</th></tr></thead>
              <tbody>
                {strategies.map(row => (
                  <tr key={row.id}>
                    <td className="nm">{row.name || row.id}</td>
                    <td className={strategyStatusClass(row.status)}>{row.status || 'active'}</td>
                    <td className="r mono">{strategyRiskPct(row, 'daily')}</td>
                    <td className="r mono">{strategyRiskPct(row, 'stop')}</td>
                    <td className="r">
                      {row.status === 'stopped' ? (
                        <span className="prototype-panel-note">已停止</span>
                      ) : (
                        <button type="button" className="btn sm ghost" onClick={() => toggleStrategy(row)}>
                          {row.status === 'paused' ? '恢复' : '暂停'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {strategies.length === 0 && <tr><td colSpan={5} className="prototype-panel-note">暂无策略实例。</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>
        </>
      )}

      {active === 'market' && (
        <>
          <PrototypeCard title="市场情绪指标" icon={<AlertOutlined />} meta="Sentiment">
            {marketSummary ? (
              <>
                <div className="kpis">
                  <MetricCard label="平均置信度" value={String(Math.round(marketSummary.avg_confidence || 0))} sub="signal/live" tone="accent" />
                  <MetricCard label="多头信号" value={String(bullCount)} sub={`强买 ${marketSummary.strong_buy_count || 0}`} tone="up" />
                  <MetricCard label="空头信号" value={String(bearCount)} sub={`强卖 ${marketSummary.strong_sell_count || 0}`} tone={bearCount > bullCount ? 'warn' : 'muted'} />
                  <MetricCard label="观望" value={String(marketSummary.hold_count || 0)} sub="hold" tone="muted" />
                </div>
                <RiskBanner
                  status={bearCount > bullCount ? 'warn' : 'pass'}
                  title={bearCount > bullCount ? '市场情绪偏空' : '市场情绪偏多/中性'}
                  detail={`强买 ${marketSummary.strong_buy_count || 0} · 买 ${marketSummary.buy_count || 0} · 持有 ${marketSummary.hold_count || 0} · 卖 ${marketSummary.sell_count || 0} · 强卖 ${marketSummary.strong_sell_count || 0}`}
                />
              </>
            ) : (
              <EmptyState title="暂无市场情绪数据" detail="signal/live 未返回汇总指标。" />
            )}
          </PrototypeCard>
          <PrototypeCard title="市场风险事件" icon={<AlertOutlined />} meta="Market">
            {contexts.length > 0 ? (
              <div className="row r-3">
                {contexts.map(item => (
                  <div className="prototype-fallback" key={item.decision_context_id}>{item.intent}</div>
                ))}
              </div>
            ) : (
              <EmptyState title="暂无市场风险上下文" detail="trade/decision-contexts 当前没有返回可展示的市场风险事件。" />
            )}
          </PrototypeCard>
        </>
      )}

      {active === 'audit' && (
        <>
          <div className="row r-6-4">
            <PrototypeCard title="RiskVerdict 审计" icon={<AuditOutlined />} meta="Order / Context">
              <table className="tbl">
                <thead><tr><th>RiskVerdict</th><th>Order</th><th>DecisionContext</th><th>结果</th><th className="r">规则</th></tr></thead>
                <tbody>
                  {verdicts.map(row => (
                    <tr key={row.verdict_id}>
                      <td className="code">{row.verdict_id}</td>
                      <td className="code">{row.order_id || '草稿'}</td>
                      <td className="code">{row.decision_context_id || '-'}</td>
                      <td className={resultClass(row.result)}>{row.result}</td>
                      <td className="r">{ruleText(row)}</td>
                    </tr>
                  ))}
                  {verdicts.length === 0 && (
                    <tr><td colSpan={5} className="prototype-panel-note">暂无 RiskVerdict 审计记录。</td></tr>
                  )}
                </tbody>
              </table>
            </PrototypeCard>
            <SideRail title="审计链路" meta="不可绕过">
              <LineageChips
                items={[
                  { label: '订单', value: firstVerdict?.order_id || '暂无' },
                  { label: '风控', value: firstVerdict?.verdict_id || '暂无', tone: 'warn' },
                  { label: '上下文', value: firstVerdict?.decision_context_id || '暂无', tone: 'accent' },
                ]}
              />
              <RiskBanner status="pass" title="留痕完整" detail="每次通过、警告、拒绝和人工复核都保留可追溯上下文。" />
            </SideRail>
          </div>
          <PrototypeCard title="审计日志" icon={<AuditOutlined />} meta="Audit Logs">
            <table className="tbl">
              <thead><tr><th>时间</th><th>动作</th><th>模式</th><th>标的</th><th>订单</th><th className="r">操作人</th></tr></thead>
              <tbody>
                {auditLogs.map(row => (
                  <tr key={row.id}>
                    <td className="mono">{auditTime(row.created_at)}</td>
                    <td className="nm">{row.action || '-'}</td>
                    <td>{row.mode || '-'}</td>
                    <td className="code">{row.symbol || '-'}</td>
                    <td className="code">{row.order_id || '-'}</td>
                    <td className="r">{row.user_id ?? '-'}</td>
                  </tr>
                ))}
                {auditLogs.length === 0 && <tr><td colSpan={6} className="prototype-panel-note">暂无审计日志记录。</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>
        </>
      )}
    </PrototypePage>
  )
}
