import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Trade from '../pages/Trade'

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
    placeOrder: vi.fn().mockResolvedValue({ success: true, data: {} }),
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

function renderTrade() {
  return render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter>
          <Trade />
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('P1-07: Trade 下单表单校验', () => {
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

    await user.click(screen.getByRole('button', { name: /下单/ }))

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

    await user.click(screen.getByRole('button', { name: /下单/ }))

    await waitFor(() => {
      expect(screen.getByText(/100 的整数倍/)).toBeInTheDocument()
    })
  })
})
