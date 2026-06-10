import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { injectAuth } from '../api/client'

// ── Types ──

export type Role = 'admin' | 'internal_analyst' | 'external_analyst' | 'user'

export interface User {
  id: number
  name: string
  email: string
  role: Role
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

// ── Context ──

const AuthContext = createContext<AuthContextValue | null>(null)

// ── Provider ──

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const isAuthenticated = !!user && !!accessToken

  // ── Token refresh function (used by interceptor too) ──

  const doRefresh = useCallback(async (): Promise<string | null> => {
    try {
      const refreshRes = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      })
      if (!refreshRes.ok) return null
      const refreshData = await refreshRes.json()
      const token: string = refreshData.access_token
      setAccessToken(token)

      // Fetch full user profile after token refresh
      const meRes = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!meRes.ok) return null
      const meData = await meRes.json()
      setUser({
        id: meData.id,
        name: meData.name,
        email: meData.email,
        role: meData.role,
      })
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
    let cancelled = false
    doRefresh().finally(() => {
      if (!cancelled) setIsLoading(false)
    })
    return () => { cancelled = true }
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
    setUser(data.user)
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
    setUser(data.user)
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
