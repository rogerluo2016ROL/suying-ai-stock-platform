import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AlertOutlined, AuditOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { tradeApi } from '../api/client'
import { liveTradeApi } from '../api/liveTrade'
import type { DecisionContextRecord, RiskVerdictRecord } from '../api/types'
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

function ruleText(record: RiskVerdictRecord) {
  const details = record.details as any
  const checks = details?.risk_check?.checks || details?.checks || []
  const first = Array.isArray(checks) ? checks[0] : undefined
  return first?.rule || first?.name || details?.message || record.scope
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
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let mounted = true
    Promise.allSettled([
      tradeApi.getRiskVerdicts({ page: 1, page_size: 20 }),
      tradeApi.getDecisionContexts({ page: 1, page_size: 20 }),
      liveTradeApi.getAuditLogs({ page: 1, page_size: 20 }),
      liveTradeApi.getRiskConfig(),
    ]).then(([verdictResponse, contextResponse, auditResponse, configResponse]) => {
        if (!mounted) return
        if (verdictResponse.status === 'fulfilled') setVerdicts(verdictResponse.value.data?.records || [])
        if (contextResponse.status === 'fulfilled') setContexts(contextResponse.value.data?.records || [])
        if (auditResponse.status === 'fulfilled') {
          setAuditTotal((auditResponse.value.data as any)?.total || (auditResponse.value.data as any)?.records?.length || 0)
        }
        if (configResponse.status === 'fulfilled') setRiskConfig((configResponse.value.data as RiskConfig) || {})
        const failed = [verdictResponse, contextResponse, auditResponse, configResponse].filter(result => result.status === 'rejected').length
        setLoadError(failed > 0 ? `${failed} 个风控数据接口连接异常` : '')
      })
    return () => {
      mounted = false
    }
  }, [])

  const blocked = verdicts.filter(row => row.result === 'reject' || row.result === 'manual_review').length
  const passed = verdicts.filter(row => row.result === 'pass').length
  const passRate = verdicts.length ? Math.round((passed / verdicts.length) * 100) : 0
  const warningCount = verdicts.filter(row => row.result === 'warn').length
  const firstVerdict = verdicts[0]
  const firstContext = contexts[0] as (DecisionContextRecord & { updated_at?: string; created_at?: string }) | undefined
  const firstRiskVerdict = firstVerdict as (RiskVerdictRecord & { updated_at?: string; created_at?: string; trade_date?: string }) | undefined

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
      )}

      {active === 'overview' && (
        <PrototypeCard title="组合风险暴露" icon={<AlertOutlined />} meta="Portfolio">
          {[
            ['单票仓位上限', Math.round((riskConfig.max_position_pct || 0) * 100), 'var(--warn)'],
            ['涨跌价差限制', Math.round((riskConfig.price_limit_pct || 0) * 100), 'var(--accent)'],
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
      )}

      {active === 'positions' && (
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
      )}

      {active === 'strategies' && (
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
      )}

      {active === 'market' && (
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
      )}

      {active === 'audit' && (
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
      )}
    </PrototypePage>
  )
}
