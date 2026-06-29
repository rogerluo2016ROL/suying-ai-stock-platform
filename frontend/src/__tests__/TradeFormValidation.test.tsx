import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Trade from '../pages/Trade'

const mocks = vi.hoisted(() => ({
  placeOrder: vi.fn(),
  authUser: {
    id: 8,
    name: '平台用户',
    email: 'platform@t.com',
    role: 'internal_analyst',
    tenantId: 'tenant-alpha',
    defaultTradeAccountId: 'qmt-880001',
    tradeMode: 'paper',
    brokerAdapter: 'paper',
    brokerConnectConfig: {
      broker_name: 'mock_qmt',
      account_id: 'qmt-880001',
      server_ip: '127.0.0.1',
      server_port: 16001,
      environment: 'sandbox',
    },
  },
}))

// Mock useLiveTrade so Trade renders in isolation (paper mode, no live broker).
vi.mock('../hooks/useLiveTrade', () => ({
  useLiveTrade: () => ({
    mode: 'paper',
    setMode: vi.fn(),
    brokerStatus: 'disconnected',
    riskConfig: null,
    circuitBreaker: null,
    apiPrefix: '/api/v1/trade',
    connectBroker: vi.fn(),
    placeOrder: mocks.placeOrder,
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mocks.authUser,
    accessToken: 'test-token',
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    hasRole: vi.fn(),
  }),
}))

// Mock tradeApi (fetched on mount) to avoid unhandled MSW requests.
vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    tradeApi: {
      getAccount: vi.fn().mockResolvedValue({ data: {} }),
      getPositions: vi.fn().mockResolvedValue({ data: { positions: [] } }),
      getOrders: vi.fn().mockResolvedValue({ data: { orders: [] } }),
    },
  }
})

