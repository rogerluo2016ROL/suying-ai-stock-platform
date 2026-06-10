import { Alert, Button, Space, Typography } from 'antd'
import { ThunderboltOutlined, CloseOutlined } from '@ant-design/icons'
import { useState } from 'react'

const { Text } = Typography

interface CircuitBreakerAlertProps {
  triggered: boolean
  lossAmount: number
  threshold: number
  message?: string
}

export default function CircuitBreakerAlert({
  triggered,
  lossAmount,
  threshold,
  message,
}: CircuitBreakerAlertProps) {
  const [dismissed, setDismissed] = useState(false)

  if (!triggered || dismissed) return null

  return (
    <Alert
      type="error"
      icon={<ThunderboltOutlined />}
      showIcon
      message={
        <Space>
          <Text strong style={{ color: '#ff4d4f' }}>日内熔断已触发</Text>
        </Space>
      }
      description={
        <div>
          <Text style={{ color: '#595959' }}>
            今日亏损 ¥{lossAmount.toLocaleString()} 已超过熔断阈值 ¥{threshold.toLocaleString()}，实盘交易已暂停。
            {message && ` ${message}`}
          </Text>
          <div style={{ marginTop: 4 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              如需恢复，请联系管理员或等待次日自动重置。
            </Text>
          </div>
        </div>
      }
      action={
        <Button
          type="text"
          size="small"
          icon={<CloseOutlined />}
          onClick={() => setDismissed(true)}
        >
          关闭
        </Button>
      }
      style={{ marginBottom: 16, borderRadius: 8 }}
      closable
      onClose={() => setDismissed(true)}
    />
  )
}
