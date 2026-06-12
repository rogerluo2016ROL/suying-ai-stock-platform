import { useState, useEffect, useCallback } from 'react'
import {
  Card, Button, Table, Tag, Typography, Space, message, Row, Col, Statistic,
  Select, InputNumber, Form, Tabs, Divider, Empty, Popconfirm, Slider,
} from 'antd'
import {
  ExperimentOutlined, PlayCircleOutlined, ReloadOutlined,
  RiseOutlined, FallOutlined, SwapOutlined, ThunderboltOutlined,
  CalendarOutlined, StockOutlined, FundOutlined, TrophyOutlined,
  AimOutlined, DashboardOutlined, BarChartOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import { backtestApi } from '../api/client'

const { Title, Text } = Typography
const { Option } = Select

// ── Types ──

interface FactorItem {
  id: string
  name: string
}

interface BacktestDetail {
  window: number
  start_date: string
  end_date: string
  forward_end: string
  picks: number
  avg_return_pct: number
  hit_rate_pct: number
  benchmark_pct: number
  excess_return: number
  ic: number
}

interface BacktestSummary {
  avg_ic: number
  icir: number
  avg_hit_rate: number
  avg_excess_return: number
  total_windows: number
}

interface BacktestResult {
  status: string
  mode: string
  windows: number
  top_n: number
  forward_days: number
  summary: BacktestSummary
  details: BacktestDetail[]
  data_source?: string
  message?: string
}

interface CompareItem {
  strategy: string
  avg_return: number
  samples: number
  period: string
}

interface CompareResult {
  status: string
  start_date: string
  end_date: string
  strategies: CompareItem[]
}

interface CalibrateFactor {
  factor_id: string
  factor_name: string
  ic_proxy: number
  suggested_weight: number
}

interface CalibrateResult {
  status: string
  mode: string
  factors: CalibrateFactor[]
  message: string
}

// ── Constants ──

type BacktestMode = 'all' | 'long' | 'short'

const MODE_LABELS: Record<BacktestMode, string> = {
  all: '全市场选股',
  long: '多头策略',
  short: '空头策略',
}

const BENCHMARK_OPTIONS = [
  { value: 'sh000001', label: '上证指数' },
  { value: 'sz399001', label: '深证成指' },
  { value: 'sz399006', label: '创业板指' },
  { value: 'sh000688', label: '科创50' },
  { value: 'sh000300', label: '沪深300' },
]

const STRATEGY_OPTIONS = Object.entries({
  momentum: '五因子-动量',
  volume: '五因子-量能',
  quality: '五因子-质量',
  composite: '综合评分',
  technical: '五因子-技术',
  margin: '融资融券',
  moneyflow: '资金流向',
  daily_basic: '每日指标',
  financial: '财报质量',
  hard_tech: '硬科技',
  growth: '成长性',
  short_term: '短线技术',
  long_term: '长线价值',
  por: 'POR估值',
}).map(([value, label]) => ({ value, label }))

// ── Chart Options ──

function buildReturnChartOption(details: BacktestDetail[]): object {
  if (!details.length) return {}
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['策略收益', '市场基准', '超额收益'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: details.map(d => `窗口${d.window}\n${d.start_date?.slice(5)}-${d.end_date?.slice(5)}`),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', name: '收益率 (%)' },
    series: [
      {
        name: '策略收益',
        type: 'bar',
        data: details.map(d => +d.avg_return_pct.toFixed(2)),
        itemStyle: { color: '#1677ff', borderRadius: [4, 4, 0, 0] },
        barGap: '20%',
      },
      {
        name: '市场基准',
        type: 'bar',
        data: details.map(d => +d.benchmark_pct.toFixed(2)),
        itemStyle: { color: '#d9d9d9', borderRadius: [4, 4, 0, 0] },
      },
      {
        name: '超额收益',
        type: 'bar',
        data: details.map(d => +d.excess_return.toFixed(2)),
        itemStyle: { color: '#52c41a', borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
}

function buildIcChartOption(details: BacktestDetail[]): object {
  if (!details.length) return {}
  const icData = details.map(d => +d.ic.toFixed(4))
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '8%', containLabel: true },
    xAxis: {
      type: 'category',
      data: details.map(d => `窗口${d.window}`),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', name: 'IC' },
    series: [
      {
        name: 'IC',
        type: 'bar',
        data: icData,
        itemStyle: {
          color: (params: { dataIndex: number }) =>
            icData[params.dataIndex] >= 0 ? '#52c41a' : '#ff4d4f',
          borderRadius: [4, 4, 0, 0],
        },
      },
      {
        name: 'IC',
        type: 'line',
        data: icData,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#1677ff', width: 2 },
        itemStyle: { color: '#1677ff' },
      },
    ],
  }
}

function buildHitRateGaugeOption(hitRate: number): object {
  return {
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        center: ['50%', '60%'],
        radius: '90%',
        min: 0,
        max: 100,
        splitNumber: 10,
        axisLine: {
          show: true,
          lineStyle: {
            width: 20,
            color: [
              [0.3, '#ff4d4f'],
              [0.5, '#faad14'],
              [0.7, '#1677ff'],
              [1, '#52c41a'],
            ],
          },
        },
        pointer: { length: '60%', width: 6 },
        detail: {
          valueAnimation: true,
          formatter: '{value}%',
          fontSize: 20,
          offsetCenter: [0, '70%'],
        },
        data: [{ value: +hitRate.toFixed(1) }],
      },
    ],
  }
}

function buildCompareChartOption(strategies: CompareItem[]): object {
  if (!strategies.length) return {}
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['平均收益'], bottom: 0 },
    grid: { left: '5%', right: '4%', bottom: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: strategies.map(s => STRATEGY_OPTIONS.find(o => o.value === s.strategy)?.label || s.strategy),
      axisLabel: { fontSize: 11, rotate: 20 },
    },
    yAxis: { type: 'value', name: '收益率 (%)' },
    series: [
      {
        name: '平均收益',
        type: 'bar',
        data: strategies.map(s => +s.avg_return.toFixed(2)),
        itemStyle: {
          color: (params: { dataIndex: number }) =>
            strategies[params.dataIndex].avg_return >= 0 ? '#52c41a' : '#ff4d4f',
          borderRadius: [4, 4, 0, 0],
        },
        label: { show: true, position: 'top', fontSize: 11 },
      },
    ],
  }
}

