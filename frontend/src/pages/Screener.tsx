import { useState, useEffect } from 'react'
import { Card, Select, Button, Table, Tag, Space, Typography, Spin, InputNumber, message } from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import { screenerApi } from '../api/client'

const { Title } = Typography

export default function Screener() {
  const [modes, setModes] = useState<any[]>([])
  const [mode, setMode] = useState('all')
  const [topN, setTopN] = useState(30)
  const [loading, setLoading] = useState(false)
  const [picks, setPicks] = useState<any[]>([])

  useEffect(() => {
    screenerApi.getModes().then(r => setModes(r.data.modes || [])).catch(() => {})
  }, [])

  const runScreening = async () => {
    setLoading(true)
    try {
      const r = await screenerApi.run(mode, topN)
      setPicks(r.data.picks || [])
      message.success(`选股完成: ${r.data.total_scored || r.data.picks?.length || 0} 只`)
    } catch (e: any) {
      message.error(e.response?.data?.detail || '选股失败')
    } finally {
      setLoading(false)
    }
  }

  const columns = [
    { title: '排名', dataIndex: 'rank', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '代码', dataIndex: 'code', width: 120 },
    { title: '名称', dataIndex: 'name', width: 100 },
    { title: '价格', dataIndex: 'price', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '评分', dataIndex: 'score', width: 80, render: (v: number) => v?.toFixed(1) },
    {
      title: '等级', dataIndex: 'grade', width: 60,
      render: (v: string) => <Tag color={v === 'S' ? 'red' : v === 'A' ? 'orange' : v === 'B' ? 'blue' : 'default'}>{v}</Tag>
    },
    { title: '入场价', dataIndex: 'entry_price', width: 80, render: (v: any) => v?.toFixed(2) || '--' },
    { title: '止损价', dataIndex: 'stop_loss', width: 80, render: (v: any) => v?.toFixed(2) || '--' },
    { title: '目标价', dataIndex: 'target_price', width: 80, render: (v: any) => v?.toFixed(2) || '--' },
  ]

  return (
    <div>
      <Title level={2}>🔍 智能选股</Title>
      <Card>
        <Space size="middle">
          <Select value={mode} onChange={setMode} style={{ width: 200 }} options={
            modes.map((m: any) => ({ label: `${m.name} (${m.cycle})`, value: m.id }))
          } />
          <span>Top</span>
          <InputNumber min={5} max={100} value={topN} onChange={v => setTopN(v || 30)} />
          <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={runScreening}>
            开始选股
          </Button>
        </Space>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <Spin spinning={loading}>
          <Table columns={columns} dataSource={picks} rowKey="code" size="small"
                 pagination={{ pageSize: 20 }} scroll={{ x: 800 }} />
        </Spin>
      </Card>
    </div>
  )
}
