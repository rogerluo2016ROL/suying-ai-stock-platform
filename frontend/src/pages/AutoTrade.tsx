import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { RobotOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import api from '../api/client'
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

const tabs = [
  { key: 'market', path: '/auto-trade', label: '策略广场', subLabel: '模板选择' },
  { key: 'config', path: '/auto-trade/config', label: '策略配置', subLabel: '账户参数' },
  { key: 'monitor', path: '/auto-trade/monitor', label: '策略监控', subLabel: '运行状态' },
  { key: 'logs', path: '/auto-trade/logs', label: '策略日志', subLabel: '执行审计' },
]

function activeKey(pathname: string) {
  if (pathname.endsWith('/config')) return 'config'
  if (pathname.endsWith('/monitor')) return 'monitor'
  if (pathname.endsWith('/logs')) return 'logs'
  return 'market'
}

export default function AutoTrade() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const [strategies, setStrategies] = useState<AutoStrategy[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState<AutoStrategy | null>(null)
  const [logs, setLogs] = useState<AutoLog[]>([])
  const [loadError, setLoadError] = useState('')
  const [logError, setLogError] = useState('')
  const [actionMessage, setActionMessage] = useState('')

  useEffect(() => {
    api.get('/strategy/list')
      .then(response => {
        const nextStrategies = (response.data as any)?.strategies || []
        setStrategies(nextStrategies)
        setSelectedStrategy(current => current || nextStrategies[0] || null)
        setLoadError('')
      })
      .catch(() => {
        setStrategies([])
        setSelectedStrategy(null)
        setLoadError('策略列表接口暂不可用')
      })
  }, [])

  const openDetail = async (strategy: AutoStrategy) => {
    setSelectedStrategy(strategy)
    setActionMessage('')
    setLogError('')
    const detailResponse = await api.get(`/strategy/${strategy.id}`).catch(() => null)
    if (detailResponse?.data) {
      setSelectedStrategy({ ...strategy, ...(detailResponse.data as AutoStrategy) })
    }
    const logResponse = await api.get(`/strategy/${strategy.id}/log`).catch(() => null)
    if (logResponse?.data) {
      setLogs((logResponse.data as any)?.logs || [])
      setLogError('')
    } else {
      setLogs([])
      setLogError('执行器未启动，暂无策略日志')
    }
  }

  const runAction = async (strategy: AutoStrategy, action: 'start' | 'pause' | 'resume' | 'stop') => {
    setActionMessage('')
    const suffix = action === 'start' ? 'start?mode=paper' : action
    const response = await api.post(`/strategy/${strategy.id}/${suffix}`).catch((error: any) => {
      setActionMessage(error?.response?.data?.detail || `${action} 接口暂不可用`)
      return null
    })
    if (!response?.data) return
    const status = (response.data as any).status
    setActionMessage((response.data as any).message || `${action} 已提交`)
    setStrategies(current => current.map(item => item.id === strategy.id ? { ...item, status } : item))
    setSelectedStrategy(current => current?.id === strategy.id ? { ...current, status } : current)
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
  const latestStrategyUpdate = logs[0]?.timestamp || (selectedStrategy as (AutoStrategy & { updated_at?: string; created_at?: string }) | null)?.updated_at || (selectedStrategy as (AutoStrategy & { updated_at?: string; created_at?: string }) | null)?.created_at

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="量化交易页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`量化交易 - ${activeTab.label}`}
        subtitle="策略实例 · 参数配置 · 运行监控 · 执行日志"
        dataFreshness={<DataFreshnessBar updatedAt={latestStrategyUpdate} source={active === 'logs' ? 'strategy/log' : 'strategy/list'} />}
        actions={[
          { key: 'paper', label: '模拟盘执行', active: true },
          { key: 'risk', label: '风控不可绕过', tone: 'warn' },
          { key: 'live', label: '自动实盘锁定', tone: 'warn' },
        ]}
      />
      <P0WorkflowNav currentStep="order" />

      <div className="kpis">
        <MetricCard label="策略实例" value={String(strategies.length)} sub="strategy/list" tone="accent" />
        <MetricCard label="账户绑定" value={selectedStrategy?.trade_mode || '未选择'} sub="策略配置" tone="muted" />
        <MetricCard label="风控开关" value="ON" sub="实盘不可绕过" tone="warn" />
        <MetricCard label="今日动作" value={String(logs.length)} sub="执行日志" tone="up" />
      </div>
      {loadError && <RiskBanner status="warn" title="策略服务异常" detail={loadError} />}
      {actionMessage && <RiskBanner status="review" title="执行动作结果" detail={actionMessage} />}

      {(active === 'market' || active === 'monitor' || active === 'logs') && (
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
                    <td className="r mono">{strategy.picks_count ?? (strategy as any).picks?.length ?? 0}</td>
                    <td className="r">
                      <button type="button" className="btn sm" onClick={() => openDetail(strategy)}>详情</button>
                      <button type="button" className="btn sm ghost" onClick={() => runAction(strategy, 'start')}>启动</button>
                      <button type="button" className="btn sm ghost" onClick={() => runAction(strategy, 'stop')}>停止</button>
                    </td>
                  </tr>
                ))}
                {strategies.length === 0 && (
                  <tr><td colSpan={5} className="prototype-panel-note">暂无自动交易策略。</td></tr>
                )}
              </tbody>
            </table>
          </PrototypeCard>
          <PrototypeCard title="执行日志" icon={<SafetyCertificateOutlined />} meta="Lineage">
            {logError && <RiskBanner status="warn" title="日志不可用" detail={logError} />}
            {logs.length === 0 && !logError && <EmptyState title="暂无执行日志" detail="选择策略后读取 strategy/{id}/log。" />}
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
      )}

      {active === 'config' && (
        <div className="row r-6-4">
          <PrototypeCard title="策略配置" icon={<RobotOutlined />} meta="Account scoped">
            {selectedStrategy ? (
              <table className="tbl">
                <tbody>
                  <tr><td>策略</td><td className="r mono">{selectedStrategy.name}</td></tr>
                  <tr><td>交易模式</td><td className="r mono">{selectedStrategy.trade_mode || 'paper'}</td></tr>
                  <tr><td>资金</td><td className="r mono">{selectedStrategy.capital ?? '--'}</td></tr>
                  <tr><td>候选数</td><td className="r mono">{selectedStrategy.picks_count ?? (selectedStrategy as any).picks?.length ?? 0}</td></tr>
                  <tr><td>最大持仓</td><td className="r mono">{(selectedStrategy as any).position_rules?.max_positions ?? '--'}</td></tr>
                  <tr><td>单票上限</td><td className="r mono">{(selectedStrategy as any).position_rules?.single_max_pct ?? '--'}</td></tr>
                  <tr><td>日内最大亏损</td><td className="r mono">{(selectedStrategy as any).risk_rules?.daily_max_loss_pct ?? '--'}</td></tr>
                </tbody>
              </table>
            ) : (
              <EmptyState title="暂无策略配置" detail="strategy/list 当前没有返回可配置策略。" />
            )}
          </PrototypeCard>
          <SideRail title="自动交易闸门" meta="策略 / 账户">
            <DataDomainBadge domain="account" label="账户私有策略" />
            <LineageChips items={[{ label: 'Strategy', value: selectedStrategy?.id || '暂无' }, { label: 'Risk', value: '强制预检', tone: 'warn' }]} />
            <RiskBanner status="warn" title="自动实盘未放行" detail="投资者默认不可自动实盘，操盘手需绑定账户和风控策略。" />
          </SideRail>
        </div>
      )}
    </PrototypePage>
  )
}