// ── Component ──

export default function Backtest() {
  // ── State ──
  const [activeTab, setActiveTab] = useState('run')

  // Run backtest
  const [runLoading, setRunLoading] = useState(false)
  const [form] = Form.useForm()
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [runError, setRunError] = useState('')

  // Factors
  const [factors, setFactors] = useState<FactorItem[]>([])
  const [factorsLoading, setFactorsLoading] = useState(false)

  // Compare
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareForm] = Form.useForm()
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null)
  const [compareError, setCompareError] = useState('')

  // Calibrate
  const [calibrateLoading, setCalibrateLoading] = useState(false)
  const [calibrateResult, setCalibrateResult] = useState<CalibrateResult | null>(null)

  // ── Load Factors ──

  const loadFactors = useCallback(async () => {
    setFactorsLoading(true)
    try {
      const r = await backtestApi.getFactors()
      setFactors(r.data.factors || [])
    } catch {
      // silent
    } finally {
      setFactorsLoading(false)
    }
  }, [])

  useEffect(() => { loadFactors() }, [loadFactors])

  // ── Run Backtest ──

  const handleRun = useCallback(async () => {
    try {
      const values = await form.validateFields()
      setRunLoading(true)
      setRunError('')
      setResult(null)

      const r = await backtestApi.run({
        mode: values.mode || 'all',
        windows: values.windows ?? 3,
        top_n: values.top_n ?? 30,
        forward_days: values.forward_days ?? 60,
      })

      const data: BacktestResult = r.data
      if (data.status === 'error') {
        setRunError(data.message || '回测数据不足')
        message.warning(data.message || '回测数据不足')
      } else {
        setResult(data)
        message.success(`回测完成: ${data.summary.total_windows} 个窗口`)
        setActiveTab('run')
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '回测请求失败'
      setRunError(msg)
      message.error(msg)
    } finally {
      setRunLoading(false)
    }
  }, [form])

  // ── Compare Strategies ──

  const handleCompare = useCallback(async () => {
    try {
      const values = await compareForm.validateFields()
      setCompareLoading(true)
      setCompareError('')
      setCompareResult(null)

      const r = await backtestApi.compare({
        strategy_ids: values.strategy_ids || ['momentum', 'quality'],
        start_date: values.date_range?.[0]?.format('YYYY-MM-DD'),
        end_date: values.date_range?.[1]?.format('YYYY-MM-DD'),
      })

      const data: CompareResult = r.data
      if (data.status === 'ok') {
        setCompareResult(data)
        message.success(`对比 ${data.strategies.length} 个策略完成`)
      } else {
        setCompareError('对比失败')
        message.warning('对比失败')
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '对比请求失败'
      setCompareError(msg)
      message.error(msg)
    } finally {
      setCompareLoading(false)
    }
  }, [compareForm])

  // ── Calibrate ──

  const handleCalibrate = useCallback(async () => {
    setCalibrateLoading(true)
    try {
      const r = await backtestApi.calibrate('all')
      const data: CalibrateResult = r.data
      if (data.status === 'ok') {
        setCalibrateResult(data)
        message.success(`校准完成: ${data.factors.length} 个因子`)
      } else {
        message.warning('校准失败')
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '校准请求失败')
    } finally {
      setCalibrateLoading(false)
    }
  }, [])

  // ── Detail Table Columns ──

  const detailColumns: ColumnsType<BacktestDetail> = [
    { title: '窗口', dataIndex: 'window', width: 60, render: (v: number) => <Tag color="blue">{v}</Tag> },
    { title: '起始日期', dataIndex: 'start_date', width: 110, render: (v: string) => <Text code>{v}</Text> },
    { title: '结束日期', dataIndex: 'end_date', width: 110, render: (v: string) => <Text code>{v}</Text> },
    { title: '预测截止', dataIndex: 'forward_end', width: 110, render: (v: string) => <Text code>{v}</Text> },
    { title: '入选数', dataIndex: 'picks', width: 70, render: (v: number) => <Tag>{v}</Tag> },
    {
      title: '平均收益', dataIndex: 'avg_return_pct', width: 100,
      render: (v: number) => (
        <Text type={v >= 0 ? 'success' : 'danger'} strong>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}%
        </Text>
      ),
    },
    {
      title: '命中率', dataIndex: 'hit_rate_pct', width: 90,
      render: (v: number) => (
        <Text type={v >= 50 ? 'success' : 'warning'}>{v.toFixed(1)}%</Text>
      ),
    },
    { title: '市场基准', dataIndex: 'benchmark_pct', width: 100, render: (v: number) => `${v.toFixed(2)}%` },
    {
      title: '超额收益', dataIndex: 'excess_return', width: 100,
      render: (v: number) => (
        <Text type={v >= 0 ? 'success' : 'danger'} strong>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}%
        </Text>
      ),
    },
    {
      title: 'IC', dataIndex: 'ic', width: 90,
      render: (v: number) => {
        const color = v > 0.03 ? 'green' : v > 0 ? 'blue' : 'red'
        return <Tag color={color}>{v.toFixed(4)}</Tag>
      },
    },
  ]

  const factorColumns: ColumnsType<FactorItem> = [
    {
      title: '因子 ID', dataIndex: 'id', width: 150,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
    },
    { title: '因子名称', dataIndex: 'name', width: 200 },
    {
      title: '操作', width: 100,
      render: (_: unknown, record: FactorItem) => (
        <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
      ),
    },
  ]

  const calibrateColumns: ColumnsType<CalibrateFactor> = [
    {
      title: '因子 ID', dataIndex: 'factor_id', width: 140,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
    },
    { title: '因子名称', dataIndex: 'factor_name', width: 160 },
    {
      title: 'IC 代理值', dataIndex: 'ic_proxy', width: 100,
      render: (v: number) => <Tag color={v >= 0 ? 'green' : 'red'}>{v.toFixed(4)}</Tag>,
    },
    {
      title: '建议权重', dataIndex: 'suggested_weight', width: 100,
      render: (v: number) => <Text strong style={{ color: '#1677ff' }}>{v.toFixed(1)}</Text>,
    },
  ]

  const compareColumns: ColumnsType<CompareItem> = [
    {
      title: '策略', dataIndex: 'strategy', width: 150,
      render: (v: string) => {
        const label = STRATEGY_OPTIONS.find(o => o.value === v)?.label || v
        return <Tag color="blue">{label}</Tag>
      },
    },
    {
      title: '平均收益', dataIndex: 'avg_return', width: 120,
      render: (v: number) => (
        <Text type={v >= 0 ? 'success' : 'danger'} strong>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}%
        </Text>
      ),
    },
    { title: '样本数', dataIndex: 'samples', width: 100 },
    { title: '回测区间', dataIndex: 'period', ellipsis: true },
  ]

  // ── Render ──

  const summary = result?.summary

  return (
    <div>
      {/* ── Page Header ── */}
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <ExperimentOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          回测分析
        </Title>
        <Text type="secondary">
          滚动窗口前向回测 · IC/ICIR 验证 · 策略绩效评估 · 因子权重校准
        </Text>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab} type="card" style={{ marginTop: 8 }}>
        {/* ── Tab 1: Run Backtest ── */}
        <Tabs.TabPane tab={<span><PlayCircleOutlined /> 回测运行</span>} key="run">
          {/* ── Parameter Config (AC-306.1) ── */}
          <Card
            title={<Space><CalendarOutlined style={{ color: '#1677ff' }} />回测参数配置</Space>}
            style={{ borderRadius: 8, marginBottom: 16 }}
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => { setResult(null); setRunError(''); form.resetFields() }}>
                  重置
                </Button>
                <Button type="primary" icon={<PlayCircleOutlined />} loading={runLoading} onClick={handleRun}>
                  运行回测
                </Button>
              </Space>
            }
          >
            <Form
              form={form}
              layout="inline"
              initialValues={{ mode: 'all', windows: 5, top_n: 30, forward_days: 60, benchmark: 'sh000300' }}
              style={{ flexWrap: 'wrap', gap: 12 }}
            >
              <Form.Item name="mode" label="策略模式" rules={[{ required: true }]}>
                <Select style={{ width: 150 }}>
                  <Option value="all">全市场选股</Option>
                  <Option value="long">多头策略</Option>
                  <Option value="short">空头策略</Option>
                </Select>
              </Form.Item>

              <Form.Item name="windows" label="回测窗口">
                <InputNumber min={1} max={12} style={{ width: 120 }} />
              </Form.Item>

              <Form.Item name="top_n" label="每窗口选股数">
                <InputNumber min={10} max={100} step={10} style={{ width: 120 }} />
              </Form.Item>

              <Form.Item name="forward_days" label="前瞻天数">
                <InputNumber min={20} max={252} step={10} style={{ width: 120 }} />
              </Form.Item>

              <Form.Item name="benchmark" label="基准指数">
                <Select style={{ width: 140 }}>
                  {BENCHMARK_OPTIONS.map(b => (
                    <Option key={b.value} value={b.value}>{b.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Form>

            <Divider style={{ margin: '12px 0 4px' }} />
            <Row gutter={16}>
              <Col span={4}>
                <Form.Item name="windows" label="窗口数（滑块）" style={{ margin: 0 }}>
                  <Slider min={1} max={12} marks={{ 1: '1', 3: '3', 6: '6', 9: '9', 12: '12' }} />
                </Form.Item>
              </Col>
              <Col span={4}>
                <Form.Item name="top_n" label="选股数（滑块）" style={{ margin: 0 }}>
                  <Slider min={10} max={100} step={10} marks={{ 10: '10', 30: '30', 50: '50', 100: '100' }} />
                </Form.Item>
              </Col>
              <Col span={4}>
                <Form.Item name="forward_days" label="前瞻天数（滑块）" style={{ margin: 0 }}>
                  <Slider min={20} max={252} step={20} marks={{ 20: '20', 60: '60', 120: '120', 252: '252' }} />
                </Form.Item>
              </Col>
            </Row>
          </Card>

          {/* ── Error ── */}
          {runError && (
            <Card style={{ marginBottom: 16, borderRadius: 8, borderColor: '#ff4d4f' }}>
              <Text type="danger">{runError}</Text>
            </Card>
          )}

          {/* ── Summary Cards (AC-306.2) ── */}
          {summary && (
            <Row gutter={12} style={{ marginBottom: 16 }}>
              <Col span={4}>
                <Card size="small" style={{ borderRadius: 8, textAlign: 'center' }}>
                  <Statistic
                    title="平均 IC"
                    value={summary.avg_ic}
                    precision={4}
                    valueStyle={{ color: summary.avg_ic > 0.02 ? '#52c41a' : '#1677ff', fontSize: 24 }}
                    prefix={<AimOutlined />}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small" style={{ borderRadius: 8, textAlign: 'center' }}>
                  <Statistic
                    title="ICIR"
                    value={summary.icir}
                    precision={2}
                    valueStyle={{ color: summary.icir > 0.5 ? '#52c41a' : '#faad14', fontSize: 24 }}
                    prefix={<ThunderboltOutlined />}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small" style={{ borderRadius: 8, textAlign: 'center' }}>
                  <Statistic
                    title="命中率"
                    value={summary.avg_hit_rate}
                    precision={1}
                    suffix="%"
                    valueStyle={{ color: summary.avg_hit_rate >= 50 ? '#52c41a' : '#ff4d4f', fontSize: 24 }}
                    prefix={<TrophyOutlined />}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small" style={{ borderRadius: 8, textAlign: 'center' }}>
                  <Statistic
                    title={summary.avg_excess_return >= 0 ? '超额收益' : '超额亏损'}
                    value={summary.avg_excess_return}
                    precision={2}
                    suffix="%"
                    valueStyle={{ color: summary.avg_excess_return >= 0 ? '#52c41a' : '#ff4d4f', fontSize: 24 }}
                    prefix={summary.avg_excess_return >= 0 ? <RiseOutlined /> : <FallOutlined />}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small" style={{ borderRadius: 8, textAlign: 'center' }}>
                  <Statistic
                    title="回测窗口"
                    value={summary.total_windows}
                    valueStyle={{ fontSize: 24 }}
                    prefix={<DashboardOutlined />}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small" style={{ borderRadius: 8, textAlign: 'center' }}>
                  <Statistic
                    title="数据源"
                    value={result?.data_source === 'pg' ? 'PostgreSQL' : result?.data_source || '—'}
                    valueStyle={{ fontSize: 16, color: '#8c8c8c' }}
                    prefix={<StockOutlined />}
                  />
                </Card>
              </Col>
            </Row>
          )}

          {/* ── Charts (AC-306.2) ── */}
          {result?.details && result.details.length > 0 && (
            <Row gutter={12} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Card
                  title={<Space><BarChartOutlined style={{ color: '#1677ff' }} />收益曲线</Space>}
                  style={{ borderRadius: 8 }}
                  size="small"
                >
                  <ReactECharts option={buildReturnChartOption(result.details)} style={{ height: 320 }} />
                </Card>
              </Col>
              <Col span={12}>
                <Card
                  title={<Space><FundOutlined style={{ color: '#1677ff' }} />IC 滚动验证</Space>}
                  style={{ borderRadius: 8 }}
                  size="small"
                >
                  <ReactECharts option={buildIcChartOption(result.details)} style={{ height: 320 }} />
                </Card>
              </Col>
            </Row>
          )}

          {/* ── Hit Rate Gauge ── */}
          {summary && (
            <Card
              title={<Space><AimOutlined style={{ color: '#1677ff' }} />命中率仪表盘</Space>}
              style={{ borderRadius: 8, marginBottom: 16 }}
              size="small"
            >
              <ReactECharts option={buildHitRateGaugeOption(summary.avg_hit_rate)} style={{ height: 220 }} />
            </Card>
          )}

          {/* ── Details Table ── */}
          {result?.details && result.details.length > 0 && (
            <Card
              title={<Space><ExperimentOutlined style={{ color: '#1677ff' }} />回测明细 ({result.details.length} 窗口)</Space>}
              style={{ borderRadius: 8 }}
              size="small"
            >
              <Table
                dataSource={result.details}
                columns={detailColumns}
                rowKey="window"
                size="small"
                pagination={{ pageSize: 10, showSizeChanger: true, showTotal: t => `共 ${t} 个窗口` }}
                locale={{ emptyText: '暂无回测数据' }}
                scroll={{ x: 1000 }}
              />
            </Card>
          )}

          {/* ── Empty State ── */}
          {!result && !runLoading && !runError && (
            <Card style={{ borderRadius: 8 }}>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <div>
                    <Text type="secondary">点击"运行回测"开始滚动窗口前向回测</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      系统将使用 PostgreSQL 真实日线数据，按滑动窗口计算 IC/ICIR、命中率和超额收益
                    </Text>
                  </div>
                }
              />
            </Card>
          )}
        </Tabs.TabPane>

        {/* ── Tab 2: Factor List ── */}
        <Tabs.TabPane tab={<span><ThunderboltOutlined /> 因子列表 ({factors.length})</span>} key="factors">
          <Card
            title={<Space><ThunderboltOutlined style={{ color: '#1677ff' }} />回测因子 ({factors.length})</Space>}
            style={{ borderRadius: 8, marginBottom: 16 }}
            extra={
              <Button icon={<ReloadOutlined />} loading={factorsLoading} onClick={loadFactors}>
                刷新
              </Button>
            }
          >
            <Table
              dataSource={factors}
              columns={factorColumns}
              rowKey="id"
              size="small"
              loading={factorsLoading}
              pagination={{ pageSize: 10, showTotal: t => `共 ${t} 个因子` }}
              locale={{ emptyText: '暂无因子数据' }}
            />
          </Card>

          {/* ── Calibrate ── */}
          <Card
            title={<Space><FundOutlined style={{ color: '#1677ff' }} />因子权重校准</Space>}
            style={{ borderRadius: 8 }}
            extra={
              <Popconfirm
                title="确认校准"
                description="将基于近期 IC 代理值重新计算所有因子建议权重"
                onConfirm={handleCalibrate}
                okText="确认"
                cancelText="取消"
              >
                <Button type="primary" icon={<SwapOutlined />} loading={calibrateLoading}>
                  执行校准
                </Button>
              </Popconfirm>
            }
          >
            {calibrateResult ? (
              <div>
                <Text type="success" style={{ display: 'block', marginBottom: 12 }}>
                  {calibrateResult.message}
                </Text>
                <Table
                  dataSource={calibrateResult.factors}
                  columns={calibrateColumns}
                  rowKey="factor_id"
                  size="small"
                  pagination={{ pageSize: 10 }}
                />
              </div>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="点击「执行校准」基于近期 IC 代理值计算因子建议权重"
              />
            )}
          </Card>
        </Tabs.TabPane>

        {/* ── Tab 3: Strategy Compare ── */}
        <Tabs.TabPane tab={<span><SwapOutlined /> 策略对比</span>} key="compare">
          <Card
            title={<Space><SwapOutlined style={{ color: '#1677ff' }} />多策略对比</Space>}
            style={{ borderRadius: 8, marginBottom: 16 }}
            extra={
              <Button type="primary" icon={<SwapOutlined />} loading={compareLoading} onClick={handleCompare}>
                开始对比
              </Button>
            }
          >
            <Form
              form={compareForm}
              layout="inline"
              initialValues={{ strategy_ids: ['momentum', 'quality', 'composite'] }}
              style={{ flexWrap: 'wrap', gap: 12, marginBottom: 16 }}
            >
              <Form.Item name="strategy_ids" label="对比策略" rules={[{ required: true, type: 'array', min: 1 }]}>
                <Select mode="multiple" style={{ minWidth: 400 }} maxTagCount={4} placeholder="选择 2-5 个策略">
                  {STRATEGY_OPTIONS.map(s => (
                    <Option key={s.value} value={s.value}>{s.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Form>

            <Divider style={{ margin: '8px 0 16px' }} />

            {compareError && (
              <Text type="danger" style={{ display: 'block', marginBottom: 12 }}>{compareError}</Text>
            )}

            {compareResult ? (
              <div>
                <Row gutter={12} style={{ marginBottom: 16 }}>
                  <Col span={24}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <ReactECharts option={buildCompareChartOption(compareResult.strategies)} style={{ height: 300 }} />
                    </Card>
                  </Col>
                </Row>
                <Table
                  dataSource={compareResult.strategies}
                  columns={compareColumns}
                  rowKey="strategy"
                  size="small"
                  pagination={false}
                  locale={{ emptyText: '暂无对比数据' }}
                />
              </div>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <div>
                    <Text type="secondary">选择 2-5 个策略进行横向对比</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      系统将在相同时间区间内比较各策略的平均收益表现
                    </Text>
                  </div>
                }
              />
            )}
          </Card>
        </Tabs.TabPane>
      </Tabs>
    </div>
  )
}
