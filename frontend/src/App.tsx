import { useState, useEffect, useMemo, lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Badge, Avatar, Dropdown, Drawer, Switch, Typography, Radio, Spin } from 'antd'
import {
  SearchOutlined, LineChartOutlined, ThunderboltOutlined,
  BellOutlined, DollarOutlined, ExperimentOutlined,
  FundOutlined, DashboardOutlined, BulbOutlined,
  SettingOutlined, UserOutlined, ReloadOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined,
  StockOutlined, RobotOutlined,
  LogoutOutlined,
  ApiOutlined, ClockCircleOutlined, ApartmentOutlined,
  CrownOutlined, DownOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons'
import { useAuth, type PermissionKey, type Role } from './contexts/AuthContext'
import { useTheme } from './contexts/ThemeContext'
import ProtectedRoute from './components/auth/ProtectedRoute'
import ErrorBoundary from './components/ErrorBoundary'
import { alertApi, clearPlatformContext, injectPlatformContext, marketApi } from './api/client'
import { liveTradeApi } from './api/liveTrade'
import LoginPage from './components/auth/LoginPage'
import RegisterPage from './components/auth/RegisterPage'
import { buildPlatformSessionFromUser } from './types/platform'

// P1-03: code-split the 14 page bundles so the initial download only carries
// the layout + auth pages; ECharts-heavy pages (Diagnosis/Backtest/Training/
// ModelRegistry/Predictions) load on demand.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const OpenDecision = lazy(() => import('./pages/OpenDecision'))
const Screener = lazy(() => import('./pages/Screener'))
const SupplyChainBom = lazy(() => import('./pages/SupplyChainBom'))
const Predictions = lazy(() => import('./pages/Predictions'))
const Signals = lazy(() => import('./pages/Signals'))
const Trade = lazy(() => import('./pages/Trade'))
const AuditLog = lazy(() => import('./pages/AuditLog'))
const RiskVerdicts = lazy(() => import('./pages/RiskVerdicts'))
const DecisionContexts = lazy(() => import('./pages/DecisionContexts'))
const Diagnosis = lazy(() => import('./pages/Diagnosis'))
const Backtest = lazy(() => import('./pages/Backtest'))
const Strategy = lazy(() => import('./pages/Strategy'))
const AutoTrade = lazy(() => import('./pages/AutoTrade'))
const RiskControl = lazy(() => import('./pages/RiskControl'))
const Training = lazy(() => import('./pages/Training'))
const ModelRegistry = lazy(() => import('./pages/ModelRegistry'))
const DataUpdate = lazy(() => import('./pages/DataUpdate'))
const RuntimeStatus = lazy(() => import('./pages/RuntimeStatus'))
const P0Workflow = lazy(() => import('./pages/P0Workflow'))
const PlatformUpgrade = lazy(() => import('./pages/PlatformUpgrade'))
const AdminPermissions = lazy(() => import('./pages/AdminPermissions'))
const MembershipManagement = lazy(() => import('./pages/MembershipManagement'))

const { Text } = Typography

// Suspense fallback for lazy page loads
const pageFallback = (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
    <Spin size="large" />
  </div>
)

// ── Menu items with role restrictions ──

interface MenuItemWithRoles {
  key: string
  icon: React.ReactNode
  label: string
  roles: Role[]
  group: '行情决策' | '交易执行' | '模型 / 系统' | '平台管理'
  permission: PermissionKey
  target?: string
  badge?: string
}

const allMenuItems: MenuItemWithRoles[] = [
  { key: '/',            icon: <DashboardOutlined />,    label: '智能看板',   group: '行情决策', permission: 'dashboard', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/open-decision', icon: <LineChartOutlined />,  label: '开盘决策',   group: '行情决策', permission: 'open_decision', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/screener',    icon: <SearchOutlined />,       label: '智能选股',   group: '行情决策', permission: 'screener', badge: '12', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/supply-chain-bom', icon: <ApartmentOutlined />, label: '产业链拆解', group: '行情决策', permission: 'supply_chain_bom', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/predictions', icon: <LineChartOutlined />,    label: 'K线预测',    group: '行情决策', permission: 'predictions', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/signals',     icon: <ThunderboltOutlined />,  label: '交易信号',   group: '行情决策', permission: 'signals', badge: '3', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/trade',       icon: <DollarOutlined />,       label: '交易中心',   group: '交易执行', permission: 'trade', roles: ['admin', 'internal_analyst', 'user'] },
  { key: '/auto-trade',  icon: <RobotOutlined />,        label: '量化交易',   group: '交易执行', permission: 'auto_trade', roles: ['admin', 'internal_analyst', 'user'] },
  { key: '/strategy',    icon: <BulbOutlined />,         label: '方案管理',   group: '交易执行', permission: 'strategy', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/risk',        icon: <BellOutlined />,         label: '风控中心',   group: '交易执行', permission: 'risk', roles: ['admin', 'internal_analyst', 'user'] },
  { key: '/backtest',    icon: <ExperimentOutlined />,   label: '回测分析',   group: '交易执行', permission: 'backtest', roles: ['admin', 'internal_analyst', 'external_analyst'] },
  { key: '/diagnosis',   icon: <FundOutlined />,         label: '个股诊断',   group: '交易执行', permission: 'diagnosis', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/training',        icon: <ExperimentOutlined />, label: '模型训练', group: '模型 / 系统', permission: 'training', roles: ['admin'] },
  { key: '/model-registry',  icon: <ApiOutlined />,        label: '模型注册', group: '模型 / 系统', permission: 'model_registry', roles: ['admin'] },
  { key: '/data-update',     icon: <ClockCircleOutlined />, label: '数据更新', group: '模型 / 系统', permission: 'data_update', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/runtime-status',  icon: <ApiOutlined />,         label: '运行状态', group: '模型 / 系统', permission: 'runtime_status', roles: ['admin'] },
  { key: '/admin/permissions', icon: <SafetyCertificateOutlined />, label: '权限授权', group: '平台管理', permission: 'admin_permissions', roles: ['admin'] },
  { key: '/admin/memberships', icon: <CrownOutlined />, label: '会员管理', group: '平台管理', permission: 'admin_memberships', roles: ['admin'] },
]

const marketTapeItems = [
  { label: '上证', value: '--', change: '待同步', tone: 'muted' },
  { label: '深成', value: '--', change: '待同步', tone: 'muted' },
  { label: '创业板', value: '--', change: '待同步', tone: 'muted' },
  { label: '北证50', value: '--', change: '待同步', tone: 'muted' },
]

type MarketTapeItem = typeof marketTapeItems[number]

const marketTapeLabels: Record<string, string> = {
  '000001': '上证',
  '399001': '深成',
  '399006': '创业板',
  '899050': '北证50',
}

function formatMarketNumber(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(2) : '--'
}

function formatMarketChange(value: unknown) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '待同步'
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}%`
}

function toneForChange(value: unknown): MarketTapeItem['tone'] {
  const number = Number(value)
  if (!Number.isFinite(number)) return 'muted'
  if (number > 0) return 'up'
  if (number < 0) return 'down'
  return 'muted'
}

// ── Protected route config ──

const protectedRoutes: { path: string; element: React.ReactNode; roles: Role[] }[] = [
  { path: '/',            element: <Dashboard />,    roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/dashboard/auction', element: <Dashboard />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/dashboard/signals', element: <Dashboard />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/dashboard/watchlist', element: <Dashboard />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/open-decision', element: <OpenDecision />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/open-decision/auction', element: <OpenDecision />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/open-decision/signals', element: <OpenDecision />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/open-decision/candidates', element: <OpenDecision />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/open-decision/execution', element: <OpenDecision />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/screener',    element: <Screener />,      roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/screener/models', element: <Screener />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/screener/factors', element: <Screener />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/supply-chain-bom', element: <SupplyChainBom />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/supply-chain-bom/policy', element: <SupplyChainBom />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/supply-chain-bom/company', element: <SupplyChainBom />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/predictions', element: <Predictions />,   roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/predictions/single', element: <Predictions />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/predictions/compare', element: <Predictions />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/predictions/backtest', element: <Predictions />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/strategy',    element: <Strategy />,      roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/strategy/detail', element: <Strategy />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/strategy/compare', element: <Strategy />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/strategy/reports', element: <Strategy />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/signals',     element: <Signals />,       roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/signals/overview', element: <Signals />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/signals/history', element: <Signals />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/signals/risk', element: <Signals />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/trade',       element: <Trade />,         roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/order', element: <Trade />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/positions', element: <Trade />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/orders', element: <Trade />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/account', element: <Trade />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/brokers', element: <Trade />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/audit-log', element: <AuditLog />,  roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/risk-verdicts', element: <RiskVerdicts />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/decision-contexts', element: <DecisionContexts />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/auto-trade',  element: <AutoTrade />,     roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/auto-trade/config', element: <AutoTrade />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/auto-trade/monitor', element: <AutoTrade />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/auto-trade/logs', element: <AutoTrade />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/risk', element: <RiskControl />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/risk/overview', element: <RiskControl />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/risk/positions', element: <RiskControl />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/risk/strategies', element: <RiskControl />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/risk/market', element: <RiskControl />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/risk/audit', element: <RiskControl />, roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/backtest',       element: <Backtest />,       roles: ['admin', 'internal_analyst', 'external_analyst'] },
  { path: '/backtest/run', element: <Backtest />, roles: ['admin', 'internal_analyst', 'external_analyst'] },
  { path: '/backtest/compare', element: <Backtest />, roles: ['admin', 'internal_analyst', 'external_analyst'] },
  { path: '/backtest/trades', element: <Backtest />, roles: ['admin', 'internal_analyst', 'external_analyst'] },
  { path: '/diagnosis',      element: <Diagnosis />,      roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/diagnosis/overview', element: <Diagnosis />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/diagnosis/model', element: <Diagnosis />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/diagnosis/compare', element: <Diagnosis />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/diagnosis/risk', element: <Diagnosis />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/training',       element: <Training />,       roles: ['admin'] },
  { path: '/training/tasks', element: <Training />, roles: ['admin'] },
  { path: '/training/mlflow', element: <Training />, roles: ['admin'] },
  { path: '/model-registry', element: <ModelRegistry />,  roles: ['admin'] },
  { path: '/data-update',    element: <DataUpdate />,     roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/data-update/overview', element: <DataUpdate />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/data-update/tables', element: <DataUpdate />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/data-update/schedule', element: <DataUpdate />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/runtime', element: <RuntimeStatus />, roles: ['admin'] },
  { path: '/runtime-status', element: <RuntimeStatus />, roles: ['admin'] },
  { path: '/workflow/p0', element: <P0Workflow />, roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/platform/upgrade', element: <PlatformUpgrade />, roles: ['admin'] },
  { path: '/admin/permissions', element: <AdminPermissions />, roles: ['admin'] },
  { path: '/admin/memberships', element: <MembershipManagement />, roles: ['admin'] },
]

const menuGroups: MenuItemWithRoles['group'][] = ['行情决策', '交易执行', '模型 / 系统', '平台管理']

function filterMenu(
  items: MenuItemWithRoles[],
  role: Role | null,
  permissions: PermissionKey[] | undefined,
): MenuItemWithRoles[] {
  const permissionSet = new Set(permissions || [])
  const hasBackendPermissions = permissionSet.size > 0
  return items
    .filter(item => {
      if (!role) return false
      if (hasBackendPermissions) return permissionSet.has(item.permission)
      return item.roles.includes(role)
    })
}

function routeTitle(pathname: string): string {
  if (pathname.startsWith('/dashboard')) return '智能看板'
  if (pathname.startsWith('/open-decision')) return '开盘决策'
  if (pathname.startsWith('/trade/risk-verdicts')) return '风控闸门'
  if (pathname.startsWith('/trade/decision-contexts')) return '决策上下文'
  if (pathname.startsWith('/trade/audit-log')) return '交易审计'
  if (pathname.startsWith('/risk')) return '风控中心'
  if (pathname.startsWith('/runtime')) return '运行状态'
  if (pathname.startsWith('/workflow/p0')) return 'P0 主链路'
  if (pathname.startsWith('/platform/upgrade')) return '平台升级'
  if (pathname.startsWith('/admin/permissions')) return '权限授权'
  if (pathname.startsWith('/admin/memberships')) return '会员管理'
  const selectedKey = '/' + pathname.split('/')[1]
  return allMenuItems.find(item => item.key === selectedKey)?.label || '智能看板'
}

function selectedMenuKey(pathname: string): string {
  if (pathname === '/' || pathname.startsWith('/dashboard')) return '/'
  if (pathname.startsWith('/runtime')) return '/runtime-status'
  if (pathname.startsWith('/admin/permissions')) return '/admin/permissions'
  if (pathname.startsWith('/admin/memberships')) return '/admin/memberships'
  return '/' + pathname.split('/')[1]
}

function routePermission(pathname: string): PermissionKey | undefined {
  if (pathname === '/' || pathname.startsWith('/dashboard')) return 'dashboard'
  if (pathname.startsWith('/open-decision')) return 'open_decision'
  if (pathname.startsWith('/screener')) return 'screener'
  if (pathname.startsWith('/supply-chain-bom')) return 'supply_chain_bom'
  if (pathname.startsWith('/predictions')) return 'predictions'
  if (pathname.startsWith('/signals')) return 'signals'
  if (pathname.startsWith('/trade')) return 'trade'
  if (pathname.startsWith('/auto-trade')) return 'auto_trade'
  if (pathname.startsWith('/strategy')) return 'strategy'
  if (pathname.startsWith('/risk')) return 'risk'
  if (pathname.startsWith('/backtest')) return 'backtest'
  if (pathname.startsWith('/diagnosis')) return 'diagnosis'
  if (pathname.startsWith('/training')) return 'training'
  if (pathname.startsWith('/model-registry')) return 'model_registry'
  if (pathname.startsWith('/data-update')) return 'data_update'
  if (pathname.startsWith('/runtime')) return 'runtime_status'
  if (pathname.startsWith('/workflow/p0')) return 'p0_workflow'
  if (pathname.startsWith('/platform/upgrade')) return 'platform_upgrade'
  if (pathname.startsWith('/admin/permissions')) return 'admin_permissions'
  if (pathname.startsWith('/admin/memberships')) return 'admin_memberships'
  return undefined
}

function roleViewLabel(roleView: ReturnType<typeof buildPlatformSessionFromUser>['roleView']): string {
  if (roleView === 'admin') return '管理员视图'
  if (roleView === 'trader') return '操盘手视图'
  return '投资者视图'
}

function tradeModeLabel(mode: ReturnType<typeof buildPlatformSessionFromUser>['tradeMode']): string {
  return mode === 'live' ? '实盘' : '模拟盘'
}

type HeaderBrokerConnection = {
  status: 'paper' | 'connected' | 'disconnected' | 'connecting' | 'error'
  accountId: string
  brokerName: string
}

function brokerConnectionText(connection: HeaderBrokerConnection): string {
  const statusText = {
    paper: '模拟引擎',
    connected: '券商已连接',
    disconnected: '券商未连接',
    connecting: '券商连接中',
    error: '券商异常',
  }[connection.status]
  return connection.accountId ? `${statusText} · ${connection.accountId}` : statusText
}

function membershipText(user: ReturnType<typeof useAuth>['user']): string {
  const membership = user?.membership
  if (!membership || !membership.isMember) return '非会员'
  const plan = membership.plan ? `${membership.plan} · ` : ''
  const days = typeof membership.daysRemaining === 'number'
    ? `剩余 ${membership.daysRemaining} 天`
    : '长期有效'
  return `${plan}${days}`
}

function membershipTone(user: ReturnType<typeof useAuth>['user']): 'safe' | 'warn' | 'danger' {
  const membership = user?.membership
  if (!membership || !membership.isMember) return 'danger'
  if (typeof membership.daysRemaining === 'number' && membership.daysRemaining <= 7) return 'warn'
  return 'safe'
}

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [unreadAlerts, setUnreadAlerts] = useState(0)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, isAuthenticated, isLoading, logout } = useAuth()
  const { mode: themeMode, setMode: setThemeMode } = useTheme()
  const [compactMode, setCompactMode] = useState(false)
  const [multiTab, setMultiTab] = useState(false)
  const [marketTape, setMarketTape] = useState<MarketTapeItem[]>(marketTapeItems)
  const [brokerConnection, setBrokerConnection] = useState<HeaderBrokerConnection>({
    status: 'paper',
    accountId: '',
    brokerName: 'paper',
  })

  const selectedKey = selectedMenuKey(location.pathname)

  // Filter menu items by role
  const mainMenu = useMemo(
    () => filterMenu(allMenuItems, user?.role ?? null, user?.permissions),
    [user?.permissions, user?.role],
  )
  const platformSession = useMemo(
    () => buildPlatformSessionFromUser(user),
    [user],
  )
  const platformContextMenuItems = useMemo(() => [
    { key: 'role', disabled: true, label: `角色：${roleViewLabel(platformSession.roleView)}` },
    { key: 'tenant', disabled: true, label: `租户：${platformSession.tenantName}` },
    { key: 'account', disabled: true, label: `账户：${platformSession.accountId || '未绑定账户'}` },
    { key: 'mode', disabled: true, label: `盘别：${tradeModeLabel(platformSession.tradeMode)}` },
    { key: 'broker', disabled: true, label: `券商：${brokerConnectionText(brokerConnection)}` },
    { key: 'membership', disabled: true, label: `会员：${membershipText(user)}` },
  ], [
    brokerConnection,
    platformSession.accountId,
    platformSession.roleView,
    platformSession.tenantName,
    platformSession.tradeMode,
    user,
  ])
  const currentRouteTitle = useMemo(
    () => routeTitle(location.pathname),
    [location.pathname],
  )

  useEffect(() => {
    if (!isAuthenticated) {
      clearPlatformContext()
      return
    }
    injectPlatformContext(() => platformSession)
    return () => clearPlatformContext()
  }, [isAuthenticated, platformSession])

  // Poll unread alerts only when authenticated
  // P1-04: go through alertApi (axios) so the request carries the Authorization
  // header and participates in 401 refresh, instead of a raw fetch + r.json()
  // that would throw on non-JSON gateway error pages.
  useEffect(() => {
    if (!isAuthenticated) return
    const poll = () => {
      alertApi.getUnreadCount()
        .then(r => setUnreadAlerts((r.data as { unread?: number })?.unread || 0))
        .catch(() => { /* best-effort poll; UI keeps last count */ })
    }
    poll()
    const timer = setInterval(poll, 30000)
    return () => clearInterval(timer)
  }, [isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated) return
    let cancelled = false

    const refreshMarketTape = () => {
      marketApi.getIndexQuotes()
        .then(response => {
          if (cancelled) return
          const rows = response.data?.data?.diff || []
          const byLabel = new Map(
            rows
              .map(row => {
                const label = marketTapeLabels[String(row.f12 || '')]
                if (!label) return null
                return [label, {
                  label,
                  value: formatMarketNumber(row.f2),
                  change: formatMarketChange(row.f3),
                  tone: toneForChange(row.f3),
                }] as const
              })
              .filter((item): item is readonly [string, MarketTapeItem] => Boolean(item)),
          )
          setMarketTape(marketTapeItems.map(item => byLabel.get(item.label) || item))
        })
        .catch(() => {
          if (!cancelled) setMarketTape(marketTapeItems)
        })
    }

    refreshMarketTape()
    const timer = setInterval(refreshMarketTape, 30000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated) return
    let cancelled = false

    const refreshBrokerConnection = () => {
      if (platformSession.tradeMode !== 'live') {
        setBrokerConnection({
          status: 'paper',
          accountId: platformSession.accountId || '',
          brokerName: platformSession.brokerAdapter || 'paper',
        })
        return
      }

      liveTradeApi.getBrokerStatus()
        .then(r => {
          if (cancelled) return
          const data = r.data || {}
          const status: HeaderBrokerConnection['status'] = data.status === 'connected'
            ? 'connected'
            : data.status === 'connecting'
              ? 'connecting'
              : data.status === 'error'
                ? 'error'
                : 'disconnected'
          setBrokerConnection({
            status,
            accountId: data.account_id || platformSession.accountId || '',
            brokerName: data.broker_name || platformSession.brokerAdapter || 'paper',
          })
        })
        .catch(() => {
          if (cancelled) return
          setBrokerConnection({
            status: 'error',
            accountId: platformSession.accountId || '',
            brokerName: platformSession.brokerAdapter || 'paper',
          })
        })
    }

    refreshBrokerConnection()
    if (platformSession.tradeMode !== 'live') return () => { cancelled = true }
    const timer = setInterval(refreshBrokerConnection, 10000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [
    isAuthenticated,
    platformSession.accountId,
    platformSession.brokerAdapter,
    platformSession.tradeMode,
  ])

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  // Auth pages: no sidebar/header layout
  const isAuthPage = location.pathname === '/login' || location.pathname === '/register'

  if (isLoading) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        height: '100vh', background: '#f5f5f5',
      }}>
        <Text type="secondary">加载中...</Text>
      </div>
    )
  }

  if (isAuthPage || !isAuthenticated) {
    // Auth pages render bare (no sidebar/header).
    // The catch-all goes through ProtectedRoute so that an unauthenticated user
    // hitting a protected URL (e.g. refreshing /backtest) gets redirected to
    // /login?redirect=<original-path> instead of landing on /login with no target.
    return (
      <ErrorBoundary>
        <Suspense fallback={pageFallback}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="*" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    )
  }

  return (
    <div className={`app suying-shell${collapsed ? ' is-collapsed' : ''}`} data-testid="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand">
          <span className="logo" aria-hidden="true">
            <StockOutlined />
          </span>
          <span className="name"><span>速赢</span><b>AI</b></span>
        </div>

        <nav className="nav">
          {menuGroups.map(group => {
            const items = mainMenu.filter(item => item.group === group)
            if (items.length === 0) return null
            return (
              <section key={group} className="nav-section">
                <div className="nav-group">
                  <span>{group}</span>
                  {(group === '模型 / 系统' || group === '平台管理') && <span className="nav-admin">ADMIN</span>}
                </div>
                {items.map(item => {
                  const active = selectedKey === item.key || (selectedKey === '/' && item.key === '/')
                  return (
                    <button
                      key={item.key}
                      type="button"
                      className={`nav-item${active ? ' active' : ''}`}
                      onClick={() => navigate(item.target || item.key)}
                    >
                      {item.icon}
                      <span className="nav-label">{item.label}</span>
                      {item.badge && <span className="pill">{item.badge}</span>}
                    </button>
                  )
                })}
              </section>
            )
          })}
        </nav>

        <div className="nav nav-bottom">
          <button type="button" className="nav-item" onClick={() => setSettingsOpen(true)}>
            <SettingOutlined />
            <span className="nav-label">系统设置</span>
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="header">
          <button
            type="button"
            className="hbtn"
            aria-label={collapsed ? '展开导航' : '收起导航'}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>

          <div className="crumb">
            <b>{currentRouteTitle}</b>
          </div>

          <div className="mkt-ticker" aria-label="市场行情">
            {marketTape.map(item => (
              <span className="tk" key={item.label}>
                <span className="lbl">{item.label}</span>
                <span className={`val mono ${item.tone}`}>{item.value}</span>
                <span className={`mono ${item.tone}`}>{item.change}</span>
              </span>
            ))}
          </div>

          <Dropdown menu={{ items: platformContextMenuItems }} placement="bottomRight" trigger={['click']}>
            <button type="button" className="platform-context-compact" aria-label="当前平台上下文">
              <span className="ctx-pill primary">{roleViewLabel(platformSession.roleView)}</span>
              <span className={`ctx-pill ${platformSession.tradeMode === 'live' ? 'danger' : 'safe'}`}>
                {tradeModeLabel(platformSession.tradeMode)}
              </span>
              <span className="ctx-pill mono">{platformSession.accountId || '未绑定账户'}</span>
              <span className={`ctx-pill ${membershipTone(user)}`}>{membershipText(user)}</span>
              <DownOutlined className="ctx-more" />
            </button>
          </Dropdown>

          <div className="header-right">
            <button type="button" className="hbtn" title="刷新页面" onClick={() => window.location.reload()}>
              <ReloadOutlined />
            </button>
            <Badge count={unreadAlerts} size="small" offset={[-2, 2]}>
              <button type="button" className="hbtn" title="交易信号" onClick={() => navigate('/signals')}>
                <BellOutlined />
              </button>
            </Badge>
            <button type="button" className="hbtn" title="页面设置" onClick={() => setSettingsOpen(true)}>
              <SettingOutlined />
            </button>
            <Dropdown menu={{ items: [
              {
                key: 'tenant',
                disabled: true,
                label: `${platformSession.tenantName} · ${tradeModeLabel(platformSession.tradeMode)} · ${membershipText(user)}`,
              },
              { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
              { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
            ]}} placement="bottomRight">
              <button type="button" className="user">
                <Avatar size={26} icon={<UserOutlined />} className="av" />
                <span className="un">{user?.name || '未登录'}</span>
              </button>
            </Dropdown>
          </div>
        </header>

        <Drawer title="页面风格设置" open={settingsOpen} onClose={() => setSettingsOpen(false)} width={280}>
          <Typography.Title level={5} style={{ marginTop: 0 }}>主题模式</Typography.Title>
          <Radio.Group
            value={themeMode}
            onChange={e => setThemeMode(e.target.value)}
            style={{ marginBottom: 24 }}
          >
            <Radio.Button value="light">浅色</Radio.Button>
            <Radio.Button value="dark">暗色</Radio.Button>
          </Radio.Group>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 24 }}>
            当前：{themeMode === 'dark' ? '暗色' : '浅色'}（选择已保存到本地）
          </Typography.Text>

          <Typography.Title level={5}>其他设置</Typography.Title>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <span>紧凑模式</span>
            <Switch size="small" checked={compactMode} onChange={setCompactMode} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>多标签页</span>
            <Switch size="small" checked={multiTab} onChange={setMultiTab} />
          </div>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 12 }}>
            偏好记录保存在本地，用于保持当前设备的操作习惯。
          </Typography.Text>
        </Drawer>

        <main className="content">
          <ErrorBoundary>
            <Suspense fallback={pageFallback}>
              <Routes>
                {protectedRoutes.map(({ path, element, roles }) => (
                  <Route
                    key={path}
                    path={path}
                    element={
                      <ProtectedRoute roles={roles} permission={routePermission(path)}>
                        {element}
                      </ProtectedRoute>
                    }
                  />
                ))}
                <Route path="*" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
          <div className="page-foot">© 2026 速赢AI · V1.0.0</div>
        </main>
      </div>
    </div>
  )
}
