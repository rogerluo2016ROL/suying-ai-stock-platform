import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AutoTrade from '../pages/AutoTrade'
import RiskVerdicts from '../pages/RiskVerdicts'
import DecisionContexts from '../pages/DecisionContexts'
import Backtest from '../pages/Backtest'

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  listInstances: vi.fn(),
  getInstance: vi.fn(),
  getInstanceLog: vi.fn(),
  startInstance: vi.fn(),
  pauseInstance: vi.fn(),
  resumeInstance: vi.fn(),
  stopInstance: vi.fn(),
  getRiskVerdicts: vi.fn(),
  getDecisionContexts: vi.fn(),
  getOrders: vi.fn(),
  getFactors: vi.fn(),
}))

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

vi.mock('../api/client', () => ({
  default: {
    get: mocks.apiGet,
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  strategyApi: {
    listInstances: mocks.listInstances,
    getInstance: mocks.getInstance,
    getInstanceLog: mocks.getInstanceLog,
    startInstance: mocks.startInstance,
    pauseInstance: mocks.pauseInstance,
    resumeInstance: mocks.resumeInstance,
    stopInstance: mocks.stopInstance,
  },
  tradeApi: {
    getRiskVerdicts: mocks.getRiskVerdicts,
    getDecisionContexts: mocks.getDecisionContexts,
    getOrders: mocks.getOrders,
  },
  backtestApi: {
    getFactors: mocks.getFactors,
  },
}))

const chain = {
  orderId: 'ORD-B6',
  verdictId: 'RV-B6',
  decisionContextId: 'CTX-auto-strat-b6-300750-1',
  planId: 'PLAN-B6',
  candidateId: 'CAND-B6-300750',
  code: '300750',
}

function setupMocks() {
  mocks.apiGet.mockReset()
  mocks.listInstances.mockReset()
  mocks.getInstance.mockReset()
  mocks.getInstanceLog.mockReset()
  mocks.startInstance.mockReset()
  mocks.getRiskVerdicts.mockReset()
  mocks.getDecisionContexts.mockReset()
  mocks.getOrders.mockReset()
  mocks.getFactors.mockReset()

  const stratData = {
    id: 'strat-b6',
    name: 'B6 自动执行策略',
    status: 'active',
    source_type: 'scheme',
    trade_mode: 'paper',
    check_interval_sec: 60,
    capital: 1_000_000,
    picks_count: 1,
    buy_conditions: [],
    sell_conditions: [],
    position_rules: { max_positions: 5, single_max_pct: 0.2, total_position_cap_pct: 0.8 },
    risk_rules: { daily_max_loss_pct: 0.03, stop_loss_pct: 0.03, take_profit_pct: 0.15, trailing_stop_pct: 0 },
  }

  mocks.listInstances.mockResolvedValue({
    data: { strategies: [{ ...stratData, created_at: '2026-06-27T10:00:00Z' }] },
  })
  mocks.getInstance.mockResolvedValue({ data: { ...stratData, picks: [] } })
  mocks.getInstanceLog.mockResolvedValue({
    data: {
      logs: [{
        timestamp: '2026-06-27T10:31:00Z',
        level: 'BUY',
        message: `买单已提交: ${chain.code} - order_id=${chain.orderId}`,
        details: {
          code: chain.code,
          order_id: chain.orderId,
          decision_context_id: chain.decisionContextId,
          plan_id: chain.planId,
          candidate_id: chain.candidateId,
        },
      }],
    },
  })

  mocks.getRiskVerdicts.mockResolvedValue({
    data: {
      total: 1,
      page: 1,
      page_size: 20,
      records: [{
        id: 1,
        verdict_id: chain.verdictId,
        tenant_id: 'tenant-alpha',
        account_id: 'paper-u7',
        result: 'pass',
        scope: 'order',
        trade_mode: 'paper',
        symbol: chain.code,
        order_id: chain.orderId,
        decision_context_id: chain.decisionContextId,
        plan_id: chain.planId,
        candidate_id: chain.candidateId,
        details: {
          risk_check: {
            checks: [{ rule: '资金充足', level: 'pass', message: '通过' }],
          },
        },
      }],
    },
  })
  mocks.getDecisionContexts.mockResolvedValue({
    data: {
      total: 1,
      page: 1,
      page_size: 20,
      records: [{
        id: 1,
        decision_context_id: chain.decisionContextId,
        tenant_id: 'tenant-alpha',
        account_id: 'paper-u7',
        source_type: 'order',
        symbol: chain.code,
        plan_id: chain.planId,
        candidate_id: chain.candidateId,
        intent: 'place_order',
        payload: { reason: 'B6 自动执行链路验证' },
      }],
    },
  })
  mocks.getOrders.mockResolvedValue({
    data: {
      orders: [{
        id: chain.orderId,
        order_id: chain.orderId,
        code: chain.code,
        direction: 'BUY',
        price: 218.5,
        volume: 100,
        status: 'filled',
        decision_context_id: chain.decisionContextId,
        plan_id: chain.planId,
        candidate_id: chain.candidateId,
      }],
    },
  })
  mocks.getFactors.mockResolvedValue({ data: { factors: [] } })
}

function renderChain(initialEntries = ['/auto-trade']) {
  return render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/auto-trade" element={<AutoTrade />} />
            <Route path="/auto-trade/monitor" element={<AutoTrade />} />
            <Route path="/trade/risk-verdicts" element={<RiskVerdicts />} />
            <Route path="/trade/decision-contexts" element={<DecisionContexts />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/backtest/run" element={<Backtest />} />
            <Route path="/backtest/compare" element={<Backtest />} />
            <Route path="/backtest/trades" element={<Backtest />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('B6 全链路模拟盘联调守门', () => {
  beforeEach(setupMocks)

  it('AutoTrade 日志可以下钻到风控闸门再进入决策上下文', async () => {
    const user = userEvent.setup()
    renderChain(['/auto-trade/monitor'])

    await user.click(await screen.findByRole('button', { name: '详情' }))
    await user.click(await screen.findByRole('button', { name: '风控' }))

    await waitFor(() => {
      expect(mocks.getRiskVerdicts).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        decision_context_id: chain.decisionContextId,
        order_id: chain.orderId,
        plan_id: chain.planId,
        candidate_id: chain.candidateId,
        code: chain.code,
      })
    })
    expect(await screen.findByText(chain.verdictId)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '决策上下文' }))

    expect(await screen.findByText(/B6 自动执行链路验证/)).toBeInTheDocument()
  })

  it('回测复盘页签展示同一条 Order/RiskVerdict/DecisionContext 链路', async () => {
    const user = userEvent.setup()
    renderChain(['/backtest'])

    await user.click(await screen.findByRole('tab', { name: /交易复盘/ }))

    expect(await screen.findByText(chain.orderId)).toBeInTheDocument()
    expect(screen.getByText(chain.verdictId)).toBeInTheDocument()
    expect(screen.getByText(chain.decisionContextId)).toBeInTheDocument()
    expect(screen.getByText(/B6 自动执行链路验证/)).toBeInTheDocument()
  })
})
