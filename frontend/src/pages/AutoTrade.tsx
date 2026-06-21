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
import api from '../api/client'

const { Title, Text } = Typography

// ── Types ──

interface Condition {
  id: string
  field: string
  operator: string
  threshold: number
  description: string
}

interface QuantStrategy {
  id: string
  name: string
  description?: string
  status: 'draft' | 'active' | 'paused' | 'stopped' | 'archived'
  source_type?: string
  source_scheme_id?: string
  trade_mode: string
  check_interval_sec: number
  capital: number
  picks_count?: number
  picks?: { code: string; name: string; price?: number }[]
  buy_conditions: Condition[]
  sell_conditions: Condition[]
  position_rules: {
    max_positions: number
    single_max_pct: number
    total_position_cap_pct: number
  }
  risk_rules: {
    daily_max_loss_pct: number
    stop_loss_pct: number
    take_profit_pct: number
    trailing_stop_pct: number
  }
  created_at: string
  updated_at?: string
}

interface LogEntry {
  timestamp: string
  level: string
  message: string
  details: Record<string, unknown>
}

// ── Constants ──

const statusConfig: Record<string, { color: string; label: string; icon: string }> = {
  draft:    { color: 'default', label: '草稿',   icon: '\u{1F4DD}' },
  active:   { color: 'green',   label: '运行中', icon: '\u{1F7E2}' },
  paused:   { color: 'gold',    label: '已暂停', icon: '\u{1F7E1}' },
  stopped:  { color: 'red',     label: '已停止', icon: '\u{1F534}' },
  archived: { color: 'blue',    label: '已归档', icon: '\u{1F535}' },
}

const fieldOptions = [
  { label: '信号强度', value: 'signal_strength' },
  { label: 'Kronos 预测收益', value: 'kronos_return' },
  { label: '因子共振数', value: 'factor_resonance' },
  { label: 'Kronos 趋势', value: 'kronos_trend' },
  { label: '止损触发', value: 'stop_loss' },
  { label: '止盈触发', value: 'take_profit' },
  { label: 'MACD 金叉', value: 'macd_cross' },
  { label: 'KDJ 超卖', value: 'kdj_oversold' },
]

const operatorOptions = [
  { label: '大于 >', value: '>' },
  { label: '小于 <', value: '<' },
  { label: '大于等于 >=', value: '>=' },
  { label: '小于等于 <=', value: '<=' },
  { label: '等于 ==', value: '==' },
  { label: '上穿', value: 'cross_above' },
  { label: '下穿', value: 'cross_below' },
]

// ── Helpers ──

