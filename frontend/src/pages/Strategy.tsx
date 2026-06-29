import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BarChartOutlined, FileTextOutlined, FundOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { P0WorkflowNav } from '../components/layout'
import {
  DataDomainBadge,
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
  status: string
  capital: number
  risk: string
  expectedReturn: number
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

const plans: PlanRow[] = [
  {
    id: 'PLAN-B3',
    name: '半导体竞价共振',
    status: '待风控',
    capital: 1_000_000,
    risk: '中',
    expectedReturn: 8.6,
    picks: [
      { code: '300750', name: '宁德时代', candidate_id: 'CAND-leader_auction-300750', source_mode: 'leader_auction', entry_price: 218.5, score: 92 },
      { code: '688981', name: '中芯国际', candidate_id: 'CAND-chain-688981', source_mode: 'chain', entry_price: 68.2, score: 88 },
    ],
  },
  {
    id: 'PLAN-V2',
    name: '价值回撤低吸',
    status: '回测通过',
    capital: 800_000,
    risk: '低',
    expectedReturn: 5.4,
    picks: [
      { code: '600519', name: '贵州茅台', source_mode: 'value', entry_price: 1785, score: 81 },
    ],
  },
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

export default function Strategy() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const selectedPlan = plans[0]

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
        actions={[
          { key: 'account', label: '账户私有', active: true },
          { key: 'paper', label: '模拟盘方案', tone: 'neutral' },
          { key: 'risk', label: '下单前风控', tone: 'warn' },
        ]}
      />
      <P0WorkflowNav currentStep="plan" />

      <div className="kpis">
        <MetricCard label="活跃方案" value={String(plans.length)} sub="账户私有" tone="accent" />
        <MetricCard label="待风控" value="1" sub="进入下单前置" tone="warn" />
        <MetricCard label="可下单" value="1" sub="回测通过" tone="up" />
        <MetricCard label="候选快照" value={String(plans.reduce((sum, item) => sum + item.picks.length, 0))} sub="Candidate" tone="muted" />
      </div>

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
                    <td className="r up">+{plan.expectedReturn}%</td>
                    <td className="r">
                      <button type="button" className="btn sm" onClick={() => navigate('/strategy/detail')}>详情</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="方案动作" meta="Plan / Order">
            <DataDomainBadge domain="account" label="账户私有方案" />
            <LineageChips
              items={[
                { label: 'Plan', value: selectedPlan.id },
                { label: 'Candidate', value: selectedPlan.picks.length },
                { label: 'RiskVerdict', value: '待生成', tone: 'warn' },
              ]}
            />
            <RiskBanner status="warn" title="下单前置未完成" detail="方案必须绑定候选快照、资金参数和 DecisionContext 后进入下单面板。" />
          </SideRail>
        </div>
      )}

      {active === 'detail' && (
        <div className="row r-6-4">
          <PrototypeCard title="方案详情" icon={<FundOutlined />} meta={selectedPlan.id}>
            <div className="op-hint">
              <div className="pos warn">{selectedPlan.risk}</div>
              <div>
                <div className="op-title">{selectedPlan.name}</div>
                <div className="op-desc">资金 {money(selectedPlan.capital)}，最大持仓 5，只提交模拟盘订单草稿。</div>
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
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="风控准备" meta="DecisionContext">
            <LineageChips
              items={[
                { label: 'DecisionContext', value: `CTX-${selectedPlan.id}` },
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
              <thead><tr><th>方案</th><th className="r">预期收益</th><th className="r">最大回撤</th><th className="r">换手</th></tr></thead>
              <tbody>
                {plans.map((plan, index) => (
                  <tr key={plan.id}>
                    <td className="nm">{plan.name}</td>
                    <td className="r up">+{plan.expectedReturn}%</td>
                    <td className="r down">-{index === 0 ? '4.2' : '2.8'}%</td>
                    <td className="r mono">{index === 0 ? '38%' : '21%'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="对比结论" meta="Backtest">
            <RiskBanner status="pass" title="模拟盘优先" detail="高波动方案先进入回测复盘，暂不开放实盘自动执行。" />
          </SideRail>
        </div>
      )}

      {active === 'reports' && (
        <div className="row r-6-4">
          <PrototypeCard title="结算报告" icon={<SafetyCertificateOutlined />} meta="Review">
            <table className="tbl">
              <thead><tr><th>报告</th><th>关联方案</th><th>结论</th><th className="r">生成时间</th></tr></thead>
              <tbody>
                <tr><td className="nm">半导体竞价复盘</td><td className="code">PLAN-B3</td><td>胜率稳定，需控制追高</td><td className="r mono">2026-06-28</td></tr>
                <tr><td className="nm">价值低吸复盘</td><td className="code">PLAN-V2</td><td>回撤低，收益慢</td><td className="r mono">2026-06-27</td></tr>
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
