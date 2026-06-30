import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BarChartOutlined, LineChartOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { P0WorkflowNav } from '../components/layout'
import {
  EmptyState,
  DataFreshnessBar,
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

interface BacktestViewRow {
  id: string
  name: string
  totalReturn?: number
  sharpe?: number
  maxDrawdown?: number
  winRate?: number
  totalTrades?: number
  detail?: string
}

function formatPct(value?: number) {
  if (typeof value !== 'number') return '--'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function average(values: number[]) {
  if (values.length === 0) return undefined
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function rowsFromRunResult(data: any): BacktestViewRow[] {
  if (Array.isArray(data?.results)) {
    return data.results.map((item: any) => ({
      id: item.strategy_id,
      name: item.strategy_name || item.strategy_id,
      totalReturn: item.total_return,
      sharpe: item.sharpe_ratio,
      maxDrawdown: item.max_drawdown,
      winRate: item.win_rate,
      totalTrades: item.total_trades,
    }))
  }
  if (Array.isArray(data?.details)) {
    return data.details.map((item: any) => ({
      id: `window-${item.window}`,
      name: `窗口 ${item.window}: ${item.start_date || '--'} ~ ${item.end_date || '--'}`,
      totalReturn: item.avg_return_pct,
      sharpe: data.summary?.icir,
      winRate: item.hit_rate_pct,
      totalTrades: item.picks,
      detail: `IC ${item.ic ?? '--'} / 超额 ${formatPct(item.excess_return)}`,
    }))
  }
  if (data?.summary) {
    return [{
      id: 'summary',
      name: '回测汇总',
      totalReturn: data.summary.avg_excess_return,
      sharpe: data.summary.icir,
      winRate: data.summary.avg_hit_rate,
      totalTrades: data.summary.total_windows,
    }]
  }
  return []
}

function rowsFromCompareResult(data: any): BacktestViewRow[] {
  if (Array.isArray(data?.comparison)) {
    return data.comparison.map((item: any) => ({
      id: item.strategy_id,
      name: item.strategy_name || item.strategy_id,
      totalReturn: item.total_return,
      maxDrawdown: item.max_drawdown,
      winRate: item.win_rate,
      totalTrades: item.total_trades,
    }))
  }
  if (Array.isArray(data?.strategies)) {
    return data.strategies.map((item: any) => ({
      id: item.strategy,
      name: item.strategy,
      totalReturn: item.avg_return,
      totalTrades: item.samples,
      detail: item.period,
    }))
  }
  return []
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
  const [factorCount, setFactorCount] = useState(0)
  const [runResult, setRunResult] = useState<any | null>(null)
  const [compareResult, setCompareResult] = useState<any | null>(null)
  const [loadingRun, setLoadingRun] = useState(false)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    backtestApi.getFactors()
      .then(response => setFactorCount((response.data as any)?.factors?.length || 0))
      .catch(() => setFactorCount(0))
  }, [])

  useEffect(() => {
    if (active !== 'compare') return
    let mounted = true
    backtestApi.compare()
      .then(response => {
        if (!mounted) return
        setCompareResult(response.data)
        setLoadError('')
      })
      .catch(() => {
        if (!mounted) return
        setCompareResult(null)
        setLoadError('策略对比接口连接异常')
      })
    return () => {
      mounted = false
    }
  }, [active])

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

  const runBacktest = () => {
    setLoadingRun(true)
    backtestApi.run({ mode: 'all', windows: 3, top_n: 30, forward_days: 60 })
      .then(response => {
        setRunResult(response.data)
        setLoadError('')
      })
      .catch(() => {
        setRunResult(null)
        setLoadError('运行回测失败')
      })
      .finally(() => setLoadingRun(false))
  }

  const runRows = rowsFromRunResult(runResult)
  const compareRows = rowsFromCompareResult(compareResult)
  const visibleResults = active === 'compare' ? compareRows : runRows
  const numericReturns = visibleResults.map(item => item.totalReturn).filter((value): value is number => typeof value === 'number')
  const numericDrawdowns = visibleResults.map(item => item.maxDrawdown).filter((value): value is number => typeof value === 'number')
  const avgReturn = average(numericReturns)
  const maxDrawdown = numericDrawdowns.length > 0 ? Math.min(...numericDrawdowns) : undefined
  const backtestFreshness = (active === 'compare' ? compareResult : runResult) as any

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
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={backtestFreshness?.data_freshness?.as_of || backtestFreshness?.summary?.end_date || backtestFreshness?.end_date}
            updatedAt={backtestFreshness?.generated_at || backtestFreshness?.updated_at || backtestFreshness?.data_freshness?.as_of}
            source={active === 'trades' ? 'trade-service' : 'backtest-service'}
          />
        )}
        actions={[
          { key: 'plan', label: '方案关联', active: true },
          { key: 'review', label: '复盘可追踪', tone: 'neutral' },
          { key: 'risk', label: '关联风控', tone: 'warn' },
        ]}
      />
      <P0WorkflowNav currentStep="review" />

      <div className="kpis">
        <MetricCard label="可用因子" value={String(factorCount)} sub="backtest/factors" tone="accent" />
        <MetricCard label="回测结果" value={String(visibleResults.length)} sub={active === 'compare' ? 'compare' : 'run'} tone="up" />
        <MetricCard label="平均收益" value={formatPct(avgReturn)} sub="真实接口结果" tone="up" />
        <MetricCard label="最大回撤" value={formatPct(maxDrawdown)} sub="后端返回" tone="warn" />
        <MetricCard label="复盘样本" value={String(reviewRows.length)} sub="Order/Risk" tone="muted" />
      </div>
      {loadError && <RiskBanner status="warn" title="回测服务异常" detail={loadError} />}

      {active === 'overview' && (
        <div className="row r-6-4">
          <PrototypeCard title="收益曲线摘要" icon={<LineChartOutlined />} meta="Backtest">
            {runRows.length > 0 ? (
              runRows.map(result => (
                <div className="dim-row" key={result.id}>
                  <div className="dim-lbl">{result.name}<span>{result.detail || `Sharpe ${result.sharpe ?? '--'}`}</span></div>
                  <div className="dim-bar-wrap">
                    <div className="dim-bar" style={{ width: `${Math.max(0, Math.min(100, result.winRate ?? 0))}%`, background: 'var(--accent)' }} />
                  </div>
                  <div className="dim-val">{formatPct(result.totalReturn)}</div>
                </div>
              ))
            ) : (
              <EmptyState title="暂无回测结果" detail="请到“运行回测”页执行真实回测，页面不会展示固定收益曲线。" />
            )}
          </PrototypeCard>
          <SideRail title="复盘链路" meta="Plan / Backtest">
            <RiskBanner status="review" title="等待真实回测结果" detail="运行回测后展示收益、胜率、回撤等后端返回指标。" />
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
          <button type="button" className="btn primary mt14" onClick={runBacktest} disabled={loadingRun}>
            {loadingRun ? '运行中' : '运行回测'}
          </button>
          {runRows.length > 0 ? (
            <table className="tbl mt14">
              <thead><tr><th>策略</th><th className="r">收益</th><th className="r">Sharpe</th><th className="r">最大回撤</th><th className="r">交易数</th></tr></thead>
              <tbody>
                {runRows.map(result => (
                  <tr key={result.id}>
                    <td className="nm">{result.name}<div className="prototype-panel-note">{result.detail || ''}</div></td>
                    <td className="r up">{formatPct(result.totalReturn)}</td>
                    <td className="r mono">{result.sharpe ?? '--'}</td>
                    <td className="r down">{formatPct(result.maxDrawdown)}</td>
                    <td className="r mono">{result.totalTrades ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState title="尚未运行回测" detail="点击运行后调用 backtest/run，并展示后端返回结果。" />
          )}
        </PrototypeCard>
      )}

      {active === 'compare' && (
        <PrototypeCard title="策略对比" icon={<BarChartOutlined />} meta="组合比较">
          {compareRows.length > 0 ? (
            <table className="tbl">
              <thead><tr><th>策略</th><th className="r">收益</th><th className="r">最大回撤</th><th className="r">胜率</th><th className="r">交易数</th></tr></thead>
              <tbody>
                {compareRows.map(result => (
                  <tr key={result.id}>
                    <td className="nm">{result.name}<div className="prototype-panel-note">{result.detail || ''}</div></td>
                    <td className="r up">{formatPct(result.totalReturn)}</td>
                    <td className="r down">{formatPct(result.maxDrawdown)}</td>
                    <td className="r mono">{formatPct(result.winRate)}</td>
                    <td className="r mono">{result.totalTrades ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState title="暂无策略对比结果" detail="页面已调用 backtest/compare；若接口无数据，会保持空态。" />
          )}
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
                {reviewRows.length === 0 && (
                  <tr><td colSpan={5} className="prototype-panel-note">暂无交易复盘链路。</td></tr>
                )}
              </tbody>
            </table>
          </PrototypeCard>
          <PrototypeCard title="复盘归因" icon={<SafetyCertificateOutlined />} meta="Lineage reason">
            {reviewRows.length > 0 ? (
              reviewRows.map(row => (
                <div className="prototype-fallback" key={`${row.orderId}-reason`} style={{ marginBottom: 10 }}>
                  {row.reason}
                </div>
              ))
            ) : (
              <EmptyState title="暂无复盘归因" detail="需要订单、风控判定和决策上下文共同返回后才能展示。" />
            )}
          </PrototypeCard>
        </div>
      )}
    </PrototypePage>
  )
}
