import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Card, Button, Table, Tag, Typography, Space, message, Modal, Form,
  Input, InputNumber, Select, Switch, Row, Col, Statistic, Progress,
  Timeline, Popconfirm, Tabs, Divider, Empty, DatePicker, Badge,
} from 'antd'
import {
  ExperimentOutlined, PlusOutlined, ReloadOutlined,
  StopOutlined, DeleteOutlined, PlayCircleOutlined,
  ClockCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  SettingOutlined, ScheduleOutlined, BarChartOutlined,
  ThunderboltOutlined, InfoCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import api from '../api/client'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

// ── Types ──

type ModelType = 'lightgbm' | 'catboost' | 'kronos_finetune'
type JobStatus = 'pending' | 'preparing' | 'running' | 'evaluating' | 'completed' | 'failed' | 'cancelled'
type LogLevel = 'info' | 'success' | 'warning' | 'error'

interface TrainingParams {
  model_type: ModelType
  horizon: number
  lookback: number
  n_trials: number
  cv_folds: number
  early_stopping_rounds: number
  learning_rate?: number
  max_depth?: number
  num_leaves?: number
  subsample?: number
  colsample_bytree?: number
  data_start_date?: string
  data_end_date?: string
  factor_whitelist?: string[]
  test_size: number
}

interface TrainingMetrics {
  trial: number
  epoch?: number
  train_loss: number
  valid_loss: number
  best_valid_loss: number
  ic?: number
  icir?: number
  feature_importance?: Record<string, number>
  elapsed_seconds: number
}

interface TrainingJob {
  job_id: string
  model_type: ModelType
  status: JobStatus
  params: TrainingParams
  best_params?: Record<string, unknown>
  metrics: TrainingMetrics[]
  final_metrics?: TrainingMetrics
  model_uri?: string
  run_id?: string
  experiment_id?: string
  created_by: string
  created_at: string
  started_at?: string
  completed_at?: string
  error_message?: string
}

interface ScheduleConfig {
  enabled: boolean
  cron: string
  model_type: ModelType
  auto_deploy: boolean
  next_run?: string
  last_run?: string
  last_job_id?: string
  last_job_status?: string
  params?: TrainingParams
}

interface ScheduleHistoryItem {
  executed_at: string
  model_type: ModelType
  result: 'success' | 'failed'
  task_id: string
}

// ── Constants ──

const modelTypeConfig: Record<string, { color: string; label: string }> = {
  lightgbm:         { color: 'blue',   label: 'LightGBM' },
  catboost:         { color: 'green',  label: 'CatBoost' },
  kronos_finetune:  { color: 'purple', label: 'Kronos Fine-tune' },
}

const jobStatusConfig: Record<string, { color: string; label: string }> = {
  pending:    { color: 'default', label: '排队中' },
  preparing:  { color: 'blue',    label: '准备中' },
  running:    { color: 'processing', label: '训练中' },
  evaluating: { color: 'orange',  label: '评估中' },
  completed:  { color: 'green',   label: '已完成' },
  failed:     { color: 'red',     label: '失败' },
  cancelled:  { color: 'default', label: '已取消' },
}

const logLevelConfig: Record<string, { color: string; icon: React.ReactNode }> = {
  info:    { color: 'blue',   icon: <InfoCircleOutlined /> },
  success: { color: 'green',  icon: <CheckCircleOutlined /> },
  warning: { color: 'gold',   icon: <ExclamationCircleOutlined /> },
  error:   { color: 'red',    icon: <ExclamationCircleOutlined /> },
}

const modelTypeOptions = Object.entries(modelTypeConfig).map(([value, { label }]) => ({
  value, label,
}))

const targetColumns = [
  { label: '次日收益', value: 'next_day_return' },
  { label: '次周收益', value: 'next_week_return' },
  { label: '次月收益', value: 'next_month_return' },
]

const factorGroupOptions = [
  { label: '技术因子', value: 'technical' },
  { label: '基本面因子', value: 'fundamental' },
  { label: '情绪因子', value: 'sentiment' },
  { label: '宏观因子', value: 'macro' },
  { label: '资金流因子', value: 'flow' },
]

const defaultCron = '0 2 * * 6'

// ── Sub-components ──

function TriggerTrainingModal({
  open, onClose, onSubmitted,
}: {
  open: boolean
  onClose: () => void
  onSubmitted: () => void
}) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const modelType = Form.useWatch('model_type', form)

  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      const [dataStart, dataEnd] = values.data_range
        ? [values.data_range[0].format('YYYY-MM-DD'), values.data_range[1].format('YYYY-MM-DD')]
        : [undefined, undefined]
      const body = {
        params: {
          model_type: values.model_type,
          horizon: values.horizon ?? 10,
          lookback: values.lookback ?? 90,
          n_trials: values.n_trials ?? 50,
          cv_folds: values.cv_folds ?? 5,
          early_stopping_rounds: values.early_stopping_rounds ?? 50,
          learning_rate: values.learning_rate ?? undefined,
          max_depth: values.max_depth ?? undefined,
          num_leaves: values.model_type === 'lightgbm' ? (values.num_leaves ?? undefined) : undefined,
          subsample: values.subsample ?? undefined,
          colsample_bytree: values.colsample_bytree ?? undefined,
          data_start_date: dataStart,
          data_end_date: dataEnd,
          factor_whitelist: values.factor_groups?.length ? values.factor_groups : undefined,
          test_size: values.test_size ?? 0.2,
        },
        auto_deploy: false,
      }
      const r = await api.post('/training/run', body)
      if (r.status === 202) {
        message.success(`训练任务已提交: ${r.data.job_id.slice(0, 12)}`)
        onSubmitted()
        onClose()
        form.resetFields()
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (err as Error)?.message
        || '提交失败'
      message.error(detail)
    } finally {
      setLoading(false)
    }
  }, [form, onSubmitted, onClose])

  return (
    <Modal
      title="触发训练"
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      width={600}
      destroyOnClose
    >
      <Form form={form} layout="vertical" size="small" initialValues={{
        model_type: 'lightgbm',
        horizon: 10,
        lookback: 90,
        n_trials: 50,
        cv_folds: 5,
        early_stopping_rounds: 50,
        test_size: 0.2,
      }}>
        <Divider orientation="left" plain>训练配置</Divider>
        <Form.Item name="model_type" label="模型类型" rules={[{ required: true, message: '请选择模型类型' }]}>
          <Select options={modelTypeOptions} />
        </Form.Item>
        <Form.Item name="data_range" label="数据时间范围">
          <RangePicker style={{ width: '100%' }} />
        </Form.Item>
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item name="horizon" label="预测持仓天数">
              <InputNumber min={1} max={60} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="lookback" label="回看天数">
              <InputNumber min={30} max={500} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="test_size" label="验证集比例">
              <InputNumber min={0.05} max={0.5} step={0.05} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item name="n_trials" label="Optuna 试验次数">
              <InputNumber min={1} max={500} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="cv_folds" label="交叉验证折数">
              <InputNumber min={2} max={10} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="early_stopping_rounds" label="早停轮次">
              <InputNumber min={10} max={200} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item name="learning_rate" label="学习率">
              <InputNumber min={0.001} max={1.0} step={0.001} style={{ width: '100%' }} placeholder="Optuna 自动搜索" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="max_depth" label="最大深度">
              <InputNumber min={2} max={16} style={{ width: '100%' }} placeholder="Optuna 自动搜索" />
            </Form.Item>
          </Col>
          {modelType === 'lightgbm' && (
            <Col span={8}>
              <Form.Item name="num_leaves" label="叶子数 (LightGBM)">
                <InputNumber min={8} max={512} style={{ width: '100%' }} placeholder="Optuna 自动搜索" />
              </Form.Item>
            </Col>
          )}
        </Row>
        <Form.Item name="factor_groups" label="因子集合">
          <Select mode="multiple" options={factorGroupOptions} placeholder="全部因子" />
        </Form.Item>
        <Form.Item name="target_column" label="目标列">
          <Select options={targetColumns} placeholder="默认" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function ScheduleConfigForm() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [config, setConfig] = useState<ScheduleConfig | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [history, setHistory] = useState<ScheduleHistoryItem[]>([])

  const loadConfig = useCallback(async () => {
    try {
      const r = await api.get('/training/schedule')
      setConfig(r.data)
      form.setFieldsValue({
        enabled: r.data.enabled,
        cron: r.data.cron || defaultCron,
        model_type: r.data.model_type || 'lightgbm',
        auto_deploy: r.data.auto_deploy ?? false,
      })
    } catch {
      // Config not yet set
    }
  }, [form])

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const r = await api.get('/training/history', { params: { page: 1, page_size: 10, created_by: 'schedule' } })
      setHistory((r.data.jobs || []).map((j: TrainingJob) => ({
        executed_at: j.created_at,
        model_type: j.model_type,
        result: j.status === 'completed' ? 'success' : 'failed',
        task_id: j.job_id,
      })))
    } catch { /* ignore */ }
    finally { setHistoryLoading(false) }
  }, [])

  useEffect(() => {
    loadConfig()
    loadHistory()
  }, [loadConfig, loadHistory])

  const handleSave = useCallback(async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      const r = await api.post('/training/schedule', {
        enabled: values.enabled,
        cron: values.cron,
        model_type: values.model_type,
        params: config?.params || {
          model_type: values.model_type,
          horizon: 10,
          lookback: 90,
          n_trials: 50,
          cv_folds: 5,
          early_stopping_rounds: 50,
          test_size: 0.2,
        },
        auto_deploy: values.auto_deploy ?? false,
        notify_on_complete: true,
        notify_channels: ['email'],
      })
      message.success(`调度配置已保存，下次执行: ${r.data.next_run || '未知'}`)
      loadConfig()
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return
      message.error('保存失败')
    } finally {
      setLoading(false)
    }
  }, [form, config, loadConfig])

  const historyColumns: ColumnsType<ScheduleHistoryItem> = [
    { title: '执行时间', dataIndex: 'executed_at', key: 'executed_at', width: 180,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
    { title: '模型类型', dataIndex: 'model_type', key: 'model_type', width: 120,
      render: (v: ModelType) => <Tag color={modelTypeConfig[v]?.color}>{modelTypeConfig[v]?.label || v}</Tag> },
    { title: '结果', dataIndex: 'result', key: 'result', width: 100,
      render: (v: string) => <Tag color={v === 'success' ? 'green' : 'red'}>{v === 'success' ? '成功' : '失败'}</Tag> },
    { title: '关联任务', dataIndex: 'task_id', key: 'task_id',
      render: (v: string) => v ? <Text code style={{ fontSize: 12 }}>{v.slice(0, 12)}</Text> : '-' },
  ]

  return (
    <>
      <Card title={<><ScheduleOutlined /> 定时训练</>} style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical" initialValues={{
          enabled: false, cron: defaultCron, model_type: 'lightgbm', auto_deploy: false,
        }}>
          <Row gutter={24}>
            <Col span={8}>
              <Form.Item name="enabled" label="启用自动训练" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="model_type" label="模型类型" rules={[{ required: true }]}>
                <Select options={modelTypeOptions} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="auto_deploy" label="自动上线" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="cron" label="Cron 表达式" rules={[{ required: true, message: '请输入 Cron 表达式' }]}>
            <Input placeholder="0 2 * * 6 (每周六 02:00)" />
          </Form.Item>
          {config?.next_run && (
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
              下次执行: {dayjs(config.next_run).format('YYYY-MM-DD HH:mm:ss')}
            </Text>
          )}
          {config?.last_run && (
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
              上次执行: {dayjs(config.last_run).format('YYYY-MM-DD HH:mm:ss')}
              {config.last_job_status && <Tag style={{ marginLeft: 8 }} color={config.last_job_status === 'completed' ? 'green' : 'red'}>{config.last_job_status}</Tag>}
            </Text>
          )}
          <Form.Item>
            <Button type="primary" onClick={handleSave} loading={loading} icon={<SettingOutlined />}>
              保存配置
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="调度历史">
        <Table
          columns={historyColumns}
          dataSource={history}
          rowKey={(r, i) => r.task_id || String(i)}
          loading={historyLoading}
          size="small"
          locale={{ emptyText: '暂无调度记录' }}
        />
      </Card>
    </>
  )
}

