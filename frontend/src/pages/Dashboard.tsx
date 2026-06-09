import { useState, useEffect } from 'react'
import { Row, Col, Card, Tag, Typography, Space, Button, Radio, Avatar, List, Progress, Tooltip } from 'antd'
import {
  RiseOutlined, FallOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ThunderboltOutlined, SearchOutlined, LineChartOutlined, SyncOutlined,
  StarOutlined, StockOutlined, DollarOutlined, ScheduleOutlined,
  BulbOutlined, BellOutlined, ExperimentOutlined, FundOutlined,
  DashboardOutlined,
} from '@ant-design/icons'
import { screenerApi } from '../api/client'

const { Title, Text } = Typography

// Mock signal data (would come from API)
const signalStocks = [
  { code: '000001', name: '平安银行', price: 13.50, change: 2.15, signal: 'Bullish', desc: '资金持续流入，突破前高', market: 'A股' },
  { code: '600519', name: '贵州茅台', price: 1680, change: -1.2, signal: 'Bearish', desc: '板块轮动承压，短期回调', market: 'A股' },
  { code: '300750', name: '宁德时代', price: 210, change: 3.5, signal: 'Bullish', desc: '产业链利好，放量上攻', market: 'A股' },
  { code: '000858', name: '五粮液', price: 156, change: -0.8, signal: 'consolidation', desc: '窄幅震荡，等待方向选择', market: 'A股' },
  { code: '002594', name: '比亚迪', price: 285, change: 1.8, signal: 'Bullish', desc: '新能源汽车销量超预期', market: 'A股' },
  { code: '601318', name: '中国平安', price: 56.9, change: 0.09, signal: 'consolidation', desc: '横盘整理，等待催化剂', market: 'A股' },
  { code: '600036', name: '招商银行', price: 42.3, change: -2.1, signal: 'Bearish', desc: '息差收窄预期，银行板块承压', market: 'A股' },
  { code: '300059', name: '东方财富', price: 18.5, change: 1.2, signal: 'Bullish', desc: '券商板块活跃，量价齐升', market: 'A股' },
]

const services = [
  { name: '选股服务', port: 8001, icon: <SearchOutlined /> },
  { name: '预测服务', port: 8002, icon: <LineChartOutlined /> },
  { name: '方案服务', port: 8003, icon: <BulbOutlined /> },
  { name: '信号服务', port: 8004, icon: <ThunderboltOutlined /> },
  { name: '预警服务', port: 8005, icon: <BellOutlined /> },
  { name: '交易服务', port: 8006, icon: <DollarOutlined /> },
  { name: '回测服务', port: 8007, icon: <ExperimentOutlined /> },
  { name: '诊断服务', port: 8009, icon: <FundOutlined /> },
]

