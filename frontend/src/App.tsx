import { useState } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Typography } from 'antd'
import {
  SearchOutlined, LineChartOutlined, ThunderboltOutlined,
  BellOutlined, DollarOutlined, ExperimentOutlined,
  FundOutlined, DashboardOutlined, BulbOutlined,
} from '@ant-design/icons'
import Dashboard from './pages/Dashboard'
import Screener from './pages/Screener'
import Predictions from './pages/Predictions'
import Signals from './pages/Signals'
import Trade from './pages/Trade'
import Diagnosis from './pages/Diagnosis'
import Backtest from './pages/Backtest'
import Strategy from './pages/Strategy'

const { Sider, Content } = Layout

const menuItems = [
  { key: '/',            icon: <DashboardOutlined />,    label: '工作台' },
  { key: '/screener',    icon: <SearchOutlined />,       label: '智能选股' },
  { key: '/predictions', icon: <LineChartOutlined />,    label: 'Kronos预测' },
  { key: '/strategy',    icon: <BulbOutlined />,         label: '方案管理' },
  { key: '/signals',     icon: <ThunderboltOutlined />,  label: '交易信号' },
  { key: '/trade',       icon: <DollarOutlined />,       label: '模拟交易' },
  { key: '/backtest',    icon: <ExperimentOutlined />,   label: '回测分析' },
  { key: '/diagnosis',   icon: <FundOutlined />,         label: '个股诊断' },
]

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, zIndex: 100 }}
      >
        <div style={{ height: 48, margin: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography.Title level={4} style={{ color: '#fff', margin: 0, whiteSpace: 'nowrap' }}>
            {collapsed ? '速赢' : '🚀 速赢AI'}
          </Typography.Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout style={{ marginLeft: collapsed ? 80 : 200, transition: 'margin-left 0.2s' }}>
        <Content style={{ padding: 24, minHeight: '100vh' }}>
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
