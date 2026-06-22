import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AuthProvider } from '../../src/contexts/AuthContext'
import { ThemeProvider } from '../../src/contexts/ThemeContext'

// ── MSW server ──

const server = setupServer(
  // No session by default → refresh 401, /me 401
  http.post('/api/v1/auth/refresh', () => {
    return HttpResponse.json({ detail: 'no session' }, { status: 401 })
  }),
  http.get('/api/v1/auth/me', () => {
    return HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())

// ── P0-03: unauthenticated protected-route access keeps redirect target ──
// The App.tsx catch-all was rewritten to route through ProtectedRoute, so hitting
// a protected URL while logged out must land on /login?redirect=<original>.
// This test exercises the App routing surface end-to-end via a full App render.

describe('P0-03: 未登录访问受保护路由保留 redirect 参数', () => {
  it('App: 未登录访问 /backtest → LoginPage 带 redirect=/backtest', async () => {
    // Full App render through MemoryRouter so we can set the initial URL.
    // Lazy-load App inside the test to keep the module graph isolated.
    const { default: App } = await import('../../src/App')

    render(
      <ConfigProvider locale={zhCN}>
        <AntdApp>
          <ThemeProvider baseToken={{}} baseComponents={{}}>
            <MemoryRouter initialEntries={['/backtest']}>
              <AuthProvider>
                <App />
              </AuthProvider>
            </MemoryRouter>
          </ThemeProvider>
        </AntdApp>
      </ConfigProvider>,
    )

    // LoginPage must render (the form placeholder), proving the catch-all went
    // to ProtectedRoute → Navigate(/login?redirect=/backtest) → /login → LoginPage.
    await waitFor(() => {
      expect(screen.getByPlaceholderText('邮箱')).toBeInTheDocument()
    })
  })
})
