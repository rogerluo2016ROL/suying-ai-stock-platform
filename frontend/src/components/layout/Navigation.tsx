/* ============================================================
   速赢AI — 三组左侧导航组件

   来源：docs/design/new front/design-spec.md 第3.1节
   用途：左侧导航分三组（行情决策/交易执行/模型系统）

   设计规范：
   - 第一组：行情决策（AI智能看板、智能选股、产业链拆解、K线预测）
   - 第二组：交易执行（方案管理、交易信号、交易中心、量化交易）
   - 第三组：模型系统（回测分析、个股诊断、模型训练、模型注册、数据更新）
   - 底部：系统设置
   - 宽度：236px（collapsed: 64px）
   ============================================================ */

import React from 'react'
import { Menu, Divider, Typography } from 'antd'
import {
  DashboardOutlined, SearchOutlined, ApartmentOutlined, LineChartOutlined,
  BulbOutlined, ThunderboltOutlined, DollarOutlined, RobotOutlined,
  ExperimentOutlined, FundOutlined, ApiOutlined, SyncOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'

const { Text } = Typography

// ═══════════════════════════════════════════════════════════════════════════
// 导航分组配置
// ═══════════════════════════════════════════════════════════════════════════

const NAV_GROUPS = [
  {
    title: '行情决策',
    items: [
      { key: '/dashboard', icon: <DashboardOutlined />, label: 'AI 智能看板' },
      { key: '/screener', icon: <SearchOutlined />, label: '智能选股' },
      { key: '/supply-chain-bom', icon: <ApartmentOutlined />, label: '产业链拆解' },
      { key: '/predictions', icon: <LineChartOutlined />, label: 'K线预测' },
    ],
  },
  {
    title: '交易执行',
    items: [
      { key: '/strategy', icon: <BulbOutlined />, label: '方案管理' },
      { key: '/signals', icon: <ThunderboltOutlined />, label: '交易信号' },
      { key: '/trade', icon: <DollarOutlined />, label: '交易中心' },
      { key: '/auto-trade', icon: <RobotOutlined />, label: '量化交易' },
    ],
  },
  {
    title: '模型系统',
    items: [
      { key: '/backtest', icon: <ExperimentOutlined />, label: '回测分析' },
      { key: '/diagnosis', icon: <FundOutlined />, label: '个股诊断' },
      { key: '/training', icon: <ApiOutlined />, label: '模型训练' },
      { key: '/model-registry', icon: <ApiOutlined />, label: '模型注册' },
      { key: '/data-update', icon: <SyncOutlined />, label: '数据更新' },
    ],
  },
]

// ═══════════════════════════════════════════════════════════════════════════
// 组件
// ═══════════════════════════════════════════════════════════════════════════

export interface NavigationProps {
  collapsed?: boolean
}

export const Navigation: React.FC<NavigationProps> = ({ collapsed = false }) => {
  const navigate = useNavigate()
  const location = useLocation()

  // 获取当前选中的菜单项
  const selectedKey = location.pathname

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--surface)',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* ── Logo区域 ── */}
      <div
        style={{
          height: 52,
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? 0 : '0 24px',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <img
          src="/stock.png"
          alt="速赢AI"
          style={{ width: 28, height: 28 }}
        />
        {!collapsed && (
          <Text
            strong
            style={{
              marginLeft: 12,
              fontSize: 16,
              fontFamily: 'var(--font-display)',
              color: 'var(--fg)',
            }}
          >
            速赢AI
          </Text>
        )}
      </div>

      {/* ── 导航分组 ── */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {NAV_GROUPS.map((group, groupIndex) => (
          <div key={groupIndex}>
            {/* 分组标题 */}
            {!collapsed && (
              <Text
                style={{
                  display: 'block',
                  padding: '12px 24px 8px',
                  fontSize: 11,
                  color: 'var(--muted)',
                  fontWeight: 600,
                  letterSpacing: 0.5,
                }}
              >
                {group.title}
              </Text>
            )}

            {/* 分组菜单 */}
            <Menu
              mode="inline"
              selectedKeys={[selectedKey]}
              style={{
                border: 'none',
                background: 'transparent',
              }}
              items={group.items.map((item) => ({
                key: item.key,
                icon: item.icon,
                label: collapsed ? null : item.label,
                style: {
                  height: 40,
                  lineHeight: '40px',
                  margin: '4px 8px',
                  borderRadius: 'var(--radius-sm)',
                  background: selectedKey === item.key ? 'var(--accent-dim)' : 'transparent',
                  color: selectedKey === item.key ? 'var(--accent)' : 'var(--fg-2)',
                },
                onItemHover: () => {},
                onClick: () => navigate(item.key),
              }))}
            />

            {/* 分组分隔线 */}
            {!collapsed && groupIndex < NAV_GROUPS.length - 1 && (
              <Divider
                style={{
                  margin: '8px 24px',
                  borderColor: 'var(--border)',
                }}
              />
            )}
          </div>
        ))}
      </div>

      {/* ── 底部系统设置 ── */}
      <div
        style={{
          borderTop: '1px solid var(--border)',
          padding: '8px',
        }}
      >
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          style={{
            border: 'none',
            background: 'transparent',
          }}
          items={[
            {
              key: '/settings',
              icon: <SettingOutlined />,
              label: collapsed ? null : '系统设置',
              style: {
                height: 40,
                lineHeight: '40px',
                margin: '4px 8px',
                borderRadius: 'var(--radius-sm)',
                background: selectedKey === '/settings' ? 'var(--accent-dim)' : 'transparent',
                color: selectedKey === '/settings' ? 'var(--accent)' : 'var(--fg-2)',
              },
              onClick: () => navigate('/settings'),
            },
          ]}
        />
      </div>
    </div>
  )
}

export default Navigation