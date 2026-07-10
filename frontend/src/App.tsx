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
import { buildMenuItems, buildProtectedRoutes, findRoute } from './app/routeRegistry'

// P1-03: code-split the 14 page bundles so the initial download only carries
// the layout + auth pages; ECharts-heavy pages (Diagnosis/Backtest/Training/
// ModelRegistry/Predictions) load on demand.
const Dashboard = lazy(() => import('./pages/Dashboard'))

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

const menuIcons: Record<string, React.ReactNode> = {
  dashboard: <DashboardOutlined />, line: <LineChartOutlined />, search: <SearchOutlined />,
  apartment: <ApartmentOutlined />, thunder: <ThunderboltOutlined />, dollar: <DollarOutlined />,
  robot: <RobotOutlined />, bulb: <BulbOutlined />, bell: <BellOutlined />,
  experiment: <ExperimentOutlined />, fund: <FundOutlined />, api: <ApiOutlined />,
  clock: <ClockCircleOutlined />, safety: <SafetyCertificateOutlined />, crown: <CrownOutlined />,
}

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

const protectedRoutes = buildProtectedRoutes()

const menuGroups: MenuItemWithRoles['group'][] = ['行情决策', '交易执行', '模型 / 系统', '平台管理']

function routeTitle(pathname: string): string {
  return findRoute(pathname)?.label || '智能看板'
}

function selectedMenuKey(pathname: string): string {
  return findRoute(pathname)?.path || '/'
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
    () => buildMenuItems(user?.role ?? null, user?.permissions).map(item => ({
      ...item,
      icon: menuIcons[item.iconKey],
      target: undefined,
    })),
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
                {protectedRoutes.map(({ path, Component, roles, permission }) => (
                  <Route
                    key={path}
                    path={path}
                    element={
                      <ProtectedRoute roles={roles} permission={permission}>
                        <Component />
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
