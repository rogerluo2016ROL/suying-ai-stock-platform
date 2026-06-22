import { useState, useEffect, useMemo, lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Space, Badge, Avatar, Dropdown, Drawer, Switch, Typography, Radio, Spin } from 'antd'
import type { ItemType } from 'antd/es/menu/interface'
import {
  SearchOutlined, LineChartOutlined, ThunderboltOutlined,
  BellOutlined, DollarOutlined, ExperimentOutlined,
  FundOutlined, DashboardOutlined, BulbOutlined,
  SettingOutlined, UserOutlined, ReloadOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined,
  GlobalOutlined, StockOutlined, RobotOutlined,
  GithubOutlined, MailOutlined, LogoutOutlined,
  ApiOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import { useAuth, type Role } from './contexts/AuthContext'
import { useTheme } from './contexts/ThemeContext'
import ProtectedRoute from './components/auth/ProtectedRoute'
import ErrorBoundary from './components/ErrorBoundary'
import { alertApi } from './api/client'
import LoginPage from './components/auth/LoginPage'
import RegisterPage from './components/auth/RegisterPage'

// P1-03: code-split the 14 page bundles so the initial download only carries
// the layout + auth pages; ECharts-heavy pages (Diagnosis/Backtest/Training/
// ModelRegistry/Predictions) load on demand.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Screener = lazy(() => import('./pages/Screener'))
const Predictions = lazy(() => import('./pages/Predictions'))
const Signals = lazy(() => import('./pages/Signals'))
const Trade = lazy(() => import('./pages/Trade'))
const AuditLog = lazy(() => import('./pages/AuditLog'))
const Diagnosis = lazy(() => import('./pages/Diagnosis'))
const Backtest = lazy(() => import('./pages/Backtest'))
const Strategy = lazy(() => import('./pages/Strategy'))
const AutoTrade = lazy(() => import('./pages/AutoTrade'))
const Training = lazy(() => import('./pages/Training'))
const ModelRegistry = lazy(() => import('./pages/ModelRegistry'))
const DataUpdate = lazy(() => import('./pages/DataUpdate'))

const { Header, Sider, Content, Footer } = Layout
const { Text, Link } = Typography

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
}

