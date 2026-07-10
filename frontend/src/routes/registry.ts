import type { PermissionKey } from '../contexts/AuthContext'

export interface RouteDefinition {
  prefix: string
  menuKey: string
  title: string
  permission?: PermissionKey
}

export const routeRegistry: readonly RouteDefinition[] = [
  { prefix: '/dashboard', menuKey: '/', title: '智能看板', permission: 'dashboard' },
  { prefix: '/open-decision', menuKey: '/open-decision', title: '开盘决策', permission: 'open_decision' },
  { prefix: '/screener', menuKey: '/screener', title: '智能选股', permission: 'screener' },
  { prefix: '/supply-chain-bom', menuKey: '/supply-chain-bom', title: '产业链拆解', permission: 'supply_chain_bom' },
  { prefix: '/predictions', menuKey: '/predictions', title: 'K线预测', permission: 'predictions' },
  { prefix: '/signals', menuKey: '/signals', title: '交易信号', permission: 'signals' },
  { prefix: '/trade/risk-verdicts', menuKey: '/trade', title: '风控闸门', permission: 'trade' },
  { prefix: '/trade/decision-contexts', menuKey: '/trade', title: '决策上下文', permission: 'trade' },
  { prefix: '/trade/audit-log', menuKey: '/trade', title: '交易审计', permission: 'trade' },
  { prefix: '/trade', menuKey: '/trade', title: '交易执行', permission: 'trade' },
  { prefix: '/auto-trade', menuKey: '/auto-trade', title: '自动交易', permission: 'auto_trade' },
  { prefix: '/strategy', menuKey: '/strategy', title: '策略管理', permission: 'strategy' },
  { prefix: '/risk', menuKey: '/risk', title: '风控中心', permission: 'risk' },
  { prefix: '/backtest', menuKey: '/backtest', title: '回测分析', permission: 'backtest' },
  { prefix: '/diagnosis', menuKey: '/diagnosis', title: '诊断中心', permission: 'diagnosis' },
  { prefix: '/training', menuKey: '/training', title: '模型训练', permission: 'training' },
  { prefix: '/model-registry', menuKey: '/model-registry', title: '模型注册', permission: 'model_registry' },
  { prefix: '/data-update', menuKey: '/data-update', title: '数据更新', permission: 'data_update' },
  { prefix: '/runtime', menuKey: '/runtime-status', title: '运行状态', permission: 'runtime_status' },
  { prefix: '/workflow/p0', menuKey: '/workflow', title: 'P0 主链路', permission: 'p0_workflow' },
  { prefix: '/platform/upgrade', menuKey: '/platform', title: '平台升级', permission: 'platform_upgrade' },
  { prefix: '/admin/permissions', menuKey: '/admin/permissions', title: '权限授权', permission: 'admin_permissions' },
  { prefix: '/admin/memberships', menuKey: '/admin/memberships', title: '会员管理', permission: 'admin_memberships' },
]

export function resolveRoute(pathname: string): RouteDefinition | undefined {
  if (pathname === '/') return routeRegistry[0]
  return routeRegistry.find(route => pathname.startsWith(route.prefix))
}
