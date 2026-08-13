import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { type AuthContextValue } from '../contexts/AuthContext'
import ProtectedRoute from '../components/auth/ProtectedRoute'

// ── Mock useAuth ──

const mockUseAuth = vi.fn<() => Partial<AuthContextValue>>()

vi.mock('../contexts/AuthContext', async () => {
  const actual = await vi.importActual('../contexts/AuthContext')
  return {
    ...actual,
    useAuth: () => {
      const state = mockUseAuth()
      return {
        user: null,
        accessToken: null,
        isAuthenticated: false,
        isLoading: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        hasRole: (...roles: string[]) => !!(state.user && roles.includes(state.user.role)),
        ...state,
      } as AuthContextValue
    },
  }
})

function renderWithRouter(initialRoute: string) {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/login" element={<div>Login Page</div>} />
        <Route path="/dashboard" element={
          <ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst', 'user']}>
            <div>Dashboard Content</div>
          </ProtectedRoute>
        } />
        <Route path="/admin/users" element={
          <ProtectedRoute roles={['admin']}>
            <div>Admin Content</div>
          </ProtectedRoute>
        } />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    mockUseAuth.mockReset()
  })

  // ── Loading state ──

  it('isLoading 时显示 Spin', () => {
    mockUseAuth.mockReturnValue({ isLoading: true })
    renderWithRouter('/dashboard')
    expect(document.querySelector('.ant-spin')).toBeTruthy()
  })

  // ── AC-20: 未登录 → 重定向到 /login?redirect=... ──

  it('未登录用户访问 /dashboard → 重定向到 /login (AC-20)', () => {
    mockUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: false,
      user: null,
      accessToken: null,
    })
    renderWithRouter('/dashboard')
    expect(screen.getByText('Login Page')).toBeInTheDocument()
  })

  // ── AC-21: 角色不足 → 403 ──

  it('普通用户访问 /admin/users → 显示 403 (AC-21)', async () => {
    mockUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      accessToken: 'test-token',
      user: { id: 1, name: '普通用户', email: 'user@t.com', role: 'user' },
    })
    renderWithRouter('/admin/users')
    await waitFor(() => {
      expect(screen.getByText('403')).toBeInTheDocument()
      expect(screen.getByText('您没有权限访问此页面')).toBeInTheDocument()
    })
  })

  // ── 角色足够 → 渲染内容 ──

  it('管理员访问 /admin/users → 渲染 Admin Content', async () => {
    mockUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      accessToken: 'test-token',
      user: { id: 1, name: '管理员', email: 'admin@t.com', role: 'admin' },
    })
    renderWithRouter('/admin/users')
    await waitFor(() => {
      expect(screen.getByText('Admin Content')).toBeInTheDocument()
    })
  })

  it('普通用户访问 /dashboard → 渲染 Dashboard', async () => {
    mockUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      accessToken: 'test-token',
      user: { id: 1, name: '普通用户', email: 'user@t.com', role: 'user' },
    })
    renderWithRouter('/dashboard')
    await waitFor(() => {
      expect(screen.getByText('Dashboard Content')).toBeInTheDocument()
    })
  })

  // ── 内部分析师可以访问交易中心 ──

  it('内部分析师访问 dashboard → 渲染内容', async () => {
    mockUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      accessToken: 'test-token',
      user: { id: 1, name: '分析师', email: 'analyst@t.com', role: 'internal_analyst' },
    })
    renderWithRouter('/dashboard')
    await waitFor(() => {
      expect(screen.getByText('Dashboard Content')).toBeInTheDocument()
    })
  })

  // ── 403 页面有返回首页按钮 ──

  it('403 页面包含返回首页按钮', async () => {
    mockUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      accessToken: 'test-token',
      user: { id: 1, name: '普通用户', email: 'user@t.com', role: 'user' },
    })
    renderWithRouter('/admin/users')
    await waitFor(() => {
      expect(screen.getByText('返回首页')).toBeInTheDocument()
    })
  })
})
