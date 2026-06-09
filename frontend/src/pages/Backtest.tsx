import { useState, useEffect } from 'react'
import { Card, Table, Button, Select, Space, Typography, Tag, InputNumber } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import { backtestApi } from '../api/client'

const { Title } = Typography

export default function Backtest() {
  const [factors, setFactors] = useState<any[]>([])
  const [mode, setMode] = useState('all')
  const [windows, setWindows] = useState(3)

  useEffect(() => {
    backtestApi.getFactors().then(r => setFactors(r.data.factors || [])).catch(() => {})
  }, [])

  return (
    <div>
      <Title level={2}><ExperimentOutlined /> 回测分析</Title>

      <Card>
        <Space>
          <Select value={mode} onChange={setMode} style={{ width: 120 }} options={[
            { label: '综合', value: 'all' }, { label: '短线', value: 'short' }, { label: '长线', value: 'long' },
          ]} />
          <span>窗口:</span>
          <InputNumber min={1} max={12} value={windows} onChange={v => setWindows(v || 3)} />
          <Button type="primary" icon={<ExperimentOutlined />}>运行回测</Button>
        </Space>
      </Card>

      <Card title={`因子列表 (${factors.length} 个)`} style={{ marginTop: 16 }}>
        <Table dataSource={factors} rowKey="id" size="small" pagination={false} columns={[
          { title: '因子ID', dataIndex: 'id', width: 160 },
          { title: '因子名称', dataIndex: 'name' },
          { title: 'IC均值', dataIndex: 'ic_mean', width: 80, render: () => <Tag>--</Tag> },
          { title: 'ICIR', dataIndex: 'icir', width: 80, render: () => <Tag>--</Tag> },
          { title: '胜率', dataIndex: 'hit_rate', width: 80, render: () => <Tag>--</Tag> },
        ]} />
      </Card>

      <Card title="回测指标" style={{ marginTop: 16 }}>
        <Typography.Text type="secondary">
          对接数据管道后填充：累计收益曲线、夏普比率、最大回撤、胜率、盈亏比、月度收益热力图
        </Typography.Text>
      </Card>
    </div>
  )
}
