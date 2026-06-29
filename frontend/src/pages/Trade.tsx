import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ApiOutlined, SafetyCertificateOutlined, WalletOutlined } from '@ant-design/icons'
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
  SegmentTabs,
  SideRail,
} from '../components/prototype'
import { tradeApi } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useLiveTrade, type OrderParams, type PreCheckResult } from '../hooks/useLiveTrade'

type RiskVerdictLike = Record<string, any>

const tabs = [
  { key: 'overview', path: '/trade', label: '交易总览', subLabel: '账户状态' },
  { key: 'order', path: '/trade/order', label: '下单面板', subLabel: 'P0 执行' },
  { key: 'positions', path: '/trade/positions', label: '持仓监控', subLabel: '资金 / 盈亏' },
  { key: 'orders', path: '/trade/orders', label: '订单管理', subLabel: '委托 / 成交' },
  { key: 'account', path: '/trade/account', label: '账户总览', subLabel: '券商资金' },
  { key: 'brokers', path: '/trade/brokers', label: '券商管理', subLabel: 'QMT / 模拟' },
]

function activeKey(pathname: string) {
  const last = pathname.split('/').filter(Boolean).pop()
  if (last && tabs.some(tab => tab.key === last)) return last
  return 'overview'
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

function rowsFromResponse(data: any, key: string) {
  const rows = data?.[key] || data?.records || data?.items || []
  return Array.isArray(rows) ? rows : []
}

function numberValue(value: unknown, fallback = '--') {
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string' && value !== '') return value
  return fallback
}

function buildRiskQuery({
  riskVerdict,
  code,
  decisionContextId,
  candidateId,
  planId,
}: {
  riskVerdict: RiskVerdictLike | null
  code: string
  decisionContextId: string
  candidateId: string
  planId: string
}) {
  const params = new URLSearchParams()
  if (decisionContextId || riskVerdict?.decision_context_id) params.set('decision_context_id', decisionContextId || riskVerdict?.decision_context_id)
  if (riskVerdict?.order_id) params.set('order_id', riskVerdict.order_id)
  if (planId || riskVerdict?.plan_id) params.set('plan_id', planId || riskVerdict?.plan_id)
  if (candidateId || riskVerdict?.candidate_id) params.set('candidate_id', candidateId || riskVerdict?.candidate_id)
  if (code || riskVerdict?.symbol) params.set('code', code || riskVerdict?.symbol)
  return params.toString()
}

export default function Trade() {
  const location = useLocation()
  const navigate = useNavigate()
  const user = useOptionalAuthUser()
  const liveTrade = useLiveTrade()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const query = useMemo(() => new URLSearchParams(location.search), [location.search])
  const [code, setCode] = useState(query.get('code') || '')
  const [price, setPrice] = useState(query.get('price') ? Number(query.get('price')).toFixed(2) : '10.00')
  const [volume, setVolume] = useState('')
  const [decisionContextId, setDecisionContextId] = useState(query.get('decision_context_id') || '')
  const [candidateId, setCandidateId] = useState(query.get('candidate_id') || '')
  const [planId, setPlanId] = useState(query.get('plan_id') || '')
  const [error, setError] = useState('')
  const [dataError, setDataError] = useState('')
  const [account, setAccount] = useState<Record<string, any> | null>(null)
  const [positions, setPositions] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [riskVerdict, setRiskVerdict] = useState<RiskVerdictLike | null>(null)
  const accountId = account?.account_id || user?.defaultTradeAccountId || '暂无账户'
  const riskChecks = getRiskChecks(riskVerdict)
  const latestTradeUpdate = orders[0]?.updated_at || orders[0]?.created_at || positions[0]?.updated_at || account?.updated_at

  useEffect(() => {
    if (liveTrade.mode !== 'paper') liveTrade.setMode('paper')
  }, [liveTrade.mode, liveTrade.setMode])

  useEffect(() => {
    let mounted = true
    Promise.allSettled([
      tradeApi.getAccount(),
      tradeApi.getPositions(),
      tradeApi.getOrders(),
    ]).then(([accountResult, positionsResult, ordersResult]) => {
      if (!mounted) return
      if (accountResult.status === 'fulfilled') setAccount(accountResult.value.data as Record<string, any>)
      if (positionsResult.status === 'fulfilled') setPositions(rowsFromResponse(positionsResult.value.data, 'positions'))
      if (ordersResult.status === 'fulfilled') setOrders(rowsFromResponse(ordersResult.value.data, 'orders'))
      const failed = [accountResult, positionsResult, ordersResult].filter(result => result.status === 'rejected').length
      setDataError(failed > 0 ? `${failed} 个交易数据接口暂不可用` : '')
    })
    return () => {
      mounted = false
    }
  }, [])

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
      const nextVerdict = result.data?.risk_verdict || result.data
      setRiskVerdict({
        ...nextVerdict,
        order_id: nextVerdict?.order_id || result.data?.order_id,
        code: nextVerdict?.code || result.data?.code,
      })
    } else if (result.error) {
      setError(result.error)
    }
  }

  const riskQuery = buildRiskQuery({ riskVerdict, code, decisionContextId, candidateId, planId })

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="交易中心页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`交易中心 - ${activeTab.label}`}
        subtitle="下单面板 · 持仓资金 · 委托回报 · 券商通道"
        dataFreshness={<DataFreshnessBar updatedAt={latestTradeUpdate} source="trade-service" />}
        actions={[
          { key: 'paper', label: '模拟盘安全', active: true },
          { key: 'live', label: '实盘锁定', tone: 'warn' },
          { key: 'broker', label: liveTrade.brokerStatus === 'connected' ? '券商已连接' : '券商未连接', tone: 'neutral' },
        ]}
      />
      <P0WorkflowNav currentStep="order" />

      <div className="kpis">
        <MetricCard label="交易模式" value={liveTrade.mode === 'live' ? 'Live' : 'Paper'} sub="hook 状态" tone="accent" />
        <MetricCard label="风控规则" value={String(riskChecks.length)} sub="最近一次预检" tone="warn" />
        <MetricCard label="今日委托" value={String(orders.length)} sub="trade/orders" tone="muted" />
        <MetricCard label="券商状态" value={liveTrade.brokerStatus} sub="broker/status" tone={liveTrade.brokerStatus === 'connected' ? 'up' : 'down'} />
      </div>
      {dataError && <RiskBanner status="warn" title="交易数据接口异常" detail={dataError} />}

      {(active === 'overview' || active === 'order') && (
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
                <button type="button" className="btn ghost" onClick={() => navigate('/trade/risk-verdicts')}>进入风控中心</button>
              </div>
            </form>
          </PrototypeCard>

          <div className="grid">
            <PrototypeCard title="下单安全门" icon={<SafetyCertificateOutlined />} meta="默认仅模拟盘">
              <SegmentTabs
                ariaLabel="交易模式"
                activeKey="paper"
                onChange={() => undefined}
                items={[{ key: 'paper', label: '模拟盘' }, { key: 'live', label: '实盘锁定中' }]}
              />
              <RiskBanner status="warn" title="实盘默认关闭" detail="实盘/QMT 提交保持关闭；当前只提交模拟盘订单，实盘必须经过券商配置与风控判定。" />
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
                <button type="button" className="btn sm mt14" onClick={() => navigate(`/trade/risk-verdicts?${riskQuery}`)}>
                  查看风控
                </button>
              </PrototypeCard>
            )}
          </div>
        </div>
      )}

      {active === 'positions' && (
        <div className="row r-6-4">
          <PrototypeCard title="持仓监控" icon={<WalletOutlined />} meta="Position">
            <table className="tbl">
              <thead><tr><th>代码</th><th>名称</th><th className="r">数量</th><th className="r">成本</th><th className="r">浮盈</th></tr></thead>
              <tbody>
                {positions.map(row => (
                  <tr key={row.code || row.symbol || row.stock_code}>
                    <td className="code">{textValue(row.code || row.symbol || row.stock_code)}</td>
                    <td className="nm">{textValue(row.name || row.stock_name)}</td>
                    <td className="r mono">{numberValue(row.volume || row.quantity || row.current_volume || row.available_volume)}</td>
                    <td className="r mono">{numberValue(row.cost || row.cost_price || row.avg_cost)}</td>
                    <td className="r up">{numberValue(row.pnl_pct || row.profit_rate || row.pnl)}</td>
                  </tr>
                ))}
                {positions.length === 0 && (
                  <tr><td colSpan={5} className="prototype-panel-note">暂无持仓数据。</td></tr>
                )}
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="持仓风控" meta="Account">
            <RiskBanner status={positions.length > 0 ? 'review' : 'warn'} title={positions.length > 0 ? '持仓来自交易服务' : '暂无持仓'} detail="持仓集中度、止损线和可用资金以后端账户数据为准。" />
          </SideRail>
        </div>
      )}

      {active === 'orders' && (
        <PrototypeCard title="订单管理" icon={<SafetyCertificateOutlined />} meta="Order">
          <table className="tbl">
            <thead><tr><th>订单</th><th>代码</th><th>方向</th><th className="r">数量</th><th className="r">状态</th></tr></thead>
            <tbody>
              {orders.map(row => (
                <tr key={row.order_id || row.id}>
                  <td className="code">{textValue(row.order_id || row.id)}</td>
                  <td className="code">{textValue(row.code || row.symbol || row.stock_code)}</td>
                  <td>{textValue(row.direction || row.side)}</td>
                  <td className="r mono">{numberValue(row.volume || row.quantity)}</td>
                  <td className="r">{textValue(row.status)}</td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr><td colSpan={5} className="prototype-panel-note">暂无订单数据。</td></tr>
              )}
            </tbody>
          </table>
        </PrototypeCard>
      )}

      {active === 'account' && (
        <div className="row r-6-4">
          <PrototypeCard title="账户总览" icon={<WalletOutlined />} meta={accountId}>
            {account ? (
              <div className="op-hint">
                <div className="pos warn">{liveTrade.mode === 'live' ? 'Live' : 'Paper'}</div>
                <div>
                  <div className="op-title">{textValue(account.account_name || account.account_id, accountId)}</div>
                  <div className="op-desc">
                    总资产 {numberValue(account.total_capital || account.total_assets)}，可用 {numberValue(account.available)}，市值 {numberValue(account.market_value)}。
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState title="暂无账户数据" detail="trade/account 当前未返回账户详情。" />
            )}
          </PrototypeCard>
          <SideRail title="数据域" meta="tenant/user/account">
            <DataDomainBadge domain="account" label="账户私有交易数据" />
            <LineageChips items={[{ label: 'Account', value: accountId }, { label: 'Broker', value: 'paper' }]} />
          </SideRail>
        </div>
      )}

      {active === 'brokers' && (
        <PrototypeCard title="券商管理" icon={<ApiOutlined />} meta="QMT / MockBroker">
          <table className="tbl">
            <tbody>
              <tr><td>当前模式</td><td><span className="tag t-neu">{liveTrade.mode}</span></td><td className="r">{accountId}</td></tr>
              <tr><td>券商状态</td><td><span className="tag t-warn">{liveTrade.brokerStatus}</span></td><td className="r">来自 broker/status</td></tr>
              <tr><td>风控配置</td><td><span className="tag t-neu">{liveTrade.riskConfig ? '已加载' : '未返回'}</span></td><td className="r">{liveTrade.riskConfig?.max_single_amount ?? '--'}</td></tr>
              <tr><td>熔断状态</td><td><span className="tag t-neu">{liveTrade.circuitBreaker?.status || '未返回'}</span></td><td className="r">{liveTrade.circuitBreaker?.date || '--'}</td></tr>
            </tbody>
          </table>
        </PrototypeCard>
      )}
    </PrototypePage>
  )
}
