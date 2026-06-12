import { useState, useEffect, useCallback } from 'react'
import {
  Card, Button, Table, Tag, Typography, Space, message, Modal, Form,
  Row, Col, Statistic, Popconfirm, Drawer, Descriptions, Divider,
  Empty, Input, InputNumber, Alert, Select,
} from 'antd'
import {
  ApiOutlined, ReloadOutlined, RocketOutlined, RollbackOutlined,
  SwapOutlined, EyeOutlined, CheckCircleOutlined, CloseCircleOutlined,
  RiseOutlined, FallOutlined, BarChartOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import api from '../api/client'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// ── Types ──

type ModelType = 'lightgbm' | 'catboost' | 'kronos_finetune'
type ModelStage = 'none' | 'staging' | 'production' | 'archived'

interface ModelMetrics {
  auc?: number
  sharpe?: number
  annual_return?: number
  max_drawdown?: number
  precision?: number
  recall?: number
  f1?: number
  ic?: number
  icir?: number
  rank_ic?: number
  train_loss?: number
  valid_loss?: number
  win_rate?: number
  profit_loss_ratio?: number
}

interface ModelRecord {
  id: string
  name: string
  version: number
  model_type: ModelType
  stage: ModelStage
  run_id?: string
  experiment_id?: string
  params?: Record<string, unknown>
  metrics?: ModelMetrics
  artifact_uri?: string
  deployed_at?: string
  deployed_by?: string
  created_by: string
  created_at: string
  updated_at?: string
  notes?: string
}

interface CompareResult {
  metric: string
  new_value: number
  old_value: number
  delta: number
  delta_pct: number
  better: boolean
  threshold: number
}

interface FactorInfo {
  name: string
  current_weight: number
  suggested_weight: number
  ic?: number
  icir?: number
  rank_ic?: number
  last_calibrated_at?: string
  weight_trend?: number[]
  factor_label?: string
  direction?: string
  significance?: string
}

interface ICWindow {
  window_end: string
  ic: number
  icir: number
  n_stocks: number
}

interface FactorICData {
  factor_name: string
  factor_label: string
  current_ic: number
  current_icir: number
  ic_mean: number
  ic_std: number
  icir_mean: number
  direction: string
  rolling: ICWindow[]
}

// ── Constants ──

const modelTypeConfig: Record<string, { color: string; label: string }> = {
  lightgbm:         { color: 'blue',   label: 'LightGBM' },
  catboost:         { color: 'green',  label: 'CatBoost' },
  kronos_finetune:  { color: 'purple', label: 'Kronos' },
}

const modelStageConfig: Record<string, { color: string; label: string }> = {
  none:       { color: 'default', label: '注册' },
  staging:    { color: 'gold',    label: '待评审' },
  production: { color: 'green',   label: '线上' },
  archived:   { color: 'default', label: '已归档' },
}

const IC_COLORS = ['#5470C6', '#91CC75', '#FAC858', '#EE6666', '#73C0DE', '#3BA272', '#FC8452', '#9A60B4', '#EA7CCC']

// ── Helpers ──

function fmtPct(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  return `${(v * 100).toFixed(decimals)}%`
}

function fmtNum(v: number | undefined, decimals = 4): string {
  if (v === undefined || v === null) return '-'
  return v.toFixed(decimals)
}

export default function ModelRegistry() {
  const [models, setModels] = useState<ModelRecord[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [detailModel, setDetailModel] = useState<ModelRecord | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [modelA, setModelA] = useState<ModelRecord | null>(null)
  const [modelB, setModelB] = useState<ModelRecord | null>(null)
  const [compareData, setCompareData] = useState<CompareResult[]>([])
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareVerdict, setCompareVerdict] = useState('')
  const [compareRecommendation, setCompareRecommendation] = useState('')
  const [rollbackReason, setRollbackReason] = useState('')
  const [rollbackOpen, setRollbackOpen] = useState<string | null>(null)
  const [targetVersion, setTargetVersion] = useState(1)
  const [archiveReason, setArchiveReason] = useState('')
  const [archiveModelId, setArchiveModelId] = useState<string | null>(null)
  const [factors, setFactors] = useState<FactorInfo[]>([])
  const [factorsLoading, setFactorsLoading] = useState(false)
  const [icData, setIcData] = useState<FactorICData[]>([])
  const [icLoading, setIcLoading] = useState(false)
  const [calibrateLoading, setCalibrateLoading] = useState(false)

  // ── Load models ──
  const loadModels = useCallback(async () => {
    setModelsLoading(true)
    try {
      const r = await api.get('/training/models', { params: { page: 1, page_size: 50 } })
      setModels(r.data.models || [])
    } catch {
      message.error('加载模型列表失败')
    } finally {
      setModelsLoading(false)
    }
  }, [])

  // ── Load factors ──
  const loadFactors = useCallback(async () => {
    setFactorsLoading(true)
    try {
      const [fRes, icRes] = await Promise.all([
        api.get('/training/factors/ic', { params: { window_days: 120 } }),
        api.get('/training/factors/ic', { params: { window_days: 120 } }),
      ])
      const factorsList = icRes.data?.factors || fRes.data?.factors || []
      setIcData(factorsList)
      setFactors(factorsList.map((f: FactorICData) => ({
        name: f.factor_name,
        factor_label: f.factor_label,
        current_weight: 0,
        suggested_weight: 0,
        ic: f.current_ic,
        icir: f.current_icir,
        rank_ic: f.current_ic,
        direction: f.direction,
        significance: '',
      })))
    } catch {
      // Factor data may not be available
    } finally {
      setFactorsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadModels()
    loadFactors()
  }, [loadModels, loadFactors])

  // ── Load model detail ──
  const loadDetail = useCallback(async (id: string) => {
    try {
      const r = await api.get(`/training/models/${id}`)
      setDetailModel(r.data)
      setDetailOpen(true)
    } catch {
      message.error('加载模型详情失败')
    }
  }, [])

  // ── A/B Compare ──
  const handleCompare = useCallback(async (model: ModelRecord) => {
    const productionModel = models.find(m => m.stage === 'production' && m.name === model.name)
    setModelA(productionModel || null)
    setModelB(model)
    setCompareOpen(true)
    setCompareLoading(true)
    try {
      const r = await api.get(`/training/models/${model.id}/compare`)
      setCompareData(r.data.comparison || [])
      setCompareVerdict(r.data.verdict || '')
      setCompareRecommendation(r.data.recommendation || '')
    } catch {
      // Build comparison from local data
      if (productionModel && model.metrics) {
        const oldMetrics = productionModel.metrics || {}
        const newMetrics = model.metrics || {}
        const metrics = [
          { key: 'sharpe', label: '夏普比率', higherBetter: true },
          { key: 'icir', label: 'ICIR', higherBetter: true },
          { key: 'max_drawdown', label: '最大回撤', higherBetter: false },
          { key: 'annual_return', label: '年化收益', higherBetter: true },
          { key: 'win_rate', label: '胜率', higherBetter: true },
          { key: 'profit_loss_ratio', label: '盈亏比', higherBetter: true },
        ]
        const results: CompareResult[] = []
        for (const m of metrics) {
          const oldV = (oldMetrics as Record<string, number>)[m.key]
          const newV = (newMetrics as Record<string, number>)[m.key]
          if (oldV !== undefined && newV !== undefined) {
            const delta = newV - oldV
            const deltaPct = oldV !== 0 ? (delta / Math.abs(oldV)) * 100 : 0
            const better = m.higherBetter ? delta > 0 : delta < 0
            results.push({
              metric: m.label, new_value: newV, old_value: oldV,
              delta, delta_pct: deltaPct, better, threshold: 0,
            })
          }
        }
        setCompareData(results)
        const betterCount = results.filter(r => r.better).length
        setCompareVerdict(betterCount >= results.length * 0.5 ? 'new_better' : 'old_better')
        setCompareRecommendation(betterCount >= results.length * 0.5 ? '建议上线新模型' : '建议保留旧模型')
      }
    } finally {
      setCompareLoading(false)
    }
  }, [models])

  // ── Deploy ──
  const handleDeploy = useCallback(async (modelId: string) => {
    try {
      await api.post(`/training/models/${modelId}/deploy`, { notes: '' })
      message.success('模型已上线')
      loadModels()
      setCompareOpen(false)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '上线失败'
      message.error(detail)
    }
  }, [loadModels])

  // ── Rollback ──
  const handleRollback = useCallback(async (modelId: string) => {
    if (!rollbackReason.trim()) {
      message.warning('请填写回滚原因')
      return
    }
    try {
      await api.post(`/training/models/${modelId}/rollback`, { target_version: targetVersion, reason: rollbackReason })
      message.success('模型已回滚')
      setRollbackReason('')
      setTargetVersion(1)
      setRollbackOpen(null)
      loadModels()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '回滚失败'
      message.error(detail)
    }
  }, [rollbackReason, loadModels])

  // ── Archive (keep old model) ──
  const handleArchive = useCallback(async () => {
    if (!archiveModelId) return
    if (!archiveReason.trim()) {
      message.warning('请填写失败原因')
      return
    }
    try {
      await api.post(`/training/models/${archiveModelId}/archive`, { reason: archiveReason })
      message.success('已归档并保留旧模型')
      setArchiveReason('')
      setArchiveModelId(null)
      loadModels()
      setCompareOpen(false)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '归档失败'
      message.error(detail)
    }
  }, [archiveModelId, archiveReason, loadModels])

  // ── Calibrate factors ──
  const handleCalibrate = useCallback(async () => {
    setCalibrateLoading(true)
    try {
      const r = await api.post('/training/calibrate', {
        mode: 'all',
        window_days: 90,
        min_samples: 30,
        apply: true,
      })
      message.success(`因子校准完成: ${r.data.summary || ''}`)
      loadFactors()
    } catch {
      message.error('因子校准失败')
    } finally {
      setCalibrateLoading(false)
    }
  }, [loadFactors])

  // ── ECharts radar for A/B compare ──
  const radarOption = modelA && modelB ? {
    tooltip: {},
    legend: {
      data: [`旧模型 (${modelA.name} v${modelA.version})`, `新模型 (${modelB.name} v${modelB.version})`],
      bottom: 0,
    },
    radar: {
      indicator: compareData.map(d => ({
        name: d.metric,
        max: Math.max(Math.abs(d.new_value), Math.abs(d.old_value)) * 1.3,
      })),
      center: ['50%', '55%'],
      radius: '65%',
    },
    series: [{
      type: 'radar',
      data: [
        {
          name: `旧模型 (${modelA.name} v${modelA.version})`,
          value: compareData.map(d => d.old_value),
          lineStyle: { color: '#faad14' },
          areaStyle: { color: 'rgba(250,173,20,0.15)' },
        },
        {
          name: `新模型 (${modelB.name} v${modelB.version})`,
          value: compareData.map(d => d.new_value),
          lineStyle: { color: '#1677ff' },
          areaStyle: { color: 'rgba(22,119,255,0.15)' },
        },
      ],
    }],
  } : null

  // ── IC line chart option ──
  const icLineOption = icData.length > 0 ? {
    tooltip: { trigger: 'axis' as const },
    legend: {
      data: icData.slice(0, 6).map(f => f.factor_label || f.factor_name),
      type: 'scroll' as const,
      bottom: 0,
    },
    xAxis: {
      type: 'time' as const,
      name: '日期',
      axisLabel: { formatter: '{value}' },
    },
    yAxis: {
      type: 'value' as const,
      name: 'IC',
      splitLine: { lineStyle: { type: 'dashed' as const } },
    },
    series: icData.slice(0, 6).map((f, i) => ({
      name: f.factor_label || f.factor_name,
      type: 'line' as const,
      data: (f.rolling || []).map(w => [w.window_end, w.ic]),
      smooth: true,
      symbol: 'none' as const,
      lineStyle: { color: IC_COLORS[i % IC_COLORS.length] },
    })),
    grid: { left: 60, right: 20, top: 20, bottom: 50 },
  } : null

  // ── Model table columns ──
  const modelColumns: ColumnsType<ModelRecord> = [
    {
      title: '名称', dataIndex: 'name', key: 'name', width: 160,
      render: (v: string, record: ModelRecord) => (
        <Button type="link" size="small" onClick={() => loadDetail(record.id)} style={{ padding: 0 }}>
          {v} <Text type="secondary" style={{ fontSize: 11 }}>v{record.version}</Text>
        </Button>
      ),
    },
    {
      title: '类型', dataIndex: 'model_type', key: 'model_type', width: 100,
      render: (v: ModelType) => <Tag color={modelTypeConfig[v]?.color}>{modelTypeConfig[v]?.label || v}</Tag>,
    },
    {
      title: '状态', dataIndex: 'stage', key: 'stage', width: 90,
      render: (v: ModelStage) => <Tag color={modelStageConfig[v]?.color}>{modelStageConfig[v]?.label || v}</Tag>,
    },
    {
      title: 'AUC', key: 'auc', width: 80,
      render: (_: unknown, record: ModelRecord) => fmtNum(record.metrics?.auc, 4),
    },
    {
      title: '夏普', key: 'sharpe', width: 80,
      render: (_: unknown, record: ModelRecord) => fmtNum(record.metrics?.sharpe, 2),
    },
    {
      title: '年化收益', key: 'annual_return', width: 90,
      render: (_: unknown, record: ModelRecord) => fmtPct(record.metrics?.annual_return),
    },
    {
      title: '最大回撤', key: 'max_drawdown', width: 90,
      render: (_: unknown, record: ModelRecord) => {
        const v = record.metrics?.max_drawdown
        if (v === undefined) return '-'
        return <Text type="danger">{fmtPct(v)}</Text>
      },
    },
    {
      title: 'IC', key: 'ic', width: 80,
      render: (_: unknown, record: ModelRecord) => fmtNum(record.metrics?.ic, 4),
    },
    {
      title: '上线时间', dataIndex: 'deployed_at', key: 'deployed_at', width: 160,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作', key: 'actions', width: 200, fixed: 'right' as const,
      render: (_: unknown, record: ModelRecord) => (
        <Space size="small">
          {record.stage === 'staging' && (
            <Popconfirm title="确认上线此模型？" onConfirm={() => handleDeploy(record.id)}>
              <Button type="link" size="small" icon={<RocketOutlined />} style={{ color: '#52c41a' }}>
                上线
              </Button>
            </Popconfirm>
          )}
          {record.stage === 'production' && (
            <Button type="link" size="small" icon={<RollbackOutlined />} danger
              onClick={() => {
                setTargetVersion(Math.max(1, record.version - 1))
                setRollbackOpen(record.id)
              }}>
              回滚
            </Button>
          )}
          <Button type="link" size="small" icon={<SwapOutlined />}
            onClick={() => handleCompare(record)}>
            对比
          </Button>
          <Button type="link" size="small" icon={<EyeOutlined />}
            onClick={() => loadDetail(record.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ]

  // ── Factor ranking table columns ──
  const factorColumns: ColumnsType<FactorInfo> = [
    {
      title: '排名', key: 'rank', width: 60,
      render: (_: unknown, __: unknown, index: number) => index + 1,
    },
    {
      title: '因子', dataIndex: 'factor_label', key: 'name', width: 140,
      render: (v: string, record: FactorInfo) => v || record.name,
    },
    {
      title: 'IC 均值', dataIndex: 'ic', key: 'ic', width: 90,
      render: (v: number | undefined) => fmtNum(v, 4),
      sorter: (a: FactorInfo, b: FactorInfo) => (a.ic || 0) - (b.ic || 0),
    },
    {
      title: 'ICIR', dataIndex: 'icir', key: 'icir', width: 80,
      render: (v: number | undefined) => fmtNum(v, 2),
      sorter: (a: FactorInfo, b: FactorInfo) => (a.icir || 0) - (b.icir || 0),
    },
    {
      title: '排名 IC', dataIndex: 'rank_ic', key: 'rank_ic', width: 90,
      render: (v: number | undefined) => fmtNum(v, 4),
    },
    {
      title: '当前权重', dataIndex: 'current_weight', key: 'current_weight', width: 90,
      render: (v: number) => v !== undefined ? v.toFixed(1) : '-',
    },
    {
      title: '建议权重', dataIndex: 'suggested_weight', key: 'suggested_weight', width: 90,
      render: (v: number) => v !== undefined ? v.toFixed(1) : '-',
    },
    {
      title: '方向', dataIndex: 'direction', key: 'direction', width: 70,
      render: (v: string) => v === 'long'
        ? <Tag color="green">多头</Tag>
        : v === 'short' ? <Tag color="red">空头</Tag> : v || '-',
    },
    {
      title: '显著性', dataIndex: 'significance', key: 'significance', width: 80,
      render: (v: string) => {
        if (v === 'significant') return <Tag color="green">显著</Tag>
        if (v === 'marginal') return <Tag color="gold">边缘</Tag>
        return v || '-'
      },
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <ApiOutlined style={{ marginRight: 8 }} />
          模型注册
        </Title>
        <Button icon={<ReloadOutlined />} onClick={() => { loadModels(); loadFactors(); }}>刷新</Button>
      </div>

      {/* ── Model List ── */}
      <Card title="模型列表" style={{ marginBottom: 16 }}>
        <Table
          columns={modelColumns}
          dataSource={models}
          rowKey="id"
          loading={modelsLoading}
          size="small"
          scroll={{ x: 1200 }}
          locale={{ emptyText: '暂无已注册模型。训练完成后模型将自动注册到此列表。' }}
          pagination={{ pageSize: 10, size: 'small' }}
        />
      </Card>

      {/* ── Factor Analysis ── */}
      <Card
        title={<><ThunderboltOutlined /> 因子分析</>}
        extra={
          <Button type="primary" size="small" icon={<ThunderboltOutlined />}
            loading={calibrateLoading} onClick={handleCalibrate}>
            权重校准
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <Row gutter={16}>
          <Col span={24}>
            <Card title="IC 滚动折线图" size="small" style={{ marginBottom: 16 }}>
              {icLineOption ? (
                <ReactECharts option={icLineOption} style={{ height: 300 }} />
              ) : (
                <Empty description="暂无因子 IC 数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </Col>
        </Row>
        <Card title="因子排名" size="small">
          <Table
            columns={factorColumns}
            dataSource={factors}
            rowKey="name"
            loading={factorsLoading}
            size="small"
            locale={{ emptyText: '暂无因子数据' }}
            pagination={false}
          />
        </Card>
      </Card>

      {/* ── Detail Drawer ── */}
      <Drawer
        title={`模型详情 - ${detailModel?.name || ''} v${detailModel?.version || ''}`}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={640}
      >
        {detailModel && (
          <>
            <Descriptions size="small" column={2} bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="模型名称">{detailModel.name}</Descriptions.Item>
              <Descriptions.Item label="版本">v{detailModel.version}</Descriptions.Item>
              <Descriptions.Item label="模型类型">
                <Tag color={modelTypeConfig[detailModel.model_type]?.color}>
                  {modelTypeConfig[detailModel.model_type]?.label || detailModel.model_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={modelStageConfig[detailModel.stage]?.color}>
                  {modelStageConfig[detailModel.stage]?.label || detailModel.stage}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{dayjs(detailModel.created_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
              <Descriptions.Item label="上线时间">{detailModel.deployed_at ? dayjs(detailModel.deployed_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
              <Descriptions.Item label="创建人">{detailModel.created_by}</Descriptions.Item>
              <Descriptions.Item label="上线人">{detailModel.deployed_by || '-'}</Descriptions.Item>
            </Descriptions>

            <Card title="评估指标" size="small" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={6}>
                  <Statistic title="AUC" value={fmtNum(detailModel.metrics?.auc, 4)} />
                </Col>
                <Col span={6}>
                  <Statistic title="夏普比率" value={fmtNum(detailModel.metrics?.sharpe, 2)} />
                </Col>
                <Col span={6}>
                  <Statistic title="年化收益" value={fmtPct(detailModel.metrics?.annual_return)} />
                </Col>
                <Col span={6}>
                  <Statistic title="最大回撤" value={fmtPct(detailModel.metrics?.max_drawdown)} />
                </Col>
              </Row>
              <Divider style={{ margin: '12px 0' }} />
              <Row gutter={16}>
                <Col span={6}><Statistic title="Precision" value={fmtNum(detailModel.metrics?.precision, 4)} /></Col>
                <Col span={6}><Statistic title="Recall" value={fmtNum(detailModel.metrics?.recall, 4)} /></Col>
                <Col span={6}><Statistic title="F1" value={fmtNum(detailModel.metrics?.f1, 4)} /></Col>
                <Col span={6}><Statistic title="ICIR" value={fmtNum(detailModel.metrics?.icir, 2)} /></Col>
              </Row>
            </Card>

            {detailModel.params && (
              <Card title="超参数" size="small" style={{ marginBottom: 16 }}>
                <pre style={{ fontSize: 12, background: '#f5f5f5', padding: 8, borderRadius: 4, margin: 0, overflow: 'auto' }}>
                  {JSON.stringify(detailModel.params, null, 2)}
                </pre>
              </Card>
            )}

            {detailModel.notes && (
              <Card title="备注" size="small">
                <Paragraph>{detailModel.notes}</Paragraph>
              </Card>
            )}
          </>
        )}
      </Drawer>

      {/* ── A/B Compare Modal ── */}
      <Modal
        title="A/B 模型对比"
        open={compareOpen}
        onCancel={() => setCompareOpen(false)}
        width={1000}
        footer={
          <Space>
            {compareVerdict === 'new_better' && modelB && (
              <Button type="primary" icon={<RocketOutlined />}
                onClick={() => handleDeploy(modelB.id)}>
                一键上线新模型
              </Button>
            )}
            {compareVerdict === 'old_better' && modelB && (
              <Button icon={<CloseCircleOutlined />} danger
                onClick={() => setArchiveModelId(modelB.id)}>
                保留旧模型
              </Button>
            )}
            <Button onClick={() => setCompareOpen(false)}>关闭</Button>
          </Space>
        }
      >
        {compareLoading ? (
          <Empty description="加载对比数据中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <>
            {modelA && modelB ? (
              <>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title={`旧模型: ${modelA.name} v${modelA.version}`} size="small"
                      style={{ background: '#fafafa' }}>
                      <Descriptions size="small" column={1}>
                        <Descriptions.Item label="类型">
                          <Tag color={modelTypeConfig[modelA.model_type]?.color}>{modelTypeConfig[modelA.model_type]?.label}</Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="状态">
                          <Tag color={modelStageConfig[modelA.stage]?.color}>{modelStageConfig[modelA.stage]?.label}</Tag>
                        </Descriptions.Item>
                      </Descriptions>
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title={`新模型: ${modelB.name} v${modelB.version}`} size="small"
                      style={{ background: '#f0f5ff' }}>
                      <Descriptions size="small" column={1}>
                        <Descriptions.Item label="类型">
                          <Tag color={modelTypeConfig[modelB.model_type]?.color}>{modelTypeConfig[modelB.model_type]?.label}</Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="状态">
                          <Tag color={modelStageConfig[modelB.stage]?.color}>{modelStageConfig[modelB.stage]?.label}</Tag>
                        </Descriptions.Item>
                      </Descriptions>
                    </Card>
                  </Col>
                </Row>

                <Divider />

                {/* Radar chart */}
                {radarOption && (
                  <ReactECharts option={radarOption} style={{ height: 320, marginBottom: 16 }} />
                )}

                <Divider />

                {/* Comparison table */}
                <Table
                  dataSource={compareData}
                  rowKey="metric"
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '指标', dataIndex: 'metric', key: 'metric', width: 120 },
                    { title: '模型 A (旧)', key: 'valueA', width: 120,
                      render: (_: unknown, r: CompareResult) => fmtNum(r.old_value, 4) },
                    { title: '模型 B (新)', key: 'valueB', width: 120,
                      render: (_: unknown, r: CompareResult) => fmtNum(r.new_value, 4) },
                    {
                      title: '变化', key: 'change', width: 120,
                      render: (_: unknown, r: CompareResult) => {
                        const isUp = r.delta_pct > 0
                        const isGood = r.better
                        const color = isGood ? '#52c41a' : '#ff4d4f'
                        return (
                          <span style={{ color }}>
                            {isUp ? <RiseOutlined /> : <FallOutlined />}
                            {' '}{r.delta_pct > 0 ? '+' : ''}{r.delta_pct.toFixed(1)}%
                          </span>
                        )
                      },
                    },
                    {
                      title: '结论', key: 'winner', width: 80,
                      render: (_: unknown, r: CompareResult) => (
                        r.better
                          ? <Tag color="green">新模型优</Tag>
                          : <Tag color="red">旧模型优</Tag>
                      ),
                    },
                  ]}
                />

                {compareRecommendation && (
                  <Alert
                    type={compareVerdict === 'new_better' ? 'success' : 'warning'}
                    message={compareRecommendation}
                    style={{ marginTop: 16 }}
                    showIcon
                  />
                )}
              </>
            ) : (
              <Empty description="当前无线上模型可作为对比基线" />
            )}
          </>
        )}
      </Modal>

      {/* ── Rollback Modal ── */}
      <Modal
        title="模型回滚"
        open={!!rollbackOpen}
        onCancel={() => { setRollbackOpen(null); setRollbackReason(''); setTargetVersion(1); }}
        onOk={() => rollbackOpen && handleRollback(rollbackOpen)}
        okText="确认回滚"
        okButtonProps={{ danger: true }}
      >
        <Paragraph>确认回滚此模型到上一版本？回滚后当前线上模型将被归档，指定版本自动上线。</Paragraph>
        <Row gutter={12} style={{ marginBottom: 12 }}>
          <Col span={8}>
            <Text type="secondary">目标版本</Text>
          </Col>
          <Col span={16}>
            <InputNumber
              min={1}
              value={targetVersion}
              onChange={(v) => setTargetVersion(v || 1)}
              style={{ width: '100%' }}
            />
          </Col>
        </Row>
        <TextArea
          rows={3}
          value={rollbackReason}
          onChange={(e) => setRollbackReason(e.target.value)}
          placeholder="请填写回滚原因 (必填)"
        />
      </Modal>

      {/* ── Archive Reason Modal ── */}
      <Modal
        title="保留旧模型"
        open={!!archiveModelId}
        onCancel={() => { setArchiveModelId(null); setArchiveReason(''); }}
        onOk={handleArchive}
        okText="确认归档"
      >
        <Paragraph>确认保留旧模型并归档新模型？请填写失败原因。</Paragraph>
        <TextArea
          rows={3}
          value={archiveReason}
          onChange={(e) => setArchiveReason(e.target.value)}
          placeholder="请填写新模型不如旧模型的原因 (必填)"
        />
      </Modal>
    </div>
  )
}
