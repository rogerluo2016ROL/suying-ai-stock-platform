import { Badge, Button, Space, Tooltip, Typography } from 'antd'
import { LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import type { BrokerStatus as BrokerStatusType } from '../../hooks/useLiveTrade'

const { Text } = Typography

const statusConfig: Record<BrokerStatusType, {
  status: 'success' | 'error' | 'processing' | 'warning'
  label: string
  color: string
}> = {
  connected:    { status: 'success',    label: '已连接', color: '#52c41a' },
  disconnected: { status: 'error',      label: '已断开', color: '#ff4d4f' },
  connecting:   { status: 'processing', label: '连接中', color: '#1677ff' },
  error:        { status: 'warning',    label: '异常',   color: '#faad14' },
}

interface BrokerStatusProps {
  status: BrokerStatusType
  onConnect: () => void
}

export default function BrokerStatus({ status, onConnect }: BrokerStatusProps) {
  const config = statusConfig[status]

  return (
    <Space size={4}>
      <Badge status={config.status} />
      <Text style={{ fontSize: 12, color: config.color }}>{config.label}</Text>
      {status === 'disconnected' || status === 'error' ? (
        <Tooltip title="点击连接券商">
          <Button
            type="link"
            size="small"
            icon={<LinkOutlined />}
            onClick={onConnect}
            style={{ padding: 0, fontSize: 12, color: config.color }}
          >
            连接
          </Button>
        </Tooltip>
      ) : null}
      {status === 'connecting' ? (
        <ReloadOutlined spin style={{ fontSize: 12, color: '#1677ff' }} />
      ) : null}
    </Space>
  )
}
