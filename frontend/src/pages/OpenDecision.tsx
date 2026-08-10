import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { chainApi, screenerApi, signalApi, tradeApi } from '../api/client'
import type { TradeOrder } from '../api/types'
import { DataFreshnessBar, PrototypePage, PrototypePageHeader, PrototypeTabs } from '../components/prototype'
import { activeKey, auctionRowsFromDashboard, auctionRowsFromSignals, bearishRowsFromSignals, candidateRowsFromApi, candidateRowsFromPool, decisionHeader, orderRowsFromApi, positionRowsFromApi, sectorRowsFromCandidates, signalRowsFromApi } from './open-decision/helpers'
import { emptyState } from './open-decision/types'
import type { OpenDecisionState } from './open-decision/types'
import OverviewTab from './open-decision/OverviewTab'
import AuctionTab from './open-decision/AuctionTab'
import SignalsTab from './open-decision/SignalsTab'
import CandidatesTab from './open-decision/CandidatesTab'
import ExecutionTab from './open-decision/ExecutionTab'

const tabs = [
  { key: 'overview', path: '/open-decision', label: '决策总览', subLabel: '开盘闸门' },
  { key: 'auction', path: '/open-decision/auction', label: '竞价分析', subLabel: '集合竞价' },
  { key: 'signals', path: '/open-decision/signals', label: '信号扫描', subLabel: '触发队列' },
  { key: 'candidates', path: '/open-decision/candidates', label: '候选池', subLabel: 'AI 队列' },
  { key: 'execution', path: '/open-decision/execution', label: '执行监控', subLabel: '链路状态' },
]

