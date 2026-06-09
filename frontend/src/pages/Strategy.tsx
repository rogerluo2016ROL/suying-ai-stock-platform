import { useState, useEffect } from 'react'
import { Card, Button, Steps, Space, Typography, Tag, message, Select } from 'antd'
import { BulbOutlined, PlayCircleOutlined, FileTextOutlined } from '@ant-design/icons'
import { strategyApi } from '../api/client'

const { Title, Text } = Typography

const planSteps = [
  { title: '选股', description: '运行模型' },
  { title: '预方案', description: '勾选标的' },
  { title: '预测验证', description: 'Kronos预测' },
  { title: '回测验证', description: '历史回测' },
  { title: '确认方案', description: '生成报告' },
  { title: '执行交易', description: '模拟/实盘' },
]

export default function Strategy() {
  const [currentStep, setCurrentStep] = useState(0)
  const [templates, setTemplates] = useState<any[]>([])

  useEffect(() => {
    strategyApi.getTemplates().then(r => setTemplates(r.data.templates || [])).catch(() => {})
  }, [])

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
        <Steps current={currentStep} size="small" items={planSteps} onChange={setCurrentStep}
               style={{ cursor: 'pointer' }} />
      </Card>

      <Card title="新建方案" style={{ borderRadius: 8, marginBottom: 16 }}>
        <Space>
          <Select defaultValue="balanced" style={{ width: 200 }} options={
            templates.map((t: any) => ({ label: `${t.name} (单票${t.single_max * 100}%)`, value: t.id }))
          } />
          <Button type="primary" icon={<PlayCircleOutlined />}
                  onClick={() => message.info('请先在智能选股页面获取 picks')}>
            生成方案
          </Button>
        </Space>
      </Card>

      <Card style={{ borderRadius: 8 }}>
        <div style={{ textAlign: 'center', padding: 40 }}>
          <FileTextOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
          <div style={{ marginTop: 12 }}>
            <Text type="secondary">暂无方案 — 请先运行选股生成标的池，再创建方案</Text>
          </div>
        </div>
      </Card>
    </div>
  )
}
