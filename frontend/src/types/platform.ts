import type { Role, User } from '../contexts/AuthContext'

export type RoleView = 'trader' | 'investor' | 'admin'
export type Visibility = 'private' | 'tenant_shared' | 'public'
export type DataScope = 'public' | 'tenant' | 'user' | 'account'
export type TradeMode = 'paper' | 'live'
export type BrokerAdapter = 'paper' | 'mock_qmt' | 'xtquant_qmt' | 'broker_rest'

export interface PlatformScope {
  tenantId: string
  ownerUserId?: string
  accountId?: string
  visibility: Visibility
  dataScope: DataScope
}

export interface PlatformSession extends PlatformScope {
  roleView: RoleView
  tenantName: string
  userName: string
  tradeMode: TradeMode
  brokerAdapter: BrokerAdapter
  cloudReady: boolean
}

export function roleToRoleView(role: Role): RoleView {
  if (role === 'admin') return 'admin'
  if (role === 'user') return 'investor'
  return 'trader'
}

export function buildPlatformSessionFromUser(user: User | null): PlatformSession {
  const role = user?.role ?? 'user'
  const roleView = roleToRoleView(role)
  const fallbackTenantId = roleView === 'admin' ? 'platform' : 'tenant-default'

  return {
    tenantId: user?.tenantId || fallbackTenantId,
    tenantName: user?.tenantName || (roleView === 'admin' ? '平台运营' : '默认租户'),
    ownerUserId: user ? String(user.id) : undefined,
    accountId: user?.defaultTradeAccountId || (roleView === 'admin' ? undefined : 'paper-default'),
    visibility: roleView === 'admin' ? 'tenant_shared' : 'private',
    dataScope: roleView === 'admin' ? 'tenant' : 'account',
    roleView,
    userName: user?.name || '未登录用户',
    tradeMode: user?.tradeMode || 'paper',
    brokerAdapter: user?.brokerAdapter || 'paper',
    cloudReady: true,
  }
}
