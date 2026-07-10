import { lazy, type LazyExoticComponent, type ComponentType } from 'react'
import type { PermissionKey, Role } from '../contexts/AuthContext'

export type MenuGroup = '行情决策' | '交易执行' | '模型 / 系统' | '平台管理'

export interface AppRouteDefinition {
  key: string
  path: string
  aliases?: string[]
  label: string
  group: MenuGroup
  roles: Role[]
  permission: PermissionKey
  navVisible: boolean
  iconKey: string
  badge?: string
  load: () => Promise<{ default: ComponentType }>
}

const allUsers: Role[] = ['admin', 'internal_analyst', 'external_analyst', 'user']
const traders: Role[] = ['admin', 'internal_analyst', 'user']
const analysts: Role[] = ['admin', 'internal_analyst', 'external_analyst']
const admin: Role[] = ['admin']

export const routeRegistry: AppRouteDefinition[] = [
  { key: 'dashboard', path: '/', aliases: ['/dashboard/auction','/dashboard/signals','/dashboard/watchlist'], label: '智能看板', group: '行情决策', roles: allUsers, permission: 'dashboard', navVisible: true, iconKey: 'dashboard', load: () => import('../pages/Dashboard') },
  { key: 'open-decision', path: '/open-decision', aliases: ['/open-decision/auction','/open-decision/signals','/open-decision/candidates','/open-decision/execution'], label: '开盘决策', group: '行情决策', roles: allUsers, permission: 'open_decision', navVisible: true, iconKey: 'line', load: () => import('../pages/OpenDecision') },
  { key: 'screener', path: '/screener', aliases: ['/screener/models','/screener/factors'], label: '智能选股', group: '行情决策', roles: allUsers, permission: 'screener', navVisible: true, iconKey: 'search', badge: '12', load: () => import('../pages/Screener') },
  { key: 'supply-chain', path: '/supply-chain-bom', aliases: ['/supply-chain-bom/policy','/supply-chain-bom/company','/supply-chain-bom/ranking'], label: '产业链拆解', group: '行情决策', roles: allUsers, permission: 'supply_chain_bom', navVisible: true, iconKey: 'apartment', load: () => import('../pages/SupplyChainBom') },
  { key: 'predictions', path: '/predictions', aliases: ['/predictions/single','/predictions/compare','/predictions/backtest'], label: 'K线预测', group: '行情决策', roles: allUsers, permission: 'predictions', navVisible: true, iconKey: 'line', load: () => import('../pages/Predictions') },
  { key: 'signals', path: '/signals', aliases: ['/signals/overview','/signals/history','/signals/risk'], label: '交易信号', group: '行情决策', roles: allUsers, permission: 'signals', navVisible: true, iconKey: 'thunder', badge: '3', load: () => import('../pages/Signals') },
  { key: 'trade', path: '/trade', aliases: ['/trade/order','/trade/positions','/trade/orders','/trade/account','/trade/brokers'], label: '交易中心', group: '交易执行', roles: traders, permission: 'trade', navVisible: true, iconKey: 'dollar', load: () => import('../pages/Trade') },
  { key: 'trade-audit', path: '/trade/audit-log', label: '交易审计', group: '交易执行', roles: traders, permission: 'trade', navVisible: false, iconKey: 'dollar', load: () => import('../pages/AuditLog') },
  { key: 'risk-verdicts', path: '/trade/risk-verdicts', label: '风控闸门', group: '交易执行', roles: traders, permission: 'trade', navVisible: false, iconKey: 'bell', load: () => import('../pages/RiskVerdicts') },
  { key: 'decision-contexts', path: '/trade/decision-contexts', label: '决策上下文', group: '交易执行', roles: traders, permission: 'trade', navVisible: false, iconKey: 'bulb', load: () => import('../pages/DecisionContexts') },
  { key: 'auto-trade', path: '/auto-trade', aliases: ['/auto-trade/config','/auto-trade/monitor','/auto-trade/logs'], label: '量化交易', group: '交易执行', roles: traders, permission: 'auto_trade', navVisible: true, iconKey: 'robot', load: () => import('../pages/AutoTrade') },
  { key: 'strategy', path: '/strategy', aliases: ['/strategy/detail','/strategy/compare','/strategy/reports'], label: '方案管理', group: '交易执行', roles: allUsers, permission: 'strategy', navVisible: true, iconKey: 'bulb', load: () => import('../pages/Strategy') },
  { key: 'risk', path: '/risk', aliases: ['/risk/overview','/risk/positions','/risk/strategies','/risk/market','/risk/audit'], label: '风控中心', group: '交易执行', roles: traders, permission: 'risk', navVisible: true, iconKey: 'bell', load: () => import('../pages/RiskControl') },
  { key: 'backtest', path: '/backtest', aliases: ['/backtest/run','/backtest/compare','/backtest/trades'], label: '回测分析', group: '交易执行', roles: analysts, permission: 'backtest', navVisible: true, iconKey: 'experiment', load: () => import('../pages/Backtest') },
  { key: 'diagnosis', path: '/diagnosis', aliases: ['/diagnosis/overview','/diagnosis/model','/diagnosis/compare','/diagnosis/risk'], label: '个股诊断', group: '交易执行', roles: allUsers, permission: 'diagnosis', navVisible: true, iconKey: 'fund', load: () => import('../pages/Diagnosis') },
  { key: 'training', path: '/training', aliases: ['/training/tasks','/training/mlflow'], label: '模型训练', group: '模型 / 系统', roles: admin, permission: 'training', navVisible: true, iconKey: 'experiment', load: () => import('../pages/Training') },
  { key: 'model-registry', path: '/model-registry', label: '模型注册', group: '模型 / 系统', roles: admin, permission: 'model_registry', navVisible: true, iconKey: 'api', load: () => import('../pages/ModelRegistry') },
  { key: 'data-update', path: '/data-update', aliases: ['/data-update/overview','/data-update/tables','/data-update/schedule'], label: '数据更新', group: '模型 / 系统', roles: allUsers, permission: 'data_update', navVisible: true, iconKey: 'clock', load: () => import('../pages/DataUpdate') },
  { key: 'runtime', path: '/runtime-status', aliases: ['/runtime'], label: '运行状态', group: '模型 / 系统', roles: admin, permission: 'runtime_status', navVisible: true, iconKey: 'api', load: () => import('../pages/RuntimeStatus') },
  { key: 'p0-workflow', path: '/workflow/p0', label: 'P0 主链路', group: '模型 / 系统', roles: allUsers, permission: 'p0_workflow', navVisible: false, iconKey: 'api', load: () => import('../pages/P0Workflow') },
  { key: 'platform-upgrade', path: '/platform/upgrade', label: '平台升级', group: '平台管理', roles: admin, permission: 'platform_upgrade', navVisible: false, iconKey: 'api', load: () => import('../pages/PlatformUpgrade') },
  { key: 'admin-permissions', path: '/admin/permissions', label: '权限授权', group: '平台管理', roles: admin, permission: 'admin_permissions', navVisible: true, iconKey: 'safety', load: () => import('../pages/AdminPermissions') },
  { key: 'admin-memberships', path: '/admin/memberships', label: '会员管理', group: '平台管理', roles: admin, permission: 'admin_memberships', navVisible: true, iconKey: 'crown', load: () => import('../pages/MembershipManagement') },
]

export function findRoute(pathname: string) {
  return routeRegistry.find(route => route.path === pathname || route.aliases?.includes(pathname))
}

export function buildMenuItems(role: Role | null, permissions: PermissionKey[] = []) {
  const permissionSet = new Set(permissions)
  return routeRegistry.filter(route => route.navVisible && !!role && route.roles.includes(role)
    && (permissionSet.size === 0 || permissionSet.has(route.permission)))
    .map(route => ({ key: route.path, label: route.label, group: route.group, roles: route.roles,
      permission: route.permission, iconKey: route.iconKey, badge: route.badge }))
}

export function buildProtectedRoutes(): Array<{ path: string; roles: Role[]; permission: PermissionKey; Component: LazyExoticComponent<ComponentType> }> {
  return routeRegistry.flatMap(route => {
    const Component = lazy(route.load)
    return [route.path, ...(route.aliases || [])].map(path => ({ path, roles: route.roles, permission: route.permission, Component }))
  })
}
