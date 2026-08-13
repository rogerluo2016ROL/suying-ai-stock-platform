import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { FundOutlined, RobotOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Modal } from 'antd'
import ReactECharts from 'echarts-for-react'
import { strategyApi } from '../api/client'
import type { AutoStrategy, AutoLog, MarketTemplate } from '../api/client'
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

type TemplateSort = 'default' | 'return' | 'drawdown'

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

function templateTypeOf(template: MarketTemplate) {
  return template.model_name || template.risk_level || template.risk || '未分类'
}

function formatPct(value?: number) {
  return value == null ? '--' : `${(value * 100).toFixed(1)}%`
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
  // ── 策略广场（模板市场）──
  const [templates, setTemplates] = useState<MarketTemplate[]>([])
  const [templatesError, setTemplatesError] = useState('')
  const [templateFilter, setTemplateFilter] = useState('all')
  const [templateSort, setTemplateSort] = useState<TemplateSort>('default')
  const [followTarget, setFollowTarget] = useState<MarketTemplate | null>(null)
  const [followName, setFollowName] = useState('')
  const [followCapital, setFollowCapital] = useState(1_000_000)
  const [followMaxPositions, setFollowMaxPositions] = useState(5)
  const [followSaving, setFollowSaving] = useState(false)
  // ── 策略配置（参数编辑）──
  const [editCapital, setEditCapital] = useState(1_000_000)
  const [editMaxPositions, setEditMaxPositions] = useState(5)
  const [configSaving, setConfigSaving] = useState(false)
  // ── 策略日志（级别筛选）──
  const [logLevelFilter, setLogLevelFilter] = useState('ALL')

  useEffect(() => {
    strategyApi.listInstances()
      .then(response => {
        const nextStrategies = response.data.strategies || []
        setStrategies(nextStrategies)
        setSelectedStrategy(current => current || nextStrategies[0] || null)
        setLoadError('')
      })
      .catch(() => {
        setStrategies([])
        setSelectedStrategy(null)
        setLoadError('策略列表接口连接异常')
      })
  }, [])

  useEffect(() => {
    if (active !== 'market') return
    strategyApi.getTemplates()
      .then(response => {
        setTemplates(response.data.templates || [])
        setTemplatesError('')
      })
      .catch(() => {
        setTemplates([])
        setTemplatesError('策略模板接口连接异常')
      })
  }, [active])

  useEffect(() => {
    setEditCapital(selectedStrategy?.capital ?? 1_000_000)
    setEditMaxPositions(selectedStrategy?.position_rules?.max_positions ?? 5)
    // 仅在切换策略时回填表单，避免详情刷新覆盖未保存输入
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStrategy?.id])

  const loadLogs = async (strategyId: string) => {
    const logResponse = await strategyApi.getInstanceLog(strategyId).catch(() => null)
    if (logResponse?.data) {
      setLogs(logResponse.data.logs || [])
      setLogError('')
    } else {
      setLogs([])
      setLogError('执行器未启动，暂无策略日志')
    }
  }

  useEffect(() => {
    if (active === 'logs' && selectedStrategy) {
      setLogLevelFilter('ALL')
      void loadLogs(selectedStrategy.id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, selectedStrategy?.id])

  const openDetail = async (strategy: AutoStrategy) => {
    setSelectedStrategy(strategy)
    setActionMessage('')
    setLogError('')
    const detailResponse = await strategyApi.getInstance(strategy.id).catch(() => null)
    if (detailResponse?.data) {
      setSelectedStrategy({ ...strategy, ...detailResponse.data })
    }
    await loadLogs(strategy.id)
  }

  const runAction = async (strategy: AutoStrategy, action: 'start' | 'pause' | 'resume' | 'stop') => {
    setActionMessage('')
    const call =
      action === 'start' ? strategyApi.startInstance(strategy.id) :
      action === 'pause' ? strategyApi.pauseInstance(strategy.id) :
      action === 'resume' ? strategyApi.resumeInstance(strategy.id) :
      strategyApi.stopInstance(strategy.id)
    const response = await call.catch((error: any) => {
      setActionMessage(error?.response?.data?.detail || `${action} 接口连接异常`)
      return null
    })
    if (!response?.data) return
    const status = response.data.status
    setActionMessage(response.data.message || `${action} 已提交`)
    setStrategies(current => current.map(item => item.id === strategy.id ? { ...item, status } : item))
    setSelectedStrategy(current => current?.id === strategy.id ? { ...current, status } : current)
  }

  // ── 一键跟单：模板 → 创建方案 ──
  const openFollow = (template: MarketTemplate) => {
    setFollowTarget(template)
    setFollowName(`${template.name} 跟单`)
    setFollowCapital(template.capital ?? 1_000_000)
    setFollowMaxPositions(template.max_positions ?? 5)
  }

  const submitFollow = async () => {
    if (!followTarget) return
    setFollowSaving(true)
    const planName = followName.trim() || `${followTarget.name} 跟单`
    const response = await strategyApi
      .createPlan(planName, followTarget.model_name || followTarget.id, followMaxPositions, followCapital)
      .catch((error: any) => {
        setActionMessage(error?.response?.data?.detail || '创建方案接口连接异常')
        return null
      })
    setFollowSaving(false)
    if (!response?.data) return
    setActionMessage(`一键跟单成功，已创建方案：${response.data.plan?.name || planName}`)
    setFollowTarget(null)
  }

  // ── 参数编辑：PUT /strategy/{id}（position_rules 整体替换，合并现有仓位规则）──
  const saveConfig = async () => {
    if (!selectedStrategy) return
    setConfigSaving(true)
    const response = await strategyApi.updateInstance(selectedStrategy.id, {
      capital: editCapital,
      position_rules: {
        max_positions: editMaxPositions,
        single_max_pct: selectedStrategy.position_rules?.single_max_pct ?? 0.2,
        total_position_cap_pct: selectedStrategy.position_rules?.total_position_cap_pct ?? 0.8,
      },
    }).catch((error: any) => {
      setActionMessage(error?.response?.data?.detail || '更新策略接口连接异常')
      return null
    })
    setConfigSaving(false)
    if (!response?.data) return
    const updated = response.data.strategy
    if (updated) {
      setStrategies(current => current.map(item => item.id === updated.id ? { ...item, ...updated } : item))
      setSelectedStrategy(current => current?.id === updated.id ? { ...current, ...updated } : current)
    }
    setActionMessage(response.data.message || '策略已更新')
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

  // ── 策略广场派生数据 ──
  const templateTypes = useMemo(() => Array.from(new Set(templates.map(templateTypeOf))), [templates])
  const visibleTemplates = useMemo(() => {
    const filtered = templates.filter(template => templateFilter === 'all' || templateTypeOf(template) === templateFilter)
    if (templateSort === 'default') return filtered
    const key: 'annual_return' | 'max_drawdown' = templateSort === 'return' ? 'annual_return' : 'max_drawdown'
    // 模板响应未携带收益率/回撤 mock 字段时保持基础顺序
    if (!filtered.some(template => template[key] != null)) return filtered
    return [...filtered].sort((a, b) => (b[key] ?? 0) - (a[key] ?? 0))
  }, [templates, templateFilter, templateSort])

  // ── 策略监控派生数据（实例无收益字段，收益 KPI 跳过）──
  const runningCount = strategies.filter(item => ['running', 'active'].includes(item.status || 'active')).length
  const pausedCount = strategies.filter(item => item.status === 'paused').length
  const todayKey = new Date().toISOString().slice(0, 10)
  const todayTrades = logs.filter(log => (log.timestamp || '').startsWith(todayKey)).length

  const equityOption = useMemo(() => {
    const labels: string[] = []
    const nav: number[] = []
    let value = 1
    const seedBase = (selectedStrategy?.id || 'strategy').length
    const count = logs.length > 1 ? logs.length : 20
    for (let index = 0; index < count; index += 1) {
      value *= 1 + Math.sin((seedBase + index) * 1.7) * 0.015
      nav.push(Number(value.toFixed(4)))
      const timestamp = logs[index]?.timestamp
      labels.push(timestamp ? String(timestamp).slice(5, 16) : `T${index + 1}`)
    }
    let peak = 0
    const drawdown = nav.map(point => {
      peak = Math.max(peak, point)
      return Number((((point - peak) / peak) * 100).toFixed(2))
    })
    return {
      grid: { left: 48, right: 48, top: 32, bottom: 26 },
      tooltip: { trigger: 'axis' },
      legend: { data: ['净值', '回撤%'], top: 0, textStyle: { fontSize: 11 } },
      xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
      yAxis: [
        { type: 'value', scale: true, axisLabel: { fontSize: 10 } },
        { type: 'value', scale: true, axisLabel: { fontSize: 10, formatter: '{value}%' } },
      ],
      series: [
        { name: '净值', type: 'line', data: nav, smooth: true, showSymbol: false, lineStyle: { width: 2 } },
        { name: '回撤%', type: 'line', yAxisIndex: 1, data: drawdown, smooth: true, showSymbol: false, areaStyle: { opacity: 0.15 }, lineStyle: { width: 1.5, type: 'dashed' } },
      ],
    }
  }, [logs, selectedStrategy])

  // ── 策略日志派生数据 ──
  const logLevels = useMemo(
    () => Array.from(new Set(logs.map(log => (log.level || 'INFO').toUpperCase()))),
    [logs],
  )
  const visibleLogs = useMemo(
    () => (logLevelFilter === 'ALL' ? logs : logs.filter(log => (log.level || 'INFO').toUpperCase() === logLevelFilter)),
    [logs, logLevelFilter],
  )

  const renderLogItem = (log: AutoLog, index: number) => (
    <div className="prototype-fallback" key={`${log.timestamp}-${index}`} style={{ marginBottom: 10 }}>
      <div className="nm">{log.message}</div>
      <div className="chips mt14">
        {log.level && <span className="chip">{log.level}</span>}
        {log.details?.decision_context_id && <span className="chip active">{log.details.decision_context_id}</span>}
        {log.details?.plan_id && <span className="chip">{log.details.plan_id}</span>}
        {log.details?.candidate_id && <span className="chip">{log.details.candidate_id}</span>}
      </div>
      <button type="button" className="btn sm mt14" onClick={() => navigateRisk(log.details)}>风控</button>
    </div>
  )

  const latestStrategyUpdate = logs[0]?.timestamp || selectedStrategy?.updated_at || selectedStrategy?.created_at
  const freshnessSource = active === 'market' ? 'strategy/templates' : active === 'logs' ? 'strategy/log' : 'strategy/list'

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
        subtitle="策略广场 · 参数配置 · 运行监控 · 执行日志"
        dataFreshness={<DataFreshnessBar updatedAt={latestStrategyUpdate} source={freshnessSource} />}
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

      {active === 'market' && (
        <PrototypeCard title="策略模板广场" icon={<FundOutlined />} meta="strategy/templates">
          <div className="param-bar" style={{ marginBottom: 12 }}>
            <span className="plabel">模型类型</span>
            <select
              className="param-select"
              aria-label="模型类型筛选"
              value={templateFilter}
              onChange={event => setTemplateFilter(event.target.value)}
            >
              <option value="all">全部</option>
              {templateTypes.map(type => <option key={type} value={type}>{type}</option>)}
            </select>
            <span className="psep" />
            <span className="plabel">排序</span>
            <select
              className="param-select"
              aria-label="模板排序"
              value={templateSort}
              onChange={event => setTemplateSort(event.target.value as TemplateSort)}
            >
              <option value="default">默认</option>
              <option value="return">收益率</option>
              <option value="drawdown">回撤</option>
            </select>
          </div>
          {templatesError && <RiskBanner status="warn" title="模板服务异常" detail={templatesError} />}
          <table className="tbl">
            <thead>
              <tr>
                <th>模板</th>
                <th>类型</th>
                <th className="r">最大持仓</th>
                <th className="r">单票上限</th>
                <th className="r">止损</th>
                <th className="r">目标收益</th>
                <th className="r">操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleTemplates.map(template => (
                <tr key={template.id}>
                  <td className="nm">
                    {template.name}
                    {template.description && <div className="prototype-panel-note">{template.description}</div>}
                  </td>
                  <td>{templateTypeOf(template)}</td>
                  <td className="r mono">{template.max_positions ?? '--'}</td>
                  <td className="r mono">{formatPct(template.single_max)}</td>
                  <td className="r mono">{formatPct(template.stop_loss_pct)}</td>
                  <td className="r mono">{formatPct(template.target_return_pct)}</td>
                  <td className="r">
                    <button type="button" className="btn sm" onClick={() => openFollow(template)}>一键跟单</button>
                  </td>
                </tr>
              ))}
              {visibleTemplates.length === 0 && (
                <tr><td colSpan={7} className="prototype-panel-note">暂无策略模板。</td></tr>
              )}
            </tbody>
          </table>
        </PrototypeCard>
      )}

      {active === 'monitor' && (
        <>
          <div className="kpis">
            <MetricCard label="运行中" value={String(runningCount)} sub="strategy/list" tone="up" />
            <MetricCard label="已暂停" value={String(pausedCount)} sub="strategy/list" tone="warn" />
            <MetricCard label="今日交易笔数" value={String(todayTrades)} sub="strategy/log" tone="accent" />
          </div>
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
                      <td className="r mono">{strategy.picks_count ?? strategy.picks?.length ?? 0}</td>
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
              {logs.map(renderLogItem)}
            </PrototypeCard>
          </div>
          <PrototypeCard title="净值 / 回撤" icon={<FundOutlined />} meta="示例数据 · 由执行日志推算">
            <ReactECharts option={equityOption} style={{ height: 260, width: '100%' }} notMerge />
          </PrototypeCard>
        </>
      )}

      {active === 'logs' && (
        <PrototypeCard title="策略日志" icon={<SafetyCertificateOutlined />} meta="strategy/{id}/log">
          <div className="param-bar" style={{ marginBottom: 12 }}>
            <span className="plabel">策略</span>
            <select
              className="param-select"
              aria-label="日志策略"
              value={selectedStrategy?.id || ''}
              onChange={event => {
                const strategy = strategies.find(item => item.id === event.target.value)
                if (strategy) {
                  setSelectedStrategy(strategy)
                  setLogLevelFilter('ALL')
                  void loadLogs(strategy.id)
                }
              }}
            >
              {strategies.length === 0 && <option value="">暂无策略</option>}
              {strategies.map(strategy => <option key={strategy.id} value={strategy.id}>{strategy.name}</option>)}
            </select>
            <span className="psep" />
            <span className="plabel">级别</span>
            <button
              type="button"
              className={`filter-btn${logLevelFilter === 'ALL' ? ' active' : ''}`}
              onClick={() => setLogLevelFilter('ALL')}
            >
              全部
            </button>
            {logLevels.map(level => (
              <button
                key={level}
                type="button"
                className={`filter-btn${logLevelFilter === level ? ' active' : ''}`}
                onClick={() => setLogLevelFilter(level)}
              >
                {level}
              </button>
            ))}
          </div>
          {logError && <RiskBanner status="warn" title="日志不可用" detail={logError} />}
          {visibleLogs.length === 0 && !logError && (
            <EmptyState title="当前级别暂无日志" detail="切换级别筛选或选择其他策略。" />
          )}
          {visibleLogs.map(renderLogItem)}
        </PrototypeCard>
      )}

      {active === 'config' && (
        <>
          <div className="row r-6-4">
            <PrototypeCard title="策略配置" icon={<RobotOutlined />} meta="Account scoped">
              {selectedStrategy ? (
                <table className="tbl">
                  <tbody>
                    <tr><td>策略</td><td className="r mono">{selectedStrategy.name}</td></tr>
                    <tr><td>交易模式</td><td className="r mono">{selectedStrategy.trade_mode || 'paper'}</td></tr>
                    <tr><td>资金</td><td className="r mono">{selectedStrategy.capital ?? '--'}</td></tr>
                    <tr><td>候选数</td><td className="r mono">{selectedStrategy.picks_count ?? selectedStrategy.picks?.length ?? 0}</td></tr>
                    <tr><td>最大持仓</td><td className="r mono">{selectedStrategy.position_rules?.max_positions ?? '--'}</td></tr>
                    <tr><td>单票上限</td><td className="r mono">{selectedStrategy.position_rules?.single_max_pct ?? '--'}</td></tr>
                    <tr><td>日内最大亏损</td><td className="r mono">{selectedStrategy.risk_rules?.daily_max_loss_pct ?? '--'}</td></tr>
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
          <PrototypeCard title="参数编辑" icon={<RobotOutlined />} meta="PUT strategy/{id}">
            {selectedStrategy ? (
              <div style={{ display: 'grid', gap: 12, maxWidth: 320 }}>
                <label>
                  <span className="plabel">初始资金</span>
                  <input
                    type="number"
                    className="param-input"
                    style={{ width: '100%', marginTop: 4 }}
                    aria-label="初始资金"
                    min={100_000}
                    step={10_000}
                    value={editCapital}
                    onChange={event => setEditCapital(Number(event.target.value))}
                  />
                </label>
                <label>
                  <span className="plabel">最大持仓数</span>
                  <input
                    type="number"
                    className="param-input"
                    style={{ width: '100%', marginTop: 4 }}
                    aria-label="最大持仓数"
                    min={1}
                    max={50}
                    step={1}
                    value={editMaxPositions}
                    onChange={event => setEditMaxPositions(Number(event.target.value))}
                  />
                </label>
                <div>
                  <button type="button" className="btn sm" onClick={saveConfig} disabled={configSaving}>
                    {configSaving ? '保存中...' : '保存配置'}
                  </button>
                </div>
              </div>
            ) : (
              <EmptyState title="无可编辑策略" detail="strategy/list 当前没有返回可编辑策略。" />
            )}
          </PrototypeCard>
        </>
      )}

      <Modal
        title={followTarget ? `一键跟单：${followTarget.name}` : '一键跟单'}
        open={followTarget !== null}
        onOk={submitFollow}
        onCancel={() => setFollowTarget(null)}
        okText="确认跟单"
        cancelText="取消"
        confirmLoading={followSaving}
      >
        {followTarget && (
          <div style={{ display: 'grid', gap: 12 }}>
            <div className="prototype-panel-note">
              模板类型 {templateTypeOf(followTarget)} · 最大持仓 {followTarget.max_positions ?? '--'} · 单票上限 {formatPct(followTarget.single_max)}
            </div>
            <label>
              <span className="plabel">方案名称</span>
              <input
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="方案名称"
                value={followName}
                onChange={event => setFollowName(event.target.value)}
              />
            </label>
            <label>
              <span className="plabel">投入本金</span>
              <input
                type="number"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="投入本金"
                min={100_000}
                step={10_000}
                value={followCapital}
                onChange={event => setFollowCapital(Number(event.target.value))}
              />
            </label>
            <label>
              <span className="plabel">最大持仓数</span>
              <input
                type="number"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="跟单最大持仓数"
                min={1}
                max={50}
                step={1}
                value={followMaxPositions}
                onChange={event => setFollowMaxPositions(Number(event.target.value))}
              />
            </label>
          </div>
        )}
      </Modal>
    </PrototypePage>
  )
}
