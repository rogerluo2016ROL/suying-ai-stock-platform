import { useState, useEffect } from 'react'
import { Card, Table, Tag, Select, Space, Typography, Badge } from 'antd'
import { signalApi } from '../api/client'

const { Title } = Typography

const signalColors: Record<string, string> = {
  '🟢 STRONG_BUY': 'red', '🟡 BUY': 'orange', '🔵 HOLD': 'blue',
  '🟠 REDUCE': 'gold', '🔴 SELL': 'volcano', '⚡ TIMING_ALERT': 'purple',
}

export default function Signals() {
  const [levels, setLevels] = useState<any[]>([])
  const [session, setSession] = useState('intra')

  useEffect(() => {
    signalApi.getLevels().then(r => setLevels(r.data.levels || [])).catch(() => {})
  }, [])

  return (
    <div>
      <Title level={2}>⚡ 实时交易信号</Title>

      <Card>
        <Space>
          <Select value={session} onChange={setSession} style={{ width: 120 }} options={[
            { label: '盘前', value: 'pre' }, { label: '盘中', value: 'intra' }, { label: '盘后', value: 'post' },
          ]} />
          <Badge status="processing" text="实时监控中" />
        </Space>
      </Card>

      <Card title="信号级别" style={{ marginTop: 16 }}>
        <Table dataSource={levels} rowKey="level" size="small" pagination={false} columns={[
          { title: '信号', dataIndex: 'icon', width: 40 },
          { title: '级别', dataIndex: 'level', width: 120,
            render: (v: string) => <Tag color={signalColors['🟢 STRONG_BUY']}>{v}</Tag> },
          { title: '最低分数', dataIndex: 'min_score', width: 80 },
          { title: '操作建议', dataIndex: 'action' },
        ]} />
      </Card>

      <Card title="信号模型" style={{ marginTop: 16 }}>
        <Typography.Text code>
          信号强度 = Kronos预测置信度 × 0.3 + 因子共振数 × 0.3 + 规则匹配度 × 0.2 + 市场环境适配度 × 0.2
        </Typography.Text>
      </Card>
    </div>
  )
}
