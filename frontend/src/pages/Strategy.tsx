import { useState, useEffect } from 'react'
import { Card, Button, Steps, Space, Typography, Tag, message, Table, Modal, Descriptions } from 'antd'
import { BulbOutlined, PlayCircleOutlined, FileTextOutlined, DeleteOutlined, CheckCircleOutlined, EyeOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

const planSteps = [
  { title: '选股', description: '运行模型' },
  { title: '预方案', description: '勾选标的' },
  { title: '预测验证', description: 'Kronos预测' },
  { title: '回测验证', description: '历史回测' },
  { title: '确认方案', description: '生成报告' },
  { title: '执行交易', description: '模拟/实盘' },
]

const statusColors: Record<string, string> = {
  draft: 'blue', confirmed: 'green', active: 'red', archived: 'default',
}

export default function Strategy() {
  const [plans, setPlans] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [detailPlan, setDetailPlan] = useState<any>(null)

  const loadPlans = () => {
    setLoading(true)
    fetch('/api/v1/strategy/plans').then(r => r.json()).then(d => {
      setPlans(d.plans || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => { loadPlans() }, [])

  const confirmPlan = async (id: string) => {
    await fetch(`/api/v1/strategy/plans/${id}/confirm`, { method: 'POST' })
    message.success('方案已确认')
    loadPlans()
  }

  const deletePlan = async (id: string) => {
    await fetch(`/api/v1/strategy/plans/${id}`, { method: 'DELETE' })
    message.success('方案已删除')
    loadPlans()
  }

  const viewPlan = async (id: string) => {
    const r = await fetch(`/api/v1/strategy/plans/${id}`)
    setDetailPlan(await r.json())
  }

  const columns = [
    { title: '方案ID', dataIndex: 'id', width: 140, render: (v: string) => <Text code style={{fontSize:11}}>{v}</Text> },
    { title: '名称', dataIndex: 'name', width: 160 },
    { title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => <Tag color={statusColors[v] || 'default'}>{v}</Tag> },
    { title: '标的数', dataIndex: 'picks_count', width: 60 },
    { title: '资金', dataIndex: 'capital', width: 90, render: (v: number) => `¥${(v/10000).toFixed(0)}万` },
    { title: '创建时间', dataIndex: 'created_at', width: 110, render: (v: string) => v?.slice(0,16) },
    { title: '操作', dataIndex: 'id', width: 200, render: (id: string, record: any) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => viewPlan(id)}>查看</Button>
        {record.status === 'draft' && (
          <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => confirmPlan(id)}>确认</Button>
        )}
        <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deletePlan(id)} />
      </Space>
    )},
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <BulbOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          方案管理
        </Title>
        <Text type="secondary">方案生命周期: 草稿 → 预测验证 → 回测验证 → 确认 → 执行</Text>
      </div>

      <Card style={{ borderRadius: 8, marginBottom: 16 }}>
        <Steps current={plans.length > 0 ? 1 : 0} size="small" items={planSteps} />
      </Card>

      <Card title={<Space><FileTextOutlined />方案列表 ({plans.length})</Space>}
            style={{ borderRadius: 8 }}
            extra={<Button icon={<PlayCircleOutlined />} onClick={loadPlans} loading={loading}>刷新</Button>}>
        <Table columns={columns} dataSource={plans} rowKey="id" size="small"
               pagination={{ pageSize: 10 }}
               locale={{ emptyText: '暂无方案。请在智能选股页面运行选股后，勾选标的生成预方案。' }} />
      </Card>

      <Modal title="方案详情" open={!!detailPlan} onCancel={() => setDetailPlan(null)} footer={null} width={600}>
        {detailPlan && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="方案ID">{detailPlan.id}</Descriptions.Item>
            <Descriptions.Item label="名称">{detailPlan.name}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={statusColors[detailPlan.status]}>{detailPlan.status}</Tag></Descriptions.Item>
            <Descriptions.Item label="选股模型">{detailPlan.model_name}</Descriptions.Item>
            <Descriptions.Item label="资金">¥{(detailPlan.capital/10000).toFixed(0)}万</Descriptions.Item>
            <Descriptions.Item label="最大持仓">{detailPlan.max_positions}只</Descriptions.Item>
            <Descriptions.Item label="标的列表">
              {(detailPlan.picks || []).map((p: any) => (
                <Tag key={p.code}>{p.code} {p.name} {p.score?.toFixed(1)}分</Tag>
              ))}
              {detailPlan.picks?.length === 0 && '暂未添加标的'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
