import { Modal, Space, Descriptions, Tag, Typography } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'
import type { OrderParams } from '../../hooks/useLiveTrade'

const { Text } = Typography

interface LargeTradeConfirmProps {
  open: boolean
  orderParams: OrderParams
  threshold: number
  estimatedAmount: number
  estimatedCommission?: number
  onConfirm: () => void
  onCancel: () => void
}

export default function LargeTradeConfirm({
  open,
  orderParams,
  threshold,
  estimatedAmount,
  estimatedCommission,
  onConfirm,
  onCancel,
}: LargeTradeConfirmProps) {
  return (
    <Modal
      title={
        <Space>
          <ExclamationCircleOutlined style={{ color: '#faad14', fontSize: 20 }} />
          <span>大额交易确认</span>
        </Space>
      }
      open={open}
      onOk={onConfirm}
      onCancel={onCancel}
      okText="确认下单"
      cancelText="取消"
      okButtonProps={{ danger: true }}
      width={440}
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">
          本次交易金额较大（超过阈值 ¥{threshold.toLocaleString()}），请仔细核对后确认：
        </Text>
      </div>

      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="股票代码">
          <Text strong>{orderParams.code}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="方向">
          <Tag color={orderParams.direction === 'BUY' ? 'red' : 'green'}>
            {orderParams.direction === 'BUY' ? '买入' : '卖出'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="价格">
          {orderParams.price > 0 ? `¥${orderParams.price.toFixed(2)}` : '市价'}
        </Descriptions.Item>
        <Descriptions.Item label="数量">
          {orderParams.volume.toLocaleString()} 股
        </Descriptions.Item>
        <Descriptions.Item label="预估金额">
          <Text type="danger" strong>
            ¥{orderParams.price > 0
              ? (orderParams.price * orderParams.volume).toLocaleString()
              : '市价成交，金额待定'}
          </Text>
        </Descriptions.Item>
        {estimatedCommission !== undefined && (
          <Descriptions.Item label="预估手续费">
            ¥{estimatedCommission.toFixed(2)}
          </Descriptions.Item>
        )}
      </Descriptions>
    </Modal>
  )
}

// Helper to show as a promise-based confirm dialog
export function showLargeTradeConfirm(
  orderParams: OrderParams,
  threshold: number,
  estimatedCommission?: number,
): Promise<boolean> {
  return new Promise((resolve) => {
    const estimatedAmount = orderParams.price > 0
      ? orderParams.price * orderParams.volume
      : 0

    Modal.confirm({
      title: (
        <Space>
          <ExclamationCircleOutlined style={{ color: '#faad14' }} />
          <span>大额交易确认</span>
        </Space>
      ),
      icon: null,
      width: 440,
      content: (
        <div>
          <div style={{ marginBottom: 12 }}>
            <Text type="secondary">
              本次交易金额较大（超过阈值 ¥{threshold.toLocaleString()}），请仔细核对：
            </Text>
          </div>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="股票代码">
              <Text strong>{orderParams.code}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="方向">
              <Tag color={orderParams.direction === 'BUY' ? 'red' : 'green'}>
                {orderParams.direction === 'BUY' ? '买入' : '卖出'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="价格">
              {orderParams.price > 0 ? `¥${orderParams.price.toFixed(2)}` : '市价'}
            </Descriptions.Item>
            <Descriptions.Item label="数量">
              {orderParams.volume.toLocaleString()} 股
            </Descriptions.Item>
            <Descriptions.Item label="预估金额">
              <Text type="danger" strong>
                ¥{estimatedAmount > 0 ? estimatedAmount.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '市价成交，金额待定'}
              </Text>
            </Descriptions.Item>
            {estimatedCommission !== undefined && (
              <Descriptions.Item label="预估手续费">
                ¥{estimatedCommission.toFixed(2)}
              </Descriptions.Item>
            )}
          </Descriptions>
        </div>
      ),
      okText: '确认下单',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
}
