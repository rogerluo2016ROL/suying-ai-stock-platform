import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Statistic, Button, Tag, Typography, Space, Radio,
  InputNumber, Form, Input, Select, Table, message, Segmented, Tooltip,
} from 'antd'
import {
  DollarOutlined, RiseOutlined, RobotOutlined, PauseCircleOutlined,
  ThunderboltOutlined, BarChartOutlined, FallOutlined, StockOutlined,
  FundOutlined, SendOutlined, WalletOutlined, LineChartOutlined,
  RightOutlined, AuditOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

import { useLiveTrade } from '../hooks/useLiveTrade'
import type { PreCheckResult, OrderParams } from '../hooks/useLiveTrade'
import BrokerStatus from '../components/trade/BrokerStatus'
import CircuitBreakerAlert from '../components/trade/CircuitBreakerAlert'
import RiskCheckModal from '../components/trade/RiskCheckModal'
import { showLargeTradeConfirm } from '../components/trade/LargeTradeConfirm'
import { tradeApi } from '../api/client'
import type { TradeOrder, TradeAccount } from '../api/client'

const { Title, Text } = Typography

const strategyCards = [
  { title: 'AI 智能创建', desc: '描述交易思路，AI 生成最优参数', icon: <ThunderboltOutlined />, tag: 'AI', color: '#1677ff', risk: '---', market: '全市场' },
  { title: '龙头战法', desc: '追最强标的，7条件铁律自动执行', icon: <RiseOutlined />, tag: '高收益', color: '#ff4d4f', risk: '高风险', market: '强势市场' },
  { title: '网格交易', desc: '设定价格区间自动低买高卖', icon: <BarChartOutlined />, tag: '震荡', color: '#faad14', risk: '中风险', market: '震荡市场' },
  { title: '趋势跟踪', desc: '跟随趋势方向自动入场', icon: <LineChartOutlined />, tag: '趋势', color: '#52c41a', risk: '中风险', market: '趋势市场' },
  { title: '马丁格尔', desc: '逢低加仓摊薄成本', icon: <FallOutlined />, tag: '抄底', color: '#ff7a45', risk: '高风险', market: '回调抄底' },
  { title: '定投策略', desc: '定期定额持续买入', icon: <FundOutlined />, tag: '稳健', color: '#1890ff', risk: '低风险', market: '长期定投' },
]

export default function Trade() {
  const navigate = useNavigate()
  const {
    mode, setMode, brokerStatus, riskConfig, circuitBreaker,
    connectBroker, placeOrder,
  } = useLiveTrade()

  const [orders, setOrders] = useState<TradeOrder[]>([])
  const [account, setAccount] = useState<TradeAccount>({})
  const [positions, setPositions] = useState<TradeOrder[]>([])

  // ── Risk check modal state ──
  const [riskCheckOpen, setRiskCheckOpen] = useState(false)
  const [riskCheckResult, setRiskCheckResult] = useState<PreCheckResult | null>(null)

  // ── Derived disable states ──
  const brokerDisconnected = mode === 'live' && (brokerStatus === 'disconnected' || brokerStatus === 'error')
  const circuitBreakerActive = mode === 'live' && (circuitBreaker?.status === 'TRIGGERED')
  const orderDisabled = brokerDisconnected || circuitBreakerActive

  const orderDisabledReason = circuitBreakerActive
    ? '熔断保护中，交易暂停'
    : brokerDisconnected
      ? '券商未连接，请先连接券商'
      : undefined

  // ── Data fetching based on mode ──
  const fetchData = useCallback(() => {
    // Account
    tradeApi.getAccount()
      .then(r => {
        const data = r.data as unknown as { account?: TradeAccount } & TradeAccount
        setAccount((data.account || data || {}) as TradeAccount)
      })
      .catch(() => {})

    // Positions
    tradeApi.getPositions()
      .then(r => setPositions((r.data as unknown as { positions?: TradeOrder[] }).positions || []))
      .catch(() => {})

    // Orders
    tradeApi.getOrders()
      .then(r => setOrders((r.data as unknown as { orders?: TradeOrder[] }).orders || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const refreshAccount = () => fetchData()

  // ── Mode switch handler ──
  const handleModeSwitch = (v: 'paper' | 'live') => {
    const newMode = v
    if (newMode === 'live' && brokerStatus === 'disconnected') {
      message.info('请先连接券商后再进行实盘交易')
    }
    setMode(newMode)
  }

  // ── Order placement with risk control ──
  const handlePlaceOrder = async (values: { code: string; direction: string; price: number; volume: number }) => {
    const orderParams: OrderParams = {
      code: values.code,
      direction: values.direction,
      price: Number(values.price || 0),
      volume: Number(values.volume),
    }

    const result = await placeOrder(orderParams, {
      // Risk pre-check failed callback
      onPreCheckFailed: (checkResult) => {
        setRiskCheckResult(checkResult)
        setRiskCheckOpen(true)
      },
      // Large order confirm callback
      onLargeOrderConfirm: async (params) => {
        const threshold = riskConfig?.large_order_threshold || 0
        return showLargeTradeConfirm(params, threshold)
      },
    })

    if (result.success) {
      // Add order to local state
      const data = result.data
      setOrders(prev => [{
        id: data?.order_id || Date.now(),
        code: data?.code || orderParams.code,
        direction: data?.direction || orderParams.direction,
        price: data?.price || orderParams.price,
        volume: data?.volume || orderParams.volume,
        status: data?.status || 'pending',
        time: data?.filled_at?.slice(11, 19) || new Date().toLocaleTimeString(),
      }, ...prev])
      refreshAccount()
    }
  }

  return (
    <div>
      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <DollarOutlined style={{ marginRight: 8 }} />
          交易中心
        </Title>

        <Space size="middle">
          {/* Mode switch */}
          <Segmented
            value={mode}
            onChange={handleModeSwitch}
            options={[
              {
                label: '📝 模拟盘',
                value: 'paper',
              },
              {
                label: '🔴 实盘',
                value: 'live',
              },
            ]}
            style={{
              backgroundColor: mode === 'live' ? '#fff2f0' : '#f0f5ff',
            }}
          />

          {/* Broker status (live mode only) */}
          {mode === 'live' && (
            <BrokerStatus status={brokerStatus} onConnect={connectBroker} />
          )}

          {/* Audit log entry (live mode only) */}
          {mode === 'live' && (
            <Button
              type="link"
              size="small"
              icon={<AuditOutlined />}
              onClick={() => navigate('/trade/audit-log')}
            >
              审计日志
            </Button>
          )}
        </Space>
      </div>

      {/* ── Circuit breaker alert (live mode + triggered) ── */}
      {circuitBreaker?.status === 'TRIGGERED' && (
        <CircuitBreakerAlert
          status={circuitBreaker.status}
          dailyLossPct={circuitBreaker.daily_loss_pct}
          thresholdPct={circuitBreaker.threshold_pct}
          dailyPnl={circuitBreaker.daily_pnl}
          initialCapital={circuitBreaker.initial_capital}
          cooldownMinutes={circuitBreaker.cooldown_minutes}
          triggeredAt={circuitBreaker.triggered_at}
        />
      )}

      {/* ── KPI Banner ── */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" style={{ borderRadius: 8 }}>
            <Space><WalletOutlined /><Text type="secondary" style={{ fontSize: 12 }}>总资产</Text></Space>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#1677ff' }}>
              ¥{(account.total_capital || account.total_assets || 0).toLocaleString()}
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderRadius: 8 }}>
            <Space><RiseOutlined /><Text type="secondary" style={{ fontSize: 12 }}>总盈亏</Text></Space>
            <div style={{ fontSize: 24, fontWeight: 700, color: (account.total_pnl || 0) >= 0 ? '#52c41a' : '#ff4d4f' }}>
              {(account.total_pnl || 0) >= 0 ? '+' : ''}¥{(account.total_pnl || 0).toLocaleString()}
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderRadius: 8 }}>
            <Space><WalletOutlined /><Text type="secondary" style={{ fontSize: 12 }}>可用资金</Text></Space>
            <div style={{ fontSize: 24, fontWeight: 700 }}>¥{(account.available || 0).toLocaleString()}</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderRadius: 8 }}>
            <Space><PauseCircleOutlined /><Text type="secondary" style={{ fontSize: 12 }}>持仓市值</Text></Space>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#8c8c8c' }}>¥{(account.market_value || 0).toLocaleString()}</div>
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        {/* ── Strategy Cards ── */}
        <Col span={14}>
          <Card title="创建交易策略" style={{ borderRadius: 8, marginBottom: 16 }}
                extra={<Button type="link" size="small" onClick={() => navigate('/strategy')}>浏览策略市场 <RightOutlined /></Button>}>
            <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
              选择一个策略类型快速创建自动化交易
            </Text>
            <Row gutter={[12, 12]}>
              {strategyCards.map(s => (
                <Col span={8} key={s.title}>
                  <Card hoverable size="small" style={{ borderRadius: 8, height: '100%' }}>
                    <div style={{ fontSize: 24, color: s.color, marginBottom: 8 }}>{s.icon}</div>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>{s.title}</div>
                    <Text type="secondary" style={{ fontSize: 11 }}>{s.desc}</Text>
                    <div style={{ marginTop: 8 }}>
                      <Tag color={s.color === '#ff4d4f' ? 'red' : s.color === '#52c41a' ? 'green' : 'blue'} style={{ fontSize: 10 }}>{s.risk}</Tag>
                      <Tag style={{ fontSize: 10 }}>{s.market}</Tag>
                    </div>
                    <Button type="link" size="small" style={{ padding: '4px 0', marginTop: 4 }}
                            onClick={() => navigate('/auto-trade')}>
                      开始创建 <RightOutlined style={{ fontSize: 10 }} />
                    </Button>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>

          {/* ── Orders Table ── */}
          <Card title={<Space>委托记录</Space>} style={{ borderRadius: 8 }}>
            {orders.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 24 }}>
                <Text type="secondary">暂无委托 — 使用右侧下单面板创建第一条交易</Text>
              </div>
            ) : (
              <Table dataSource={orders} rowKey="id" size="small" pagination={{ pageSize: 8 }} columns={[
                { title: '时间', dataIndex: 'time', width: 80 },
                { title: '代码', dataIndex: 'code', width: 90 },
                { title: '方向', dataIndex: 'direction', width: 55,
                  render: (v: string) => <Tag color={v === 'BUY' ? 'red' : 'green'}>{v}</Tag> },
                { title: '价格', dataIndex: 'price', width: 70 },
                { title: '数量', dataIndex: 'volume', width: 70 },
                { title: '状态', dataIndex: 'status', width: 70,
                  render: (v: string) => <Tag>{v}</Tag> },
              ]} />
            )}
          </Card>
        </Col>

        {/* ── Order Panel ── */}
        <Col span={10}>
          <Card title="下单" style={{ borderRadius: 8, position: 'sticky', top: 64 }}>
            <Form layout="vertical" onFinish={handlePlaceOrder} size="small">
              <Form.Item
                label="股票代码"
                name="code"
                rules={[
                  { required: true, message: '请输入代码' },
                  { pattern: /^\d{6}$/, message: '股票代码为 6 位数字' },
                ]}
              >
                <Input placeholder="000001" maxLength={6} />
              </Form.Item>
              <Form.Item label="方向" name="direction" initialValue="BUY">
                <Radio.Group buttonStyle="solid" size="small" style={{ width: '100%' }}>
                  <Radio.Button value="BUY" style={{ width: '50%', textAlign: 'center', color: '#ff4d4f' }}>🟢 买入</Radio.Button>
                  <Radio.Button value="SELL" style={{ width: '50%', textAlign: 'center', color: '#52c41a' }}>🔴 卖出</Radio.Button>
                </Radio.Group>
              </Form.Item>
              <Form.Item
                label={<Tooltip title="0 表示市价单（按当前盘口价成交）">价格 (0=市价)</Tooltip>}
                name="price"
                initialValue={0}
              >
                <InputNumber style={{ width: '100%' }} min={0} precision={2} />
              </Form.Item>
              <Form.Item
                label="数量 (股)"
                name="volume"
                rules={[
                  { required: true, message: '请输入数量' },
                  {
                    validator: (_, value: number) =>
                      value && value % 100 === 0
                        ? Promise.resolve()
                        : Promise.reject(new Error('数量须为 100 的整数倍（A股一手 100 股）')),
                  },
                ]}
              >
                <InputNumber style={{ width: '100%' }} min={100} step={100} />
              </Form.Item>
              <Tooltip title={orderDisabledReason}>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SendOutlined />}
                  block
                  disabled={orderDisabled}
                >
                  下单
                </Button>
              </Tooltip>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  需要完整脚本策略控制？<Button type="link" size="small" style={{ padding: 0, fontSize: 11 }} onClick={() => navigate('/strategy')}>前往方案管理 <RightOutlined style={{ fontSize: 10 }} /></Button>
                </Text>
              </div>
            </Form>
          </Card>
        </Col>
      </Row>

      {/* ── Risk Check Modal ── */}
      <RiskCheckModal
        open={riskCheckOpen}
        result={riskCheckResult}
        onClose={() => setRiskCheckOpen(false)}
      />
    </div>
  )
}
