import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AuthProvider } from '../../src/contexts/AuthContext'
import LoginPage from '../../src/components/auth/LoginPage'
import RegisterPage from '../../src/components/auth/RegisterPage'
import ProtectedRoute from '../../src/components/auth/ProtectedRoute'

// ── MSW server ──

const server = setupServer(
  // Refresh endpoint (fails by default = no existing session)
  http.post('/api/v1/auth/refresh', () => {
    return HttpResponse.json({ detail: 'Token 已过期或无效' }, { status: 401 })
  }),
  // /me endpoint (won't be called unless refresh succeeds)
  http.get('/api/v1/auth/me', () => {
    return HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })
  }),
  // Login
  http.post('/api/v1/auth/login', async ({ request }) => {
    const body = await request.json() as { email: string; password: string }
    if (body.email === 'admin@test.com' && body.password === 'Abc12345') {
      return HttpResponse.json({
        access_token: 'login-token',
        token_type: 'bearer',
        expires_in: 900,
        user: { id: 1, name: 'Admin', email: 'admin@test.com', role: 'admin' },
      })
    }
    return HttpResponse.json({ detail: '邮箱或密码错误' }, { status: 401 })
  }),
  // Register
  http.post('/api/v1/auth/register', async ({ request }) => {
    const body = await request.json() as { email: string }
    if (body.email === 'existing@test.com') {
      return HttpResponse.json({ detail: '邮箱已被注册' }, { status: 409 })
    }
    return HttpResponse.json({
      access_token: 'reg-token',
      token_type: 'bearer',
      expires_in: 900,
      user: { id: 2, name: 'NewUser', email: body.email, role: 'user' },
    }, { status: 201 })
  }),
  // Logout
  http.post('/api/v1/auth/logout', () => {
    return HttpResponse.json({ message: '已登出' })
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// ── Helper: mock a successful session restore (refresh + /me) ──

function mockSessionRestore(userData: Record<string, unknown> = {}) {
  server.use(
    http.post('/api/v1/auth/refresh', () => {
      return HttpResponse.json({
        access_token: 'restored-token', token_type: 'bearer', expires_in: 900,
      })
    }),
    http.get('/api/v1/auth/me', () => {
      return HttpResponse.json({
        id: 1, name: 'TestUser', email: 'test@test.com', role: 'user',
        is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
        ...userData,
      })
    }),
  )
}

// ── Helpers ──

async function fillLoginForm(email: string, password: string) {
  await waitFor(() => {
    expect(screen.getByPlaceholderText('邮箱')).toBeInTheDocument()
  })
  fireEvent.change(screen.getByPlaceholderText('邮箱'), { target: { value: email } })
  fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: password } })
  await waitFor(() => {
    const btn = screen.getByRole('button', { name: /登录/ })
    expect(btn).not.toBeDisabled()
  })
  fireEvent.click(screen.getByRole('button', { name: /登录/ }))
}

async function fillRegisterForm(name: string, email: string, password: string, confirm: string) {
  await waitFor(() => {
    expect(screen.getByPlaceholderText('用户名')).toBeInTheDocument()
  })
  fireEvent.change(screen.getByPlaceholderText('用户名'), { target: { value: name } })
  fireEvent.change(screen.getByPlaceholderText('邮箱'), { target: { value: email } })
  fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: password } })
  fireEvent.change(screen.getByPlaceholderText('确认密码'), { target: { value: confirm } })
  await waitFor(() => {
    const btn = screen.getByRole('button', { name: /注册/ })
    expect(btn).not.toBeDisabled()
  })
  fireEvent.click(screen.getByRole('button', { name: /注册/ }))
}

// ── SIT: Auth Flow ──

describe('SIT: Auth Flow', () => {

  // ── AC-23: Login success → auto-redirect ──

  it('AC-23: 登录成功 → 跳转首页', async () => {
    render(
      <MemoryRouter initialEntries={['/login?redirect=/dashboard']}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    await fillLoginForm('admin@test.com', 'Abc12345')

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /登录/ })).not.toBeInTheDocument()
    })
  })

  // ── AC-24: Login failure → error message ──

  it('AC-24: 登录失败 → 显示错误消息', async () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    await fillLoginForm('wrong@test.com', 'wrongpass')

    await waitFor(() => {
      expect(screen.getByText('邮箱或密码错误')).toBeInTheDocument()
    })
  })

  // ── AC-26: Register success → auto-login → redirect ──

  it('AC-26: 注册成功 → 自动登录', async () => {
    render(
      <MemoryRouter initialEntries={['/register']}>
        <AuthProvider>
          <RegisterPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    await fillRegisterForm('NewUser', 'new@test.com', 'Abc12345', 'Abc12345')

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /注册/ })).not.toBeInTheDocument()
    })
  })

  // ── Register failure ──

  it('注册失败：邮箱已被注册', async () => {
    render(
      <MemoryRouter initialEntries={['/register']}>
        <AuthProvider>
          <RegisterPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    await fillRegisterForm('Existing', 'existing@test.com', 'Abc12345', 'Abc12345')

    await waitFor(() => {
      expect(screen.getByText('邮箱已被注册')).toBeInTheDocument()
    })
  })

  // ── AC-21: ProtectedRoute 403 ──

  it('AC-21: 普通用户访问管理员页面 → 403', async () => {
    mockSessionRestore({ id: 2, name: 'User', email: 'u@t.com', role: 'user' })

    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <AuthProvider>
          <ProtectedRoute roles={['admin']}>
            <div>Admin Panel</div>
          </ProtectedRoute>
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('403')).toBeInTheDocument()
      expect(screen.getByText('您没有权限访问此页面')).toBeInTheDocument()
    })
  })

  // ── AC-20: Unauthenticated → redirect to login ──

  it('AC-20: 未登录访问 /dashboard → 重定向', async () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthProvider>
          <ProtectedRoute>
            <div>Dashboard</div>
          </ProtectedRoute>
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
    })
  })

  // ── AC-27: Already logged in → auto-redirect from /login ──

  it('AC-27: 已登录访问 /login → 自动跳转', async () => {
    mockSessionRestore({ id: 1, name: 'Admin', email: 'a@t.com', role: 'admin' })

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /登录/ })).not.toBeInTheDocument()
    })
  })

  // ── AC-28: AuthProvider restore session on mount ──

  it('AC-28: refresh 成功 → 静默恢复登录态', async () => {
    mockSessionRestore({ id: 1, name: 'Restored', email: 'r@t.com', role: 'user' })

    render(
      <MemoryRouter>
        <AuthProvider>
          <ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst', 'user']}>
            <div>Restored Content</div>
          </ProtectedRoute>
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Restored Content')).toBeInTheDocument()
    })
  })
})
