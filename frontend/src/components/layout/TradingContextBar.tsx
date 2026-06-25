/* ============================================================
   速赢AI — 交易上下文条组件

   来源：docs/design/new front/design-spec.md 第3.3节
   用途：显示交易日/执行模式/风控闸门/数据状态

   设计规范：
   - 高度：36px
   - 背景：var(--surface-3)
   - 前景色：var(--fg-2)
   - 警告色：var(--warn)
   - 数值：等宽数字(.mono)
   ============================================================ */

import React from 'react'
import { Space, Tag, Typography, Badge, Tooltip } from 'antd'
import {
  CalendarOutlined, SettingOutlined, WarningOutlined,
  CheckCircleOutlined, SyncOutlined, ClockCircleOutlined,
} from '@ant-design/icons'

const { Text } = Typography

// ═══════════════════════════════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════════════════════════════

export interface TradingContext {
  tradeDate?: string
  executionMode?: 'paper' | 'live'
  riskGateStatus?: 'open' | 'closed' | 'warning'
  dataStatus?: 'fresh' | 'stale' | 'offline'
  lastDataUpdate?: string
}

export interface TradingContextBarProps {
  context: TradingContext
}

// ═══════════════════════════════════════════════════════════════════════════
// 组件
// ═══════════════════════════════════════════════════════════════════════════

export const TradingContextBar: React.FC<TradingContextBarProps> = ({
  context,
}) => {
  const {
    tradeDate,
    executionMode = 'paper',
    riskGateStatus = 'open',
    dataStatus = 'fresh',
    lastDataUpdate,
  } = context

  return (
    <div
      style={{
        height: 36,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        background: 'var(--surface-3)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      {/* ── 左侧：交易日 + 执行模式 ── */}
      <Space size={16}>
        {/* 交易日 */}
        {tradeDate && (
          <Space size={4}>
            <CalendarOutlined style={{ fontSize: 12, color: 'var(--muted)' }} />
            <Text className="mono" style={{ fontSize: 12, color: 'var(--fg-2)' }}>
              {tradeDate}
            </Text>
          </Space>
        )}

        {/* 执行模式 */}
        <Tag
          style={{
            margin: 0,
            fontSize: 11,
            background: executionMode === 'live' ? 'var(--up-bg)' : 'var(--surface-2)',
            borderColor: executionMode === 'live' ? 'var(--up)' : 'var(--border)',
            color: executionMode === 'live' ? 'var(--up)' : 'var(--fg-2)',
          }}
        >
          <SettingOutlined style={{ fontSize: 10, marginRight: 4 }} />
          {executionMode === 'live' ? '实盘' : '模拟'}
        </Tag>
      </Space>

      {/* ── 右侧：风控闸门 + 数据状态 ── */}
      <Space size={16}>
        {/* 风控闸门 */}
        <Tooltip title={riskGateStatus === 'open' ? '风控闸门开启，允许交易' : '风控闸门关闭，禁止交易'}>
          <Space size={4}>
            {riskGateStatus === 'warning' && (
              <WarningOutlined style={{ fontSize: 12, color: 'var(--warn)' }} />
            )}
            {riskGateStatus === 'open' && (
              <CheckCircleOutlined style={{ fontSize: 12, color: 'var(--down)' }} />
            )}
            {riskGateStatus === 'closed' && (
              <ClockCircleOutlined style={{ fontSize: 12, color: 'var(--muted)' }} />
            )}
            <Text
              style={{
                fontSize: 11,
                color: riskGateStatus === 'warning' ? 'var(--warn)' : 'var(--fg-2)',
              }}
            >
              风控闸门
            </Text>
            <Tag
              style={{
                margin: 0,
                fontSize: 10,
                background: riskGateStatus === 'warning' ? 'var(--warn-bg)' : 'var(--surface-2)',
                borderColor: riskGateStatus === 'warning' ? 'var(--warn)' : 'var(--border)',
                color: riskGateStatus === 'warning' ? 'var(--warn)' : 'var(--fg-2)',
              }}
            >
              {riskGateStatus === 'open' ? '开启' : riskGateStatus === 'warning' ? '预警' : '关闭'}
            </Tag>
          </Space>
        </Tooltip>

        {/* 数据状态 */}
        <Tooltip title={`最后更新: ${lastDataUpdate || '--'}`}>
          <Space size={4}>
            <SyncOutlined
              spin={dataStatus === 'stale'}
              style={{
                fontSize: 12,
                color: dataStatus === 'fresh' ? 'var(--down)' : dataStatus === 'stale' ? 'var(--warn)' : 'var(--muted)',
              }}
            />
            <Text
              style={{
                fontSize: 11,
                color: dataStatus === 'fresh' ? 'var(--fg-2)' : dataStatus === 'stale' ? 'var(--warn)' : 'var(--muted)',
              }}
            >
              数据状态
            </Text>
            <Badge
              status={dataStatus === 'fresh' ? 'success' : dataStatus === 'stale' ? 'warning' : 'error'}
              text={dataStatus === 'fresh' ? '实时' : dataStatus === 'stale' ? '延迟' : '离线'}
              style={{
                fontSize: 10,
                color: dataStatus === 'fresh' ? 'var(--down)' : dataStatus === 'stale' ? 'var(--warn)' : 'var(--muted)',
              }}
            />
          </Space>
        </Tooltip>
      </Space>
    </div>
  )
}

export default TradingContextBar