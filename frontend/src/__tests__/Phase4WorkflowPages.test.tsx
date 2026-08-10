import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import P0Workflow from '../pages/P0Workflow'
import RiskControl from '../pages/RiskControl'
import { backtestApi, chainApi, signalApi, strategyApi, tradeApi } from '../api/client'

vi.mock('../api/client', () => ({
  backtestApi: {
    getFactors: vi.fn(),
  },
  chainApi: {
    getCandidates: vi.fn(),
  },
  signalApi: {
    getLive: vi.fn(),
  },
  strategyApi: {
    getPlans: vi.fn(),
    listInstances: vi.fn(),
    pauseInstance: vi.fn(),
    resumeInstance: vi.fn(),
  },
  tradeApi: {
    getOrders: vi.fn(),
    getRiskVerdicts: vi.fn(),
    getDecisionContexts: vi.fn(),
    getAuditLogs: vi.fn(),
    getRiskConfig: vi.fn(),
    getCircuitBreakerStatus: vi.fn(),
    getPositions: vi.fn(),
  },
}))

function renderPage(page: React.ReactNode, route: string) {
  return render(<MemoryRouter initialEntries={[route]}>{page}</MemoryRouter>)
}

describe('Phase 4 workflow pages', () => {
  beforeEach(() => {
    vi.mocked(chainApi.getCandidates).mockResolvedValue({
      data: {
        filter: 'all',
        total_count: 1,
        candidates: [{ code: '002138', name: '顺络电子', score: 88, industry: '电子元件' }],
        filter_summary: {},
        resonance_summary: {},
        elapsed_ms: 12,
      },
    } as any)
    vi.mocked(strategyApi.getPlans).mockResolvedValue({
      data: {
        plans: [{ id: 'PLAN-live-001', name: 'P0 paper plan', max_positions: 5, capital: 1000000, status: 'active' }],
        total: 1,
      },
    } as any)
    vi.mocked(tradeApi.getOrders).mockResolvedValue({
      data: {
        orders: [{ id: 'ORD-live-001', code: '002138', name: '顺络电子', direction: 'buy', price: 42.8, volume: 1000, status: 'pending', plan_id: 'PLAN-live-001' }],
        total: 1,
      },
    } as any)
    vi.mocked(signalApi.getLive).mockResolvedValue({
      data: {
        session: 'intra',
        signals: [{ code: '002138', name: '顺络电子', level: 'buy', score: 76, confidence: 72 }],
      },
    } as any)
    vi.mocked(backtestApi.getFactors).mockResolvedValue({
      data: { factors: [{ name: 'momentum', category: 'technical' }] },
    } as any)
    vi.mocked(tradeApi.getRiskVerdicts).mockResolvedValue({
      data: {
        records: [{
          id: 1,
          verdict_id: 'RV-live-001',
          tenant_id: 'default',
          result: 'reject',
          scope: 'order',
          trade_mode: 'paper',
          symbol: '002138',
          order_id: 'ORD-live-001',
          plan_id: 'PLAN-live-001',
          candidate_id: 'CAND-live-001',
          decision_context_id: 'CTX-live-001',
          details: { risk_check: { checks: [{ rule: '仓位上限', passed: false }] } },
          created_at: '2026-06-29T09:30:00Z',
        }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    } as any)
    vi.mocked(tradeApi.getDecisionContexts).mockResolvedValue({
      data: {
        records: [{
          id: 1,
          decision_context_id: 'CTX-live-001',
          tenant_id: 'default',
          source_type: 'order',
          symbol: '002138',
          plan_id: 'PLAN-live-001',
          candidate_id: 'CAND-live-001',
          intent: '下单前风控',
          payload: {},
          created_at: '2026-06-29T09:30:00Z',
        }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    } as any)
    vi.mocked(tradeApi.getAuditLogs).mockResolvedValue({
      data: { records: [{ id: 1, action_type: 'risk_check' }], total: 1, page: 1, page_size: 20 },
    } as any)
    vi.mocked(tradeApi.getRiskConfig).mockResolvedValue({
      data: { max_position_pct: 0.2, max_single_amount: 100000, price_limit_pct: 0.1, large_order_threshold: 50000 },
    } as any)
    vi.mocked(tradeApi.getCircuitBreakerStatus).mockResolvedValue({
      data: { breakers: [{ account_id: 'default', status: 'NORMAL', daily_loss_pct: 0, threshold_pct: 5, daily_pnl: 0, can_trade: true }] },
    } as any)
    vi.mocked(tradeApi.getPositions).mockResolvedValue({
      data: {
        positions: [{ code: '002138', name: '顺络电子', volume: 1000, avg_cost: 40, current_price: 42.8, market_value: 42800, pnl: 2800, pnl_pct: 0.07, stop_loss: 41.5 }],
        total_market_value: 42800,
        total_pnl: 2800,
      },
    } as any)
    vi.mocked(strategyApi.listInstances).mockResolvedValue({
      data: {
        strategies: [{ id: 'STR-live-001', name: '动量执行器', status: 'active', risk_rules: { daily_max_loss_pct: 0.03, stop_loss_pct: 0.03 } }],
        total: 1,
      },
    } as any)
  })

  it('renders the P0 decision chain with the five shared objects', () => {
    renderPage(<P0Workflow />, '/p0')

    expect(screen.getByRole('heading', { name: 'P0 主链路' })).toBeInTheDocument()
    expect(screen.getByText('Candidate')).toBeInTheDocument()
    expect(screen.getByText('Plan')).toBeInTheDocument()
    expect(screen.getByText('Order')).toBeInTheDocument()
    expect(screen.getByText('RiskVerdict')).toBeInTheDocument()
    expect(screen.getByText('BacktestReview')).toBeInTheDocument()
  })

  it('loads P0 workflow evidence from chain, strategy, trade, signal and backtest APIs', async () => {
    renderPage(<P0Workflow />, '/p0')

    expect(await screen.findByText('1 条 方案')).toBeInTheDocument()
    await waitFor(() => {
      expect(chainApi.getCandidates).toHaveBeenCalledWith({ filter: 'all', top_n: 20 })
      expect(strategyApi.getPlans).toHaveBeenCalled()
      expect(tradeApi.getOrders).toHaveBeenCalled()
      expect(tradeApi.getRiskVerdicts).toHaveBeenCalledWith({ page: 1, page_size: 20 })
      expect(tradeApi.getDecisionContexts).toHaveBeenCalledWith({ page: 1, page_size: 20 })
      expect(signalApi.getLive).toHaveBeenCalledWith('intra')
      expect(backtestApi.getFactors).toHaveBeenCalled()
    })
  })

  it('renders risk audit as a concrete RiskVerdict view instead of a generic note', () => {
    renderPage(<RiskControl />, '/risk/audit')

    expect(screen.getByRole('heading', { name: '风控中心 - 事件审计' })).toBeInTheDocument()
    expect(screen.getByText('RiskVerdict 审计')).toBeInTheDocument()
    expect(screen.getByText('DecisionContext')).toBeInTheDocument()
    expect(screen.queryByText(/风控总览、持仓风险、策略回撤/)).not.toBeInTheDocument()
  })

  it('loads risk control evidence from trade service APIs', async () => {
    renderPage(<RiskControl />, '/risk/audit')

    expect((await screen.findAllByText('RV-live-001')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('CTX-live-001').length).toBeGreaterThan(0)
    await waitFor(() => expect(tradeApi.getRiskVerdicts).toHaveBeenCalled())
    expect(tradeApi.getDecisionContexts).toHaveBeenCalled()
    expect(tradeApi.getAuditLogs).toHaveBeenCalled()
    expect(tradeApi.getRiskConfig).toHaveBeenCalled()
  })

  it('loads breaker, positions, strategy and sentiment evidence for the risk dashboard', async () => {
    renderPage(<RiskControl />, '/risk')

    await waitFor(() => expect(tradeApi.getCircuitBreakerStatus).toHaveBeenCalled())
    expect(tradeApi.getPositions).toHaveBeenCalled()
    expect(strategyApi.listInstances).toHaveBeenCalled()
    expect(signalApi.getLive).toHaveBeenCalled()
    expect(await screen.findByText('四层防御状态')).toBeInTheDocument()
    expect(screen.getByText('运行策略 1 个')).toBeInTheDocument()
  })
})
