import { useState, useEffect } from 'react'
import { Card, Table, Button, Select, Space, Typography, Tag, Row, Col, Statistic, message } from 'antd'
import { ExperimentOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { backtestApi } from '../api/client'

const { Title, Text } = Typography

export default function Backtest() {
  const [factors, setFactors] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    backtestApi.getFactors().then(r => setFactors(r.data.factors || [])).catch(() => {})
  }, [])

  const runBacktest = () => {
    setLoading(true)
    backtestApi.run().then(() => { message.success('回测已触发'); setLoading(false) }).catch(() => setLoading(false))
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <ExperimentOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          回测分析
        </Title>
        <Text type="secondary">滚动窗口 IC/ICIR 验证 · 策略绩效评估 · 因子校准</Text>
      </div>

      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small" style={{ borderRadius: 8 }}><Statistic title="因子数" value={factors.length} /></Card></Col>
        <Col span={6}><Card size="small" style={{ borderRadius: 8 }}><Statistic title="策略" value="6" suffix="套" /></Card></Col>
        <Col span={6}><Card size="small" style={{ borderRadius: 8 }}><Statistic title="胜率" value="--" /></Card></Col>
        <Col span={6}><Card size="small" style={{ borderRadius: 8 }}><Statistic title="夏普比" value="--" /></Card></Col>
      </Row>

      <Card title={<Space><ExperimentOutlined style={{color:'#1677ff'}} />因子列表 ({factors.length})</Space>}
            style={{ borderRadius: 8, marginBottom: 16 }}
            extra={<Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={runBacktest}>运行回测</Button>}>
        <Table dataSource={factors} rowKey="id" size="small" pagination={{ pageSize: 10 }} columns={[
          { title: '因子ID', dataIndex: 'id', width: 160, render: (v: string) => <Text code style={{fontSize:11}}>{v}</Text> },
          { title: '因子名称', dataIndex: 'name' },
          { title: 'IC', width: 60, render: () => <Tag>--</Tag> },
          { title: 'ICIR', width: 60, render: () => <Tag>--</Tag> },
          { title: '胜率', width: 60, render: () => <Tag>--</Tag> },
        ]} />
      </Card>
    </div>
  )
}
