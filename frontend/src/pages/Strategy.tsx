import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Button, Steps, Space, Typography, Tag, message, Table, Modal, Descriptions, List, Row, Col } from 'antd'
import { BulbOutlined, PlayCircleOutlined, FileTextOutlined, DeleteOutlined, CheckCircleOutlined, EyeOutlined, FundOutlined, ExperimentOutlined, RobotOutlined, ThunderboltOutlined, SafetyOutlined, BankOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

// ── Types ──

interface PlanPick {
  code: string
  name: string
  price: number
  score: number
  grade: string
  entry_price?: number
  stop_loss?: number
  target_price?: number
}

interface Plan {
  id: string
  name: string
  status: string
  picks_count: number
  model_name: string
  capital: number
  max_positions: number
  single_max_pct: number
  picks: PlanPick[]
  created_at: string
  updated_at: string
}

interface PlanReport {
  title: string
  generated_at: string
  plan: { id: string; name: string; model: string; capital: number; max_positions: number }
  picks: Array<{
    code: string; name: string; price: number; score: number; grade: string
    entry_price?: number; stop_loss?: number; target_price?: number
    operation?: { entry_price: number; stop_loss: number; target_price: number; position_pct: number }
  }>
  quant_strategy?: { buy_conditions: string[]; sell_conditions: string[]; execution_mode: string }
  risk_warnings?: string[]
}

interface StrategyTemplate {
  id: string
  name: string
  risk: string
  max_positions: number
  single_max: number
}

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
  const navigate = useNavigate()
  const [plans, setPlans] = useState<Plan[]>([])
  const [templates, setTemplates] = useState<StrategyTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [detailPlan, setDetailPlan] = useState<Plan | null>(null)
  const [report, setReport] = useState<PlanReport | null>(null)

  const loadPlans = () => {
    setLoading(true)
    fetch('/api/v1/strategy/plans').then(r => r.json()).then(d => {
      setPlans(d.plans || d.items || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  const loadTemplates = () => {
    fetch('/api/v1/strategy/templates').then(r => r.json()).then(d => {
      setTemplates(d.templates || [])
    }).catch(() => {})
  }

  const createFromTemplate = async (template: StrategyTemplate) => {
    setCreating(true)
    try {
      const r = await fetch('/api/v1/strategy/plans', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: `${template.name}方案-${Date.now().toString(36)}`,
          model: 'template',
          capital: 1000000,
          max_positions: template.max_positions || 5,
          single_max_pct: template.single_max || 0.2,
          risk: template.risk || 'medium',
        }),
      })
      if (r.ok) {
        message.success(`已基于"${template.name}"创建方案`)
        loadPlans()
      } else {
        const err = await r.json().catch(() => ({}))
        message.error(err.detail || '创建失败')
      }
    } catch {
      message.error('策略服务未连接')
    } finally { setCreating(false) }
  }

  useEffect(() => { loadPlans(); loadTemplates() }, [])

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
    if (r.ok) {
      setDetailPlan(await r.json())
    } else {
      message.error('方案不存在或已被删除')
    }
  }

  const viewReport = async (id: string) => {
    const r = await fetch(`/api/v1/strategy/plans/${id}/report`)
    if (r.ok) {
      const data = await r.json()
      if (data.title) setReport(data)
    } else {
      message.error('报告生成失败，请先确认方案')
    }
  }

  const runBacktestOnPlan = async (id: string) => {
    message.loading('回测运行中...')
    try {
      await fetch(`/api/v1/backtest/run?mode=all`, { method: 'POST' })
      message.success('回测完成, 请查看回测分析页面')
    } catch { message.error('回测服务未连接') }
  }

  const generateQuantStrategy = async (id: string) => {
    message.loading('正在生成量化策略...')
    try {
      const r = await fetch(`/api/v1/strategy/generate-from-scheme/${id}`, { method: 'POST' })
      if (r.ok) {
        message.success('量化策略生成成功')
        navigate('/auto-trade')
      } else {
        const err = await r.json().catch(() => ({ detail: '生成失败' }))
        message.error(err.detail || '生成失败')
      }
    } catch {
      message.error('策略服务未连接')
    }
  }

  const columns = [
    { title: '方案ID', dataIndex: 'id', width: 140, render: (v: string) => <Text code style={{fontSize:11}}>{v}</Text> },
    { title: '名称', dataIndex: 'name', width: 160 },
    { title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => <Tag color={statusColors[v] || 'default'}>{v}</Tag> },
    { title: '标的数', dataIndex: 'picks_count', width: 60 },
    { title: '资金', dataIndex: 'capital', width: 90, render: (v: number) => `¥${(v/10000).toFixed(0)}万` },
    { title: '创建时间', dataIndex: 'created_at', width: 110, render: (v: string) => v?.slice(0,16) },
    { title: '操作', dataIndex: 'id', width: 280, render: (id: string, record: Plan) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => viewPlan(id)}>查看</Button>
        {record.status === 'draft' && (
          <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => confirmPlan(id)}>确认</Button>
        )}
        {record.status === 'confirmed' && (
          <>
            <Button size="small" icon={<FundOutlined />} onClick={() => viewReport(id)}>报告</Button>
            <Button size="small" icon={<ExperimentOutlined />} onClick={() => runBacktestOnPlan(id)}>回测</Button>
            <Button size="small" type="primary" icon={<RobotOutlined />} onClick={() => generateQuantStrategy(id)}>量化策略</Button>
          </>
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
        <Steps current={plans.length > 0 ? 2 : 0} size="small" items={planSteps} />
      </Card>

      <Card
        title={<Space><ThunderboltOutlined style={{color:'#fa8c16'}} />预设策略模板</Space>}
        style={{ borderRadius: 8, marginBottom: 16 }}
        styles={{ body: { padding: '16px 24px' } }}
      >
        <Row gutter={16}>
          {templates.map((tpl: StrategyTemplate) => {
            const icons: Record<string, React.ReactNode> = { aggressive: <ThunderboltOutlined />, balanced: <SafetyOutlined />, conservative: <BankOutlined /> }
            const colors: Record<string, string> = { aggressive: '#ff4d4f', balanced: '#1677ff', conservative: '#52c41a' }
            const descs: Record<string, string> = {
              aggressive: '高收益高风险，最多3只标的，单票上限20%',
              balanced: '收益风险均衡，最多5只标的，单票上限12%',
              conservative: '稳健低风险，最多8只标的，单票上限8%',
            }
            return (
              <Col span={8} key={tpl.id}>
                <Card
                  hoverable
                  size="small"
                  style={{ borderRadius: 8, borderTop: `3px solid ${colors[tpl.id] || '#1677ff'}` }}
                  onClick={() => createFromTemplate(tpl)}
                >
                  <Space direction="vertical" size={4} style={{width:'100%'}}>
                    <Space>
                      <span style={{fontSize:20, color: colors[tpl.id]}}>{icons[tpl.id]}</span>
                      <Text strong style={{fontSize:16}}>{tpl.name}</Text>
                      <Tag color={colors[tpl.id]} style={{margin:0}}>{tpl.risk === 'high' ? '高风险' : tpl.risk === 'medium' ? '中风险' : '低风险'}</Tag>
                    </Space>
                    <Text type="secondary" style={{fontSize:12}}>{descs[tpl.id] || '自定义策略模板'}</Text>
                    <Button type="link" size="small" loading={creating} style={{padding:0}}>使用此模板 →</Button>
                  </Space>
                </Card>
              </Col>
            )
          })}
          {templates.length === 0 && (
            <Col span={24}><Text type="secondary">模板加载中...</Text></Col>
          )}
        </Row>
      </Card>

      <Card title={<Space><FileTextOutlined />我的方案 ({plans.length})</Space>}
            style={{ borderRadius: 8 }}
            extra={<Button icon={<PlayCircleOutlined />} onClick={loadPlans} loading={loading}>刷新</Button>}>
        <Table columns={columns} dataSource={plans} rowKey="id" size="small"
               pagination={{ pageSize: 10 }}
               locale={{ emptyText: '暂无方案。请在智能选股页面运行选股后，勾选标的生成预方案。' }} />
      </Card>

      <Modal title="选股报告" open={!!report} onCancel={() => setReport(null)} footer={null} width={700}>
        {report && (
          <>
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 12 }}>
              <Descriptions.Item label="方案">{report.plan?.name}</Descriptions.Item>
              <Descriptions.Item label="模型">{report.plan?.model}</Descriptions.Item>
              <Descriptions.Item label="资金">¥{(report.plan?.capital/10000).toFixed(0)}万</Descriptions.Item>
              <Descriptions.Item label="最大持仓">{report.plan?.max_positions}只</Descriptions.Item>
            </Descriptions>
            <Typography.Title level={5}>推荐标的</Typography.Title>
            <List size="small" dataSource={report.picks || []} renderItem={(p: PlanReport['picks'][number]) => (
              <List.Item>
                <Space direction="vertical" size={0}>
                  <Space><Tag color="blue">{p.code}</Tag><Text strong>{p.name}</Text><Tag>{p.grade}级</Tag></Space>
                  <Text type="secondary" style={{fontSize:12}}>
                    入场:{p.operation?.entry_price} | 止损:{p.operation?.stop_loss} | 目标:{p.operation?.target_price} | 仓位:{p.operation?.position_pct}%
                  </Text>
                </Space>
              </List.Item>
            )} />
            <Typography.Title level={5}>量化策略</Typography.Title>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="买入条件">{report.quant_strategy?.buy_conditions?.join(' / ')}</Descriptions.Item>
              <Descriptions.Item label="卖出条件">{report.quant_strategy?.sell_conditions?.join(' / ')}</Descriptions.Item>
              <Descriptions.Item label="执行模式">{report.quant_strategy?.execution_mode}</Descriptions.Item>
            </Descriptions>
            <Typography.Title level={5} style={{marginTop:12}}>风险提示</Typography.Title>
            {report.risk_warnings?.map((w: string) => <Tag key={w} color="orange" style={{marginBottom:4}}>{w}</Tag>)}
          </>
        )}
      </Modal>

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
              {(detailPlan.picks || []).map((p: PlanPick) => (
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
