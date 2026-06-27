import { renderHook, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider, useAuth } from '../contexts/AuthContext'
import React, { type ReactNode } from 'react'

// ── Mock fetch ──

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as any

function resetFetch() {
  mockFetch.mockReset()
}

// ── Wrapper ──

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <AuthProvider>{children}</AuthProvider>
    </MemoryRouter>
  )
}

function strictWrapper({ children }: { children: ReactNode }) {
  return (
    <React.StrictMode>
      <MemoryRouter>
        <AuthProvider>{children}</AuthProvider>
      </MemoryRouter>
    </React.StrictMode>
  )
}

// ── Helper: mock a successful refresh response ──

// btoa-safe base64url encode
function toBase64Url(str: string): string {
  return btoa(unescape(encodeURIComponent(str)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function mockRefreshSuccess() {
  // Step 1: refresh endpoint returns new access_token
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ access_token: 'refreshed-token', token_type: 'bearer', expires_in: 900 }),
  })
  // Step 2: /me endpoint returns user info
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      id: 1, name: 'test', email: 'test@t.com', role: 'user',
      is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    }),
  })
}

function mockRefreshFailure() {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    json: async () => ({ detail: 'Token 已过期或无效' }),
  })
}

describe('AuthContext', () => {
  beforeEach(() => {
    resetFetch()
  })

  // ── AC-28: 初始化时检查 refreshToken ──

  it('初始状态 isLoading=true', () => {
    mockRefreshSuccess()
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.isLoading).toBe(true)
    expect(result.current.isAuthenticated).toBe(false)
  })

  it('refresh 成功 → 恢复登录态 (AC-28)', async () => {
    mockRefreshSuccess()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user).toMatchObject({
      id: 1,
      name: 'test',
      email: 'test@t.com',
      role: 'user',
    })
    expect(result.current.accessToken).toBeTruthy()
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/auth/refresh', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }))
  })

  it('refresh 成功时兼容后端 snake_case 平台字段', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: 'refreshed-token', token_type: 'bearer', expires_in: 900 }),
    })
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: 8,
        name: '平台用户',
        email: 'platform@t.com',
        role: 'internal_analyst',
        tenant_id: 'tenant-alpha',
        tenant_name: 'Alpha 机构',
        default_trade_account_id: 'qmt-880001',
        trade_mode: 'live',
        broker_adapter: 'xtquant_qmt',
      }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.user).toMatchObject({
      tenantId: 'tenant-alpha',
      tenantName: 'Alpha 机构',
      defaultTradeAccountId: 'qmt-880001',
      tradeMode: 'live',
      brokerAdapter: 'xtquant_qmt',
    })
  })

  it('StrictMode 下 refresh 成功仍恢复登录态', async () => {
    mockRefreshSuccess()
    const { result } = renderHook(() => useAuth(), { wrapper: strictWrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user).toMatchObject({
      id: 1,
      name: 'test',
      email: 'test@t.com',
      role: 'user',
    })
  })

  it('refresh 失败 → 保持未登录 (AC-28)', async () => {
    mockRefreshFailure()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
  })

  // ── AC-23: 登录成功 ──

  it('login 成功 → 设置 user + accessToken (AC-23)', async () => {
    mockRefreshFailure() // initial refresh fails
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // mock login success
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: 'login-token',
        token_type: 'bearer',
        expires_in: 900,
        user: { id: 2, name: '张三', email: 'zhang@t.com', role: 'admin' },
      }),
    })

    await act(async () => {
      await result.current.login('zhang@t.com', 'Abc12345')
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user).toMatchObject({
      id: 2, name: '张三', email: 'zhang@t.com', role: 'admin',
    })
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }))
  })

  // ── AC-24: 登录失败 ──

  it('login 失败 → 抛出错误 (AC-24)', async () => {
    mockRefreshFailure()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: '邮箱或密码错误' }),
    })

    let error: Error | null = null
    try {
      await act(async () => {
        await result.current.login('wrong@t.com', 'wrong')
      })
    } catch (err: any) {
      error = err
    }

    expect(error).not.toBeNull()
    expect(error!.message).toBe('邮箱或密码错误')
    expect(result.current.isAuthenticated).toBe(false)
  })

  // ── AC-26: 注册成功 → 自动登录 ──

  it('register 成功 → 自动登录 (AC-26)', async () => {
    mockRefreshFailure()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: 'reg-token',
        token_type: 'bearer',
        expires_in: 900,
        user: { id: 3, name: '新用户', email: 'new@t.com', role: 'user' },
      }),
    })

    await act(async () => {
      await result.current.register('新用户', 'new@t.com', 'Abc12345')
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user).toMatchObject({ name: '新用户', role: 'user' })
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/auth/register', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }))
  })

  // ── hasRole ──

  it('hasRole 正确判断角色', async () => {
    mockRefreshFailure()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => { expect(result.current.isLoading).toBe(false) })

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: 'tok', token_type: 'bearer', expires_in: 900,
        user: { id: '1', name: 'A', email: 'a@t.com', role: 'user' },
      }),
    })
    await act(async () => { await result.current.login('a@t.com', 'Abc12345') })

    expect(result.current.hasRole('user')).toBe(true)
    expect(result.current.hasRole('admin')).toBe(false)
    expect(result.current.hasRole('admin', 'user')).toBe(true)
  })

  // ── logout ──

  it('logout 清除状态', async () => {
    mockRefreshFailure()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => { expect(result.current.isLoading).toBe(false) })

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: 'tok', token_type: 'bearer', expires_in: 900,
        user: { id: '1', name: 'A', email: 'a@t.com', role: 'user' },
      }),
    })
    await act(async () => { await result.current.login('a@t.com', 'Abc12345') })
    expect(result.current.isAuthenticated).toBe(true)

    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ message: '已登出' }) })
    await act(async () => { await result.current.logout() })
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
  })

  // ── 账号已被禁用 ──

  it('login 账号已被禁用返回 403', async () => {
    mockRefreshFailure()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => { expect(result.current.isLoading).toBe(false) })

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: async () => ({ detail: '账号已被禁用' }),
    })

    let error: Error | null = null
    try {
      await act(async () => { await result.current.login('a@t.com', 'Abc12345') })
    } catch (err: any) { error = err }

    expect(error).not.toBeNull()
    expect(error!.message).toBe('账号已被禁用')
  })
})
