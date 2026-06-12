import { Alert, Button, Space, Typography } from 'antd'
import { ThunderboltOutlined, CloseOutlined } from '@ant-design/icons'
import { useState } from 'react'

const { Text } = Typography

interface CircuitBreakerAlertProps {
  status: 'NORMAL' | 'TRIGGERED'
  dailyLossPct: number
  thresholdPct: number
  dailyPnl: number
  initialCapital: number
  cooldownMinutes: number
  triggeredAt: string | null
}

export default function CircuitBreakerAlert({
  status,
  dailyLossPct,
  thresholdPct,
  dailyPnl,
  initialCapital,
  cooldownMinutes,
  triggeredAt,
}: CircuitBreakerAlertProps) {
  const [dismissed, setDismissed] = useState(false)

  if (status !== 'TRIGGERED' || dismissed) return null

  return (
    <Alert
      type="error"
      icon={<ThunderboltOutlined />}
      showIcon
      message={
        <Space>
          <Text strong style={{ color: '#ff4d4f' }}>日亏损熔断已触发</Text>
        </Space>
      }
      description={
        <div>
          <Text style={{ color: '#595959' }}>
            今日亏损 {dailyLossPct.toFixed(2)}%（¥{Math.abs(dailyPnl).toLocaleString()} / ¥{initialCapital.toLocaleString()}），
            已超过熔断阈值 {thresholdPct}%，实盘交易已暂停。
          </Text>
          {triggeredAt && (
            <div style={{ marginTop: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                触发时间：{new Date(triggeredAt).toLocaleString()}
              </Text>
            </div>
          )}
          <div style={{ marginTop: 4 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              冷却 {cooldownMinutes} 分钟后可联系管理员手动重置，或等待次日开盘自动恢复。
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