function makeId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function emptyCondition(): Condition {
  return { id: makeId(), field: 'signal_strength', operator: '>=', threshold: 60, description: '' }
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
    api.get('/strategy/list')
      .then(({ data: d }) => setStrategies(d.strategies || []))
      .catch(() => message.error('加载策略列表失败'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadStrategies() }, [loadStrategies])

  // ── Fetch logs for detail ──
  const loadLogs = (strategyId: string) => {
    setLogsLoading(true)
    api.get(`/strategy/${strategyId}/log`)
      .then(({ data: d }) => setLogEntries(d.logs || []))
      .catch(() => setLogEntries([]))
      .finally(() => setLogsLoading(false))
  }

  // ── Open drawer for new/edit ──
  const openCreate = () => {
    setEditingStrategy(null)
    form.resetFields()
    form.setFieldsValue({
      trade_mode: 'paper',
      check_interval_sec: 300,
      capital: 1000000,
      position_rules: {
        max_positions: 5,
        single_max_pct: 20,
        total_position_cap_pct: 80,
      },
      risk_rules: {
        daily_max_loss_pct: 3,
        stop_loss_pct: 3,
        take_profit_pct: 15,
        trailing_stop_pct: 0,
      },
      buy_conditions: [emptyCondition()],
      sell_conditions: [emptyCondition()],
      picks: [],
    })
    setDrawerOpen(true)
  }

  const openEdit = (s: QuantStrategy) => {
    setEditingStrategy(s)
    form.setFieldsValue({
      name: s.name,
      description: s.description || '',
      trade_mode: s.trade_mode || 'paper',
      check_interval_sec: s.check_interval_sec || 300,
      capital: s.capital || 1000000,
      position_rules: {
        max_positions: s.position_rules?.max_positions ?? 5,
        single_max_pct: (s.position_rules?.single_max_pct ?? 0.2) * 100,
        total_position_cap_pct: (s.position_rules?.total_position_cap_pct ?? 0.8) * 100,
      },
      risk_rules: {
        daily_max_loss_pct: (s.risk_rules?.daily_max_loss_pct ?? 0.03) * 100,
        stop_loss_pct: (s.risk_rules?.stop_loss_pct ?? 0.03) * 100,
        take_profit_pct: (s.risk_rules?.take_profit_pct ?? 0.15) * 100,
        trailing_stop_pct: (s.risk_rules?.trailing_stop_pct ?? 0) * 100,
      },
      buy_conditions: s.buy_conditions?.length > 0
        ? s.buy_conditions.map(c => ({ ...c, id: c.id || makeId() }))
        : [emptyCondition()],
      sell_conditions: s.sell_conditions?.length > 0
        ? s.sell_conditions.map(c => ({ ...c, id: c.id || makeId() }))
        : [emptyCondition()],
      picks: s.picks || [],
    })
    setDrawerOpen(true)
  }

  // ── Transform form values to API body ──
  const buildApiBody = (values: Record<string, unknown>) => {
    const pr = (values.position_rules as Record<string, number>) || {}
    const rr = (values.risk_rules as Record<string, number>) || {}
    return {
      name: values.name,
      description: (values.description as string) || '',
      buy_conditions: ((values.buy_conditions as Condition[]) || []).map(c => ({
        field: c.field,
        operator: c.operator,
        threshold: c.threshold,
        description: c.description || `${c.field} ${c.operator} ${c.threshold}`,
      })),
      sell_conditions: ((values.sell_conditions as Condition[]) || []).map(c => ({
        field: c.field,
        operator: c.operator,
        threshold: c.threshold,
        description: c.description || `${c.field} ${c.operator} ${c.threshold}`,
      })),
      position_rules: {
        max_positions: pr.max_positions ?? 5,
        single_max_pct: (pr.single_max_pct ?? 20) / 100,
        total_position_cap_pct: (pr.total_position_cap_pct ?? 80) / 100,
      },
      risk_rules: {
        daily_max_loss_pct: (rr.daily_max_loss_pct ?? 3) / 100,
        stop_loss_pct: (rr.stop_loss_pct ?? 3) / 100,
        take_profit_pct: (rr.take_profit_pct ?? 15) / 100,
        trailing_stop_pct: (rr.trailing_stop_pct ?? 0) / 100,
      },
      trade_mode: (values.trade_mode as string) || 'paper',
      check_interval_sec: (values.check_interval_sec as number) || 300,
      capital: (values.capital as number) || 1000000,
      picks: (values.picks as Array<{ code: string; name: string; price?: number }>) || [],
    }
  }

  // ── Submit form ──
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const body = buildApiBody(values)
      try {
        if (editingStrategy) {
          await api.put(`/strategy/${editingStrategy.id}`, body)
          message.success('策略已更新')
        } else {
          await api.post('/strategy/custom', body)
          message.success('策略已创建')
        }
        setDrawerOpen(false)
        loadStrategies()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '保存失败')
      }
    } catch {
      // validation error handled by antd
    }
  }

  // ── Strategy actions ──
  const actionStrategy = async (id: string, action: string) => {
    try {
      await api.post(`/strategy/${id}/${action}`)
      const labels: Record<string, string> = {
        start: '已启动', pause: '已暂停', resume: '已恢复', stop: '已终止',
      }
      message.success(`策略${labels[action] || '操作成功'}`)
      loadStrategies()
    } catch (e: any) {
      message.error(e.response?.data?.detail || '操作失败')
    }
  }

  const deleteStrategy = async (id: string) => {
    await api.delete(`/strategy/${id}`)
    message.success('策略已删除')
    loadStrategies()
  }

  const viewDetail = async (id: string) => {
    setLoading(true)
    try {
      const { data: d } = await api.get(`/strategy/${id}`)
      setDetailStrategy(d)
      loadLogs(id)
    } catch (e: any) { message.error(e.response?.data?.detail || '加载详情失败') }
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
      title: '来源', dataIndex: 'source_type', width: 80,
      render: (v: string) => (
        <Tag color={v === 'scheme' ? 'blue' : 'default'}>
          {v === 'scheme' ? '方案' : '自定义'}
        </Tag>
      ),
    },
    {
      title: '交易模式', dataIndex: 'trade_mode', width: 80,
      render: (v: string) => (
        <Tag color={v === 'live' ? 'red' : 'green'}>
          {v === 'live' ? '实盘' : '模拟'}
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
      title: '资金', dataIndex: 'capital', width: 100,
      render: (v: number) => v ? `¥${(v / 10000).toFixed(0)}万` : '--',
    },
    {
      title: '检查间隔', dataIndex: 'check_interval_sec', width: 90,
      render: (v: number) => v ? `${v}秒` : '--',
    },
    {
      title: '创建时间', dataIndex: 'created_at', width: 130,
      render: (v: string) => v ? v.slice(0, 10) : '--',
    },
    {
      title: '操作', dataIndex: 'id', width: 240, fixed: 'right',
      render: (id: string, record: QuantStrategy) => (
        <Space size="small" wrap>
          {(record.status === 'draft' || record.status === 'paused') && (
            <Tooltip title="启动">
              <Button size="small" type="primary" icon={<PlayCircleOutlined />}
                      onClick={() => actionStrategy(id, 'start')} />
            </Tooltip>
          )}
          {record.status === 'active' && (
            <Tooltip title="暂停">
              <Button size="small" icon={<PauseCircleOutlined />}
                      onClick={() => actionStrategy(id, 'pause')} />
            </Tooltip>
          )}
          {(record.status === 'paused' || record.status === 'active') && (
            <Tooltip title="终止">
              <Popconfirm title="确定终止此策略?" onConfirm={() => actionStrategy(id, 'stop')}>
                <Button size="small" danger icon={<StopOutlined />} />
              </Popconfirm>
            </Tooltip>
          )}
          {(record.status === 'stopped' || record.status === 'archived') && (
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
              {(detailStrategy.status === 'active' || detailStrategy.status === 'paused') && (
                <>
                  {detailStrategy.status === 'active' ? (
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
              <Tag color={detailStrategy.trade_mode === 'live' ? 'red' : 'green'} style={{ fontSize: 14, padding: '4px 12px' }}>
                {detailStrategy.trade_mode === 'live' ? '实盘交易' : '模拟交易 (paper)'}
              </Tag>
            </div>

            {/* KPI cards */}
            <Row gutter={12} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Card size="small" style={{ borderRadius: 8 }}>
                  <Statistic
                    title="初始资金"
                    value={detailStrategy.capital || 0}
                    precision={0}
                    prefix="¥"
                    valueStyle={{ fontSize: 18 }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ borderRadius: 8 }}>
                  <Statistic
                    title="最大持仓"
                    value={detailStrategy.position_rules?.max_positions || 0}
                    precision={0}
                    suffix="只"
                    valueStyle={{ fontSize: 18 }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ borderRadius: 8 }}>
                  <Statistic
                    title="标的数"
                    value={detailStrategy.picks_count ?? detailStrategy.picks?.length ?? 0}
                    precision={0}
                    suffix="只"
                    valueStyle={{ fontSize: 18 }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ borderRadius: 8 }}>
                  <Statistic
                    title="检查间隔"
                    value={detailStrategy.check_interval_sec || 0}
                    precision={0}
                    suffix="秒"
                    valueStyle={{ fontSize: 18 }}
                  />
                </Card>
              </Col>
            </Row>

            {/* Position & Risk Rules */}
            <Row gutter={12} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Card title={<Space><WalletOutlined />仓位规则</Space>} size="small" style={{ borderRadius: 8 }}>
                  <Row gutter={[0, 8]}>
                    <Col span={24}>
                      <Text type="secondary">最大持仓数：</Text>
                      <Text strong>{detailStrategy.position_rules?.max_positions ?? '--'} 只</Text>
                    </Col>
                    <Col span={24}>
                      <Text type="secondary">单票最大仓位：</Text>
                      <Text strong>{((detailStrategy.position_rules?.single_max_pct ?? 0) * 100).toFixed(0)}%</Text>
                    </Col>
                    <Col span={24}>
                      <Text type="secondary">总仓位上限：</Text>
                      <Text strong>{((detailStrategy.position_rules?.total_position_cap_pct ?? 0) * 100).toFixed(0)}%</Text>
                    </Col>
                  </Row>
                </Card>
              </Col>
              <Col span={12}>
                <Card title={<Space><ExclamationCircleOutlined />风控规则</Space>} size="small" style={{ borderRadius: 8 }}>
                  <Row gutter={[0, 8]}>
                    <Col span={24}>
                      <Text type="secondary">日亏损上限：</Text>
                      <Text strong>{((detailStrategy.risk_rules?.daily_max_loss_pct ?? 0) * 100).toFixed(1)}%</Text>
                    </Col>
                    <Col span={24}>
                      <Text type="secondary">止损：</Text>
                      <Text strong>{((detailStrategy.risk_rules?.stop_loss_pct ?? 0) * 100).toFixed(1)}%</Text>
                      <Text type="secondary" style={{ marginLeft: 16 }}>止盈：</Text>
                      <Text strong>{((detailStrategy.risk_rules?.take_profit_pct ?? 0) * 100).toFixed(1)}%</Text>
                    </Col>
                    <Col span={24}>
                      <Text type="secondary">移动止损：</Text>
                      <Text strong>{((detailStrategy.risk_rules?.trailing_stop_pct ?? 0) * 100).toFixed(1)}%</Text>
                    </Col>
                  </Row>
                </Card>
              </Col>
            </Row>

            {/* Strategy log timeline */}
            <Card title={<Space><LineChartOutlined />策略日志</Space>} size="small" style={{ borderRadius: 8 }} loading={logsLoading}>
              {logEntries.length > 0 ? (
                <Timeline
                  items={logEntries.map(log => {
                    const levelIcons: Record<string, React.ReactNode> = {
                      INFO: <InfoCircleOutlined style={{ color: '#1677ff' }} />,
                      BUY: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
                      SELL: <CheckCircleOutlined style={{ color: '#ff4d4f' }} />,
                      WARN: <ExclamationCircleOutlined style={{ color: '#faad14' }} />,
                      ERROR: <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />,
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
                            <Text strong style={{ fontSize: 13 }}>{log.message}</Text>
                            <Text type="secondary" style={{ fontSize: 11 }}>{log.timestamp?.slice(0, 19)}</Text>
                          </div>
                          {log.details && Object.keys(log.details).length > 0 && (
                            <Text style={{ fontSize: 12, color: '#666' }}>
                              {JSON.stringify(log.details)}
                            </Text>
                          )}
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

          <Form.Item label="策略描述" name="description">
            <Input.TextArea placeholder="策略说明（可选）" rows={2} />
          </Form.Item>

          <Form.Item label="交易模式" name="trade_mode" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio.Button value="paper">
                <Space><RobotOutlined />模拟交易</Space>
              </Radio.Button>
              <Radio.Button value="live">
                <Space><BellOutlined />实盘交易</Space>
              </Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Row gutter={12}>
            <Col span={8}>
              <Form.Item label="初始资金" name="capital" rules={[{ required: true, message: '请输入初始资金' }]}>
                <InputNumber min={100000} step={100000} style={{ width: '100%' }} formatter={v => `¥ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} parser={v => Number((v || '').replace(/[^\d]/g, '')) as any} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="检查间隔(秒)" name="check_interval_sec" rules={[{ required: true, message: '必填' }]}>
                <InputNumber min={30} max={3600} step={30} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="最大持仓数" name={['position_rules', 'max_positions']}>
                <InputNumber min={1} max={20} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="单票最大仓位 (%)" name={['position_rules', 'single_max_pct']}>
                <InputNumber min={5} max={50} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="总仓位上限 (%)" name={['position_rules', 'total_position_cap_pct']}>
                <InputNumber min={10} max={100} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
          </Row>

          {/* ── Risk Rules ── */}
          <Divider orientation="left" plain>
            <ExclamationCircleOutlined style={{ marginRight: 6 }} />风控规则
          </Divider>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="日亏损上限 (%)" name={['risk_rules', 'daily_max_loss_pct']}>
                <InputNumber min={0.1} max={20} step={0.5} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="止损比例 (%)" name={['risk_rules', 'stop_loss_pct']}>
                <InputNumber min={0.1} max={20} step={0.5} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="止盈比例 (%)" name={['risk_rules', 'take_profit_pct']}>
                <InputNumber min={0.5} max={100} step={1} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="移动止损 (%)" name={['risk_rules', 'trailing_stop_pct']}>
                <InputNumber min={0} max={20} step={0.5} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
          </Row>

          {/* ── Stock Picks ── */}
          <Divider orientation="left" plain>
            <StockOutlined style={{ marginRight: 6 }} />交易标的
          </Divider>
          <Form.List name="picks">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Card
                    key={key}
                    size="small"
                    style={{ marginBottom: 8, borderRadius: 8, background: '#fafafa' }}
                    extra={
                      <Button type="link" danger size="small" onClick={() => remove(name)}>删除</Button>
                    }
                  >
                    <Row gutter={8} align="middle">
                      <Col flex="120px">
                        <Form.Item name={[name, 'code']} style={{ marginBottom: 0 }} rules={[{ required: true, message: '股票代码' }]}>
                          <Input placeholder="代码 如 600519" />
                        </Form.Item>
                      </Col>
                      <Col flex="auto">
                        <Form.Item name={[name, 'name']} style={{ marginBottom: 0 }}>
                          <Input placeholder="名称（可选）" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'price']} style={{ marginBottom: 0 }}>
                          <InputNumber style={{ width: '100%' }} placeholder="价格" min={0} />
                        </Form.Item>
                      </Col>
                    </Row>
                  </Card>
                ))}
                <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({ code: '', name: '', price: 0 })}>
                  添加标的
                </Button>
              </>
            )}
          </Form.List>

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
                      <Col flex="auto">
                        <Form.Item name={[name, 'field']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={fieldOptions} placeholder="指标字段" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'operator']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={operatorOptions} placeholder="运算符" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'threshold']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <InputNumber style={{ width: '100%' }} placeholder="阈值" />
                        </Form.Item>
                      </Col>
                      <Col flex="auto">
                        <Form.Item name={[name, 'description']} style={{ marginBottom: 0 }}>
                          <Input placeholder="说明（可选）" />
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
                      <Col flex="auto">
                        <Form.Item name={[name, 'field']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={fieldOptions} placeholder="指标字段" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'operator']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <Select options={operatorOptions} placeholder="运算符" />
                        </Form.Item>
                      </Col>
                      <Col flex="120px">
                        <Form.Item name={[name, 'threshold']} style={{ marginBottom: 0 }} rules={[{ required: true }]}>
                          <InputNumber style={{ width: '100%' }} placeholder="阈值" />
                        </Form.Item>
                      </Col>
                      <Col flex="auto">
                        <Form.Item name={[name, 'description']} style={{ marginBottom: 0 }}>
                          <Input placeholder="说明（可选）" />
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
        </Form>
      </Drawer>
    </div>
  )
}