// ── Main Training Page ──

export default function Training() {
  const [tasks, setTasks] = useState<TrainingJob[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [triggerOpen, setTriggerOpen] = useState(false)
  const [liveJobId, setLiveJobId] = useState<string | null>(null)
  const [liveMetrics, setLiveMetrics] = useState<TrainingMetrics[]>([])
  const [liveLogs, setLiveLogs] = useState<Array<{ time: string; level: LogLevel; message: string }>>([])
  const [activeTab, setActiveTab] = useState('tasks')
  const eventSourceRef = useRef<EventSource | null>(null)

  // ── Load tasks ──
  const loadTasks = useCallback(async () => {
    setTasksLoading(true)
    try {
      const r = await api.get('/training/history', { params: { page: 1, page_size: 50 } })
      setTasks(r.data.jobs || [])
    } catch {
      message.error('加载训练任务失败')
    } finally {
      setTasksLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTasks()
  }, [loadTasks])

  // ── SSE live monitoring ──
  useEffect(() => {
    if (!liveJobId) return

    setLiveMetrics([])
    setLiveLogs([])

    const es = new EventSource(`/api/v1/training/status/${liveJobId}`)
    eventSourceRef.current = es

    es.addEventListener('metric', ((e: MessageEvent) => {
      try {
        const metric = JSON.parse(e.data) as TrainingMetrics
        setLiveMetrics(prev => [...prev, metric])
      } catch { /* ignore parse errors */ }
    }) as EventListener)

    es.addEventListener('complete', ((e: MessageEvent) => {
      try {
        const result = JSON.parse(e.data)
        message.success(`训练完成: ${result.job_id?.slice(0, 12)}`)
        setLiveJobId(null)
        loadTasks()
      } catch { /* ignore */ }
    }) as EventListener)

    es.addEventListener('error', ((e: Event) => {
      const msgEvent = e as MessageEvent
      if (msgEvent.data) {
        try {
          const err = JSON.parse(msgEvent.data)
          message.error(`训练失败: ${err.error_message || '未知错误'}`)
        } catch {
          message.error('训练异常终止')
        }
      } else {
        message.error('训练异常终止')
      }
      setLiveJobId(null)
      loadTasks()
    }) as EventListener)

    es.addEventListener('trial_complete', (() => {
      // trial complete, metrics will follow
    }) as EventListener)

    es.addEventListener('evaluating', (() => {
      setLiveLogs(prev => [...prev, {
        time: new Date().toISOString(),
        level: 'info',
        message: '正在对比新旧模型回测表现...',
      }])
    }) as EventListener)

    es.onerror = () => {
      es.close()
      // retry after 5s if still monitoring
      setTimeout(() => {
        if (eventSourceRef.current === es) {
          loadTasks()
        }
      }, 5000)
    }

    return () => {
      es.close()
      eventSourceRef.current = null
    }
  }, [liveJobId, loadTasks])

  // ── Cancel job ──
  const handleCancel = useCallback(async (jobId: string) => {
    try {
      const r = await api.post(`/training/status/${jobId}/cancel`)
      if (r.status === 200) {
        message.success('任务已取消')
        if (liveJobId === jobId) setLiveJobId(null)
        loadTasks()
      }
    } catch {
      message.error('取消失败')
    }
  }, [liveJobId, loadTasks])

  // ── View live details ──
  const handleViewDetail = useCallback((job: TrainingJob) => {
    if (job.status === 'running' || job.status === 'preparing' || job.status === 'evaluating') {
      setLiveJobId(job.job_id)
      setActiveTab('monitor')
    } else {
      // For completed jobs, show metrics from the job record
      setLiveMetrics(job.metrics || [])
      setActiveTab('monitor')
    }
  }, [])

  // ── ECharts loss option ──
  const lossOption = {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['训练 Loss', '验证 Loss'] },
    xAxis: { type: 'category' as const, name: 'Trial', data: liveMetrics.map(m => m.trial) },
    yAxis: { type: 'value' as const, name: 'Loss' },
    series: [
      {
        name: '训练 Loss', type: 'line', data: liveMetrics.map(m => m.train_loss),
        smooth: true, itemStyle: { color: '#1677ff' },
      },
      {
        name: '验证 Loss', type: 'line', data: liveMetrics.map(m => m.valid_loss),
        smooth: true, itemStyle: { color: '#52c41a' },
      },
    ],
    grid: { left: 60, right: 20, top: 40, bottom: 40 },
  }

  // ── ECharts feature importance option ──
  const latestFeatureImportance = liveMetrics.length > 0
    ? liveMetrics[liveMetrics.length - 1].feature_importance
    : null
  const featureImportanceOption = latestFeatureImportance ? (() => {
    const entries = Object.entries(latestFeatureImportance).sort((a, b) => b[1] - a[1]).slice(0, 15)
    return {
      tooltip: { trigger: 'axis' as const, axisPointer: { type: 'shadow' as const } },
      xAxis: { type: 'value' as const, name: 'Importance' },
      yAxis: { type: 'category' as const, data: entries.map(e => e[0]), inverse: true,
        axisLabel: { width: 100, overflow: 'truncate' } },
      series: [{
        type: 'bar', data: entries.map(e => e[1]),
        itemStyle: { color: '#1677ff', borderRadius: [0, 4, 4, 0] },
      }],
      grid: { left: 120, right: 20, top: 20, bottom: 30 },
    }
  })() : null

  // ── Table columns ──
  const taskColumns: ColumnsType<TrainingJob> = [
    {
      title: 'Job ID', dataIndex: 'job_id', key: 'job_id', width: 140,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v.slice(0, 12)}</Text>,
    },
    {
      title: '模型类型', dataIndex: 'model_type', key: 'model_type', width: 130,
      render: (v: ModelType) => <Tag color={modelTypeConfig[v]?.color}>{modelTypeConfig[v]?.label || v}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: JobStatus) => (
        <Badge status={jobStatusConfig[v]?.color === 'processing' ? 'processing' : (jobStatusConfig[v]?.color as 'default' | 'success' | 'error' | 'warning') || 'default'}
          text={jobStatusConfig[v]?.label || v} />
      ),
    },
    {
      title: '数据范围', key: 'data_range', width: 200,
      render: (_: unknown, record: TrainingJob) => {
        const s = record.params?.data_start_date || '-'
        const e = record.params?.data_end_date || '-'
        return <Text style={{ fontSize: 12 }}>{s} ~ {e}</Text>
      },
    },
    {
      title: '开始时间', dataIndex: 'started_at', key: 'started_at', width: 160,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '耗时', dataIndex: 'completed_at', key: 'duration', width: 100,
      render: (_: string, record: TrainingJob) => {
        if (!record.started_at) return '-'
        const end = record.completed_at ? dayjs(record.completed_at) : dayjs()
        const seconds = end.diff(dayjs(record.started_at), 'second')
        if (seconds < 60) return `${seconds}s`
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
        return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
      },
    },
    {
      title: '最优 Loss', key: 'best_loss', width: 120,
      render: (_: unknown, record: TrainingJob) => {
        const fl = record.final_metrics
        if (!fl) return '-'
        return <Text style={{ fontSize: 12 }}>
          {fl.best_valid_loss?.toFixed(4)}
        </Text>
      },
    },
    {
      title: '操作', key: 'actions', width: 200,
      render: (_: unknown, record: TrainingJob) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => handleViewDetail(record)}>
            详情
          </Button>
          {(record.status === 'running' || record.status === 'pending' || record.status === 'preparing') && (
            <Popconfirm title="确认取消此训练任务？" onConfirm={() => handleCancel(record.job_id)}>
              <Button type="link" size="small" danger icon={<StopOutlined />}>
                取消
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const hasRunningJob = tasks.some(t => t.status === 'running' || t.status === 'preparing' || t.status === 'evaluating')
  const latestTrial = liveMetrics.length > 0 ? liveMetrics[liveMetrics.length - 1].trial : 0

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <ExperimentOutlined style={{ marginRight: 8 }} />
          训练中心
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadTasks}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setTriggerOpen(true)}
            disabled={hasRunningJob}>
            手动触发训练
          </Button>
        </Space>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        {
          key: 'tasks',
          label: <><PlayCircleOutlined /> 训练任务</>,
          children: (
            <Card>
              <Table
                columns={taskColumns}
                dataSource={tasks}
                rowKey="job_id"
                loading={tasksLoading}
                size="small"
                locale={{ emptyText: '暂无训练任务，点击"手动触发训练"创建。' }}
                pagination={{ pageSize: 10, size: 'small' }}
              />
            </Card>
          ),
        },
        {
          key: 'monitor',
          label: <><BarChartOutlined /> 训练监控 {liveJobId && <Badge status="processing" style={{ marginLeft: 4 }} />}</>,
          children: (
            <>
              {liveMetrics.length === 0 && !liveJobId ? (
                <Empty description="当前无训练中的任务，请从训练任务列表查看详情或触发新训练。" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Loss 曲线" size="small" style={{ marginBottom: 16 }}>
                      {liveMetrics.length > 0 ? (
                        <ReactECharts option={lossOption} style={{ height: 280 }} />
                      ) : (
                        <Empty description="等待数据..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      )}
                    </Card>
                    <Card title="学习率" size="small" style={{ marginBottom: 16 }}>
                      {liveMetrics.length > 0 ? (
                        <ReactECharts option={{
                          tooltip: { trigger: 'axis' as const },
                          xAxis: { type: 'category' as const, data: liveMetrics.map(m => m.trial) },
                          yAxis: { type: 'value' as const, name: 'LR' },
                          series: [{
                            type: 'line', data: liveMetrics.map(() => liveMetrics[0]?.epoch ?? 0.05),
                            itemStyle: { color: '#faad14' },
                          }],
                          grid: { left: 60, right: 20, top: 20, bottom: 30 },
                        }} style={{ height: 200 }} />
                      ) : (
                        <Empty description="等待数据..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      )}
                    </Card>
                    <Card size="small">
                      <Statistic title="当前 Trial" value={`${latestTrial}`} suffix={liveMetrics.length > 0 ? `/ ${liveMetrics.length > 0 ? liveMetrics.length * 2 : '-'}` : ''} />
                      <Progress percent={liveMetrics.length > 0 ? Math.min(100, Math.round((latestTrial / (liveMetrics.length * 2 || 1)) * 100)) : 0}
                        status="active" size="small" />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="特征重要性" size="small" style={{ marginBottom: 16 }}>
                      {featureImportanceOption ? (
                        <ReactECharts option={featureImportanceOption} style={{ height: 280 }} />
                      ) : (
                        <Empty description="等待数据..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      )}
                    </Card>
                    <Card title="训练日志" size="small">
                      <div style={{ maxHeight: 400, overflow: 'auto' }}>
                        {liveLogs.length === 0 && !liveJobId ? (
                          <Empty description="暂无日志" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        ) : liveLogs.length === 0 ? (
                          <Empty description="等待日志..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        ) : (
                          <Timeline items={liveLogs.map(log => ({
                            color: logLevelConfig[log.level]?.color || 'blue',
                            children: (
                              <div>
                                <Text type="secondary" style={{ fontSize: 11 }}>{dayjs(log.time).format('HH:mm:ss')}</Text>
                                <Text style={{ marginLeft: 8, fontSize: 13 }}>{log.message}</Text>
                              </div>
                            ),
                          }))} />
                        )}
                      </div>
                    </Card>
                  </Col>
                </Row>
              )}
            </>
          ),
        },
        {
          key: 'schedule',
          label: <><ScheduleOutlined /> 调度配置</>,
          children: <ScheduleConfigForm />,
        },
      ]} />

      {/* Trigger Training Modal */}
      <TriggerTrainingModal
        open={triggerOpen}
        onClose={() => setTriggerOpen(false)}
        onSubmitted={loadTasks}
      />
    </div>
  )
}
