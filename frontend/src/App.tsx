import { useState } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Typography, Button, Space, Avatar, Dropdown, Badge } from 'antd'
import {
  SearchOutlined, LineChartOutlined, ThunderboltOutlined,
  BellOutlined, DollarOutlined, ExperimentOutlined,
  FundOutlined, DashboardOutlined, BulbOutlined,
  SettingOutlined, UserOutlined, LogoutOutlined,
  StockOutlined,
} from '@ant-design/icons'
import Dashboard from './pages/Dashboard'
import Screener from './pages/Screener'
import Predictions from './pages/Predictions'
import Signals from './pages/Signals'
import Trade from './pages/Trade'
import Diagnosis from './pages/Diagnosis'
import Backtest from './pages/Backtest'
import Strategy from './pages/Strategy'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const menuItems = [
  { key: '/',            icon: <DashboardOutlined />,    label: '工作台' },
  { key: '/screener',    icon: <SearchOutlined />,       label: '智能选股' },
  { key: '/predictions', icon: <LineChartOutlined />,    label: 'K线预测' },
  { key: '/strategy',    icon: <BulbOutlined />,         label: '方案管理' },
  { key: '/signals',     icon: <ThunderboltOutlined />,  label: '交易信号' },
  { key: '/trade',       icon: <DollarOutlined />,       label: '模拟交易' },
  { key: '/backtest',    icon: <ExperimentOutlined />,   label: '回测分析' },
  { key: '/diagnosis',   icon: <FundOutlined />,         label: '个股诊断' },
]

const userMenuItems: any[] = [
  { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
  { type: 'divider' as const },
  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
]

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey = '/' + location.pathname.split('/')[1]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* ── Top Header ── */}
      <Header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px', borderBottom: '1px solid #e8e8e8',
        height: 56, lineHeight: '56px', position: 'sticky', top: 0, zIndex: 100,
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}>
        <Space size="middle">
          <StockOutlined style={{ fontSize: 24, color: '#1a73e8' }} />
          <span style={{ fontSize: 18, fontWeight: 700, color: '#1a1a2e', letterSpacing: 1 }}>
            速赢AI
          </span>
          <Text type="secondary" style={{ fontSize: 13, marginLeft: 8 }}>
            AI驱动的量化投资平台
          </Text>
        </Space>

        <Space size="middle">
          <Badge count={3} size="small">
            <Button type="text" icon={<BellOutlined />} />
          </Badge>
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>
              <Avatar size={32} icon={<UserOutlined />} style={{ backgroundColor: '#1a73e8' }} />
              <span style={{ fontSize: 14 }}>管理员</span>
            </Space>
          </Dropdown>
        </Space>
      </Header>

      <Layout>
        {/* ── Sidebar ── */}
        <Sider
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          width={200}
          style={{
            borderRight: '1px solid #e8e8e8',
            background: '#ffffff',
          }}
        >
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ borderRight: 0, paddingTop: 8 }}
          />
        </Sider>

        {/* ── Content ── */}
        <Content style={{ padding: 24, background: '#f5f7fa', minHeight: 'calc(100vh - 56px)' }}>
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
      </Layout>
    </Layout>
  )
}
