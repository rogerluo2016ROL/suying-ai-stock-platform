import { Modal, Space, Typography, Tag } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, WarningOutlined } from '@ant-design/icons'
import type { PreCheckResult } from '../../hooks/useLiveTrade'

const { Text, Title } = Typography

interface RiskCheckModalProps {
  open: boolean
  result: PreCheckResult | null
  onClose: () => void
}

export default function RiskCheckModal({ open, result, onClose }: RiskCheckModalProps) {
  if (!result) return null

  const blockingChecks = result.checks?.filter(c => !c.passed && c.block) || []
  const warningChecks = result.checks?.filter(c => !c.passed && !c.block) || []

  return (
    <Modal
      title={
        <Space>
          <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 20 }} />
          <span>风控拦截</span>
        </Space>
      }
      open={open}
      onOk={onClose}
      onCancel={onClose}
      cancelButtonProps={{ style: { display: 'none' } }}
      okText="知道了"
      width={480}
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">以下风控规则未通过，订单已被拦截：</Text>
      </div>

      {blockingChecks.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ color: '#ff4d4f' }}>
            <CloseCircleOutlined style={{ marginRight: 4 }} />
            拦截项
          </Text>
          <div style={{ marginTop: 8 }}>
            {blockingChecks.map((check, idx) => (
              <div
                key={idx}
                style={{
                  padding: '8px 12px',
                  marginBottom: 8,
                  background: '#fff2f0',
                  border: '1px solid #ffccc7',
                  borderRadius: 6,
                }}
              >
                <div>
                  <Tag color="red">{check.name}</Tag>
                </div>
                <Text style={{ fontSize: 13, color: '#595959' }}>{check.message}</Text>
              </div>
            ))}
          </div>
        </div>
      )}

      {warningChecks.length > 0 && (
        <div>
          <Text strong style={{ color: '#faad14' }}>
            <WarningOutlined style={{ marginRight: 4 }} />
            风险提示（不阻止下单，仅供参考）
          </Text>
          <div style={{ marginTop: 8 }}>
            {warningChecks.map((check, idx) => (
              <div
                key={idx}
                style={{
                  padding: '8px 12px',
                  marginBottom: 8,
                  background: '#fffbe6',
                  border: '1px solid #ffe58f',
                  borderRadius: 6,
                }}
              >
                <div>
                  <Tag color="orange">{check.name}</Tag>
                </div>
                <Text style={{ fontSize: 13, color: '#595959' }}>{check.message}</Text>
              </div>
            ))}
          </div>
        </div>
      )}

      {result.passed && (
        <div style={{ textAlign: 'center', padding: 16 }}>
          <CheckCircleOutlined style={{ fontSize: 32, color: '#52c41a', marginBottom: 12 }} />
          <div>
            <Text type="success" strong>风控检查全部通过</Text>
          </div>
        </div>
      )}
    </Modal>
  )
}

// Helper to format risk check messages
export function formatRiskErrorMessage(checkName: string, message: string): string {
  const nameMap: Record<string, string> = {
    insufficient_funds: '资金不足',
    position_limit: '超持仓上限',
    price_limit: '涨跌停限制',
    max_single_amount: '超单笔上限',
    circuit_breaker: '熔断保护',
    daily_loss_limit: '日亏损超限',
    blacklist: '黑名单限制',
    frequency_limit: '交易频率限制',
    price_deviation: '价格偏离过大',
  }

  const displayName = nameMap[checkName] || checkName
  return `风控拦截：${displayName}，${message}`
}