function renderTrade(initialEntries = ['/trade']) {
  return render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/trade" element={<Trade />} />
            <Route path="/trade/risk-verdicts" element={<div>风控闸门页</div>} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('P1-07: Trade 下单表单校验', () => {
  beforeEach(() => {
    mocks.placeOrder.mockReset()
    mocks.placeOrder.mockResolvedValue({ success: true, data: {} })
  })

  it('券商账户配置使用登录用户默认账户预填', async () => {
    renderTrade()

    await waitFor(() => {
      expect(screen.getByDisplayValue('qmt-880001')).toBeInTheDocument()
    })
  })

  it('股票代码非 6 位数字 → 提交时显示校验错误', async () => {
    const user = userEvent.setup()
    renderTrade()

    // Wait for the form to mount.
    await waitFor(() => {
      expect(screen.getByPlaceholderText('000001')).toBeInTheDocument()
    })

    // Type an invalid code (letters).
    await user.type(screen.getByPlaceholderText('000001'), 'abc12')
    // Fill volume with a valid 100-multiple so only code validation fails.
    const volumeInput = screen.getByRole('spinbutton', { name: /数量/ })
    await user.type(volumeInput, '100')
    await user.clear(volumeInput)
    await user.type(volumeInput, '100')

    await user.click(screen.getByRole('button', { name: /^下单$/ }))

    await waitFor(() => {
      expect(screen.getByText('股票代码为 6 位数字')).toBeInTheDocument()
    })
  })

  it('数量非 100 整数倍 → 提示须为 100 的整数倍', async () => {
    const user = userEvent.setup()
    renderTrade()

    await waitFor(() => {
      expect(screen.getByPlaceholderText('000001')).toBeInTheDocument()
    })

    // Valid 6-digit code.
    await user.type(screen.getByPlaceholderText('000001'), '000001')
    // Invalid volume (150 is not a multiple of 100).
    const volumeInput = screen.getByRole('spinbutton', { name: /数量/ })
    await user.type(volumeInput, '150')

    await user.click(screen.getByRole('button', { name: /^下单$/ }))

    await waitFor(() => {
      expect(screen.getByText(/100 的整数倍/)).toBeInTheDocument()
    })
  })

  it('提交订单时携带决策链路字段', async () => {
    const user = userEvent.setup()
    renderTrade()

    await waitFor(() => {
      expect(screen.getByPlaceholderText('000001')).toBeInTheDocument()
    })

    await user.type(screen.getByPlaceholderText('000001'), '300750')
    await user.type(screen.getByRole('spinbutton', { name: /数量/ }), '100')
    await user.type(screen.getByPlaceholderText('CTX-'), 'CTX-B3-3')
    await user.type(screen.getByPlaceholderText('CAND-'), 'CAND-leader_auction-300750')
    await user.type(screen.getByPlaceholderText('PLAN-'), 'PLAN-B3')

    await user.click(screen.getByRole('button', { name: /^下单$/ }))

    await waitFor(() => {
      expect(mocks.placeOrder).toHaveBeenCalledWith(
        expect.objectContaining({
          code: '300750',
          direction: 'BUY',
          volume: 100,
          decision_context_id: 'CTX-B3-3',
          candidate_id: 'CAND-leader_auction-300750',
          plan_id: 'PLAN-B3',
        }),
        expect.any(Object),
      )
    })
  })

  it('下单成功后展示风控判定结果', async () => {
    const user = userEvent.setup()
    mocks.placeOrder.mockResolvedValue({
      success: true,
      data: {
        order_id: 'ORD-B3',
        code: '300750',
        direction: 'BUY',
        price: 10,
        volume: 100,
        status: 'filled',
        risk_verdict: {
          verdict_id: 'RV-B3',
          result: 'pass',
          scope: 'order',
          account_id: 'paper-u105',
          decision_context_id: 'CTX-B3-3',
          candidate_id: 'CAND-leader_auction-300750',
          plan_id: 'PLAN-B3',
          risk_check: {
            passed: true,
            checks: [
              { rule: '资金充足', level: 'pass', message: '' },
              { rule: '仓位上限', level: 'pass', message: '' },
            ],
          },
        },
      },
    })
    renderTrade()

    await waitFor(() => {
      expect(screen.getByPlaceholderText('000001')).toBeInTheDocument()
    })

    await user.type(screen.getByPlaceholderText('000001'), '300750')
    await user.type(screen.getByRole('spinbutton', { name: /数量/ }), '100')
    await user.type(screen.getByPlaceholderText('CTX-'), 'CTX-B3-3')
    await user.type(screen.getByPlaceholderText('CAND-'), 'CAND-leader_auction-300750')
    await user.type(screen.getByPlaceholderText('PLAN-'), 'PLAN-B3')
    await user.click(screen.getByRole('button', { name: /^下单$/ }))

    expect(await screen.findByText('风控判定')).toBeInTheDocument()
    expect(screen.getAllByText('RV-B3').length).toBeGreaterThan(0)
    expect(screen.getByText('pass')).toBeInTheDocument()
    expect(screen.getByText('2 条规则')).toBeInTheDocument()
    expect(screen.getAllByText('CAND-leader_auction-300750').length).toBeGreaterThan(1)
    expect(await screen.findByText('来源')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getAllByText('PLAN-B3').length).toBeGreaterThan(1)
    })

    await user.click(screen.getByRole('button', { name: '查看风控' }))
    expect(screen.getByText('风控闸门页')).toBeInTheDocument()
  })

  it('从方案详情跳转的 query 会预填下单表单', async () => {
    renderTrade([
      '/trade?code=300750&price=218.5&plan_id=PLAN-B3&candidate_id=CAND-leader_auction-300750&decision_context_id=CTX-B3-3',
    ])

    await waitFor(() => {
      expect(screen.getByPlaceholderText('000001')).toHaveValue('300750')
    })
    expect(screen.getByRole('spinbutton', { name: /价格/ })).toHaveValue('218.50')
    expect(screen.getByDisplayValue('PLAN-B3')).toBeInTheDocument()
    expect(screen.getByDisplayValue('CAND-leader_auction-300750')).toBeInTheDocument()
    expect(screen.getByDisplayValue('CTX-B3-3')).toBeInTheDocument()
  })

  it('交易中心提供风控闸门入口', async () => {
    renderTrade()

    expect(await screen.findByRole('button', { name: /风控闸门/ })).toBeInTheDocument()
  })
})
