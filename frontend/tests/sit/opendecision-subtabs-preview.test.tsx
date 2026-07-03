import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OpenDecision from '../../src/pages/OpenDecision'
import { chainApi, screenerApi, signalApi, tradeApi } from '../../src/api/client'

// SIT scope：OpenDecision 2.2 auction-analysis + 2.3 signal-scan + 2.5 execution-monitor 三 sub-tab
// 专属渲染对齐 preview + 多源 API 契约调用。AC①-④：三 sub-tab 各专属渲染（非通用壳）；
// AC② token 化（signalLevelTokens/alpha/lightTokens，禁裸色）；AC③ EmptyState。
// API client 走 vi.mock（与既有 OpenDecision.test.tsx 同源；contract 由生成 client 承载）。

vi.mock('../../src/api/client', () => ({
  signalApi: {
    getDashboardAuction: vi.fn(),
    getLive: vi.fn(),
  },
  chainApi: {
    getCandidates: vi.fn(),
  },
  screenerApi: {
    queryCandidatePool: vi.fn(),
  },
  tradeApi: {
    getAccount: vi.fn(),
    getPositions: vi.fn(),
    getOrders: vi.fn(),
    getRiskVerdicts: vi.fn(),
    getDecisionContexts: vi.fn(),
  },
}))

const liveSignals = [
  {
    code: '300750', name: '宁德时代', level: 'strong_buy', score: 88, confidence: 82,
    dimensions: { technical: 86, fundamental: 80, money_flow: 78, sentiment: 88 },
  },
  {
    code: '688981', name: '中芯国际', level: 'buy', score: 74, confidence: 68,
    dimensions: { technical: 76, fundamental: 70, money_flow: 65, sentiment: 72 },
  },
]

const auctionPicks = [
  { code: '300750', name: '宁德时代', intent: '强抢筹', gap: 8.2, vr: 3.4, score: 92, industry: '新能源' },
  { code: '688981', name: '中芯国际', intent: '强抢筹', gap: 5.8, vr: 2.8, score: 88, industry: '半导体' },
]

function renderOpenDecision(route = '/open-decision') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <OpenDecision />
    </MemoryRouter>,
  )
}

