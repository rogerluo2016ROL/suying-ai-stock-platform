import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { BarChartOutlined, FileTextOutlined, FundOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { strategyApi, type StrategyPlan } from '../api/client'
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

interface PlanPick {
  code: string
  name?: string
  candidate_id?: string
  source_mode?: string
  entry_price?: number
  score?: number
}

interface PlanRow {
  id: string
  name: string
  modelName?: string
  status: string
  maxPositions: number
  capital: number
  risk: string
  expectedReturn?: number
  createdAt?: string
  updatedAt?: string
  picks: PlanPick[]
}

export function buildTradeUrlForPick(planId: string, pick: Pick<PlanPick, 'code' | 'candidate_id' | 'source_mode' | 'entry_price'>) {
  const sourceMode = pick.source_mode || 'manual'
  const candidateId = pick.candidate_id || `CAND-${sourceMode}-${pick.code}`
  const decisionContextId = `CTX-${planId}-${sourceMode}-${pick.code}`
  const params = new URLSearchParams({
    code: pick.code,
    price: String(pick.entry_price || 0),
    plan_id: planId,
    candidate_id: candidateId,
    decision_context_id: decisionContextId,
  })
  return `/trade?${params.toString()}`
}

const tabs = [
  { key: 'list', path: '/strategy', label: '方案列表', subLabel: '生命周期' },
  { key: 'detail', path: '/strategy/detail', label: '方案详情', subLabel: '参数 / 候选' },
  { key: 'compare', path: '/strategy/compare', label: '方案对比', subLabel: '组合比较' },
  { key: 'reports', path: '/strategy/reports', label: '结算报告', subLabel: '复盘输出' },
]

function activeKey(pathname: string) {
  if (pathname.endsWith('/detail')) return 'detail'
  if (pathname.endsWith('/compare')) return 'compare'
  if (pathname.endsWith('/reports')) return 'reports'
  return 'list'
}

function money(value: number) {
  return `${Math.round(value / 10000)}万`
}

function formatReturn(value?: number) {
  if (typeof value !== 'number') return '--'
  return `${value > 0 ? '+' : ''}${value}%`
}

function riskLabel(riskScore?: number) {
  if (riskScore === undefined) return '待评估'
  if (riskScore >= 70) return '高'
  if (riskScore >= 40) return '中'
  return '低'
}

function normalisePlan(plan: StrategyPlan): PlanRow {
  return {
    id: plan.id,
    name: plan.name,
    modelName: plan.model_name,
    status: plan.status || 'draft',
    maxPositions: plan.max_positions || 0,
    capital: plan.capital || 0,
    risk: riskLabel(plan.risk_score),
    expectedReturn: plan.expected_return,
    createdAt: plan.created_at,
    updatedAt: plan.updated_at,
    picks: plan.picks || [],
  }
}

export default function Strategy() {
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const [plans, setPlans] = useState<PlanRow[]>([])
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let mounted = true
    strategyApi.getPlans()
      .then(response => {
        if (!mounted) return
        setPlans((response.data?.plans || []).map(normalisePlan))
        setLoadError('')
      })
      .catch(() => {
        if (!mounted) return
        setPlans([])
        setLoadError('方案服务暂不可用')
      })
    return () => {
      mounted = false
    }
  }, [])

  const selectedPlan = plans.find(plan => plan.id === searchParams.get('plan_id')) ?? plans[0]
  const totalPicks = plans.reduce((sum, item) => sum + item.picks.length, 0)
  const riskPending = plans.filter(plan => plan.status === 'draft' || plan.risk === '待评估').length
  const tradable = plans.filter(plan => plan.status === 'confirmed' || plan.status === 'active').length
  const latestPlanUpdate = selectedPlan?.updatedAt || selectedPlan?.createdAt || plans[0]?.updatedAt || plans[0]?.createdAt

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="方案管理页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`方案管理 - ${activeTab.label}`}
        subtitle="账户私有方案 · 候选快照 · 风控前置 · 结算复盘"
        dataFreshness={<DataFreshnessBar updatedAt={latestPlanUpdate} source="strategy-service" />}
        actions={[
          { key: 'account', label: '账户私有', active: true },
          { key: 'paper', label: '模拟盘方案', tone: 'neutral' },
          { key: 'risk', label: '下单前风控', tone: 'warn' },
        ]}
      />
      <P0WorkflowNav currentStep="plan" />

      <div className="kpis">
        <MetricCard label="活跃方案" value={String(plans.length)} sub="策略服务" tone="accent" />
        <MetricCard label="待风控" value={String(riskPending)} sub="进入下单前置" tone="warn" />
        <MetricCard label="可下单" value={String(tradable)} sub="已确认方案" tone="up" />
        <MetricCard label="候选快照" value={String(totalPicks)} sub="Candidate" tone="muted" />
      </div>
      {loadError && <RiskBanner status="warn" title="方案服务异常" detail={loadError} />}

      {active === 'list' && (
        <div className="row r-6-4">
          <PrototypeCard title="方案列表" icon={<FileTextOutlined />} meta="Plan lifecycle">
            <table className="tbl">
              <thead><tr><th>方案</th><th>状态</th><th>风险</th><th className="r">资金</th><th className="r">预期</th><th className="r">动作</th></tr></thead>
              <tbody>
                {plans.map(plan => (
                  <tr key={plan.id}>
                    <td className="nm">{plan.name}<div className="prototype-panel-note">{plan.id}</div></td>
                    <td><span className="tag t-neu">{plan.status}</span></td>
                    <td>{plan.risk}</td>
                    <td className="r mono">{money(plan.capital)}</td>
                    <td className="r up">{formatReturn(plan.expectedReturn)}</td>
                    <td className="r">
                      <button type="button" className="btn sm" onClick={() => navigate(`/strategy/detail?plan_id=${encodeURIComponent(plan.id)}`)}>详情</button>
                    </td>
                  </tr>
                ))}
                {plans.length === 0 && (
                  <tr>
                    <td colSpan={6} className="prototype-panel-note">暂无策略服务返回的方案。</td>
                  </tr>
                )}
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="方案动作" meta="Plan / Order">
            <DataDomainBadge domain="account" label="账户私有方案" />
            <LineageChips
              items={[
                { label: 'Plan', value: selectedPlan?.id || '暂无' },
                { label: 'Candidate', value: selectedPlan?.picks.length || 0 },
                { label: 'RiskVerdict', value: '待生成', tone: 'warn' },
              ]}
            />
            <RiskBanner status="warn" title="下单前置未完成" detail="方案必须绑定候选快照、资金参数和 DecisionContext 后进入下单面板。" />
          </SideRail>
        </div>
      )}

      {active === 'detail' && (
        <div className="row r-6-4">
          <PrototypeCard title="方案详情" icon={<FundOutlined />} meta={selectedPlan?.id || 'Plan'}>
            {selectedPlan ? (
              <>
                <div className="op-hint">
                  <div className="pos warn">{selectedPlan.risk}</div>
                  <div>
                    <div className="op-title">{selectedPlan.name}</div>
                    <div className="op-desc">
                      资金 {money(selectedPlan.capital)}，最大持仓 {selectedPlan.maxPositions || '--'}，模型 {selectedPlan.modelName || '--'}。
                    </div>
                  </div>
                </div>
                <table className="tbl mt14">
                  <thead><tr><th>代码</th><th>名称</th><th>Candidate</th><th className="r">入场价</th><th className="r">评分</th><th className="r">下单</th></tr></thead>
                  <tbody>
                    {selectedPlan.picks.map(pick => (
                      <tr key={pick.code}>
                        <td className="code">{pick.code}</td>
                        <td className="nm">{pick.name}</td>
                        <td className="code">{pick.candidate_id || `CAND-${pick.code}`}</td>
                        <td className="r mono">{pick.entry_price}</td>
                        <td className="r mono">{pick.score}</td>
                        <td className="r"><button type="button" className="btn sm primary" onClick={() => navigate(buildTradeUrlForPick(selectedPlan.id, pick))}>下单</button></td>
                      </tr>
                    ))}
                    {selectedPlan.picks.length === 0 && (
                      <tr><td colSpan={6} className="prototype-panel-note">该方案暂无候选快照。</td></tr>
                    )}
                  </tbody>
                </table>
              </>
            ) : (
              <EmptyState title="暂无可查看的方案详情" detail="strategy/plans 当前没有返回方案。" />
            )}
          </PrototypeCard>
          <SideRail title="风控准备" meta="DecisionContext">
            <LineageChips
              items={[
                { label: 'DecisionContext', value: selectedPlan ? `CTX-${selectedPlan.id}` : '暂无' },
                { label: 'Order', value: '草稿', tone: 'warn' },
              ]}
            />
            <RiskBanner status="review" title="等待订单预检" detail="进入交易中心后由交易服务生成 RiskVerdict。" />
          </SideRail>
        </div>
      )}

      {active === 'compare' && (
        <div className="row r-6-4">
          <PrototypeCard title="方案对比" icon={<BarChartOutlined />} meta="组合比较">
            <table className="tbl">
              <thead><tr><th>方案</th><th>状态</th><th>风险</th><th className="r">候选数</th><th className="r">预期收益</th></tr></thead>
              <tbody>
                {plans.map(plan => (
                  <tr key={plan.id}>
                    <td className="nm">{plan.name}</td>
                    <td>{plan.status}</td>
                    <td>{plan.risk}</td>
                    <td className="r mono">{plan.picks.length}</td>
                    <td className="r up">{formatReturn(plan.expectedReturn)}</td>
                  </tr>
                ))}
                {plans.length === 0 && (
                  <tr><td colSpan={5} className="prototype-panel-note">暂无可对比方案。</td></tr>
                )}
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="对比结论" meta="Backtest">
            <RiskBanner status="review" title="仅展示策略服务字段" detail="当前 strategy/plans 未返回最大回撤和换手率，页面不再展示固定演示指标。" />
          </SideRail>
        </div>
      )}

      {active === 'reports' && (
        <div className="row r-6-4">
          <PrototypeCard title="结算报告" icon={<SafetyCertificateOutlined />} meta="Review">
            <table className="tbl">
              <thead><tr><th>报告</th><th>关联方案</th><th>结论</th><th className="r">生成时间</th></tr></thead>
              <tbody>
                {plans.map(plan => (
                  <tr key={plan.id}>
                    <td className="nm">{plan.name} 复盘</td>
                    <td className="code">{plan.id}</td>
                    <td>{plan.status === 'confirmed' ? '已确认，等待交易回填' : '等待风控与回测补充'}</td>
                    <td className="r mono">{plan.updatedAt || plan.createdAt || '--'}</td>
                  </tr>
                ))}
                {plans.length === 0 && (
                  <tr><td colSpan={4} className="prototype-panel-note">暂无方案复盘记录。</td></tr>
                )}
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="复盘链路" meta="Order / RiskVerdict">
            <RiskBanner status="review" title="等待交易回填" detail="成交、风控和 DecisionContext 汇总后生成正式结算报告。" />
          </SideRail>
        </div>
      )}
    </PrototypePage>
  )
}
