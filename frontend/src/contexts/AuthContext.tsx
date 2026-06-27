import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { injectAuth } from '../api/client'

// ── Types ──

export type Role = 'admin' | 'internal_analyst' | 'external_analyst' | 'user'

export interface User {
  id: number
  name: string
  email: string
  role: Role
  tenantId?: string
  tenantName?: string
  defaultTradeAccountId?: string
  tradeMode?: 'paper' | 'live'
  brokerAdapter?: 'paper' | 'xtquant_qmt' | 'broker_rest'
}

export interface AuthState {
  user: User | null
  accessToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

export interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasRole: (...roles: Role[]) => boolean
}

type RawAuthUserPayload = Record<string, unknown>

function readString(payload: RawAuthUserPayload, camelKey: string, snakeKey?: string): string | undefined {
  const value = payload[camelKey] ?? (snakeKey ? payload[snakeKey] : undefined)
  return typeof value === 'string' ? value : undefined
}

export function normalizeAuthUserPayload(payload: RawAuthUserPayload): User {
  return {
    id: Number(payload.id),
    name: readString(payload, 'name') || '',
    email: readString(payload, 'email') || '',
    role: (readString(payload, 'role') || 'user') as Role,
    tenantId: readString(payload, 'tenantId', 'tenant_id'),
    tenantName: readString(payload, 'tenantName', 'tenant_name'),
    defaultTradeAccountId: readString(payload, 'defaultTradeAccountId', 'default_trade_account_id'),
    tradeMode: readString(payload, 'tradeMode', 'trade_mode') as User['tradeMode'],
    brokerAdapter: readString(payload, 'brokerAdapter', 'broker_adapter') as User['brokerAdapter'],
  }
}

// ── Context ──

const AuthContext = createContext<AuthContextValue | null>(null)

// ── Provider ──

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const isAuthenticated = !!user && !!accessToken

  // P2-04: keep the mount-only refresh idempotent under React.StrictMode.
  // StrictMode runs effect setup -> cleanup -> setup in dev. The first request
  // must remain usable by the second setup instead of being cancelled forever.
  const mountedRef = useRef(false)
  const initRefreshPromiseRef = useRef<Promise<string | null> | null>(null)

  // ── Token refresh function (used by interceptor too) ──
  // P1-06: accept an optional mounted-guard so the mount effect can prevent
  // setState after unmount. The axios interceptor omits the guard (AuthContext
  // is an app-level singleton that never unmounts, so its calls are safe).

  const doRefresh = useCallback(async (
    isCancelled?: () => boolean,
  ): Promise<string | null> => {
    try {
      const refreshRes = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      })
      if (!refreshRes.ok) return null
      const refreshData = await refreshRes.json()
      const token: string = refreshData.access_token
      if (isCancelled?.()) return null
      setAccessToken(token)

      // Fetch full user profile after token refresh
      const meRes = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!meRes.ok) return null
      const meData = await meRes.json()
      if (isCancelled?.()) return null
      setUser(normalizeAuthUserPayload(meData))
      return token
    } catch {
      return null
    }
  }, [])

  // ── Force logout (called by interceptor on unrecoverable 401) ──

  const doForceLogout = useCallback(() => {
    setUser(null)
    setAccessToken(null)
  }, [])

  // ── Wire axios interceptor ──

  useEffect(() => {
    injectAuth(
      () => accessToken,
      doRefresh,
      doForceLogout,
    )
  }, [accessToken, doRefresh, doForceLogout])

  // ── Initialization: try refresh on mount ──

  useEffect(() => {
    mountedRef.current = true
    if (!initRefreshPromiseRef.current) {
      initRefreshPromiseRef.current = doRefresh(() => !mountedRef.current)
    }
    initRefreshPromiseRef.current.finally(() => {
      if (mountedRef.current) setIsLoading(false)
    })
    return () => { mountedRef.current = false }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── login ──

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '登录失败' }))
      throw new Error(err.detail || '登录失败')
    }
    const data = await res.json()
    setAccessToken(data.access_token)
    setUser(normalizeAuthUserPayload(data.user))
  }, [])

  // ── register ──

  const register = useCallback(async (name: string, email: string, password: string) => {
    const res = await fetch('/api/v1/auth/register', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '注册失败' }))
      throw new Error(err.detail || '注册失败')
    }
    const data = await res.json()
    setAccessToken(data.access_token)
    setUser(normalizeAuthUserPayload(data.user))
  }, [])

  // ── logout ──

  const logout = useCallback(async () => {
    try {
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
      })
    } finally {
      setUser(null)
      setAccessToken(null)
    }
  }, [accessToken])

  // ── hasRole ──

  const hasRole = useCallback(
    (...roles: Role[]) => !!(user && roles.includes(user.role)),
    [user],
  )

  const value: AuthContextValue = {
    user,
    accessToken,
    isAuthenticated,
    isLoading,
    login,
    register,
    logout,
    hasRole,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ── Hook ──

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