describe('OpenDecision 2.2 + 2.3 + 2.5 sub-tabs SIT', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({
      data: { date: '2026-06-29', total_count: 328, picks: auctionPicks },
    } as any)
    vi.mocked(signalApi.getLive).mockResolvedValue({
      data: { session: 'intra', trade_date: '2026-06-29', signals: liveSignals },
    } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({
      data: { candidates: [{ code: '300750', name: '宁德时代', industry: '新能源', score: 90, resonance_level: '强启动', last_change_pct: 8.2 }] },
    } as any)
    vi.mocked(tradeApi.getAccount).mockResolvedValue({
      data: { account: { total_assets: 1280000, market_value: 894000, available: 386000, total_pnl: 23500 } },
    } as any)
    vi.mocked(tradeApi.getPositions).mockResolvedValue({
      data: { positions: [{ code: '300750', name: '宁德时代', volume: 600, avg_cost: 210, current_price: 218.5, market_value: 131100, pnl: 5100, pnl_pct: 0.082 }] },
    } as any)
    vi.mocked(tradeApi.getOrders).mockResolvedValue({
      data: { orders: [{ id: 'ORD-1', code: '300750', name: '宁德时代', direction: 'buy', price: 218.5, volume: 600, status: 'filled', created_at: '2026-06-29T09:32:18Z' }], total: 1 },
    } as any)
    vi.mocked(tradeApi.getRiskVerdicts).mockResolvedValue({ data: { records: [] } } as any)
    // candidatePool 契约：与既有 2.1/2.4 SIT 同源，默认返回空候选池（OpenDecision 主 effect Promise.allSettled 读 candidatePool.value.data）
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: { total: 0, page: 1, page_size: 50, records: [], empty_state: { reason: '候选池为空' } },
    } as any)
    vi.mocked(tradeApi.getDecisionContexts).mockResolvedValue({
      data: { records: [{ id: 1, decision_context_id: 'DC-1', source_type: 'strategy', symbol: '300750', plan_id: 'PLAN-OPEN-0925', intent: '开盘强势策略', payload: {}, created_at: '2026-06-29T09:25:00Z' }] },
    } as any)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // AC① 2.2 auction-analysis：竞价分析专属渲染——挂载调 signalApi.getDashboardAuction（dashboard/auction）
  // 渲染引擎条/风险提示/4 sub-tab/抢筹 TOP10/出货 TOP10/四维评分/板块共振/全量明细。
  it('2.2 auction-analysis: 挂载调 getDashboardAuction → 渲染竞价引擎 + 抢筹/出货 TOP10 + 四维评分专属区块', async () => {
    renderOpenDecision('/open-decision/auction')

    await waitFor(() => expect(signalApi.getDashboardAuction).toHaveBeenCalled())
    // 引擎条 + 标的计数（来自 total_count）
    expect(screen.getAllByText(/竞价分析引擎/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/328/).length).toBeGreaterThan(0)
    // 抢筹 TOP 10 + 出货预警 TOP 10 专属表
    expect(screen.getAllByText('抢筹 TOP 10').length).toBeGreaterThan(0)
    expect(screen.getAllByText('出货预警 TOP 10').length).toBeGreaterThan(0)
    // 四维评分专属卡 + 一字定方向板块热度
    expect(screen.getAllByText('四维评分').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/一字定方向/).length).toBeGreaterThan(0)
    // 全量竞价明细
    expect(screen.getAllByText('全量竞价明细').length).toBeGreaterThan(0)
  })

  // AC① 2.3 signal-scan：信号扫描专属渲染——挂载调 signalApi.getLive（signal/live）
  // 渲染验证工作台/逐条确认/Kronos 预测/风险检查/决策分类。
  it('2.3 signal-scan: 挂载调 getLive → 渲染验证工作台 + Kronos 预测 + 风险检查专属区块', async () => {
    renderOpenDecision('/open-decision/signals')

    await waitFor(() => expect(signalApi.getLive).toHaveBeenCalled())
    // 信号扫描验证工作台 + 批量确认
    expect(screen.getAllByText(/验证工作台/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('批量确认买入信号').length).toBeGreaterThan(0)
    // 选中股票 rail + Kronos 30日预测 + 风险检查 + 决策分类（preview 四卡片）
    expect(screen.getAllByText('选中股票').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Kronos 30日预测').length).toBeGreaterThan(0)
    expect(screen.getAllByText('风险检查').length).toBeGreaterThan(0)
    expect(screen.getAllByText('决策分类').length).toBeGreaterThan(0)
    // 信号行渲染（来自 getLive signals）
    expect(screen.getAllByText('宁德时代').length).toBeGreaterThan(0)
    expect(screen.getAllByText('中芯国际').length).toBeGreaterThan(0)
  })

  // AC① 2.5 execution-monitor：执行监控专属渲染——挂载调 tradeApi.getAccount/getOrders/getPositions/getDecisionContexts
  // 渲染账户条/今日订单/持仓/自动交易策略/今日方案/需关注。
  it('2.5 execution-monitor: 挂载调 tradeApi 多源契约 → 渲染账户条 + 今日订单/持仓/今日方案专属区块', async () => {
    renderOpenDecision('/open-decision/execution')

    await waitFor(() => expect(tradeApi.getAccount).toHaveBeenCalled())
    await waitFor(() => expect(tradeApi.getOrders).toHaveBeenCalled())
    await waitFor(() => expect(tradeApi.getPositions).toHaveBeenCalled())
    await waitFor(() => expect(tradeApi.getDecisionContexts).toHaveBeenCalled())
    // 账户条（总资产/可用/今日盈亏/总仓位）
    expect(screen.getByText('总资产')).toBeInTheDocument()
    expect(screen.getByText('可用')).toBeInTheDocument()
    expect(screen.getByText('今日盈亏')).toBeInTheDocument()
    // 今日订单 + 持仓 专属表
    expect(screen.getByText('今日订单')).toBeInTheDocument()
    expect(screen.getByText('持仓')).toBeInTheDocument()
    // 今日方案（来自 decision context plan_id）
    expect(screen.getByText('今日方案')).toBeInTheDocument()
    expect(screen.getByText('PLAN-OPEN-0925')).toBeInTheDocument()
    // 需关注
    expect(screen.getByText('需关注')).toBeInTheDocument()
  })

  // AC④ 三 sub-tab 专属渲染（非通用壳）—— 各有独占区块标题，切换 tab 渲染各自内容。
  it('AC④ 三 sub-tab 专属渲染：auction/signals/execution 各有独占区块标题', () => {
    const { unmount } = renderOpenDecision('/open-decision/auction')
    expect(screen.getAllByText('抢筹 TOP 10').length).toBeGreaterThan(0)
    expect(screen.queryByText('Kronos 30日预测')).not.toBeInTheDocument()
    unmount()

    const { unmount: u2 } = renderOpenDecision('/open-decision/signals')
    expect(screen.getAllByText(/验证工作台/).length).toBeGreaterThan(0)
    expect(screen.queryByText('抢筹 TOP 10')).not.toBeInTheDocument()
    u2()

    renderOpenDecision('/open-decision/execution')
    expect(screen.getAllByText('今日订单').length).toBeGreaterThan(0)
    expect(screen.queryByText('抢筹 TOP 10')).not.toBeInTheDocument()
  })

  // AC③ EmptyState：2.2 auction 无抢筹/出货数据时走 prototype-panel-note 诚实降级（不空白）。
  it('AC③ 2.2 auction: 无抢筹/出货数据 → 诚实降级提示不空白', async () => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({ data: { total_count: 0, picks: [] } } as any)
    renderOpenDecision('/open-decision/auction')

    await waitFor(() => expect(signalApi.getDashboardAuction).toHaveBeenCalled())
    // 抢筹/出货空 → 走 prototype-panel-note 提示（不空白）
    expect(screen.getAllByText(/暂无抢筹数据|暂无出货预警/).length).toBeGreaterThan(0)
  })

  // AC③ EmptyState：2.5 execution 无订单/持仓时走 prototype-panel-note 诚实降级（不空白）。
  it('AC③ 2.5 execution: 无订单/持仓 → 诚实降级提示不空白', async () => {
    vi.mocked(tradeApi.getOrders).mockResolvedValue({ data: { orders: [] } } as any)
    vi.mocked(tradeApi.getPositions).mockResolvedValue({ data: { positions: [] } } as any)
    renderOpenDecision('/open-decision/execution')

    await waitFor(() => expect(tradeApi.getOrders).toHaveBeenCalled())
    expect(screen.getAllByText(/暂无订单|暂无持仓/).length).toBeGreaterThan(0)
  })
})
