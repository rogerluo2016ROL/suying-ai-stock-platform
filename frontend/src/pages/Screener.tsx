import { useState, useEffect } from 'react'
import { Card, Select, Button, Table, Tag, Space, Typography, InputNumber, message, Row, Col, Divider } from 'antd'
import { PlayCircleOutlined, TrophyOutlined, FilterOutlined } from '@ant-design/icons'
import { screenerApi } from '../api/client'

const { Title, Text } = Typography

export default function Screener() {
  const [modes, setModes] = useState<any[]>([])
  const [mode, setMode] = useState('all')
  const [topN, setTopN] = useState(20)
  const [loading, setLoading] = useState(false)
  const [picks, setPicks] = useState<any[]>([])
  const [marketEnv, setMarketEnv] = useState('')
  const [stats, setStats] = useState({ scored: 0, excluded: 0, elapsed: 0 })

  useEffect(() => {
    screenerApi.getModes().then(r => setModes(r.data.modes || [])).catch(() => {})
  }, [])

  const runScreening = async () => {
    setLoading(true)
    try {
      const r = await screenerApi.run(mode, topN)
      const data = r.data
      setPicks(data.picks || [])
      setMarketEnv(data.market_env || '')
      setStats({
        scored: data.total_scored || data.picks?.length || 0,
        excluded: data.total_excluded || 0,
        elapsed: data.elapsed || 0,
      })
      message.success(`选股完成: ${data.total_scored || data.picks?.length || 0} 只 | ${(data.elapsed || 0).toFixed(0)}s`)
    } catch (e: any) {
      message.error(e.response?.data?.detail || '选股失败')
    } finally { setLoading(false) }
  }

  const columns = [
    { title: '#', width: 40, render: (_: any, __: any, i: number) => (
      <Text type="secondary" style={{ fontSize: 12 }}>{i + 1}</Text>
    )},
    { title: '代码', dataIndex: 'code', width: 100, render: (v: string) => (
      <Text code style={{ fontSize: 12 }}>{v}</Text>
    )},
    { title: '名称', dataIndex: 'name', width: 90 },
    { title: '价格', dataIndex: 'price', width: 70, render: (v: number) => v?.toFixed(2) },
    { title: '评分', dataIndex: 'score', width: 65, render: (v: number) => (
      <Text strong style={{ color: v >= 16 ? '#ff4d4f' : v >= 12 ? '#fa8c16' : '#1890ff' }}>
        {v?.toFixed(1)}
      </Text>
    )},
    { title: '等级', dataIndex: 'grade', width: 50, render: (v: string) => {
      const color = v === 'S' ? '#ff4d4f' : v === 'A' ? '#fa8c16' : v === 'B' ? '#1890ff' : '#8c8c8c'
      return <Tag color={color} style={{ fontWeight: 600 }}>{v}</Tag>
    }},
    { title: '入场', dataIndex: 'entry_price', width: 70, render: (v: any) => v ? (
      <Text style={{ color: '#52c41a' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text> },
    { title: '止损', dataIndex: 'stop_loss', width: 70, render: (v: any) => v ? (
      <Text style={{ color: '#ff4d4f' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text> },
    { title: '目标', dataIndex: 'target_price', width: 70, render: (v: any) => v ? (
      <Text style={{ color: '#1a73e8' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text> },
  ]

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <div className="section-title">智能选股</div>
        <Text type="secondary">6套内置策略 · 全市场5000+标的 · 多因子智能排序</Text>
      </div>

      {/* ── Control Panel ── */}
      <Card style={{ borderRadius: 8, marginBottom: 16 }}>
        <Row gutter={[16, 12]} align="middle">
          <Col>
            <Space>
              <FilterOutlined style={{ color: '#8c8c8c' }} />
              <Select value={mode} onChange={setMode} style={{ width: 220 }} options={
                modes.map((m: any) => ({ label: `${m.name} (${m.cycle})`, value: m.id }))
              } />
            </Space>
          </Col>
          <Col>
            <Space>
              <TrophyOutlined style={{ color: '#8c8c8c' }} />
              <InputNumber min={5} max={100} value={topN} onChange={v => setTopN(v || 20)}
                           style={{ width: 80 }} />
              <Text type="secondary" style={{ fontSize: 12 }}>只</Text>
            </Space>
          </Col>
          <Col>
            <Button type="primary" icon={<PlayCircleOutlined />} loading={loading}
                    onClick={runScreening} size="middle">
              开始选股
            </Button>
          </Col>
          {marketEnv && (
            <Col>
              <Tag color="blue">{marketEnv}</Tag>
            </Col>
          )}
          {stats.elapsed > 0 && (
            <Col>
              <Text type="secondary" style={{ fontSize: 12 }}>
                评分 {stats.scored} 只 · 排除 {stats.excluded} · 耗时 {stats.elapsed.toFixed(0)}s
              </Text>
            </Col>
          )}
        </Row>
      </Card>

      {/* ── Results ── */}
      <Card style={{ borderRadius: 8 }} loading={loading}
            title={picks.length > 0 ? `选股结果 (Top ${picks.length})` : '等待选股'}
      >
        <Table columns={columns} dataSource={picks} rowKey="code" size="small"
               pagination={{ pageSize: 15, showSizeChanger: false }}
               scroll={{ x: 750 }}
               locale={{ emptyText: '点击「开始选股」运行模型筛选全市场标的' }} />
      </Card>
    </div>
  )
}