const allMenuItems: MenuItemWithRoles[] = [
  { key: '/',            icon: <DashboardOutlined />,    label: 'AI 智能看板', roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/screener',    icon: <SearchOutlined />,       label: '智能选股',   roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/predictions', icon: <LineChartOutlined />,    label: 'K线预测',    roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/strategy',    icon: <BulbOutlined />,         label: '方案管理',   roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/signals',     icon: <ThunderboltOutlined />,  label: '交易信号',   roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/trade',       icon: <DollarOutlined />,       label: '交易中心',   roles: ['admin', 'internal_analyst', 'user'] },
  { key: '/auto-trade',  icon: <RobotOutlined />,        label: '量化交易',   roles: ['admin', 'internal_analyst', 'user'] },
  { key: '/backtest',    icon: <ExperimentOutlined />,   label: '回测分析',   roles: ['admin', 'internal_analyst', 'external_analyst'] },
  { key: '/diagnosis',   icon: <FundOutlined />,         label: '个股诊断',   roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { key: '/training',        icon: <ExperimentOutlined />, label: '模型训练',   roles: ['admin'] },
  { key: '/model-registry',  icon: <ApiOutlined />,        label: '模型注册',   roles: ['admin'] },
  { key: '/data-update',     icon: <ClockCircleOutlined />, label: '数据更新',   roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
]

const bottomMenuItems: MenuItemWithRoles[] = [
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置', roles: ['admin'] },
]

// ── Protected route config ──

const protectedRoutes: { path: string; element: React.ReactNode; roles: Role[] }[] = [
  { path: '/',            element: <Dashboard />,    roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/screener',    element: <Screener />,      roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/predictions', element: <Predictions />,   roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/strategy',    element: <Strategy />,      roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/signals',     element: <Signals />,       roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/trade',       element: <Trade />,         roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/trade/audit-log', element: <AuditLog />,  roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/auto-trade',  element: <AutoTrade />,     roles: ['admin', 'internal_analyst', 'user'] },
  { path: '/backtest',       element: <Backtest />,       roles: ['admin', 'internal_analyst', 'external_analyst'] },
  { path: '/diagnosis',      element: <Diagnosis />,      roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
  { path: '/training',       element: <Training />,       roles: ['admin'] },
  { path: '/model-registry', element: <ModelRegistry />,  roles: ['admin'] },
  { path: '/data-update',    element: <DataUpdate />,     roles: ['admin', 'internal_analyst', 'external_analyst', 'user'] },
]

function filterMenu(items: MenuItemWithRoles[], role: Role | null): ItemType[] {
  return items
    .filter(item => role && item.roles.includes(role))
    .map(({ key, icon, label }) => ({ key, icon, label }))
}

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [unreadAlerts, setUnreadAlerts] = useState(0)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, isAuthenticated, isLoading, logout, hasRole } = useAuth()
  const { mode: themeMode, setMode: setThemeMode } = useTheme()
  const [compactMode, setCompactMode] = useState(false)
  const [multiTab, setMultiTab] = useState(false)

  const selectedKey = '/' + location.pathname.split('/')[1]

  // Filter menu items by role
  const mainMenu = useMemo(
    () => filterMenu(allMenuItems, user?.role ?? null),
    [user?.role],
  )
  const bottomMenu = useMemo(
    () => filterMenu(bottomMenuItems, user?.role ?? null),
    [user?.role],
  )

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
    <Layout style={{ minHeight: '100vh' }}>
      {/* ── Sidebar ── */}
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={256}
        style={{
          overflow: 'auto', height: '100vh', position: 'fixed', left: 0, zIndex: 100,
          background: '#fff', boxShadow: '2px 0px 8px 0px rgba(29, 35, 41, 0.05)',
        }}
      >
        {/* Logo */}
        <div style={{
          height: 64, display: 'flex', alignItems: 'center',
          padding: collapsed ? '0 8px' : '0 24px',
          justifyContent: collapsed ? 'center' : 'flex-start',
        }}>
          <StockOutlined style={{ fontSize: 24, color: '#1677ff' }} />
          {!collapsed && (
            <span style={{ marginLeft: 12, fontSize: 16, fontWeight: 600, color: '#000000d9', whiteSpace: 'nowrap' }}>
              速赢AI
            </span>
          )}
        </div>

        {/* Main Menu */}
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={mainMenu}
          onClick={({ key }) => navigate(key)}
          style={{
            border: 'none',
            background: '#fff',
          }}
        />

        {/* Bottom Menu */}
        {bottomMenu.length > 0 && (
          <div style={{ position: 'absolute', bottom: 0, width: '100%' }}>
            <Menu
              mode="inline"
              selectable={false}
              items={bottomMenu}
              onClick={({ key }) => navigate(key)}
              style={{
                border: 'none',
                background: '#fff',
              }}
            />
          </div>
        )}
      </Sider>

      {/* ── Main Layout ── */}
      <Layout style={{ marginLeft: collapsed ? 80 : 256, transition: 'margin-left 0.2s' }}>
        {/* ── Top Header Bar ── */}
        <Header style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 24px', height: 48, lineHeight: '48px',
          background: '#fff',
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          position: 'sticky', top: 0, zIndex: 99,
        }}>
          <Space>
            <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                    onClick={() => setCollapsed(!collapsed)}
            />
            <Button type="text" icon={<ReloadOutlined />} title="刷新页面"
                    onClick={() => window.location.reload()} />
          </Space>

          <Space size="middle">
            <Badge count={unreadAlerts} size="small" offset={[-2, 2]}>
              <Button type="text" icon={<BellOutlined />} title="交易信号"
                      onClick={() => navigate('/signals')} />
            </Badge>
            <Button type="text" icon={<GlobalOutlined />} title="多语言（开发中）" disabled />
            <Button type="text" icon={<SettingOutlined />} title="页面设置"
                    onClick={() => setSettingsOpen(true)} />
            <Dropdown menu={{ items: [
              { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
              { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
            ]}} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar size={28} icon={<UserOutlined />} style={{ backgroundColor: '#1677ff' }} />
                <span style={{ fontSize: 13 }}>{user?.name || '未登录'}</span>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        {/* ── Page Style Settings Drawer (P1-05: live controls, persisted) ── */}
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
            注：紧凑模式/多标签页为偏好记录，后续迭代接入布局。
          </Typography.Text>
        </Drawer>

        {/* ── Content ── */}
        <Content style={{ margin: 16, minHeight: 'calc(100vh - 48px - 180px)' }}>
          {/* P1-02: per-route error boundary so a single page throw doesn't white-screen the app;
              P1-03: Suspense wraps the lazy-loaded page bundles. */}
          <ErrorBoundary>
            <Suspense fallback={pageFallback}>
              <Routes>
                {protectedRoutes.map(({ path, element, roles }) => (
                  <Route
                    key={path}
                    path={path}
                    element={<ProtectedRoute roles={roles}>{element}</ProtectedRoute>}
                  />
                ))}
                <Route path="*" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </Content>

        {/* ── Footer ── */}
        <Footer style={{ textAlign: 'center', padding: '24px 50px', background: '#f5f5f5' }}>
          <div style={{ marginBottom: 12 }}>
            <Space size="large">
              <span style={{ fontWeight: 600, color: '#00000073' }}>联系我们</span>
              <Link href="mailto:support@suying.ai"><MailOutlined /> Email</Link>
            </Space>
          </div>
          <div style={{ marginBottom: 8 }}>
            <Space size="middle">
              <GithubOutlined />
              <GlobalOutlined />
              <MailOutlined />
            </Space>
          </div>
          <div>
            <Space split={<span style={{ color: '#d9d9d9' }}>|</span>}>
              <Link style={{ fontSize: 12 }}>用户协议</Link>
              <Link style={{ fontSize: 12 }}>隐私政策</Link>
            </Space>
          </div>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              © 2026 速赢AI. All rights reserved. V1.0.0
            </Text>
          </div>
        </Footer>
      </Layout>
    </Layout>
  )
}
