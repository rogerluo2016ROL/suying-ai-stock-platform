import { renderHook, act, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import type { ReactNode } from 'react'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import { useLiveTrade } from '../hooks/useLiveTrade'

// P2-09: cover the risk-control branches of placeOrder — large-order confirmation
// and circuit-breaker/disable behaviour. The paper/live auth-unification branch
// is already covered in useLiveTrade.test.tsx (P0-01).

const server = setupServer(
  http.get('/api/v1/trade/risk-config', () => HttpResponse.json({})),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => server.close())

function wrapper({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter>{children}</MemoryRouter>
      </AntdApp>
    </ConfigProvider>
  )
}

describe('P2-09: useLiveTrade 风控分支', () => {
  it('live 模式 + 后端返回 large_order_threshold → 超阈值触发 onLargeOrderConfirm', async () => {
    // threshold 5000; order amount = 10.5 * 1000 = 10500 > 5000 → must confirm
    server.use(
      http.get('/api/v1/trade/risk-config', () =>
        HttpResponse.json({ large_order_threshold: 5000 }),
      ),
      http.post('/api/v1/trade/order/pre-check', () =>
        HttpResponse.json({ passed: true, checks: [] }),
      ),
      http.post('/api/v1/trade/order', () =>
        HttpResponse.json({ message: 'ok', order_id: 'x' }),
      ),
    )

    const { result } = renderHook(() => useLiveTrade(), { wrapper })
    act(() => result.current.setMode('live'))

    // wait for risk config to load
    await waitFor(() => {
      expect(result.current.riskConfig?.large_order_threshold).toBe(5000)
    })

    const confirmSpy = vi.fn().mockResolvedValue(false) // user declines
    let outcome: { success: boolean; error?: string } | undefined
    await act(async () => {
      outcome = await result.current.placeOrder(
        { code: '600000', direction: 'buy', price: 10.5, volume: 1000 },
        { onLargeOrderConfirm: confirmSpy },
      )
    })

    expect(confirmSpy).toHaveBeenCalledTimes(1)
    // user declined → order aborted
    expect(outcome?.success).toBe(false)
    expect(outcome?.error).toBe('用户取消大额交易')
  })

  it('live 模式 + 预检未通过 → 调 onPreCheckFailed 且不下单', async () => {
    server.use(
      http.get('/api/v1/trade/risk-config', () => HttpResponse.json({})),
      http.post('/api/v1/trade/order/pre-check', () =>
        HttpResponse.json({
          passed: false,
          checks: [{ rule: 'daily_loss', level: 'reject', message: '熔断中' }],
        }),
      ),
    )

    const { result } = renderHook(() => useLiveTrade(), { wrapper })
    act(() => result.current.setMode('live'))

    const preCheckSpy = vi.fn()
    let outcome: { success: boolean; error?: string } | undefined
    await act(async () => {
      outcome = await result.current.placeOrder(
        { code: '600000', direction: 'buy', price: 10, volume: 100 },
        { onPreCheckFailed: preCheckSpy },
      )
    })

    expect(preCheckSpy).toHaveBeenCalledTimes(1)
    expect(preCheckSpy).toHaveBeenCalledWith(expect.objectContaining({ passed: false }))
    expect(outcome?.success).toBe(false)
    expect(outcome?.error).toBe('风控检查未通过')
  })

  it('paper 模式不触发预检/大额确认（直接下单）', async () => {
    let orderCalled = false
    server.use(
      http.post('/api/v1/trade/order', () => {
        orderCalled = true
        return HttpResponse.json({ message: 'ok' })
      }),
      http.post('/api/v1/trade/order/pre-check', () => {
        throw new Error('pre-check should NOT be called in paper mode')
      }),
    )

    const { result } = renderHook(() => useLiveTrade(), { wrapper })
    expect(result.current.mode).toBe('paper')

    const confirmSpy = vi.fn()
    const preCheckSpy = vi.fn()
    let outcome: { success: boolean } | undefined
    await act(async () => {
      outcome = await result.current.placeOrder(
        { code: '600000', direction: 'buy', price: 10, volume: 100 },
        { onLargeOrderConfirm: confirmSpy, onPreCheckFailed: preCheckSpy },
      )
    })

    expect(orderCalled).toBe(true)
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(preCheckSpy).not.toHaveBeenCalled()
    expect(outcome?.success).toBe(true)
  })
})
