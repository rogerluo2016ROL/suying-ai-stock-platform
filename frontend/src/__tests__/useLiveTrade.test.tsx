import { renderHook, act, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import type { ReactNode } from 'react'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import { useLiveTrade } from '../hooks/useLiveTrade'

// ── MSW server (hand-written, same pattern as tests/sit/auth-flow.test.tsx;
//    this repo has no orval/MSW generation pipeline — see CLAUDE.md ADR-006) ──

const server = setupServer(
  // risk config — return empty so the large-order branch stays inert
  http.get('/api/v1/trade/risk-config', () => {
    return HttpResponse.json({})
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => server.close())

// ── Wrapper: antd message needs App.message context; router for any navigate ──

function wrapper({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter>{children}</MemoryRouter>
      </AntdApp>
    </ConfigProvider>
  )
}

// ── P0-01: paper mode order must go through the axios-wrapped client ──

describe('P0-01: placeOrder 鉴权口径统一', () => {
  it('paper 模式下单走 /api/v1/trade/order（不再是裸 fetch）', async () => {
    let orderRequested = false
    let orderBody: unknown = null
    server.use(
      http.post('/api/v1/trade/order', async ({ request }) => {
        orderRequested = true
        orderBody = await request.json()
        return HttpResponse.json({ message: '下单成功', order_id: 'p-1' })
      }),
    )

    const { result } = renderHook(() => useLiveTrade(), { wrapper })
    // default mode is paper
    expect(result.current.mode).toBe('paper')

    let outcome: { success: boolean; data?: unknown; error?: string } | undefined
    await act(async () => {
      outcome = await result.current.placeOrder(
        { code: '600000', direction: 'buy', price: 10.5, volume: 100 },
        {},
      )
    })

    expect(orderRequested).toBe(true)
    expect(orderBody).toEqual({ code: '600000', direction: 'buy', price: 10.5, volume: 100 })
    expect(outcome).toEqual(expect.objectContaining({ success: true }))
  })

  it('paper 模式下单失败 → 返回 success:false + 后端 detail', async () => {
    server.use(
      http.post('/api/v1/trade/order', () => {
        return HttpResponse.json({ detail: '余额不足' }, { status: 400 })
      }),
    )

    const { result } = renderHook(() => useLiveTrade(), { wrapper })

    let outcome: { success: boolean; error?: string } | undefined
    await act(async () => {
      outcome = await result.current.placeOrder(
        { code: '600000', direction: 'buy', price: 10.5, volume: 100 },
        {},
      )
    })

    expect(outcome?.success).toBe(false)
    expect(outcome?.error).toBe('余额不足')
  })
})

// ── P0-04: circuit breaker poll must not silently clear state on transient errors ──

describe('P0-04: 熔断器轮询错误分级', () => {
  it('404（无熔断器配置）→ 置 null', async () => {
    server.use(
      http.get('/api/v1/trade/circuit-breaker/status', () => {
        return HttpResponse.json({ detail: 'no breaker configured' }, { status: 404 })
      }),
    )

    const { result } = renderHook(() => useLiveTrade(), { wrapper })
    // force live mode so the breaker poll effect runs
    act(() => {
      result.current.setMode('live')
    })

    await waitFor(() => {
      expect(result.current.circuitBreaker).toBeNull()
    })
  })

  it('网络错误（500）→ 保留上一次有效状态，不清空', async () => {
    // Install fake timers BEFORE mounting so the hook's setInterval is captured.
    vi.useFakeTimers({ shouldAdvanceTime: true })

    // First poll returns a TRIGGERED breaker, second+ poll 500s — state must stay.
    let callCount = 0
    const triggered = {
      account_id: 'a1',
      status: 'TRIGGERED',
      triggered_at: '2026-06-22T00:00:00Z',
      daily_pnl: -5000,
      initial_capital: 100000,
      daily_loss_pct: -5,
      threshold_pct: 5,
      cooldown_minutes: 30,
      can_trade: false,
      date: '2026-06-22',
    }
    server.use(
      http.get('/api/v1/trade/circuit-breaker/status', () => {
        callCount += 1
        if (callCount === 1) {
          return HttpResponse.json({ breakers: [triggered] })
        }
        return HttpResponse.json({ detail: 'server error' }, { status: 500 })
      }),
    )

    const { result } = renderHook(() => useLiveTrade(), { wrapper })
    act(() => {
      result.current.setMode('live')
    })

    // first poll (fired synchronously on mount of the effect) resolves with TRIGGERED
    await waitFor(() => {
      expect(result.current.circuitBreaker?.status).toBe('TRIGGERED')
    })

    // advance past the 30s poll interval so the second (500) request fires
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31000)
    })

    // let the rejected request's .catch handler settle
    await waitFor(() => {
      expect(callCount).toBeGreaterThanOrEqual(2)
    })

    vi.useRealTimers()

    // breaker state must be retained, NOT cleared to null
    expect(result.current.circuitBreaker).not.toBeNull()
    expect(result.current.circuitBreaker?.status).toBe('TRIGGERED')
  })
})
