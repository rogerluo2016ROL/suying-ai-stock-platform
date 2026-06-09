import { useState, useEffect } from 'react'
import { Row, Col, Card, Statistic, Tag, List, Typography } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { screenerApi } from '../api/client'

const { Title, Text } = Typography

const services = [
  { name: '选股服务', port: 8001, key: 'screener' },
  { name: '预测服务', port: 8002, key: 'prediction' },
  { name: '方案服务', port: 8003, key: 'strategy' },
  { name: '信号服务', port: 8004, key: 'signal' },
  { name: '预警服务', port: 8005, key: 'alert' },
  { name: '交易服务', port: 8006, key: 'trade' },
  { name: '回测服务', port: 8007, key: 'backtest' },
  { name: '诊断服务', port: 8009, key: 'diagnosis' },
]

export default function Dashboard() {
  const [modes, setModes] = useState<any[]>([])
  const [serviceStatus, setServiceStatus] = useState<Record<string, boolean>>({})

  useEffect(() => {
    screenerApi.getModes().then(r => setModes(r.data.modes || [])).catch(() => {})
    services.forEach(s => {
      fetch(`/api/v1/health`, { signal: AbortSignal.timeout(2000) })
        .then(r => setServiceStatus(prev => ({ ...prev, [s.key]: r.ok })))
        .catch(() => setServiceStatus(prev => ({ ...prev, [s.key]: false })))
    })
  }, [])

  const onlineCount = Object.values(serviceStatus).filter(Boolean).length

  return (
    <div>
      <Title level={2}>🚀 速赢AI 智能证券投资管理平台</Title>
      <Text type="secondary">一站式选股 → 方案 → 预测 → 回测 → 信号 → 交易 → 诊断</Text>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col span={6}>
          <Card><Statistic title="在线服务" value={onlineCount} suffix={`/ ${services.length}`} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="选股模式" value={modes.length} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="今日信号" value="--" /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="持仓标的" value="--" /></Card>
        </Col>
      </Row>

      <Card title="服务状态" style={{ marginTop: 24 }}>
        <Row gutter={[16, 8]}>
          {services.map(s => (
            <Col span={6} key={s.key}>
              <Tag icon={serviceStatus[s.key] ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                   color={serviceStatus[s.key] ? 'success' : 'error'}>
                {s.name} (:80{s.port % 10})
              </Tag>
            </Col>
          ))}
        </Row>
      </Card>

      <Card title="选股模式" style={{ marginTop: 24 }}>
        <List dataSource={modes} renderItem={(m: any) => (
          <List.Item>
            <Tag color="blue">{m.id}</Tag>
            <Text strong>{m.name}</Text>
            <Tag style={{ marginLeft: 8 }}>{m.cycle}</Tag>
            <Tag color={m.style === '激进' ? 'red' : m.style === '稳健' ? 'green' : 'orange'}>{m.style}</Tag>
          </List.Item>
        )} />
      </Card>
    </div>
  )
}
