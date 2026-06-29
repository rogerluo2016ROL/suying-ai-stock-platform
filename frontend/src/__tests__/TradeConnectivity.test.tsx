import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Trade from '../pages/Trade'
import { tradeApi } from '../api/client'

vi.mock('../hooks/useLiveTrade', () => ({
  useLiveTrade: () => ({
    mode: 'paper',
    setMode: vi.fn(),
    brokerStatus: 'connected',
    riskConfig: { max_single_amount: 100000, large_order_threshold: 50000 },
    circuitBreaker: null,
    apiPrefix: '/api/v1/trade',
    connectBroker: vi.fn(),
    placeOrder: vi.fn(),
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { defaultTradeAccountId: 'paper-live-001' },
  }),
}))

vi.mock('../api/client', () => ({
  tradeApi: {
    getAccount: vi.fn(),
    getPositions: vi.fn(),
    getOrders: vi.fn(),
  },
}))

function renderTrade(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/trade/*" element={<Trade />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Trade page connectivity', () => {
  beforeEach(() => {
    vi.mocked(tradeApi.getAccount).mockResolvedValue({
      data: {
        account_id: 'paper-live-001',
        account_name: '真实模拟账户',
        total_capital: 1000000,
        available: 650000,
        market_value: 350000,
      },
    } as any)
    vi.mocked(tradeApi.getPositions).mockResolvedValue({
      data: {
        positions: [
          { code: '000001', name: '平安银行', volume: 1000, cost: 10.5, pnl_pct: 1.8 },
        ],
      },
    } as any)
    vi.mocked(tradeApi.getOrders).mockResolvedValue({
      data: {
        orders: [
          { order_id: 'ORD-live-001', code: '000001', direction: 'BUY', volume: 1000, status: 'pending' },
        ],
      },
    } as any)
  })

  it('renders positions from trade service instead of hard-coded samples', async () => {
    renderTrade('/trade/positions')

    expect(await screen.findByText('平安银行')).toBeInTheDocument()
    expect(screen.queryByText('宁德时代')).not.toBeInTheDocument()
    expect(screen.queryByText('中芯国际')).not.toBeInTheDocument()
  })

  it('renders orders from trade service instead of hard-coded order rows', async () => {
    renderTrade('/trade/orders')

    expect(await screen.findByText('ORD-live-001')).toBeInTheDocument()
    expect(screen.queryByText('ORD-001')).not.toBeInTheDocument()
    expect(screen.queryByText('ORD-002')).not.toBeInTheDocument()
  })

  it('renders account state from trade account API', async () => {
    renderTrade('/trade/account')

    expect(await screen.findByText('真实模拟账户')).toBeInTheDocument()
    expect(screen.getByText(/总资产 1000000/)).toBeInTheDocument()
  })

  it('renders broker state from live trade hook', async () => {
    renderTrade('/trade/brokers')
    await screen.findAllByText('券商管理')
    expect(screen.getAllByText('connected').length).toBeGreaterThan(0)
    expect(screen.getByText('100000')).toBeInTheDocument()
  })
})