export default function Dashboard() {
  const [modes, setModes] = useState<any[]>([])
  const [serviceStatus, setServiceStatus] = useState<Record<number, boolean>>({})
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('A股')

  useEffect(() => {
    screenerApi.getModes().then(r => setModes(r.data.modes || [])).catch(() => {})
    services.forEach(s => {
      fetch(`/api/v1/health`, { signal: AbortSignal.timeout(1500) })
        .then(r => setServiceStatus(prev => ({ ...prev, [s.port]: r.ok })))
        .catch(() => setServiceStatus(prev => ({ ...prev, [s.port]: false })))
    })
  }, [])

  const onlineCount = Object.values(serviceStatus).filter(Boolean).length

  return (
    <div>
      {/* ── AI Opportunity Radar ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          <ThunderboltOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          AI 机会雷达
        </Title>
        <Space>
          <Text type="secondary" style={{ fontSize: 12 }}>每分钟更新</Text>
          <Button size="small" icon={<SyncOutlined />} loading={loading}>刷新</Button>
        </Space>
      </div>

      {/* Signal Cards — horizontal scroll */}
      <div style={{
        display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 12,
        scrollbarWidth: 'none',
      }}>
        {signalStocks.map(stock => (
          <Card
            key={stock.code}
            size="small"
            style={{
              minWidth: 200, maxWidth: 200, borderRadius: 8, cursor: 'pointer', flexShrink: 0,
              border: '1px solid #f0f0f0',
            }}
            hoverable
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <Text strong style={{ fontSize: 14 }}>{stock.code}</Text>
                <Tag style={{ marginLeft: 4, fontSize: 10 }}>{stock.market}</Tag>
              </div>
              <Tag color={
                stock.signal === 'Bullish' ? '#52c41a' :
                stock.signal === 'Bearish' ? '#ff4d4f' : '#1890ff'
              } style={{ fontSize: 10 }}>
                {stock.signal === 'Bullish' ? '📈 看涨' :
                 stock.signal === 'Bearish' ? '📉 看跌' : '➡️ 震荡'}
              </Tag>
            </div>
            <div style={{ marginTop: 8 }}>
              <Text style={{ fontSize: 20, fontWeight: 700 }}>{stock.price}</Text>
              <Text style={{
                fontSize: 13, marginLeft: 8,
                color: stock.change >= 0 ? '#52c41a' : '#ff4d4f',
              }}>
                {stock.change >= 0 ? '+' : ''}{stock.change}%
              </Text>
            </div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
              {stock.desc}
            </Text>
          </Card>
        ))}
      </div>

      {/* ── Market Indicators ── */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card size="small" style={{ borderRadius: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>市场情绪</Text>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#faad14' }}>62</div>
            <Progress percent={62} size="small" showInfo={false} strokeColor="#faad14" />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" style={{ borderRadius: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>涨停/跌停</Text>
            <div style={{ fontSize: 24, fontWeight: 700 }}>
              <span style={{ color: '#ff4d4f' }}>45</span>
              <span style={{ color: '#d9d9d9', margin: '0 4px' }}>/</span>
              <span style={{ color: '#52c41a' }}>8</span>
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" style={{ borderRadius: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>服务状态</Text>
            <div style={{ fontSize: 24, fontWeight: 700, color: onlineCount >= 6 ? '#52c41a' : '#faad14' }}>
              {onlineCount}<span style={{ fontSize: 14, fontWeight: 400, color: '#8c8c8c' }}>/8</span>
            </div>
          </Card>
        </Col>
      </Row>

      {/* ── Main Content Area ── */}
      <Row gutter={16}>
        {/* Left: Quick Actions + Model Info */}
        <Col span={16}>
          {/* Asset Class Tabs */}
          <Radio.Group value={activeTab} onChange={e => setActiveTab(e.target.value)}
                       style={{ marginBottom: 16 }} size="small">
            <Radio.Button value="A股">A股</Radio.Button>
            <Radio.Button value="港股">港股</Radio.Button>
            <Radio.Button value="板块">板块</Radio.Button>
          </Radio.Group>

          {/* AI Analysis Engine Card */}
          <Card style={{ borderRadius: 8, marginBottom: 16 }}
                title={<Space><StarOutlined style={{ color: '#1677ff' }} />AI 分析引擎</Space>}
                extra={<Tag color="blue">AI-POWERED</Tag>}>
            <Text type="secondary">多源数据驱动 · 机构级洞察 · 实时市场脉动</Text>
            <Row gutter={12} style={{ marginTop: 16 }}>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center', borderRadius: 8 }}>
                  <LineChartOutlined style={{ fontSize: 28, color: '#1677ff' }} />
                  <div style={{ fontWeight: 600, marginTop: 8 }}>多周期预测</div>
                  <Text type="secondary" style={{ fontSize: 11 }}>融合4时间维度AI共识</Text>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center', borderRadius: 8 }}>
                  <DashboardOutlined style={{ fontSize: 28, color: '#1677ff' }} />
                  <div style={{ fontWeight: 600, marginTop: 8 }}>因子矩阵</div>
                  <Text type="secondary" style={{ fontSize: 11 }}>机构级量化指标体系</Text>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center', borderRadius: 8 }}>
                  <StarOutlined style={{ fontSize: 28, color: '#1677ff' }} />
                  <div style={{ fontWeight: 600, marginTop: 8 }}>一键选股</div>
                  <Text type="secondary" style={{ fontSize: 11 }}>方案直达 · 智能监控</Text>
                </Card>
              </Col>
            </Row>
          </Card>

          {/* Screening Models */}
          <Card title={<Space><SearchOutlined style={{ color: '#1677ff' }} />选股模型 ({modes.length})</Space>}
                style={{ borderRadius: 8 }}>
            <List dataSource={modes} renderItem={(m: any) => (
              <List.Item style={{ padding: '8px 0' }}>
                <Space>
                  <Tag color="blue" style={{ fontFamily: 'monospace' }}>{m.id}</Tag>
                  <Text strong>{m.name}</Text>
                  <Tag>{m.cycle}</Tag>
                  <Tag color={m.style === '激进' ? '#ff4d4f' : m.style === '稳健' ? '#52c41a' : '#1890ff'}>
                    {m.style}
                  </Tag>
                </Space>
              </List.Item>
            )} />
          </Card>
        </Col>

        {/* Right: Watchlist + Service Status */}
        <Col span={8}>
          <Card
            title={<Space><StarOutlined /> 自选监控</Space>}
            size="small" style={{ borderRadius: 8, marginBottom: 16 }}
            extra={<Button size="small" type="text" icon={<StarOutlined />} />}
          >
            {signalStocks.slice(0, 4).map(s => (
              <div key={s.code} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '6px 0', borderBottom: '1px solid #f0f0f0',
              }}>
                <div>
                  <Text strong style={{ fontSize: 13 }}>{s.code}</Text>
                  <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>{s.market}</Text>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <Text style={{ fontSize: 13 }}>{s.price}</Text>
                  <Text style={{
                    fontSize: 12, marginLeft: 8,
                    color: s.change >= 0 ? '#52c41a' : '#ff4d4f',
                  }}>{s.change >= 0 ? '+' : ''}{s.change}%</Text>
                </div>
              </div>
            ))}
          </Card>

          <Card title="服务状态" size="small" style={{ borderRadius: 8 }}>
            {services.map(s => (
              <div key={s.port} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '4px 0', fontSize: 12,
              }}>
                <Space size="small">
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
                    backgroundColor: serviceStatus[s.port] ? '#52c41a' : '#d9d9d9',
                  }} />
                  <Text style={{ fontSize: 12 }}>{s.name}</Text>
                </Space>
                <Tag color={serviceStatus[s.port] ? 'success' : 'default'} style={{ fontSize: 10 }}>
                  :{s.port}
                </Tag>
              </div>
            ))}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