export default function OpenDecision() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const [state, setState] = useState<OpenDecisionState>(emptyState)

  // refreshData 抽成 callback：供 mount effect + AuctionAnalysis「刷新」按钮共用。
  // loading 由各调用方按需置位（mount 用 state.loading，刷新按钮用各自局部 refreshing）。
  const refreshData = useCallback(async () => {
    const results = await Promise.allSettled([
      signalApi.getDashboardAuction(),
      signalApi.getLive('intra'),
      chainApi.getCandidates({ filter: 'all', top_n: 20 }),
      // 候选池（M0 持久化）：scope 不走明文入参，由拦截器头注入（契约 §9.3）
      screenerApi.queryCandidatePool({ source_module: 'open-decision', page: 1, page_size: 50 }),
      tradeApi.getAccount(),
      tradeApi.getPositions(),
      tradeApi.getOrders(),
      tradeApi.getRiskVerdicts({ page: 1, page_size: 20 }),
      tradeApi.getDecisionContexts({ page: 1, page_size: 20 }),
    ])
    const [auction, live, candidates, candidatePool, account, positions, orders, verdicts, contexts] = results
    const rejected = results.filter(result => result.status === 'rejected').length
    setState({
      auction: auction.status === 'fulfilled' ? auction.value.data || {} : {},
      liveSignals: live.status === 'fulfilled' ? live.value.data?.signals || [] : [],
      liveTradeDate: live.status === 'fulfilled'
        ? (live.value.data as typeof live.value.data & { trade_date?: string })?.trade_date || live.value.data?.data_freshness?.as_of || undefined
        : undefined,
      candidates: candidates.status === 'fulfilled' ? candidates.value.data?.candidates || [] : [],
      candidatePool: candidatePool.status === 'fulfilled' ? candidatePool.value.data : undefined,
      account: account.status === 'fulfilled' ? account.value.data?.account : undefined,
      positions: positions.status === 'fulfilled' ? positions.value.data?.positions || [] : [],
      orders: orders.status === 'fulfilled' ? orders.value.data?.orders || [] : [],
      verdicts: verdicts.status === 'fulfilled' ? verdicts.value.data?.records || [] : [],
      contexts: contexts.status === 'fulfilled' ? contexts.value.data?.records || [] : [],
      loading: false,
      error: rejected ? `${rejected} 个接口连接异常，页面已保留可用数据。` : '',
    })
  }, [])

  useEffect(() => {
    refreshData()
  }, [refreshData])

  const signalRows = useMemo(() => signalRowsFromApi(state.liveSignals, state.verdicts), [state.liveSignals, state.verdicts])
  const chainCandidateRows = useMemo(() => candidateRowsFromApi(state.candidates, state.verdicts), [state.candidates, state.verdicts])
  const poolRecords = useMemo(() => state.candidatePool?.records ?? [], [state.candidatePool])
  const poolCandidateRows = useMemo(() => candidateRowsFromPool(poolRecords, state.verdicts), [poolRecords, state.verdicts])
  // 多源融合去重：chain 候选优先，候选池补齐（按 code 去重）
  const candidateRows = useMemo(() => {
    const seen = new Set<string>()
    return [...chainCandidateRows, ...poolCandidateRows].filter(row => {
      if (seen.has(row.code)) return false
      seen.add(row.code)
      return true
    })
  }, [chainCandidateRows, poolCandidateRows])
  const candidatePoolTotal = state.candidatePool?.total ?? 0
  // DEF-3: 后端实际返 empty_state {hint, suggestion}（types.ts 标 {reason}）；最小侵入兼容三者，不碰临界区 types.ts
  const candidatePoolEmptyState = state.candidatePool?.empty_state as { reason?: string; hint?: string; suggestion?: string } | undefined
  const candidatePoolEmptyReason = candidatePoolEmptyState?.reason || candidatePoolEmptyState?.hint || candidatePoolEmptyState?.suggestion
  const sectors = useMemo(() => sectorRowsFromCandidates(state.candidates), [state.candidates])
  const dashboardAuctionRows = useMemo(() => auctionRowsFromDashboard(state.auction), [state.auction])
  const bullishRows = useMemo(
    () => dashboardAuctionRows.bullish.length ? dashboardAuctionRows.bullish : auctionRowsFromSignals(signalRows, candidateRows),
    [dashboardAuctionRows.bullish, signalRows, candidateRows],
  )
  const bearishRows = useMemo(
    () => dashboardAuctionRows.bearish.length ? dashboardAuctionRows.bearish : bearishRowsFromSignals(signalRows),
    [dashboardAuctionRows.bearish, signalRows],
  )
  const orderRows = useMemo(() => orderRowsFromApi(state.orders), [state.orders])
  const positionRows = useMemo(() => positionRowsFromApi(state.positions, state.account?.market_value), [state.positions, state.account?.market_value])
  const auctionTradeDate = typeof state.auction.trade_date === 'string'
    ? state.auction.trade_date
    : (typeof state.auction.date === 'string' ? state.auction.date : undefined)
  const candidateTradeDates = state.candidates
    .map(candidate => candidate.last_trade_date)
    .filter((value): value is string => typeof value === 'string' && value.length > 0)
    .sort()
  const candidatesTradeDate = candidateTradeDates[candidateTradeDates.length - 1]
  const freshnessTradeDate = active === 'signals'
    ? state.liveTradeDate || auctionTradeDate
    : active === 'candidates'
      ? candidatesTradeDate || auctionTradeDate
      : auctionTradeDate
  const freshnessSource = active === 'execution'
    ? 'trade-service'
    : active === 'signals'
      ? 'signal/live'
      : active === 'candidates'
        ? 'supply-chain/workbench'
        : 'dashboard/auction'
  const auctionUpdatedAt = typeof state.auction.updated_at === 'string'
    ? state.auction.updated_at
    : (typeof state.auction.refreshed_at === 'string' ? state.auction.refreshed_at : undefined)
  const firstOrder = state.orders[0] as (TradeOrder & { updated_at?: string; created_at?: string }) | undefined
  const latestRuntimeUpdate = auctionUpdatedAt
    || firstOrder?.updated_at
    || firstOrder?.created_at
    || state.contexts[0]?.created_at
    || state.verdicts[0]?.created_at

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="开盘决策页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ key: tab.key, label: tab.label, subLabel: tab.subLabel, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`开盘决策 - ${activeTab.label}`}
        subtitle={decisionHeader(activeTab.label)}
        dataFreshness={<DataFreshnessBar tradeDate={freshnessTradeDate} updatedAt={latestRuntimeUpdate} source={freshnessSource} />}
      />

      {active === 'overview' && <OverviewTab loading={state.loading} error={state.error} signalRows={signalRows} candidateRows={candidateRows} sectorRows={sectors} />}
      {active === 'auction' && <AuctionTab loading={state.loading} error={state.error} bullishRows={bullishRows} bearishRows={bearishRows} candidateRows={candidateRows} sectorRows={sectors} auction={state.auction} tradeDate={freshnessTradeDate} onRefresh={refreshData} />}
      {active === 'signals' && <SignalsTab loading={state.loading} error={state.error} signalRows={signalRows} />}
      {active === 'candidates' && <CandidatesTab loading={state.loading} error={state.error} candidateRows={candidateRows} verdicts={state.verdicts} poolTotal={candidatePoolTotal} poolEmptyReason={candidatePoolEmptyReason} />}
      {active === 'execution' && <ExecutionTab loading={state.loading} error={state.error} account={state.account} orderRows={orderRows} positionRows={positionRows} contexts={state.contexts} />}
    </PrototypePage>
  )
}
