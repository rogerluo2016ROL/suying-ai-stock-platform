import { useState } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Space, Badge, Avatar, Dropdown, Drawer, Switch, Typography, theme as antTheme, Radio } from 'antd'
import {
  SearchOutlined, LineChartOutlined, ThunderboltOutlined,
  BellOutlined, DollarOutlined, ExperimentOutlined,
  FundOutlined, DashboardOutlined, BulbOutlined,
  SettingOutlined, UserOutlined, ReloadOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined,
  GlobalOutlined, StockOutlined, RobotOutlined,
  GithubOutlined, MailOutlined,
} from '@ant-design/icons'
import Dashboard from './pages/Dashboard'
import Screener from './pages/Screener'
import Predictions from './pages/Predictions'
import Signals from './pages/Signals'
import Trade from './pages/Trade'
import Diagnosis from './pages/Diagnosis'
import Backtest from './pages/Backtest'
import Strategy from './pages/Strategy'

const { Header, Sider, Content, Footer } = Layout
const { Text, Link } = Typography

const menuItems = [
  { key: '/',            icon: <DashboardOutlined />,    label: 'AI 智能看板' },
  { key: '/screener',    icon: <SearchOutlined />,       label: '智能选股' },
  { key: '/predictions', icon: <LineChartOutlined />,    label: 'K线预测' },
  { key: '/strategy',    icon: <BulbOutlined />,         label: '方案管理' },
  { key: '/signals',     icon: <ThunderboltOutlined />,  label: '交易信号' },
  { key: '/trade',       icon: <DollarOutlined />,       label: '交易中心' },
  { key: '/backtest',    icon: <ExperimentOutlined />,   label: '回测分析' },
  { key: '/diagnosis',   icon: <FundOutlined />,         label: '个股诊断' },
]

const bottomMenuItems = [
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
]

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const selectedKey = '/' + location.pathname.split('/')[1]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* ── Sidebar (QuantDinger style) ── */}
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={220}
        style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, zIndex: 100 }}
      >
        {/* Logo */}
        <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 16px' }}>
          <StockOutlined style={{ fontSize: 24, color: '#fff', marginRight: collapsed ? 0 : 10 }} />
          {!collapsed && (
            <span style={{ color: '#fff', fontSize: 16, fontWeight: 700, whiteSpace: 'nowrap' }}>
              速赢AI
            </span>
          )}
        </div>

        {/* Main Menu */}
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />

        {/* Bottom Menu */}
        <div style={{ position: 'absolute', bottom: 0, width: '100%' }}>
          <Menu
            theme="dark"
            mode="inline"
            selectable={false}
            items={bottomMenuItems}
            onClick={({ key }) => navigate(key)}
          />
        </div>
      </Sider>

      {/* ── Main Layout ── */}
      <Layout style={{ marginLeft: collapsed ? 80 : 220, transition: 'margin-left 0.2s' }}>
        {/* ── Top Header Bar (QuantDinger style) ── */}
        <Header style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 24px', height: 48, lineHeight: '48px',
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          position: 'sticky', top: 0, zIndex: 99,
        }}>
          <Space>
            <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                    onClick={() => setCollapsed(!collapsed)}
            />
            <Button type="text" icon={<ReloadOutlined />} title="刷新" />
          </Space>

          <Space size="middle">
            <Badge count={5} size="small">
              <Button type="text" icon={<BellOutlined />} />
            </Badge>
            <Button type="text" icon={<GlobalOutlined />} title="语言" />
            <Button type="text" icon={<SettingOutlined />} title="页面设置"
                    onClick={() => setSettingsOpen(true)} />
            <Dropdown menu={{ items: [
              { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
              { key: 'logout', icon: <UserOutlined />, label: '退出登录' },
            ]}} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar size={28} icon={<UserOutlined />} style={{ backgroundColor: '#1677ff' }} />
                <span style={{ fontSize: 13 }}>Admin</span>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        {/* ── Page Style Settings Drawer (QuantDinger style) ── */}
        <Drawer title="页面风格设置" open={settingsOpen} onClose={() => setSettingsOpen(false)} width={280}>
          <Typography.Title level={5} style={{ marginTop: 0 }}>主题模式</Typography.Title>
          <Radio.Group defaultValue="light" style={{ marginBottom: 24 }}>
            <Radio.Button value="dark">暗色</Radio.Button>
            <Radio.Button value="light">浅色</Radio.Button>
          </Radio.Group>

          <Typography.Title level={5}>其他设置</Typography.Title>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <span>弱色模式</span>
            <Switch size="small" />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>多标签页</span>
            <Switch size="small" />
          </div>
        </Drawer>

        {/* ── Content ── */}
        <Content style={{ margin: 16, minHeight: 'calc(100vh - 48px - 180px)' }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/screener" element={<Screener />} />
            <Route path="/predictions" element={<Predictions />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/trade" element={<Trade />} />
            <Route path="/diagnosis" element={<Diagnosis />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/strategy" element={<Strategy />} />
          </Routes>
        </Content>

        {/* ── Footer (QuantDinger style) ── */}
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
