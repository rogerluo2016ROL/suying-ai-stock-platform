import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Backtest from '../pages/Backtest'

const mocks = vi.hoisted(() => ({
  getFactors: vi.fn(),
  getOrders: vi.fn(),
  getRiskVerdicts: vi.fn(),
  getDecisionContexts: vi.fn(),
}))

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    backtestApi: {
      ...actual.backtestApi,
      getFactors: mocks.getFactors,
    },
    tradeApi: {
      ...actual.tradeApi,
      getOrders: mocks.getOrders,
      getRiskVerdicts: mocks.getRiskVerdicts,
      getDecisionContexts: mocks.getDecisionContexts,
    },
  }
})

function renderBacktest() {
  return render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter>
          <Backtest />
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('Backtest 交易复盘', () => {
  beforeEach(() => {
    mocks.getFactors.mockReset()
    mocks.getOrders.mockReset()
    mocks.getRiskVerdicts.mockReset()
    mocks.getDecisionContexts.mockReset()

    mocks.getFactors.mockResolvedValue({ data: { factors: [] } })
    mocks.getOrders.mockResolvedValue({
      data: {
        orders: [
          {
            id: 'ORD-1',
            order_id: 'ORD-1',
            code: '300750',
            direction: 'BUY',
            price: 218.5,
            volume: 100,
            status: 'filled',
            time: '10:30:00',
            decision_context_id: 'CTX-1',
            plan_id: 'PLAN-1',
            candidate_id: 'CAND-1',
          },
        ],
      },
    })
    mocks.getRiskVerdicts.mockResolvedValue({
      data: {
        total: 1,
        records: [
          {
            id: 1,
            verdict_id: 'RV-1',
            result: 'pass',
            scope: 'order',
            trade_mode: 'paper',
            symbol: '300750',
            order_id: 'ORD-1',
            decision_context_id: 'CTX-1',
            plan_id: 'PLAN-1',
            candidate_id: 'CAND-1',
            details: { risk_check: { checks: [{ rule: '资金充足', level: 'pass' }] } },
          },
        ],
      },
    })
    mocks.getDecisionContexts.mockResolvedValue({
      data: {
        total: 1,
        records: [
          {
            id: 1,
            decision_context_id: 'CTX-1',
            tenant_id: 'tenant-alpha',
            source_type: 'order',
            symbol: '300750',
            plan_id: 'PLAN-1',
            candidate_id: 'CAND-1',
            intent: 'place_order',
            payload: { reason: '候选池强势突破' },
          },
        ],
      },
    })
  })

  it('聚合 Order、RiskVerdict、DecisionContext 形成复盘链路', async () => {
    const user = userEvent.setup()
    renderBacktest()

    await user.click(await screen.findByRole('tab', { name: /交易复盘/ }))

    await waitFor(() => {
      expect(mocks.getOrders).toHaveBeenCalled()
      expect(mocks.getRiskVerdicts).toHaveBeenCalledWith({ page: 1, page_size: 50 })
      expect(mocks.getDecisionContexts).toHaveBeenCalledWith({ page: 1, page_size: 50 })
    })

    expect(await screen.findByText('ORD-1')).toBeInTheDocument()
    expect(screen.getByText('RV-1')).toBeInTheDocument()
    expect(screen.getByText('CTX-1')).toBeInTheDocument()
    expect(screen.getByText('PLAN-1')).toBeInTheDocument()
    expect(screen.getByText('CAND-1')).toBeInTheDocument()
    expect(screen.getByText(/候选池强势突破/)).toBeInTheDocument()
  })
})
