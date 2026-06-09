import { useState, useEffect } from 'react'
import { Card, Button, Table, Tag, Space, Typography, Select, message, Steps } from 'antd'
import { BulbOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { strategyApi, screenerApi } from '../api/client'

const { Title, Text } = Typography

const planSteps = [
  { title: '选股', description: '运行选股模型' },
  { title: '预方案', description: '勾选心水标的' },
  { title: '预测', description: 'Kronos预测验证' },
  { title: '回测', description: '历史回测验证' },
  { title: '确认', description: '生成报告+量化策略' },
  { title: '执行', description: '模拟/实盘交易' },
]

export default function Strategy() {
  const [plans, setPlans] = useState<any[]>([])
  const [currentStep, setCurrentStep] = useState(0)
  const [templates, setTemplates] = useState<any[]>([])
  const [template, setTemplate] = useState('balanced')

  useEffect(() => {
    strategyApi.getTemplates().then(r => setTemplates(r.data.templates || [])).catch(() => {})
  }, [])

  const generatePlan = async () => {
    message.info('方案生成需要先运行选股。请前往"智能选股"页面获取 picks。')
  }

  const planColumns = [
    { title: '方案ID', dataIndex: 'plan_id', width: 120 },
    { title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => <Tag color={v === 'confirmed' ? 'green' : v === 'draft' ? 'blue' : 'orange'}>{v}</Tag> },
    { title: '标的数', dataIndex: 'picks_count', width: 60 },
    { title: '资金', dataIndex: 'capital', width: 100, render: (v: number) => v ? `¥${(v / 10000).toFixed(0)}万` : '--' },
    { title: '操作', dataIndex: 'status', width: 160, render: (_: string, r: any) => (
      <Space>
        {r.status === 'draft' && <Button size="small" type="primary">预测验证</Button>}
        {r.status === 'confirmed' && <Button size="small">启动交易</Button>}
      </Space>
    )},
  ]

  return (
    <div>
      <Title level={2}><BulbOutlined /> 方案管理</Title>

      <Card>
        <Steps current={currentStep} size="small" items={planSteps} onChange={setCurrentStep}
               style={{ cursor: 'pointer' }} />
      </Card>

      <Card title="新建方案" style={{ marginTop: 16 }}>
        <Space>
          <Select value={template} onChange={setTemplate} style={{ width: 200 }} options={
            templates.map((t: any) => ({ label: `${t.name} (单票上限${t.single_max * 100}%)`, value: t.id }))
          } />
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={generatePlan}>
            生成方案
          </Button>
        </Space>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary">
            方案生命周期: 草稿 → 预测验证 → 回测验证 → 确认方案 → 生成报告 → 执行交易
          </Text>
        </div>
      </Card>

      <Card title="方案列表" style={{ marginTop: 16 }}>
        <Table columns={planColumns} dataSource={plans} rowKey="plan_id" size="small"
               locale={{ emptyText: '暂无方案。请先运行选股生成 picks，再创建方案。' }} />
      </Card>
    </div>
  )
}
