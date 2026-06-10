import { useState, useEffect, useCallback } from 'react'
import {
  Card, Button, Table, Tag, Typography, Space, message, Modal, Form,
  Input, InputNumber, Select, Switch, Radio, Row, Col, Statistic,
  Timeline, Badge, Popconfirm, Tooltip, Drawer, Divider, Empty,
} from 'antd'
import {
  RobotOutlined, PlusOutlined, PlayCircleOutlined, PauseCircleOutlined,
  StopOutlined, ReloadOutlined, DeleteOutlined, EditOutlined,
  SettingOutlined, RiseOutlined, FallOutlined, ClockCircleOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined, InfoCircleOutlined,
  BarChartOutlined, StockOutlined, FundOutlined, WalletOutlined,
  ThunderboltOutlined, LineChartOutlined, ArrowUpOutlined, ArrowDownOutlined,
  BellOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

const { Title, Text } = Typography

// ── Types ──

interface Condition {
  id: string
  enabled: boolean
  indicator: string
  operator: string
  value: number
  period?: number
}

interface RiskRule {
  id: string
  enabled: boolean
  rule_type: string
  value: number
}

interface QuantStrategy {
  id: string
  name: string
  plan_id?: string
  plan_name: string
  status: 'running' | 'paused' | 'terminated' | 'completed'
  pnl: number
  pnl_pct: number
  execution_mode: 'full_auto' | 'semi_auto'
  current_positions: { code: string; name: string; volume: number; cost: number; price: number; pnl: number }[]
  next_rebalance_at?: string
  today_return: number
  today_return_pct: number
  created_at: string
  buy_conditions: Condition[]
  sell_conditions: Condition[]
  risk_rules: RiskRule[]
  max_position_pct: number
  max_single_pct: number
}

interface LogEntry {
  id: string
  time: string
  action: string
  detail: string
  level: 'info' | 'success' | 'warning' | 'error'
}

// ── Constants ──

const statusConfig: Record<string, { color: string; label: string; icon: string }> = {
  running:   { color: 'green',  label: '运行中', icon: '🟢' },
  paused:    { color: 'gold',   label: '暂停',   icon: '🟡' },
  terminated:{ color: 'red',    label: '已终止', icon: '🔴' },
  completed: { color: 'blue',   label: '已完成', icon: '🔵' },
}

const indicatorOptions = [
  { label: 'MA 均线', value: 'MA' },
  { label: 'EMA 指数均线', value: 'EMA' },
  { label: 'MACD', value: 'MACD' },
  { label: 'RSI 相对强弱', value: 'RSI' },
  { label: 'KDJ 随机指标', value: 'KDJ' },
  { label: 'BOLL 布林带', value: 'BOLL' },
  { label: 'VOL 成交量', value: 'VOL' },
  { label: 'OBV 能量潮', value: 'OBV' },
]

const operatorOptions = [
  { label: '大于 >', value: '>' },
  { label: '小于 <', value: '<' },
  { label: '大于等于 >=', value: '>=' },
  { label: '小于等于 <=', value: '<=' },
  { label: '上穿', value: 'cross_above' },
  { label: '下穿', value: 'cross_below' },
]

const riskRuleOptions = [
  { label: '单日最大亏损', value: 'max_daily_loss' },
  { label: '总回撤上限', value: 'max_drawdown' },
  { label: '连续止损次数', value: 'max_consecutive_stops' },
  { label: '最低现金比例', value: 'min_cash_ratio' },
]

// ── Helpers ──

function makeId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function emptyCondition(): Condition {
  return { id: makeId(), enabled: false, indicator: 'MA', operator: '>', value: 0, period: 20 }
}

function emptyRiskRule(): RiskRule {
  return { id: makeId(), enabled: false, rule_type: 'max_daily_loss', value: 0 }
}

function countdownText(iso?: string): string {
  if (!iso) return '--'
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return '即将调仓'
  const m = Math.floor(diff / 60000)
  const s = Math.floor((diff % 60000) / 1000)
  return `${m}分${s}秒`
}

// ── Component ──

export default function AutoTrade() {
  const [strategies, setStrategies] = useState<QuantStrategy[]>([])
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingStrategy, setEditingStrategy] = useState<QuantStrategy | null>(null)
  const [detailStrategy, setDetailStrategy] = useState<QuantStrategy | null>(null)
  const [logEntries, setLogEntries] = useState<LogEntry[]>([])
  const [logsLoading, setLogsLoading] = useState(false)
  const [form] = Form.useForm()

  // ── Fetch strategies ──
  const loadStrategies = useCallback(() => {
    setLoading(true)
    fetch('/api/v1/auto-trade/strategies')
      .then(r => r.json())
      .then(d => setStrategies(d.strategies || []))
      .catch(() => message.error('加载策略列表失败'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadStrategies() }, [loadStrategies])

  // ── Fetch logs for detail ──
  const loadLogs = (strategyId: string) => {
    setLogsLoading(true)
    fetch(`/api/v1/auto-trade/strategies/${strategyId}/logs`)
      .then(r => r.json())
      .then(d => setLogEntries(d.logs || []))
      .catch(() => setLogEntries([]))
      .finally(() => setLogsLoading(false))
  }

  // ── Open drawer for new/edit ──
  const openCreate = () => {
    setEditingStrategy(null)
    form.resetFields()
    form.setFieldsValue({
      execution_mode: 'semi_auto',
      max_position_pct: 80,
      max_single_pct: 20,
      buy_conditions: [emptyCondition()],
      sell_conditions: [emptyCondition()],
      risk_rules: [emptyRiskRule()],
    })
    setDrawerOpen(true)
  }

  const openEdit = (s: QuantStrategy) => {
    setEditingStrategy(s)
    form.setFieldsValue({
      name: s.name,
      plan_id: s.plan_id,
      execution_mode: s.execution_mode,
      max_position_pct: s.max_position_pct,
      max_single_pct: s.max_single_pct,
      buy_conditions: s.buy_conditions.length > 0 ? s.buy_conditions : [emptyCondition()],
      sell_conditions: s.sell_conditions.length > 0 ? s.sell_conditions : [emptyCondition()],
      risk_rules: s.risk_rules.length > 0 ? s.risk_rules : [emptyRiskRule()],
    })
    setDrawerOpen(true)
  }

  // ── Submit form ──
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const url = editingStrategy
        ? `/api/v1/auto-trade/strategies/${editingStrategy.id}`
        : '/api/v1/auto-trade/strategies'
      const method = editingStrategy ? 'PUT' : 'POST'
      const r = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      if (r.ok) {
        message.success(editingStrategy ? '策略已更新' : '策略已创建')
        setDrawerOpen(false)
        loadStrategies()
      } else {
        const err = await r.json().catch(() => ({ detail: '保存失败' }))
        message.error(err.detail || '保存失败')
      }
    } catch {
      // validation error handled by antd
    }
  }

  // ── Strategy actions ──
  const actionStrategy = async (id: string, action: string) => {
    try {
      const r = await fetch(`/api/v1/auto-trade/strategies/${id}/${action}`, { method: 'POST' })
      if (r.ok) {
        message.success(`策略已${action === 'start' ? '启动' : action === 'pause' ? '暂停' : action === 'resume' ? '恢复' : '终止'}`)
        loadStrategies()
      } else {
        const err = await r.json().catch(() => ({ detail: '操作失败' }))
        message.error(err.detail || '操作失败')
      }
    } catch {
      message.error('操作失败')
    }
  }

  const deleteStrategy = async (id: string) => {
    await fetch(`/api/v1/auto-trade/strategies/${id}`, { method: 'DELETE' })
    message.success('策略已删除')
    loadStrategies()
  }

  const viewDetail = async (id: string) => {
    setLoading(true)
    try {
      const r = await fetch(`/api/v1/auto-trade/strategies/${id}`)
      if (r.ok) {
        const d = await r.json()
        setDetailStrategy(d)
        loadLogs(id)
      }
    } catch { message.error('加载详情失败') }
    finally { setLoading(false) }
  }

  // ── Countdown timer ──
  const [, setTick] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  // ── Table columns ──
  const columns: ColumnsType<QuantStrategy> = [
    {
      title: '策略名称', dataIndex: 'name', width: 160,
      render: (v: string, r) => (
        <Space direction="vertical" size={0}>
          <Text strong style={{ cursor: 'pointer' }} onClick={() => viewDetail(r.id)}>{v}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.id?.slice(0, 12)}</Text>
        </Space>
      ),
    },
    {
      title: '关联方案', dataIndex: 'plan_name', width: 120,
      render: (v: string) => v ? <Tag color="blue">{v}</Tag> : <Tag>自定义</Tag>,
    },
    {
      title: '执行模式', dataIndex: 'execution_mode', width: 100,
      render: (v: string) => (
        <Tag color={v === 'full_auto' ? 'green' : 'orange'}>
          {v === 'full_auto' ? '全自动' : '半自动'}
        </Tag>
      ),
    },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => {
        const cfg = statusConfig[v] || { color: 'default', label: v, icon: '' }
        return <Tag color={cfg.color}>{cfg.icon} {cfg.label}</Tag>
      },
    },
    {
      title: '累计盈亏', dataIndex: 'pnl', width: 120,
      render: (v: number, r) => (
        <Space direction="vertical" size={0}>
          <Text style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f', fontWeight: 600 }}>
            {v >= 0 ? '+' : ''}¥{v.toLocaleString()}
          </Text>
          <Text style={{ fontSize: 11, color: r.pnl_pct >= 0 ? '#52c41a' : '#ff4d4f' }}>
            {r.pnl_pct >= 0 ? '+' : ''}{r.pnl_pct?.toFixed(2)}%
          </Text>
        </Space>
      ),
    },
    {
      title: '今日收益', dataIndex: 'today_return', width: 120,
      render: (v: number, r) => (
        <Space direction="vertical" size={0}>
          <Text style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f', fontWeight: 600 }}>
            {v >= 0 ? '+' : ''}¥{v.toLocaleString()}
          </Text>
          <Text style={{ fontSize: 11, color: r.today_return_pct >= 0 ? '#52c41a' : '#ff4d4f' }}>
            {r.today_return_pct >= 0 ? '+' : ''}{r.today_return_pct?.toFixed(2)}%
          </Text>
        </Space>
      ),
    },
    {
      title: '下次调仓', dataIndex: 'next_rebalance_at', width: 110,
      render: (v: string) => (
        <Space><ClockCircleOutlined /><Text style={{ fontSize: 12 }}>{countdownText(v)}</Text></Space>
      ),
    },
    {
      title: '操作', dataIndex: 'id', width: 240, fixed: 'right',
      render: (id: string, record: QuantStrategy) => (
        <Space size="small" wrap>
          {record.status === 'paused' && (
            <Tooltip title="启动">
              <Button size="small" type="primary" icon={<PlayCircleOutlined />}
                      onClick={() => actionStrategy(id, 'start')} />
            </Tooltip>
          )}
          {record.status === 'running' && (
            <Tooltip title="暂停">
              <Button size="small" icon={<PauseCircleOutlined />}
                      onClick={() => actionStrategy(id, 'pause')} />
            </Tooltip>
          )}
          {(record.status === 'paused' || record.status === 'running') && (
            <Tooltip title="终止">
              <Popconfirm title="确定终止此策略?" onConfirm={() => actionStrategy(id, 'stop')}>
                <Button size="small" danger icon={<StopOutlined />} />
              </Popconfirm>
            </Tooltip>
          )}
          {(record.status === 'terminated' || record.status === 'completed') && (
            <Tooltip title="重新启动">
              <Button size="small" icon={<ReloadOutlined />}
                      onClick={() => actionStrategy(id, 'start')} />
            </Tooltip>
          )}
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Popconfirm title="确定删除?" onConfirm={() => deleteStrategy(id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
          <Button size="small" type="link" onClick={() => viewDetail(id)}>详情</Button>
        </Space>
      ),
    },
  ]

  // ── Render ──

  return (
    <div>
      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <RobotOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          量化交易
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadStrategies} loading={loading}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建策略
          </Button>
        </Space>
      </div>

      {/* ── Strategy Table ── */}
      <Card
        title={<Space><SettingOutlined />策略列表 ({strategies.length})</Space>}
        style={{ borderRadius: 8, marginBottom: 16 }}
      >
        <Table
          columns={columns}
          dataSource={strategies}
          rowKey="id"
          size="small"
          loading={loading}
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: '暂无量化策略，点击"新建策略"创建或从方案管理页面生成。' }}
        />
      </Card>

      {/* ── Strategy Detail Drawer ── */}
      <Drawer
        title={detailStrategy ? `策略详情: ${detailStrategy.name}` : '策略详情'}
        open={!!detailStrategy}
        onClose={() => setDetailStrategy(null)}
        width={720}
        extra={
          detailStrategy && (
            <Space>
              {(detailStrategy.status === 'running' || detailStrategy.status === 'paused') && (
                <>
                  {detailStrategy.status === 'running' ? (
                    <Button icon={<PauseCircleOutlined />}
                            onClick={() => { actionStrategy(detailStrategy.id, 'pause'); setDetailStrategy(null) }}>
                      暂停
                    </Button>
                  ) : (
                    <Button icon={<PlayCircleOutlined />}
                            onClick={() => { actionStrategy(detailStrategy.id, 'resume'); setDetailStrategy(null) }}>
                      恢复
                    </Button>
                  )}
                  <Popconfirm title="确定终止?" onConfirm={() => { actionStrategy(detailStrategy.id, 'stop'); setDetailStrategy(null) }}>
                    <Button danger icon={<StopOutlined />}>终止</Button>
                  </Popconfirm>
                </>
              )}
            </Space>
          )
        }
      >
        {detailStrategy && (
          <>
            {/* Status badge */}
            <div style={{ marginBottom: 16 }}>
              {(() => {
                const cfg = statusConfig[detailStrategy.status]
                return <Tag color={cfg?.color} style={{ fontSize: 14, padding: '4px 12px' }}>{cfg?.icon} {cfg?.label}</Tag>
              })()}
              <Tag color={detailStrategy.execution_mode === 'full_auto' ? 'green' : 'orange'} style={{ fontSize: 14, padding: '4px 12px' }}>
                {detailStrategy.execution_mode === 'full_auto' ? '全自动执行' : '半自动(信号提醒+手动确认)'}
              </Tag>
            </div>

            {/* KPI cards */}
            <Row gutter={12} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Card size="small" style={{ borderRadius: 8 }}>
                  <Statistic
                    title="累计盈亏"
                    value={detailStrategy.pnl}
                    precision={0}
                    prefix="¥"
                    valueStyle={{ color: detailStrategy.pnl >= 0 ? '#52c41a' : '#ff4d4f', fontSize: 20 }}
                    suffix={<span style={{ fontSize: 13 }}>({detailStrategy.pnl_pct >= 0 ? '+' : ''}{detailStrategy.pnl_pct?.toFixed(2)}%)</span>}
                  />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ borderRadius: 8 }}>
                  <Statistic
                    title="今日收益"
                    value={detailStrategy.today_return}
                    precision={0}
                    prefix="¥"
                    valueStyle={{ color: detailStrategy.today_return >= 0 ? '#52c41a' : '#ff4d4f', fontSize: 20 }}
                    suffix={<span style={{ fontSize: 13 }}>({detailStrategy.today_return_pct >= 0 ? '+' : ''}{detailStrategy.today_return_pct?.toFixed(2)}%)</span>}
                  />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ borderRadius: 8 }}>
                  <Statistic
                    title="下次调仓"
                    value={countdownText(detailStrategy.next_rebalance_at)}
                    prefix={<ClockCircleOutlined />}
                    valueStyle={{ fontSize: 20 }}
                  />
                </Card>
              </Col>
            </Row>

            {/* Current positions */}
            <Card title={<Space><WalletOutlined />当前持仓</Space>} size="small" style={{ borderRadius: 8, marginBottom: 16 }}>
              {detailStrategy.current_positions?.length > 0 ? (
                <Table
                  dataSource={detailStrategy.current_positions}
                  rowKey="code"
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '代码', dataIndex: 'code', width: 80 },
                    { title: '名称', dataIndex: 'name', width: 100 },
                    { title: '数量', dataIndex: 'volume', width: 70 },
                    { title: '成本', dataIndex: 'cost', width: 80, render: (v: number) => `¥${v?.toFixed(2)}` },
                    { title: '现价', dataIndex: 'price', width: 80, render: (v: number) => `¥${v?.toFixed(2)}` },
                    {
                      title: '盈亏', dataIndex: 'pnl', width: 80,
                      render: (v: number) => (
                        <Text style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f' }}>
                          {v >= 0 ? '+' : ''}¥{v?.toLocaleString()}
                        </Text>
                      ),
                    },
                  ]}
                />
              ) : (
                <Empty description="暂无持仓" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>

            {/* Strategy log timeline */}
            <Card title={<Space><LineChartOutlined />策略日志</Space>} size="small" style={{ borderRadius: 8 }} loading={logsLoading}>
              {logEntries.length > 0 ? (
                <Timeline
                  items={logEntries.map(log => {
                    const levelIcons: Record<string, React.ReactNode> = {
                      info: <InfoCircleOutlined style={{ color: '#1677ff' }} />,
                      success: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
                      warning: <ExclamationCircleOutlined style={{ color: '#faad14' }} />,
                      error: <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />,
                    }
                    return {
                      dot: levelIcons[log.level] || levelIcons.info,
                      children: (
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                            <Text strong style={{ fontSize: 13 }}>{log.action}</Text>
                            <Text type="secondary" style={{ fontSize: 11 }}>{log.time?.slice(0, 19)}</Text>
                          </div>
                          <Text style={{ fontSize: 12 }}>{log.detail}</Text>
                        </div>
                      ),
                    }
                  })}
                />
              ) : (
                <Empty description="暂无日志" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </>
        )}
      </Drawer>

      {/* ── Create / Edit Strategy Drawer ── */}
      <Drawer
        title={editingStrategy ? '编辑策略' : '新建量化策略'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={640}
        footer={
          <Space style={{ float: 'right' }}>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" onClick={handleSubmit}>
              {editingStrategy ? '保存修改' : '创建策略'}
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical" size="small">
          <Divider orientation="left" plain>基本信息</Divider>

          <Form.Item label="策略名称" name="name" rules={[{ required: true, message: '请输入策略名称' }]}>
            <Input placeholder="例如: 均线金叉策略" />
          </Form.Item>

          <Form.Item label="执行模式" name="execution_mode" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio.Button value="full_auto">
                <Space><RobotOutlined />全自动</Space>
              </Radio.Button>
              <Radio.Button value="semi_auto">
                <Space><BellOutlined />半自动 (信号提醒+手动确认)</Space>
              </Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item label="最大总仓位 (%)" name="max_position_pct">
            <InputNumber min={0} max={100} style={{ width: '100%' }} addonAfter="%" />
          </Form.Item>

          <Form.Item label="单票最大仓位 (%)" name="max_single_pct">
            <InputNumber min={0} max={100} style={{ width: '100%' }} addonAfter="%" />
          </Form.Item>

          {/* ── Buy Conditions ── */}
          <Divider orientation="left" plain>
            <ThunderboltOutlined style={{ marginRight: 6 }} />买入条件
          </Divider>
          <Form.List name="buy_conditions">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Card
                    key={key}
                    size="small"
                    style={{ marginBottom: 8, borderRadius: 8, background: '#fafafa' }}
                    extra={
                      fields.length > 1 && (
                        <Button type="link" danger size="small" onClick={() => remove(name)}>删除</Button>
                      )
                    }
                  >
                    <Row gutter={8} align="middle">
                      <Col flex="50px">
                        <Form.Item name={[name, 'enabled']} valuePropName="checked" style={{ marginBottom: 0 }}>
                          <Switch size="small" />
                        </Form.Item>
                      </Col>
                      <Col flex="auto">
                        <Form.Item name={[name, 'indicator']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={indicatorOptions} placeholder="指标" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'operator']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={operatorOptions} placeholder="运算符" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'value']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <InputNumber style={{ width: '100%' }} placeholder="数值" />
                        </Form.Item>
                      </Col>
                      <Col flex="60px">
                        <Form.Item name={[name, 'period']} style={{ marginBottom: 0 }}>
                          <InputNumber style={{ width: '100%' }} placeholder="周期" min={1} max={250} />
                        </Form.Item>
                      </Col>
                    </Row>
                  </Card>
                ))}
                <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add(emptyCondition())}>
                  添加买入条件
                </Button>
              </>
            )}
          </Form.List>

          {/* ── Sell Conditions ── */}
          <Divider orientation="left" plain>
            <FallOutlined style={{ marginRight: 6 }} />卖出条件
          </Divider>
          <Form.List name="sell_conditions">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Card
                    key={key}
                    size="small"
                    style={{ marginBottom: 8, borderRadius: 8, background: '#fafafa' }}
                    extra={
                      fields.length > 1 && (
                        <Button type="link" danger size="small" onClick={() => remove(name)}>删除</Button>
                      )
                    }
                  >
                    <Row gutter={8} align="middle">
                      <Col flex="50px">
                        <Form.Item name={[name, 'enabled']} valuePropName="checked" style={{ marginBottom: 0 }}>
                          <Switch size="small" />
                        </Form.Item>
                      </Col>
                      <Col flex="auto">
                        <Form.Item name={[name, 'indicator']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={indicatorOptions} placeholder="指标" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'operator']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={operatorOptions} placeholder="运算符" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'value']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <InputNumber style={{ width: '100%' }} placeholder="数值" />
                        </Form.Item>
                      </Col>
                      <Col flex="60px">
                        <Form.Item name={[name, 'period']} style={{ marginBottom: 0 }}>
                          <InputNumber style={{ width: '100%' }} placeholder="周期" min={1} max={250} />
                        </Form.Item>
                      </Col>
                    </Row>
                  </Card>
                ))}
                <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add(emptyCondition())}>
                  添加卖出条件
                </Button>
              </>
            )}
          </Form.List>

          {/* ── Risk Rules ── */}
          <Divider orientation="left" plain>
            <ExclamationCircleOutlined style={{ marginRight: 6 }} />风控规则
          </Divider>
          <Form.List name="risk_rules">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Card
                    key={key}
                    size="small"
                    style={{ marginBottom: 8, borderRadius: 8, background: '#fafafa' }}
                    extra={
                      fields.length > 1 && (
                        <Button type="link" danger size="small" onClick={() => remove(name)}>删除</Button>
                      )
                    }
                  >
                    <Row gutter={8} align="middle">
                      <Col flex="50px">
                        <Form.Item name={[name, 'enabled']} valuePropName="checked" style={{ marginBottom: 0 }}>
                          <Switch size="small" />
                        </Form.Item>
                      </Col>
                      <Col flex="auto">
                        <Form.Item name={[name, 'rule_type']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={riskRuleOptions} placeholder="规则类型" />
                        </Form.Item>
                      </Col>
                      <Col flex="180px">
                        <Form.Item name={[name, 'value']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <InputNumber style={{ width: '100%' }} placeholder="阈值" />
                        </Form.Item>
                      </Col>
                    </Row>
                  </Card>
                ))}
                <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add(emptyRiskRule())}>
                  添加风控规则
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Drawer>
    </div>
  )
}
