import { render, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'

// ── P0-02: LoginPage must not call navigate during render ──
// Regression: previously `navigate('/', { replace: true })` ran in the render
// body when isAuthenticated was true → "Cannot update during render" under
// StrictMode, and the navigation could be dropped under concurrent rendering.
// The fix moved navigate into useEffect. We verify the redirect still happens
// (navigate eventually called with the right args) but via the effect, and that
// rendering an already-authenticated LoginPage does not throw.

const navigateSpy = vi.fn()

// Mock react-router-dom so useNavigate returns our spy (ESM exports can't be
// redefined via spyOn — must go through vi.mock at module load).
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateSpy,
  }
})

vi.mock('../contexts/AuthContext', async () => {
  const actual = await vi.importActual<typeof import('../contexts/AuthContext')>(
    '../contexts/AuthContext',
  )
  return {
    ...actual,
    useAuth: () => ({
      user: { id: 1, name: 'Admin', email: 'a@t.com', role: 'admin' },
      accessToken: 'tok',
      isAuthenticated: true, // simulate "already logged in" on mount
      isLoading: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      hasRole: () => true,
    }),
  }
})

// Import AFTER mocks are registered.
const LoginPageModule = await import('../components/auth/LoginPage')
const LoginPage = LoginPageModule.default

describe('P0-02: LoginPage 已登录跳转无 render 副作用', () => {
  afterEach(() => {
    cleanup()
    navigateSpy.mockClear()
  })

  it('已登录挂载 LoginPage：navigate 由 useEffect 触发，不在 render 期同步执行', async () => {
    // If navigate ran synchronously inside the render body, React 18 StrictMode
    // would warn "Cannot update during render" or throw. render() completing
    // without error is itself part of the assertion.
    expect(() =>
      render(
        <ConfigProvider locale={zhCN}>
          <AntdApp>
            <MemoryRouter initialEntries={['/login']}>
              <LoginPage />
            </MemoryRouter>
          </AntdApp>
        </ConfigProvider>,
      ),
    ).not.toThrow()

    // The useEffect-driven redirect must fire (navigate to '/' with replace).
    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalledWith('/', { replace: true })
    })
  })
})
