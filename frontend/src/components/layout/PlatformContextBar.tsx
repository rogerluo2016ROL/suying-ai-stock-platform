import React from 'react'
import { Space, Tag, Tooltip, Typography } from 'antd'
import {
  BankOutlined,
  CloudOutlined,
  ClusterOutlined,
  SafetyCertificateOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons'
import type { PlatformSession, RoleView } from '../../types/platform'

const { Text } = Typography

export interface PlatformContextBarProps {
  session: PlatformSession
}

const roleLabels: Record<RoleView, string> = {
  trader: '操盘手',
  investor: '个人投资者',
  admin: '系统管理员',
}

export const PlatformContextBar: React.FC<PlatformContextBarProps> = ({ session }) => {
  const accountLabel = session.accountId || '未绑定交易账户'

  return (
    <div
      style={{
        minHeight: 40,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        padding: '6px 24px',
        background: 'linear-gradient(90deg, rgba(22,119,255,0.08), rgba(82,196,26,0.05))',
        borderBottom: '1px solid var(--border, #edf1f7)',
        flexWrap: 'wrap',
      }}
    >
      <Space size={10} wrap>
        <Tooltip title="当前角色视图决定导航、页面密度和可操作能力">
          <Tag color="blue" style={{ margin: 0 }}>
            <UserSwitchOutlined /> {roleLabels[session.roleView]}
          </Tag>
        </Tooltip>

        <Tooltip title={`tenantId: ${session.tenantId}`}>
          <Tag style={{ margin: 0 }}>
            <ClusterOutlined /> {session.tenantName} <Text code>{session.tenantId}</Text>
          </Tag>
        </Tooltip>

        <Tooltip title="公共行情/模型数据共享，方案/订单/账户数据按租户和账户隔离">
          <Tag color="geekblue" style={{ margin: 0 }}>
            <SafetyCertificateOutlined /> 公共+私有隔离
          </Tag>
        </Tooltip>
      </Space>

      <Space size={10} wrap>
        <Tooltip title={`accountId: ${session.accountId || 'none'}`}>
          <Text style={{ fontSize: 12, color: 'var(--fg-2, #64748b)' }}>
            账户 <Text code>{accountLabel}</Text>
          </Text>
        </Tooltip>

        <Tag
          color={session.tradeMode === 'live' ? 'red' : 'default'}
          style={{ margin: 0 }}
        >
          <BankOutlined /> {session.tradeMode === 'live' ? '实盘' : '模拟盘'}
        </Tag>

        <Tooltip title="BrokerAdapter 统一模拟盘、QMT 和未来券商接口">
          <Tag color={session.brokerAdapter === 'paper' ? 'default' : 'orange'} style={{ margin: 0 }}>
            {session.brokerAdapter}
          </Tag>
        </Tooltip>

        <Tooltip title="云端多租户基线已启用，当前阶段使用前端默认值兼容旧后端响应">
          <Tag color={session.cloudReady ? 'green' : 'default'} style={{ margin: 0 }}>
            <CloudOutlined /> Cloud Ready
          </Tag>
        </Tooltip>
      </Space>
    </div>
  )
}

export default PlatformContextBar
