import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BarChartOutlined, LineChartOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { P0WorkflowNav } from '../components/layout'
import {
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SideRail,
} from '../components/prototype'
import { backtestApi, tradeApi } from '../api/client'
import type { RiskVerdictRecord } from '../api/types'

interface ReviewRow {
  orderId: string
  verdictId: string
  decisionContextId: string
  planId: string
  candidateId: string
  reason: string
}

const tabs = [
  { key: 'overview', path: '/backtest', label: '回测总览', subLabel: '收益 / 回撤' },
  { key: 'run', path: '/backtest/run', label: '运行回测', subLabel: '参数执行' },
  { key: 'compare', path: '/backtest/compare', label: '策略对比', subLabel: '组合比较' },
  { key: 'trades', path: '/backtest/trades', label: '交易复盘', subLabel: '交易拆解' },
]

function activeKey(pathname: string) {
  if (pathname.endsWith('/run')) return 'run'
  if (pathname.endsWith('/compare')) return 'compare'
  if (pathname.endsWith('/trades')) return 'trades'
  return 'overview'
}

export default function Backtest() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const [reviewRows, setReviewRows] = useState<ReviewRow[]>([])

  useEffect(() => {
    backtestApi.getFactors().catch(() => undefined)
  }, [])

  useEffect(() => {
    if (active !== 'trades') return
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
  }, [active])

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="回测分析页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`回测分析 - ${activeTab.label}`}
        subtitle="参数运行 · 收益曲线 · 策略对比 · 交易拆解"
        actions={[
          { key: 'plan', label: '方案关联', active: true },
          { key: 'review', label: '复盘可追踪', tone: 'neutral' },
          { key: 'risk', label: '关联风控', tone: 'warn' },
        ]}
      />
      <P0WorkflowNav currentStep="review" />

      <div className="kpis">
        <MetricCard label="最近回测" value="23" sub="方案关联" tone="accent" />
        <MetricCard label="平均收益" value="+8.5%" sub="近 30 日" tone="up" />
        <MetricCard label="最大回撤" value="-4.2%" sub="需复核" tone="warn" />
        <MetricCard label="复盘样本" value={String(reviewRows.length || 9)} sub="Order/Risk" tone="muted" />
      </div>

      {active === 'overview' && (
        <div className="row r-6-4">
          <PrototypeCard title="收益曲线摘要" icon={<LineChartOutlined />} meta="Backtest">
            {[
              ['累计收益', 68, 'var(--down)'],
              ['胜率', 72, 'var(--accent)'],
              ['回撤控制', 54, 'var(--warn)'],
              ['换手稳定', 61, 'var(--up)'],
            ].map(([label, value, color]) => (
              <div className="dim-row" key={String(label)}>
                <div className="dim-lbl">{label}</div>
                <div className="dim-bar-wrap"><div className="dim-bar" style={{ width: `${value}%`, background: String(color) }} /></div>
                <div className="dim-val">{value}</div>
              </div>
            ))}
          </PrototypeCard>
          <SideRail title="复盘链路" meta="Plan / Backtest">
            <RiskBanner status="review" title="等待订单回填" detail="正式复盘需要关联订单、风控判定和决策上下文。" />
          </SideRail>
        </div>
      )}

      {active === 'run' && (
        <PrototypeCard title="运行回测" icon={<BarChartOutlined />} meta="参数执行">
          <div className="row r-3">
            {['时间窗口 60 日', 'Top 30 候选', '前向收益 20 日'].map(item => (
              <div className="prototype-fallback" key={item}>{item}</div>
            ))}
          </div>
          <button type="button" className="btn primary mt14">运行回测</button>
        </PrototypeCard>
      )}

      {active === 'compare' && (
        <PrototypeCard title="策略对比" icon={<BarChartOutlined />} meta="组合比较">
          <table className="tbl">
            <thead><tr><th>策略</th><th className="r">收益</th><th className="r">最大回撤</th><th className="r">IC</th></tr></thead>
            <tbody>
              <tr><td className="nm">半导体竞价共振</td><td className="r up">+12.1%</td><td className="r down">-4.2%</td><td className="r mono">0.18</td></tr>
              <tr><td className="nm">价值回撤低吸</td><td className="r up">+6.4%</td><td className="r down">-2.1%</td><td className="r mono">0.12</td></tr>
            </tbody>
          </table>
        </PrototypeCard>
      )}

      {active === 'trades' && (
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
      )}
    </PrototypePage>
  )
}
