import { useEffect, useMemo, useState } from 'react'
import { CheckCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { backtestApi, chainApi, signalApi, strategyApi, tradeApi } from '../api/client'
import type { ChainCandidate, DecisionContextRecord, RiskVerdictRecord, StockSignal, StrategyPlan, TradeOrder } from '../api/types'
import { P0WorkflowNav } from '../components/layout'
import {
  DataDomainBadge,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  RiskBanner,
  SideRail,
} from '../components/prototype'

interface P0EvidenceState {
  candidates: ChainCandidate[]
  plans: StrategyPlan[]
  orders: TradeOrder[]
  verdicts: RiskVerdictRecord[]
  contexts: DecisionContextRecord[]
  signals: StockSignal[]
  factorCount: number
  loading: boolean
  error: string
}

const initialEvidence: P0EvidenceState = {
  candidates: [],
  plans: [],
  orders: [],
  verdicts: [],
  contexts: [],
  signals: [],
  factorCount: 0,
  loading: true,
  error: '',
}

function statusCount(label: string, count: number, loading: boolean) {
  if (loading) return '加载中'
  return `${count} 条 ${label}`
}

export default function P0Workflow() {
  const [evidence, setEvidence] = useState<P0EvidenceState>(initialEvidence)

  useEffect(() => {
    let mounted = true
    Promise.allSettled([
      chainApi.getCandidates({ filter: 'all', top_n: 20 }),
      strategyApi.getPlans(),
      tradeApi.getOrders(),
      tradeApi.getRiskVerdicts({ page: 1, page_size: 20 }),
      tradeApi.getDecisionContexts({ page: 1, page_size: 20 }),
      signalApi.getLive('intra'),
      backtestApi.getFactors(),
    ]).then(results => {
      if (!mounted) return
      const [candidateResult, planResult, orderResult, verdictResult, contextResult, signalResult, factorResult] = results
      const failed = results.filter(result => result.status === 'rejected').length
      setEvidence({
        candidates: candidateResult.status === 'fulfilled' ? candidateResult.value.data?.candidates || [] : [],
        plans: planResult.status === 'fulfilled' ? planResult.value.data?.plans || [] : [],
        orders: orderResult.status === 'fulfilled' ? orderResult.value.data?.orders || [] : [],
        verdicts: verdictResult.status === 'fulfilled' ? verdictResult.value.data?.records || [] : [],
        contexts: contextResult.status === 'fulfilled' ? contextResult.value.data?.records || [] : [],
        signals: signalResult.status === 'fulfilled' ? signalResult.value.data?.signals || [] : [],
        factorCount: factorResult.status === 'fulfilled' ? factorResult.value.data?.factors?.length || 0 : 0,
        loading: false,
        error: failed ? `${failed} 个链路接口暂不可用` : '',
      })
    })
    return () => {
      mounted = false
    }
  }, [])

  const objects = useMemo(() => [
    { name: 'Candidate', cn: '候选池', owner: 'screener/open-decision', status: statusCount('候选', Math.max(evidence.candidates.length, evidence.signals.length), evidence.loading), detail: 'chain/candidates + signal/live，保留来源、评分、证据、账户作用域' },
    { name: 'Plan', cn: '方案管理', owner: 'strategy-service', status: statusCount('方案', evidence.plans.length, evidence.loading), detail: 'strategy/plans，候选快照、资金、仓位、执行约束' },
    { name: 'Order', cn: '下单面板', owner: 'trade-service', status: statusCount('订单', evidence.orders.length, evidence.loading), detail: 'trade/orders，方向、价格、数量、账户、交易模式' },
    { name: 'RiskVerdict', cn: '风控闸门', owner: 'trade-service', status: statusCount('判定', evidence.verdicts.length, evidence.loading), detail: 'trade/risk-verdicts，通过、警告、拒绝、人工复核与规则明细' },
    { name: 'BacktestReview', cn: '回测复盘', owner: 'backtest-service', status: statusCount('因子', evidence.factorCount, evidence.loading), detail: 'backtest/factors，订单、风控和决策上下文聚合归因' },
  ], [evidence])
  const blocked = evidence.verdicts.filter(item => item.result === 'reject' || item.result === 'manual_review').length
  const latestContext = evidence.contexts[0]

  return (
    <PrototypePage>
      <PrototypePageHeader
        title="P0 主链路"
        subtitle="候选池 -> 方案管理 -> 下单面板 -> 风控闸门 -> 回测复盘"
        actions={[
          { key: 'paper', label: '模拟盘优先', active: true },
          { key: 'live', label: '实盘锁定', tone: 'warn' },
        ]}
      />
      <P0WorkflowNav currentStep="candidate" />

      <div className="kpis">
        <MetricCard label="链路对象" value="5" sub="公共契约" tone="accent" />
        <MetricCard label="账户域" value="tenant/user/account" sub="私有数据隔离" tone="muted" />
        <MetricCard label="风控闸门" value={String(evidence.verdicts.length)} sub={`拦截/复核 ${blocked}`} tone="warn" />
        <MetricCard label="实盘路径" value={evidence.error ? '复核' : 'Gate'} sub={evidence.error || '人工放行'} tone="down" />
      </div>

      <div className="row r-6-4">
        <PrototypeCard title="主链路对象" icon={<CheckCircleOutlined />} meta="P0 contract">
          <table className="tbl">
            <thead><tr><th>对象</th><th>业务节点</th><th>Owner</th><th>状态</th><th>字段重点</th></tr></thead>
            <tbody>
              {objects.map(item => (
                <tr key={item.name}>
                  <td className="nm">{item.name}</td>
                  <td>{item.cn}</td>
                  <td className="code">{item.owner}</td>
                  <td><span className="tag t-neu">{item.status}</span></td>
                  <td>{item.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>
        <SideRail title="执行闸门" meta="paper/live">
          <DataDomainBadge domain="account" label="账户私有链路" />
          <RiskBanner status="warn" title="实盘默认关闭" detail={evidence.error || '模拟盘链路跑通后，QMT/券商实盘仍必须经过券商配置、风控判定和审计留痕。'} />
          <LineageChips
            items={[
              { label: '候选', value: String(Math.max(evidence.candidates.length, evidence.signals.length)) },
              { label: 'Risk', value: `${evidence.verdicts.length} 条`, tone: 'warn' },
              { label: 'Audit', value: latestContext?.decision_context_id || '待记录', tone: 'accent' },
            ]}
          />
        </SideRail>
      </div>

      <div className="row r-3">
        {['候选进入方案', '方案生成订单', '订单触发风控'].map((item, index) => (
          <PrototypeCard key={item} title={item} icon={<SafetyCertificateOutlined />} meta={`Step ${index + 1}`}>
            <div className="prototype-panel-note">
              {index === 0 && `候选 ${Math.max(evidence.candidates.length, evidence.signals.length)} 条，保留来源模式、评分、证据和账户归属。`}
              {index === 1 && `方案 ${evidence.plans.length} 条，订单 ${evidence.orders.length} 条，必须带 plan_id、candidate_id、decision_context_id。`}
              {index === 2 && `RiskVerdict ${evidence.verdicts.length} 条，未通过时只能保存草稿，不能进入实盘提交。`}
            </div>
          </PrototypeCard>
        ))}
      </div>
    </PrototypePage>
  )
}
