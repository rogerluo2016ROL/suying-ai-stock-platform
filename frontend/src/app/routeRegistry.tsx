import type { ComponentType } from 'react'
import type { PermissionKey, Role } from '../contexts/AuthContext'

export interface AppRouteDefinition {
  key: string
  path: string
  label: string
  group: '行情决策' | '交易执行' | '模型 / 系统' | '平台管理'
  roles: Role[]
  permission: PermissionKey
  navVisible: boolean
  load: () => Promise<{ default: ComponentType }>
}

export const routeRegistry: AppRouteDefinition[] = [
  { key: 'dashboard', path: '/', label: '智能看板', group: '行情决策', roles: ['admin','internal_analyst','external_analyst','user'], permission: 'dashboard', navVisible: true, load: () => import('../pages/Dashboard') },
  { key: 'screener', path: '/screener', label: '智能选股', group: '行情决策', roles: ['admin','internal_analyst','external_analyst','user'], permission: 'screener', navVisible: true, load: () => import('../pages/Screener') },
  { key: 'trade', path: '/trade', label: '交易中心', group: '交易执行', roles: ['admin','internal_analyst','user'], permission: 'trade', navVisible: true, load: () => import('../pages/Trade') },
  { key: 'runtime', path: '/runtime-status', label: '运行状态', group: '模型 / 系统', roles: ['admin'], permission: 'runtime_status', navVisible: true, load: () => import('../pages/RuntimeStatus') },
]

export function buildMenuItems(role: Role | null, permissions: PermissionKey[] = []) {
  return routeRegistry.filter(route => route.navVisible && !!role && route.roles.includes(role) && (permissions.length === 0 || permissions.includes(route.permission))).map(route => ({ key: route.path, label: route.label }))
}

export function buildProtectedRoutes() {
  return routeRegistry.map(route => ({ path: route.path, roles: route.roles, load: route.load }))
}
