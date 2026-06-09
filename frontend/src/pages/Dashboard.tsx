import { useState, useEffect } from 'react'
import { Row, Col, Card, Tag, Typography, Space, Statistic, Progress, Table } from 'antd'
import {
  RiseOutlined, FallOutlined, CheckCircleOutlined,
  ThunderboltOutlined, SearchOutlined, LineChartOutlined,
} from '@ant-design/icons'
import { screenerApi } from '../api/client'

const { Title, Text } = Typography

const services = [
  { name: '选股服务', port: 8001, icon: <SearchOutlined /> },
  { name: '预测服务', port: 8002, icon: <LineChartOutlined /> },
  { name: '方案服务', port: 8003, icon: <SearchOutlined /> },
  { name: '信号服务', port: 8004, icon: <ThunderboltOutlined /> },
  { name: '预警服务', port: 8005, icon: <ThunderboltOutlined /> },
  { name: '交易服务', port: 8006, icon: <RiseOutlined /> },
  { name: '回测服务', port: 8007, icon: <LineChartOutlined /> },
  { name: '诊断服务', port: 8009, icon: <SearchOutlined /> },
]

export default function Dashboard() {
  const [modes, setModes] = useState<any[]>([])
  const [serviceStatus, setServiceStatus] = useState<Record<number, boolean>>({})

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
      {/* ── Page Header ── */}
      <div style={{ marginBottom: 24 }}>
        <div className="section-title" style={{ marginBottom: 4 }}>工作台</div>
        <Text type="secondary" style={{ fontSize: 14 }}>
          全景监控 · 选股 → 方案 → 预测 → 回测 → 信号 → 交易 · 一站式量化决策
        </Text>
      </div>

      {/* ── KPI Cards ── */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <div className="metric-card">
            <div className="metric-label">在线服务</div>
            <div className="metric-value" style={{ color: onlineCount >= 6 ? '#52c41a' : '#faad14' }}>
              {onlineCount}<span style={{ fontSize: 14, fontWeight: 400, color: '#8c8c8c' }}> / {services.length}</span>
            </div>
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div className="metric-card">
            <div className="metric-label">选股模式</div>
            <div className="metric-value">{modes.length}</div>
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div className="metric-card">
            <div className="metric-label">股票池</div>
            <div className="metric-value">5,235</div>
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div className="metric-card">
            <div className="metric-label">最新数据</div>
            <div className="metric-value" style={{ fontSize: 18 }}>2026-06-09</div>
          </div>
        </Col>
      </Row>

      {/* ── Main Content ── */}
      <Row gutter={[16, 16]}>
        {/* 选股模式 */}
        <Col xs={24} lg={14}>
          <Card
            title={<Space><SearchOutlined style={{ color: '#1a73e8' }} />选股模型</Space>}
            style={{ borderRadius: 8 }}
          >
            <Table
              dataSource={modes}
              rowKey="id"
              size="small"
              pagination={false}
              showHeader={false}
              columns={[
                { dataIndex: 'id', width: 140, render: (v: string) => (
                  <Tag color="blue" style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</Tag>
                )},
                { dataIndex: 'name', render: (v: string) => <Text strong>{v}</Text> },
                { dataIndex: 'cycle', width: 80, render: (v: string) => (
                  <Tag style={{ fontSize: 11 }}>{v}</Tag>
                )},
                { dataIndex: 'style', width: 60, render: (v: string) => (
                  <Tag color={v === '激进' ? '#ff4d4f' : v === '稳健' ? '#52c41a' : '#1890ff'}
                       style={{ fontSize: 11 }}>{v}</Tag>
                )},
              ]}
            />
          </Card>
        </Col>

        {/* 服务状态 */}
        <Col xs={24} lg={10}>
          <Card
            title={<Space><CheckCircleOutlined style={{ color: '#52c41a' }} />服务状态</Space>}
            style={{ borderRadius: 8 }}
          >
            {services.map(s => (
              <div key={s.port} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '8px 0', borderBottom: '1px solid #f0f0f0',
              }}>
                <Space size="small">
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                    backgroundColor: serviceStatus[s.port] ? '#52c41a' : '#d9d9d9',
                  }} />
                  <Text style={{ fontSize: 13 }}>{s.name}</Text>
                </Space>
                <Tag color={serviceStatus[s.port] ? 'success' : 'default'} style={{ fontSize: 11 }}>
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
